import time
import logging
from typing import List, Dict, Any
from src.ingestion.vector_store import SearchResult

# Initialize structured logging
logger = logging.getLogger("rag_system.retrieval.fusion")


class FusionError(Exception):
    """Raised when reciprocal rank fusion fails."""
    pass


class ReciprocalRankFusion:
    """Combines multiple ranked search results using the Reciprocal Rank Fusion (RRF) algorithm."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initializes ReciprocalRankFusion with system configuration.

        Args:
            config: System configuration dictionary.
        """
        self.config = config
        ret_conf = config.get("retrieval", {})
        self.rrf_k: int = ret_conf.get("rrf_k", 60)

    def fuse(self, runs: List[List[SearchResult]]) -> List[SearchResult]:
        """Merges multiple lists of search results using Reciprocal Rank Fusion.

        Args:
            runs: A list of search results lists (each list is from a different retriever).

        Returns:
            A deduplicated list of SearchResult objects sorted by RRF score descending.

        Raises:
            FusionError: If fusion processing fails.
        """
        start_time = time.perf_counter()
        logger.info(f"Starting Reciprocal Rank Fusion on {len(runs)} search runs...")

        try:
            # Map chunk_id to its accumulated RRF score
            rrf_scores: Dict[str, float] = {}
            # Map chunk_id to the SearchResult details (text, metadata)
            chunk_details: Dict[str, SearchResult] = {}

            for run_idx, run in enumerate(runs):
                for rank_idx, result in enumerate(run):
                    chunk_id = result.chunk_id
                    # 1-based rank
                    rank = rank_idx + 1
                    
                    # Compute RRF score contribution: 1 / (k + rank)
                    contribution = 1.0 / (self.rrf_k + rank)
                    rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + contribution

                    # Store details if not already present
                    if chunk_id not in chunk_details:
                        chunk_details[chunk_id] = result

            # Create final fused results with RRF scores
            fused_results: List[SearchResult] = []
            for chunk_id, rrf_score in rrf_scores.items():
                original_result = chunk_details[chunk_id]
                fused_results.append(
                    SearchResult(
                        chunk_id=chunk_id,
                        text=original_result.text,
                        score=rrf_score,
                        metadata=original_result.metadata
                    )
                )

            # Sort fused results descending by RRF score
            fused_results.sort(key=lambda x: x.score, reverse=True)

            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info(f"RRF fusion completed in {latency_ms:.2f}ms. Total unique chunks fused: {len(fused_results)}.")
            return fused_results

        except Exception as e:
            error_msg = f"Failed to perform reciprocal rank fusion: {str(e)}"
            logger.error(error_msg)
            raise FusionError(error_msg) from e
