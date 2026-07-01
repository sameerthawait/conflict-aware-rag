import time
import logging
import math
from typing import List, Dict, Any, Optional
from openai import OpenAI
from src.ingestion.vector_store import SearchResult
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.retrieval.reranker")


class RerankerError(Exception):
    """Raised when document reranking fails."""
    pass


class Reranker:
    """Reranks search results using a local Cross-Encoder or an LLM-based relevance scorer."""

    def __init__(self, config: Dict[str, Any], prompt_manager: PromptManager, client: Optional[OpenAI] = None) -> None:
        """Initializes the Reranker.

        Args:
            config: System configuration dictionary.
            prompt_manager: PromptManager instance.
            client: Optional OpenAI client for LLM-based fallback.
        """
        self.config = config
        self.prompt_manager = prompt_manager
        self.client = client

        ret_conf = config.get("retrieval", {})
        self.reranker_type: str = ret_conf.get("reranker", "cross-encoder")
        self.reranker_model_name: str = ret_conf.get("reranker_model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self.min_score: float = ret_conf.get("reranker_min_score", 0.5)

        llm_conf = config.get("llm", {})
        self.llm_model: str = llm_conf.get("model_name", "meta/llama-3.1-70b-instruct")
        self.temperature: float = llm_conf.get("temperature", 0.0)

        # Lazy-loaded CrossEncoder instance
        self._cross_encoder: Any = None
        self._cross_encoder_loaded = False

    def _load_cross_encoder(self) -> None:
        """Attempts to lazy-load the local Cross-Encoder model.

        Raises:
            RerankerError: If sentence-transformers library cannot be loaded or model fails to load.
        """
        if self._cross_encoder_loaded:
            return

        logger.info(f"Loading local Cross-Encoder model: '{self.reranker_model_name}'...")
        start_time = time.perf_counter()
        try:
            from sentence_transformers import CrossEncoder
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Reranker device: {device}")
            self._cross_encoder = CrossEncoder(
                self.reranker_model_name,
                device=device
            )
            self._cross_encoder_loaded = True
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info(f"Cross-Encoder model loaded successfully in {latency_ms:.2f}ms.")
        except Exception as e:
            error_msg = f"Failed to initialize CrossEncoder: {str(e)}"
            logger.error(error_msg)
            raise RerankerError(error_msg) from e

    def _rerank_with_cross_encoder(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """Reranks results using the local Cross-Encoder model.

        Args:
            query: The user search query.
            results: List of SearchResult objects to rerank.

        Returns:
            List of rescored SearchResult objects.
        """
        if not results:
            return []

        # Prepare pairs for cross encoder: (query, document)
        pairs = [[query, res.text] for res in results]
        
        # Predict scores
        logger.info(f"Running Cross-Encoder prediction for {len(results)} candidate pairs...")
        start_time = time.perf_counter()
        scores = self._cross_encoder.predict(pairs)
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"Cross-Encoder inference completed in {latency_ms:.2f}ms.")

        reranked_results: List[SearchResult] = []
        for i, res in enumerate(results):
            raw_score = float(scores[i])
            # Apply sigmoid to map logit scores (e.g. from -10 to +10) into a [0, 1] range
            normalized_score = 1.0 / (1.0 + math.exp(-raw_score))
            
            # Log score shift
            logger.debug(f"Chunk ID: {res.chunk_id} | Raw Logit: {raw_score:.4f} | Normalized Sigmoid: {normalized_score:.4f}")
            
            reranked_results.append(
                SearchResult(
                    chunk_id=res.chunk_id,
                    text=res.text,
                    score=normalized_score,
                    metadata=res.metadata
                )
            )

        return reranked_results

    def _rerank_with_llm(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """Reranks results using LLM relevance scoring prompts.

        Args:
            query: The user search query.
            results: List of SearchResult objects to rerank.

        Returns:
            List of rescored SearchResult objects.
        """
        if not results:
            return []

        if not self.client:
            logger.warning("No LLM client configured for LLM Reranking. Returning results with original scores.")
            return results

        logger.info(f"Reranking {len(results)} chunks using LLM scoring API...")
        start_time = time.perf_counter()

        reranked_results: List[SearchResult] = []
        for res in results:
            try:
                # Format prompt using PromptManager
                prompt = self.prompt_manager.get_prompt(
                    "reranker_relevance_scoring",
                    query=query,
                    chunk_text=res.text
                )
                
                # Request LLM score
                response = self.client.chat.completions.create(
                    model=self.llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=16
                )
                response_text = response.choices[0].message.content.strip()
                
                # Parse float score from output
                # Expecting exactly a float between 0.0 and 10.0
                score_match = re.search(r"(\d+(\.\d+)?)", response_text)
                if score_match:
                    raw_score = float(score_match.group(1))
                else:
                    logger.warning(f"Could not parse float score from response: '{response_text}'. Defaulting to 0.0.")
                    raw_score = 0.0

                # Normalize 0.0 - 10.0 scale to 0.0 - 1.0 range
                normalized_score = min(max(raw_score / 10.0, 0.0), 1.0)
                logger.debug(f"LLM Rerank | Chunk ID: {res.chunk_id} | Raw LLM Score: {raw_score:.2f} | Normalized: {normalized_score:.2f}")

                reranked_results.append(
                    SearchResult(
                        chunk_id=res.chunk_id,
                        text=res.text,
                        score=normalized_score,
                        metadata=res.metadata
                    )
                )
            except Exception as e:
                logger.warning(f"LLM scoring failed for chunk {res.chunk_id}: {str(e)}. Using default score 0.0.")
                reranked_results.append(
                    SearchResult(
                        chunk_id=res.chunk_id,
                        text=res.text,
                        score=0.0,
                        metadata=res.metadata
                    )
                )

        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"LLM Reranking completed in {latency_ms:.2f}ms.")
        return reranked_results

    def rerank(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """Reranks search results based on the configured mode and filters by min score.

        Args:
            query: The user search query.
            results: List of SearchResult objects to rerank.

        Returns:
            List of reranked SearchResult objects sorted descending by score, filtered by min_score.
        """
        if not results:
            return []

        if self.reranker_type == "none":
            logger.info("Reranker is disabled (reranker: 'none'). Skipping.")
            return results

        start_time = time.perf_counter()
        active_type = self.reranker_type

        # Try to run Cross-Encoder reranking
        if active_type == "cross-encoder":
            try:
                self._load_cross_encoder()
                reranked = self._rerank_with_cross_encoder(query, results)
            except Exception as e:
                logger.warning(f"Local Cross-Encoder reranking failed: {str(e)}. Falling back to LLM reranking...")
                active_type = "llm"

        # Run LLM reranking if configured or if Cross-Encoder failed
        if active_type == "llm":
            try:
                reranked = self._rerank_with_llm(query, results)
            except Exception as e:
                logger.error(f"LLM reranking failed: {str(e)}. Returning original results.")
                reranked = results

        # Filter by min_score threshold
        filtered_results = [res for res in reranked if res.score >= self.min_score]
        
        # Sort descending by score
        filtered_results.sort(key=lambda x: x.score, reverse=True)

        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Reranking ({active_type}) completed in {latency_ms:.2f}ms. "
            f"Filtered candidates from {len(results)} to {len(filtered_results)} based on min_score threshold ({self.min_score})."
        )
        return filtered_results
import re
