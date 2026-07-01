import time
import logging
import json
import hashlib
import asyncio
from typing import Dict, List, Any, Tuple, Optional, Set
import numpy as np
from openai import OpenAI

from src.ingestion.vector_store import SearchResult
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.multiperspective.contradiction_detector")


class ContradictionResult:
    """Structure encapsulating a single contradiction evaluation output."""

    def __init__(
        self,
        is_contradiction: bool,
        confidence: float,
        contradiction_type: Optional[str],
        claim_a: str,
        claim_b: str,
        explanation: str,
        chunk_a_id: str,
        chunk_b_id: str
    ) -> None:
        self.is_contradiction = is_contradiction
        self.confidence = confidence
        self.contradiction_type = contradiction_type
        self.claim_a = claim_a
        self.claim_b = claim_b
        self.explanation = explanation
        self.chunk_a_id = chunk_a_id
        self.chunk_b_id = chunk_b_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_contradiction": self.is_contradiction,
            "confidence": self.confidence,
            "contradiction_type": self.contradiction_type,
            "claim_a": self.claim_a,
            "claim_b": self.claim_b,
            "explanation": self.explanation,
            "chunk_a_id": self.chunk_a_id,
            "chunk_b_id": self.chunk_b_id
        }


class ContradictionMatrix:
    """Consolidated matrix containing all checked combinations and identified conflicts."""

    def __init__(
        self,
        contradictions: List[ContradictionResult],
        contradiction_pairs: Set[Tuple[str, str]],
        has_contradictions: bool,
        max_contradiction_confidence: float
    ) -> None:
        self.contradictions = contradictions
        self.contradiction_pairs = contradiction_pairs
        self.has_contradictions = has_contradictions
        self.max_contradiction_confidence = max_contradiction_confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contradictions": [c.to_dict() for c in self.contradictions],
            "has_contradictions": self.has_contradictions,
            "max_contradiction_confidence": self.max_contradiction_confidence
        }


