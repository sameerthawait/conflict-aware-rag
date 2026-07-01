import logging
from datetime import datetime
import re
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np

from src.ca_rag.claim_extractor import Claim
from src.ca_rag.evidence_clusterer import EvidenceCluster
from src.ca_rag.nli_detector import NLIMatrix, NLILabel, NLIResult
from src.ca_rag.conflict_graph import ConflictGraph

logger = logging.getLogger("rag_system.ca_rag.confidence_scorer")

@dataclass
class ClaimConfidence:
    claim_id: str
    retrieval_relevance: float
    source_quality: float
    citation_count_score: float
    contradiction_strength_score: float
    freshness: float
    composite_score: float
    dimension_weights: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "retrieval_relevance": self.retrieval_relevance,
            "source_quality": self.source_quality,
            "citation_count_score": self.citation_count_score,
            "contradiction_strength_score": self.contradiction_strength_score,
            "freshness": self.freshness,
            "composite_score": self.composite_score,
            "dimension_weights": self.dimension_weights
        }

@dataclass
class ResponseConfidence:
    overall: float
    dominant_cluster_confidence: float
    minority_cluster_confidence: float
    conflict_clarity: float
    interpretation: str
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": self.overall,
            "dominant_cluster_confidence": self.dominant_cluster_confidence,
            "minority_cluster_confidence": self.minority_cluster_confidence,
            "conflict_clarity": self.conflict_clarity,
            "interpretation": self.interpretation,
            "recommendation": self.recommendation
        }


