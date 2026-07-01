import time
import logging
import json
import uuid
from enum import Enum
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np
from openai import OpenAI

from src.ca_rag.claim_extractor import Claim
from src.ca_rag.nli_detector import NLIMatrix, NLILabel, NLIResult
from src.utils.prompt_manager import PromptManager

logger = logging.getLogger("rag_system.ca_rag.evidence_clusterer")

class StanceLabel(str, Enum):
    SUPPORTS = "SUPPORTS"
    OPPOSES = "OPPOSES"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"

@dataclass
class EvidenceCluster:
    cluster_id: str
    label: str
    stance: StanceLabel
    claims: List[Claim]
    representative_claim: Claim
    centroid_embedding: List[float]
    source_count: int
    chunk_ids: List[str]
    doc_ids: List[str]
    confidence: float
    avg_source_freshness: float
    internal_consistency: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "label": self.label,
            "stance": self.stance.value,
            "claims": [c.to_dict() for c in self.claims],
            "representative_claim": self.representative_claim.to_dict(),
            "centroid_embedding": self.centroid_embedding,
            "source_count": self.source_count,
            "chunk_ids": self.chunk_ids,
            "doc_ids": self.doc_ids,
            "confidence": self.confidence,
            "avg_source_freshness": self.avg_source_freshness,
            "internal_consistency": self.internal_consistency
        }