class ContradictionDetector:
    """Pairs search chunks to evaluate and detect contradictions using semantic cosine rules and LLM audits."""

    def __init__(
        self,
        config: Dict[str, Any],
        prompt_manager: PromptManager,
        vector_store: Any,
        client: OpenAI
    ) -> None:
        self.config = config
        self.prompt_manager = prompt_manager
        self.vector_store = vector_store
        self.client = client
        
        # Thread-safe in-memory cache to skip repeat checks
        self._cache: Dict[Tuple[str, str, str], ContradictionResult] = {}
        
        # Threshold constants loaded from configuration
        mp_conf = config.get("multiperspective", {})
        self.confidence_threshold = mp_conf.get("contradiction_confidence_threshold", 0.7)
        self.similarity_min = mp_conf.get("embedding_similarity_min", 0.3)
        self.similarity_max = mp_conf.get("embedding_similarity_max", 0.95)

    def _get_query_hash(self, query: str) -> str:
        return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()

    def _cosine_similarity(self, u: np.ndarray, v: np.ndarray) -> float:
        norm_u = np.linalg.norm(u)
        norm_v = np.linalg.norm(v)
        if norm_u == 0 or norm_v == 0:
            return 0.0
        return float(np.dot(u, v) / (norm_u * norm_v))

    def detect_pairwise(
        self,
        chunk_a: SearchResult,
        chunk_b: SearchResult,
        query: str
    ) -> ContradictionResult:
        """Determines if chunk_a and chunk_b present conflicting claims regarding the query."""
        
        # Enforce canonical order to prevent checking both (a, b) and (b, a)
        c1, c2 = (chunk_a, chunk_b) if chunk_a.chunk_id < chunk_b.chunk_id else (chunk_b, chunk_a)
        
        q_hash = self._get_query_hash(query)
        cache_key = (c1.chunk_id, c2.chunk_id, q_hash)
        
        # Check cache
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. First Pass: Compute Embedding Similarity
        try:
            model = self.vector_store.embedding_model
            # Encode chunks
            emb_a = model.encode(c1.text)
            emb_b = model.encode(c2.text)
            similarity = self._cosine_similarity(emb_a, emb_b)
        except Exception as e:
            logger.warning(f"Failed to calculate cosine similarity: {str(e)}. Proceeding to LLM directly.")
            similarity = 0.5  # Fallback to allow LLM check

        # Pre-filter checks
        if similarity < self.similarity_min:
            res = ContradictionResult(
                is_contradiction=False,
                confidence=0.0,
                contradiction_type=None,
                claim_a="",
                claim_b="",
                explanation=f"Topic shift detected (cosine: {similarity:.2f} < threshold: {self.similarity_min})",
                chunk_a_id=c1.chunk_id,
                chunk_b_id=c2.chunk_id
            )
            self._cache[cache_key] = res
            return res

        if similarity > self.similarity_max:
            res = ContradictionResult(
                is_contradiction=False,
                confidence=0.0,
                contradiction_type=None,
                claim_a="",
                claim_b="",
                explanation=f"Semantic duplicates (cosine: {similarity:.2f} > threshold: {self.similarity_max})",
                chunk_a_id=c1.chunk_id,
                chunk_b_id=c2.chunk_id
            )
            self._cache[cache_key] = res
            return res

        # 2. Second Pass: Call LLM Contradiction Detector Prompt
        try:
            source_a = c1.metadata.get("title", "Passage A")
            source_b = c2.metadata.get("title", "Passage B")
            
            prompt_text = self.prompt_manager.get_prompt(
                "contradiction_detector",
                source_a=source_a,
                chunk_a=c1.text,
                source_b=source_b,
                chunk_b=c2.text
            )

            llm_model = self.config.get("llm", {}).get("model_name", "meta/llama-3.1-70b-instruct")
            temperature = self.config.get("llm", {}).get("temperature", 0.0)

            response = self.client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=temperature,
                response_format={"type": "json_object"}
            )
            
            output_text = response.choices[0].message.content.strip()
            data = json.loads(output_text)
            
            is_contradiction = bool(data.get("is_contradiction", False))
            confidence = float(data.get("confidence", 0.0))
            
            # Apply confidence thresholds filter
            if is_contradiction and confidence < self.confidence_threshold:
                logger.info(f"Filtered out contradiction with confidence {confidence} below threshold.")
                is_contradiction = False

            res = ContradictionResult(
                is_contradiction=is_contradiction,
                confidence=confidence,
                contradiction_type=data.get("contradiction_type") if is_contradiction else None,
                claim_a=data.get("claim_a", "") if is_contradiction else "",
                claim_b=data.get("claim_b", "") if is_contradiction else "",
                explanation=data.get("explanation", ""),
                chunk_a_id=c1.chunk_id,
                chunk_b_id=c2.chunk_id
            )
            
        except Exception as e:
            logger.error(f"Failed to check contradiction via LLM: {str(e)}")
            res = ContradictionResult(
                is_contradiction=False,
                confidence=0.0,
                contradiction_type=None,
                claim_a="",
                claim_b="",
                explanation=f"Contradiction check failed: {str(e)}",
                chunk_a_id=c1.chunk_id,
                chunk_b_id=c2.chunk_id
            )

        self._cache[cache_key] = res
        return res

    async def detect_all(self, chunks: List[SearchResult], query: str) -> ContradictionMatrix:
        """Evaluates contradictions across all pairwise combinations of chunks in parallel."""
        n = len(chunks)
        if n < 2:
            return ContradictionMatrix([], set(), False, 0.0)

        # Generate unique pairs
        pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                pairs.append((chunks[i], chunks[j]))

        logger.info(f"Analyzing {len(pairs)} pairs for contradiction...")
        
        # Run detection in parallel using thread pool executors (via asyncio.to_thread)
        tasks = [
            asyncio.to_thread(self.detect_pairwise, c1, c2, query)
            for c1, c2 in pairs
        ]
        
        results: List[ContradictionResult] = await asyncio.gather(*tasks)
        
        # Collate results
        contradictions = [r for r in results if r.is_contradiction]
        contradiction_pairs = {
            (r.chunk_a_id, r.chunk_b_id) for r in contradictions
        }
        
        max_conf = max([r.confidence for r in contradictions]) if contradictions else 0.0
        has_contradictions = len(contradictions) > 0
        
        logger.info(
            f"Contradiction detection finished. Checked {len(pairs)} pairs. "
            f"Found {len(contradictions)} contradictions."
        )
        
        return ContradictionMatrix(
            contradictions=contradictions,
            contradiction_pairs=contradiction_pairs,
            has_contradictions=has_contradictions,
            max_contradiction_confidence=max_conf
        )