class ConfidenceScorer:
    """Calculates multi-dimensional confidence metrics across five validation axes for claims, clusters, and response profiles."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        ca_config = config.get("ca_rag", {})
        self.decay_rates = ca_config.get("domain_decay_rates", {
            "ai_ml": 1.3,
            "data_science": 1.1,
            "cloud": 1.2,
            "devops": 1.2,
            "ar_vr": 1.4,
            "medical": 0.7,
            "legal": 0.7,
            "historical": 0.3,
            "general": 1.0
        })
        
        # Scoring weights summing to 1.0
        self.weights = {
            "retrieval_relevance": 0.25,
            "source_quality": 0.20,
            "citation_count": 0.15,
            "contradiction_strength": 0.25,
            "freshness": 0.15
        }

    def _extract_year(self, metadata: Dict[str, Any]) -> int:
        """Parses calendar dates or publishing records to extract the year of release."""
        # Check standard fields
        for field_name in ["publish_date", "date", "year", "created_at"]:
            val = metadata.get(field_name)
            if not val:
                continue
            if isinstance(val, int) and 1900 <= val <= 2100:
                return val
            # Try parsing string
            matches = re.findall(r"\b(19\d{2}|20\d{2})\b", str(val))
            if matches:
                return int(matches[0])
        return datetime.utcnow().year

    def compute_source_quality(self, title: str) -> float:
        title_lower = title.lower()
        if "arxiv" in title_lower or "doi:" in title_lower or "journal" in title_lower or "clinical" in title_lower:
            return 1.0
        elif "docs" in title_lower or "official" in title_lower or "manual" in title_lower or "guideline" in title_lower:
            return 0.85
        elif "news" in title_lower or "blog" in title_lower or "post" in title_lower:
            return 0.65
        return 0.40

    def compute_freshness(self, metadata: Dict[str, Any]) -> float:
        """Computes time-decay freshness score adjusted by domain specific decay multipliers."""
        year = self._extract_year(metadata)
        current_year = datetime.utcnow().year
        age = max(0, current_year - year)
        
        # Resolve domain decay rate
        domain = metadata.get("domain", "general").lower()
        decay_modifier = self.decay_rates.get(domain, 1.0)
        
        effective_age = age * decay_modifier
        
        if effective_age < 1.0:
            return 1.0
        elif effective_age < 2.0:
            return 0.85
        elif effective_age < 3.0:
            return 0.70
        elif effective_age < 5.0:
            return 0.50
        return 0.30

    def score_claim(self, claim: Claim, nli_matrix: NLIMatrix, retrieval_score: float, chunk_metadata: Dict[str, Any]) -> ClaimConfidence:
        """Scores a claim across the 5 dimensions, combining them into a composite score."""
        # 1. Retrieval Relevance: normalise cross-encoder score (0-10) to 0-1
        relevance = min(max(retrieval_score / 10.0, 0.0), 1.0)

        # 2. Source Quality
        quality = self.compute_source_quality(claim.source_title)

        # 3. Citation Count: log-normalized citation counts
        citations = int(chunk_metadata.get("citations", chunk_metadata.get("citation_count", 0)))
        if citations > 0:
            # Assumes 100 is max citations standard scaling baseline
            citation_score = np.log1p(citations) / np.log1p(100)
            citation_score = min(citation_score, 1.0)
        else:
            citation_score = 0.5  # Neutral fallback

        # 4. Contradiction Strength: 1.0 - mean contradiction strength involving this claim
        contra_strengths = []
        for res in nli_matrix.results:
            if res.claim_a_id == claim.claim_id or res.claim_b_id == claim.claim_id:
                if res.final_verdict == NLILabel.CONTRADICTION:
                    contra_strengths.append(res.contradiction_strength)
        
        if contra_strengths:
            contra_score = 1.0 - float(np.mean(contra_strengths))
        else:
            contra_score = 1.0

        # 5. Freshness
        freshness = self.compute_freshness(chunk_metadata)

        # Weighted composite score
        composite = (
            relevance * self.weights["retrieval_relevance"] +
            quality * self.weights["source_quality"] +
            citation_score * self.weights["citation_count"] +
            contra_score * self.weights["contradiction_strength"] +
            freshness * self.weights["freshness"]
        )

        return ClaimConfidence(
            claim_id=claim.claim_id,
            retrieval_relevance=relevance,
            source_quality=quality,
            citation_count_score=citation_score,
            contradiction_strength_score=contra_score,
            freshness=freshness,
            composite_score=min(max(composite, 0.0), 1.0),
            dimension_weights=self.weights
        )

    def score_cluster(self, cluster: EvidenceCluster, claim_confidences: Dict[str, ClaimConfidence]) -> float:
        """Computes weighted mean of claim scores with cluster size bonuses and internal inconsistency penalties."""
        scores = []
        for claim in cluster.claims:
            conf = claim_confidences.get(claim.claim_id)
            if conf:
                scores.append(conf.composite_score)
        
        base_score = float(np.mean(scores)) if scores else 0.5
        
        # Size Bonus: +0.05 if cluster has > 2 independent sources
        bonus = 0.0
        if cluster.source_count > 2:
            bonus = 0.05
            
        # Consistency Penalty: -0.10 if cluster has high internal contradiction
        penalty = 0.0
        if cluster.internal_consistency < 0.7:
            penalty = 0.10 * (1.0 - cluster.internal_consistency)

        final_score = base_score + bonus - penalty
        return min(max(final_score, 0.0), 1.0)

    def score_response(self, clusters: List[EvidenceCluster], conflict_graph: ConflictGraph, claim_confidences: Dict[str, ClaimConfidence]) -> ResponseConfidence:
        """Assembles aggregate response confidence, separating dominant vs. minority stances, and calculating clarity ratings."""
        if not clusters:
            return ResponseConfidence(
                overall=0.0,
                dominant_cluster_confidence=0.0,
                minority_cluster_confidence=0.0,
                conflict_clarity=0.0,
                interpretation="UNKNOWN",
                recommendation="Ingest additional sources to evaluate the query."
            )

        # Calculate cluster confidences
        cluster_conf_map = {}
        for c in clusters:
            cluster_conf_map[c.cluster_id] = self.score_cluster(c, claim_confidences)

        # Average of all cluster confidences
        overall_score = float(np.mean(list(cluster_conf_map.values())))

        # Sort clusters by claims size to locate dominant vs minority stances
        sorted_clusters = sorted(clusters, key=lambda x: len(x.claims), reverse=True)
        dominant_cluster = sorted_clusters[0]
        dom_conf = cluster_conf_map[dominant_cluster.cluster_id]

        if len(sorted_clusters) > 1:
            minority_cluster = sorted_clusters[1]
            min_conf = cluster_conf_map[minority_cluster.cluster_id]
        else:
            min_conf = 0.0

        # Conflict Clarity: separation score * (1.0 - mean contradiction involvement variance)
        sep_score = conflict_graph.metrics.cluster_separation_score
        
        # Calculate contradiction density
        contra_density = conflict_graph.metrics.contradiction_density
        clarity = sep_score * (1.0 - contra_density)

        # Deduce verbal interpretation
        if contra_density > 0.3:
            interpretation = "HIGHLY CONTESTED"
            recommendation = "Direct contradiction identified. Read supporting and contradicting viewpoints below and check temporal differences."
        elif overall_score >= 0.75:
            interpretation = "HIGHLY RELIABLE"
            recommendation = "Factual consensus exists across high-quality academic sources."
        elif overall_score >= 0.55:
            interpretation = "MODERATELY RELIABLE"
            recommendation = "General agreement, though some minor methodology or scope variances exist."
        else:
            interpretation = "LOW CONFIDENCE"
            recommendation = "Limited or conflicting evidence found. Consult primary sources directly."

        return ResponseConfidence(
            overall=overall_score,
            dominant_cluster_confidence=dom_conf,
            minority_cluster_confidence=min_conf,
            conflict_clarity=clarity,
            interpretation=interpretation,
            recommendation=recommendation
        )