class EvidenceClusterer:
    """Groups factual claims into distinct clusters representing different viewpoints or stances on the query."""

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
        
        ca_config = config.get("ca_rag", {})
        self.cluster_similarity_threshold = ca_config.get("cluster_similarity_threshold", 0.85)
        self.max_clusters = ca_config.get("max_clusters", 6)

    def _cosine_similarity(self, u: List[float], v: List[float]) -> float:
        if not u or not v:
            return 0.0
        arr_u, arr_v = np.array(u), np.array(v)
        norm_u = np.linalg.norm(arr_u)
        norm_v = np.linalg.norm(arr_v)
        if norm_u == 0 or norm_v == 0:
            return 0.0
        return float(np.dot(arr_u, arr_v) / (norm_u * norm_v))

    def build_affinity_matrix(self, claims: List[Claim], nli_matrix: NLIMatrix) -> np.ndarray:
        """Constructs an affinity matrix combining NLI relationships and semantic embeddings similarity."""
        n = len(claims)
        affinity = np.zeros((n, n))
        
        # Mapping from claim pairs to their NLI results
        nli_map = {}
        for nli_res in nli_matrix.results:
            nli_map[(nli_res.claim_a_id, nli_res.claim_b_id)] = nli_res
            nli_map[(nli_res.claim_b_id, nli_res.claim_a_id)] = nli_res

        for i in range(n):
            for j in range(n):
                if i == j:
                    affinity[i, j] = 1.0
                    continue
                
                c1, c2 = claims[i], claims[j]
                cos_sim = self._cosine_similarity(c1.embedding, c2.embedding)
                
                res: Optional[NLIResult] = nli_map.get((c1.claim_id, c2.claim_id))
                if res:
                    if res.final_verdict == NLILabel.ENTAILMENT:
                        # Entailment implies claims belong to the same stance
                        affinity[i, j] = 0.9
                    elif res.final_verdict == NLILabel.CONTRADICTION:
                        # Contradiction implies opposing stances
                        affinity[i, j] = -0.5
                    else:
                        affinity[i, j] = cos_sim
                else:
                    affinity[i, j] = cos_sim
                    
        # Make affinity non-negative for standard spectral clustering
        affinity = np.clip(affinity, 0.0, 1.0)
        return affinity

    def _numpy_kmeans(self, X: np.ndarray, k: int, max_iters: int = 100) -> np.ndarray:
        """Pure numpy K-means implementation to keep clustering dependency-free."""
        if X.shape[0] < k:
            k = X.shape[0]
        # Randomly choose initial centroids
        indices = np.random.choice(X.shape[0], k, replace=False)
        centroids = X[indices]
        
        labels = np.zeros(X.shape[0], dtype=int)
        for _ in range(max_iters):
            # Compute distance from all points to centroids
            distances = np.linalg.norm(X[:, np.newaxis] - centroids, axis=2)
            new_labels = np.argmin(distances, axis=1)
            
            # Check if convergence achieved
            if np.array_equal(labels, new_labels):
                break
            labels = new_labels
            
            # Recompute centroids
            for j in range(k):
                points = X[labels == j]
                if len(points) > 0:
                    centroids[j] = points.mean(axis=0)
        return labels

    def spectral_cluster(self, affinity_matrix: np.ndarray, n_claims: int) -> np.ndarray:
        """Executes Spectral Clustering on the affinity matrix using the Eigengap heuristic for automated cluster counts."""
        n = affinity_matrix.shape[0]
        if n < 2:
            return np.zeros(n, dtype=int)

        # Degree matrix
        D = np.diag(np.sum(affinity_matrix, axis=1))
        
        # Laplacian matrix L = D - A
        L = D - affinity_matrix
        
        # Calculate eigenvalues and eigenvectors
        try:
            eigenvalues, eigenvectors = np.linalg.eigh(L)
        except Exception as e:
            logger.warning(f"Symmetric eigendecomposition failed: {str(e)}. Using standard decomposition.")
            eigenvalues, eigenvectors = np.linalg.eig(L)
            # Ensure eigenvalues are real
            eigenvalues = np.real(eigenvalues)
            eigenvectors = np.real(eigenvectors)
            
        # Sort eigenvalues ascending
        idx = np.argsort(eigenvalues)
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        # Eigengap heuristic: find index that maximizes gap between consecutive eigenvalues
        min_k = 2
        max_k = min(self.max_clusters, n_claims // 2)
        max_k = max(min_k, max_k)
        
        if n <= min_k:
            k_opt = n
        else:
            gaps = np.diff(eigenvalues[min_k-1:max_k+1])
            if len(gaps) > 0:
                k_opt = min_k + np.argmax(gaps)
            else:
                k_opt = min_k

        # Project claims into low-dimensional space spanned by first k_opt eigenvectors
        X_proj = eigenvectors[:, :k_opt]
        
        # Normalize rows of projection matrix
        norms = np.linalg.norm(X_proj, axis=1, keepdims=True)
        norms[norms == 0] = 1e-12
        X_proj = X_proj / norms

        # Cluster in projected space using K-means
        labels = self._numpy_kmeans(X_proj, k_opt)
        return labels

    def label_cluster(self, user_query: str, claims: List[Claim]) -> Tuple[str, StanceLabel, str]:
        """Queries LLM with cluster_labeler_prompt to generate descriptive stance labels and interpretations."""
        claims_list = "\n".join([f"- {c.normalized_text} [Source: {c.source_title}]" for c in claims])
        
        try:
            prompt_text = self.prompt_manager.get_prompt(
                "cluster_labeler_prompt",
                user_query=user_query,
                claims_list=claims_list
            )

            llm_model = self.config.get("llm", {}).get("model_name", "meta/llama-3.3-70b-instruct")
            response = self.client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            
            data = json.loads(response.choices[0].message.content.strip())
            label = data.get("label", "Supports a general position").strip()
            stance_str = data.get("stance", "NEUTRAL").upper()
            summary = data.get("summary", "").strip()
            
            try:
                stance = StanceLabel(stance_str)
            except ValueError:
                stance = StanceLabel.NEUTRAL
                
            return label, stance, summary

        except Exception as e:
            logger.error(f"Failed to generate cluster label: {str(e)}")
            return "General perspective", StanceLabel.NEUTRAL, "A viewpoint gathered from retrieved chunks."

    def compute_source_quality(self, title: str) -> float:
        """Determines source trust value based on paper headers or domain metadata."""
        title_lower = title.lower()
        if "arxiv" in title_lower or "doi:" in title_lower or "journal" in title_lower or "clinical" in title_lower:
            return 1.0
        elif "docs" in title_lower or "official" in title_lower or "manual" in title_lower or "guideline" in title_lower:
            return 0.85
        elif "news" in title_lower or "blog" in title_lower or "post" in title_lower:
            return 0.65
        return 0.40

    def compute_cluster_confidence(self, claims: List[Claim]) -> float:
        """Scores cluster confidence using source trust, claim accuracy, and volume log-normalizations."""
        mean_quality = np.mean([self.compute_source_quality(c.source_title) for c in claims])
        mean_extraction_conf = np.mean([c.confidence for c in claims])
        
        # Logarithmic normalization of citation count (volume of claims)
        citation_count = len(claims)
        vol_bonus = np.log1p(citation_count) / np.log1p(10)  # normalized assuming 10 is max standard
        vol_bonus = min(vol_bonus, 1.0)
        
        # Combined score bounded 0-1
        score = 0.5 * mean_quality + 0.3 * mean_extraction_conf + 0.2 * vol_bonus
        return min(max(score, 0.0), 1.0)

    def _get_cluster_consistency(self, claims: List[Claim], nli_matrix: NLIMatrix) -> float:
        """Evaluates internal cluster consistency by calculating mean entailment scores within the cluster."""
        n = len(claims)
        if n < 2:
            return 1.0
            
        nli_map = {}
        for nli_res in nli_matrix.results:
            nli_map[(nli_res.claim_a_id, nli_res.claim_b_id)] = nli_res
            nli_map[(nli_res.claim_b_id, nli_res.claim_a_id)] = nli_res

        entailment_scores = []
        for i in range(n):
            for j in range(i + 1, n):
                c1, c2 = claims[i], claims[j]
                nli_res = nli_map.get((c1.claim_id, c2.claim_id))
                if nli_res:
                    fwd_ent = nli_res.forward_scores.get(NLILabel.ENTAILMENT.value, 0.0)
                    bwd_ent = nli_res.backward_scores.get(NLILabel.ENTAILMENT.value, 0.0)
                    entailment_scores.append(max(fwd_ent, bwd_ent))
                else:
                    # Fallback to cosine embedding similarity
                    entailment_scores.append(self._cosine_similarity(c1.embedding, c2.embedding))
                    
        return float(np.mean(entailment_scores)) if entailment_scores else 1.0

    def cluster(self, user_query: str, claims: List[Claim], nli_matrix: NLIMatrix) -> List[EvidenceCluster]:
        """Clusters claims, resolves centroid representatives, and computes metrics to generate finished Stances."""
        n_claims = len(claims)
        if n_claims == 0:
            return []
            
        if n_claims == 1:
            label, stance, summary = self.label_cluster(user_query, claims)
            return [EvidenceCluster(
                cluster_id=str(uuid.uuid4()),
                label=label,
                stance=stance,
                claims=claims,
                representative_claim=claims[0],
                centroid_embedding=claims[0].embedding,
                source_count=1,
                chunk_ids=[claims[0].chunk_id],
                doc_ids=[claims[0].doc_id],
                confidence=self.compute_cluster_confidence(claims),
                avg_source_freshness=1.0,
                internal_consistency=1.0
            )]

        # 1. Build affinity and execute spectral clustering
        affinity = self.build_affinity_matrix(claims, nli_matrix)
        labels = self.spectral_cluster(affinity, n_claims)

        # 2. Form initial clusters
        raw_clusters: Dict[int, List[Claim]] = {}
        for idx, label_id in enumerate(labels):
            if label_id not in raw_clusters:
                raw_clusters[label_id] = []
            raw_clusters[label_id].append(claims[idx])

        # 3. Build cluster entities
        clusters = []
        for cluster_id_int, cluster_claims in raw_clusters.items():
            # Centroid embedding calculation
            embeddings = np.array([c.embedding for c in cluster_claims if c.embedding])
            if len(embeddings) > 0:
                centroid = np.mean(embeddings, axis=0).tolist()
            else:
                centroid = [0.0] * 384  # default dummy size

            # Representative claim (closest to centroid)
            rep_claim = cluster_claims[0]
            max_sim = -1.0
            for c in cluster_claims:
                sim = self._cosine_similarity(c.embedding, centroid)
                if sim > max_sim:
                    max_sim = sim
                    rep_claim = c

            doc_ids = list(set(c.doc_id for c in cluster_claims))
            chunk_ids = list(set(c.chunk_id for c in cluster_claims))
            
            # Stance and descriptive labeling via LLM
            label_text, stance, summary = self.label_cluster(user_query, cluster_claims)
            
            confidence = self.compute_cluster_confidence(cluster_claims)
            consistency = self._get_cluster_consistency(cluster_claims, nli_matrix)

            clusters.append(EvidenceCluster(
                cluster_id=str(uuid.uuid4()),
                label=label_text,
                stance=stance,
                claims=cluster_claims,
                representative_claim=rep_claim,
                centroid_embedding=centroid,
                source_count=len(doc_ids),
                chunk_ids=chunk_ids,
                doc_ids=doc_ids,
                confidence=confidence,
                avg_source_freshness=1.0,  # Computed in scoring layer
                internal_consistency=consistency
            ))

        # 4. Centroid-based cluster merging
        merged = True
        while merged and len(clusters) > 1:
            merged = False
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    sim = self._cosine_similarity(clusters[i].centroid_embedding, clusters[j].centroid_embedding)
                    if sim > self.cluster_similarity_threshold:
                        # Merge j into i
                        c_i = clusters[i]
                        c_j = clusters[j]
                        merged_claims = c_i.claims + c_j.claims
                        
                        # Re-calculate Representative Claim
                        embeddings = np.array([c.embedding for c in merged_claims if c.embedding])
                        centroid = np.mean(embeddings, axis=0).tolist() if len(embeddings) > 0 else c_i.centroid_embedding
                        
                        rep_claim = merged_claims[0]
                        max_sim = -1.0
                        for c in merged_claims:
                            sim_c = self._cosine_similarity(c.embedding, centroid)
                            if sim_c > max_sim:
                                max_sim = sim_c
                                rep_claim = c
                                
                        doc_ids = list(set(c.doc_id for c in merged_claims))
                        chunk_ids = list(set(c.chunk_id for c in merged_claims))
                        
                        label_text, stance, summary = self.label_cluster(user_query, merged_claims)
                        confidence = self.compute_cluster_confidence(merged_claims)
                        consistency = self._get_cluster_consistency(merged_claims, nli_matrix)
                        
                        # Replace i with merged cluster, remove j
                        clusters[i] = EvidenceCluster(
                            cluster_id=c_i.cluster_id,
                            label=label_text,
                            stance=stance,
                            claims=merged_claims,
                            representative_claim=rep_claim,
                            centroid_embedding=centroid,
                            source_count=len(doc_ids),
                            chunk_ids=chunk_ids,
                            doc_ids=doc_ids,
                            confidence=confidence,
                            avg_source_freshness=1.0,
                            internal_consistency=consistency
                        )
                        clusters.pop(j)
                        merged = True
                        break
                if merged:
                    break

        return clusters
