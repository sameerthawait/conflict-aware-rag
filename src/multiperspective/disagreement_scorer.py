import logging
from typing import Dict, List, Any, Tuple, Optional
from src.multiperspective.contradiction_detector import ContradictionMatrix
from src.multiperspective.perspective_clusterer import PerspectiveCluster

# Initialize structured logging
logger = logging.getLogger("rag_system.multiperspective.disagreement_scorer")


class DisagreementScore:
    """Structure encapsulating disagreement evaluation score details."""

    def __init__(
        self,
        raw_score: float,
        display_score: int,
        interpretation: str,
        dominant_perspective: str,
        minority_perspective: str
    ) -> None:
        self.raw_score = raw_score
        self.display_score = display_score
        self.interpretation = interpretation
        self.dominant_perspective = dominant_perspective
        self.minority_perspective = minority_perspective

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_score": self.raw_score,
            "display_score": self.display_score,
            "interpretation": self.interpretation,
            "dominant_perspective": self.dominant_perspective,
            "minority_perspective": self.minority_perspective
        }


class DisagreementScorer:
    """Quantifies disagreement level (0-10) using cluster properties and contradiction confidence metrics."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def compute_score(
        self,
        contradiction_matrix: ContradictionMatrix,
        perspective_clusters: List[PerspectiveCluster]
    ) -> DisagreementScore:
        """Computes the final disagreement score and assigns interpretation and perspective labels."""
        
        # 1. Base Score: Mean of top-3 contradiction confidence ratings
        if not contradiction_matrix.has_contradictions or not contradiction_matrix.contradictions:
            raw_score = 0.0
        else:
            sorted_confs = sorted(
                [c.confidence for c in contradiction_matrix.contradictions],
                reverse=True
            )
            top_3 = sorted_confs[:3]
            raw_score = sum(top_3) / len(top_3)

        # 2. Cluster Count Multiplier
        cluster_count = len(perspective_clusters)
        if cluster_count <= 2:
            cluster_mult = 1.0
        elif cluster_count == 3:
            cluster_mult = 1.15
        else:
            cluster_mult = 1.25

        # 3. Imbalance Penalty
        # Unequal sizes (e.g. 5 sources in A, 1 in B) indicate less balanced debate, reducing score
        if cluster_count >= 2:
            sizes = [c.chunk_count for c in perspective_clusters]
            max_size = max(sizes)
            min_size = min(sizes)
            balance_ratio = min_size / max_size
            imbalance_penalty = 0.7 + 0.3 * balance_ratio
        else:
            imbalance_penalty = 1.0

        # Apply multipliers
        raw_score = raw_score * cluster_mult * imbalance_penalty
        
        # Keep score strictly within [0.0, 1.0]
        raw_score = min(1.0, max(0.0, raw_score))
        display_score = int(round(raw_score * 10))

        # 4. Determine Stance Dominance
        dominant_perspective = ""
        minority_perspective = ""
        
        if cluster_count > 0:
            dominant_perspective = perspective_clusters[0].label
        if cluster_count > 1:
            minority_perspective = perspective_clusters[1].label

        # 5. Compile Interpretation
        if display_score < 3:
            interpretation = "Sources broadly agree with minor variations"
        elif display_score < 7:
            interpretation = "Meaningful disagreement exists — review both perspectives"
        else:
            interpretation = "Strong contradiction — do not rely on single source"

        logger.info(
            f"Disagreement score calculated: {display_score}/10 (raw: {raw_score:.4f}, "
            f"interpretation: '{interpretation}')"
        )

        return DisagreementScore(
            raw_score=raw_score,
            display_score=display_score,
            interpretation=interpretation,
            dominant_perspective=dominant_perspective,
            minority_perspective=minority_perspective
        )
