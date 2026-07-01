import time
import logging
import json
import asyncio
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
from openai import OpenAI

from src.ingestion.vector_store import SearchResult
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.multiperspective.perspective_clusterer")


class Perspective:
    """Represents the extracted stance, position, and caveats of a single chunk."""

    def __init__(
        self,
        chunk_id: str,
        source: str,
        position: str,
        key_evidence: str,
        source_confidence: str,
        caveats: str,
        stance_label: str,
        embedding: List[float]
    ) -> None:
        self.chunk_id = chunk_id
        self.source = source
        self.position = position
        self.key_evidence = key_evidence
        self.source_confidence = source_confidence
        self.caveats = caveats
        self.stance_label = stance_label.lower().strip()
        self.embedding = embedding

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source": self.source,
            "position": self.position,
            "key_evidence": self.key_evidence,
            "source_confidence": self.source_confidence,
            "caveats": self.caveats,
            "stance_label": self.stance_label
        }


class PerspectiveCluster:
    """Groups similar perspectives representing a unified stance on the query topic."""

    def __init__(
        self,
        cluster_id: str,
        label: str,
        perspectives: List[Perspective],
        centroid_embedding: List[float],
        representative_chunk_id: str,
        chunk_count: int,
        avg_confidence: float
    ) -> None:
        self.cluster_id = cluster_id
        self.label = label
        self.perspectives = perspectives
        self.centroid_embedding = centroid_embedding
        self.representative_chunk_id = representative_chunk_id
        self.chunk_count = chunk_count
        self.avg_confidence = avg_confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "label": self.label,
            "perspectives": [p.to_dict() for p in self.perspectives],
            "representative_chunk_id": self.representative_chunk_id,
            "chunk_count": self.chunk_count,
            "avg_confidence": self.avg_confidence
        }


class PerspectiveClusterer:
    """Extracts positions and clusters retrieved chunks by their stance."""

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
        
        mp_conf = config.get("multiperspective", {})
        self.cluster_similarity_threshold = mp_conf.get("cluster_similarity_threshold", 0.85)

    def _cosine_similarity(self, u: np.ndarray, v: np.ndarray) -> float:
        norm_u = np.linalg.norm(u)
        norm_v = np.linalg.norm(v)
        if norm_u == 0 or norm_v == 0:
            return 0.0
        return float(np.dot(u, v) / (norm_u * norm_v))

    def extract_single_perspective(
        self,
        chunk: SearchResult,
        query: str
    ) -> Optional[Perspective]:
        """Extracts the position details of a single chunk using the LLM."""
        try:
            source_title = chunk.metadata.get("title", "Unknown Source")
            prompt_text = self.prompt_manager.get_prompt(
                "perspective_extractor",
                query=query,
                source=source_title,
                chunk_text=chunk.text
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
            
            position = data.get("position", "").strip()
            if not position:
                position = f"Discusses aspect of {query}."

            # Compute embedding of the position text
            embedding_model = self.vector_store.embedding_model
            embedding = embedding_model.encode(position).tolist()

            return Perspective(
                chunk_id=chunk.chunk_id,
                source=source_title,
                position=position,
                key_evidence=data.get("key_evidence", ""),
                source_confidence=data.get("source_confidence", "MEDIUM"),
                caveats=data.get("caveats", "none"),
                stance_label=data.get("stance_label", "neutral"),
                embedding=embedding
            )

        except Exception as e:
            logger.error(f"Failed to extract perspective for chunk {chunk.chunk_id}: {str(e)}")
            return None

    async def extract_perspectives(
        self,
        chunks: List[SearchResult],
        query: str
    ) -> List[Perspective]:
        """Extracts perspectives for all chunks in parallel."""
        tasks = [
            asyncio.to_thread(self.extract_single_perspective, chunk, query)
            for chunk in chunks
        ]
        results = await asyncio.gather(*tasks)
        # Filter out failed extractions
        return [r for r in results if r is not None]

    def label_cluster(self, perspectives: List[Perspective], stance_label: str) -> str:
        """Generates a representative short summary label for a stance cluster."""
        if not perspectives:
            return "Neutral stance"

        # Sort perspectives by length of position statement to find a detailed one
        sorted_p = sorted(perspectives, key=lambda p: len(p.position), reverse=True)
        rep = sorted_p[0]
        
        position_text = rep.position
        
        # Heuristic to clean up and shorten the position sentence
        prefixes_to_strip = [
            "argues that", "concludes that", "finds that", "recommends that",
            "supports the idea that", "argues", "concludes", "finds", "recommends",
            "asserts that", "states that"
        ]
        
        cleaned = position_text.strip()
        for pfx in prefixes_to_strip:
            if cleaned.lower().startswith(pfx):
                cleaned = cleaned[len(pfx):].strip()
                # Capitalize first letter of remaining text
                if cleaned:
                    cleaned = cleaned[0].upper() + cleaned[1:]
                break

        # Crop to first 45 characters
        if len(cleaned) > 45:
            cleaned = cleaned[:45].strip() + "..."
            
        # Ensure it has a leading action verb matching the stance if it got stripped
        if stance_label == "supports" and not cleaned.lower().startswith("support"):
            return f"Supports: {cleaned}"
        if stance_label == "opposes" and not cleaned.lower().startswith("oppos"):
            return f"Opposes: {cleaned}"
            
        return cleaned

    def cluster_perspectives(self, perspectives: List[Perspective]) -> List[PerspectiveCluster]:
        """Groups perspectives hierarchically by stance_label first, then by embedding similarity."""
        if not perspectives:
            return []

        # 1. Group by stance label (supports, opposes, neutral, mixed)
        groups_by_stance: Dict[str, List[Perspective]] = {}
        for p in perspectives:
            groups_by_stance.setdefault(p.stance_label, []).append(p)

        clusters: List[PerspectiveCluster] = []
        cluster_counter = 1

        for stance, group in groups_by_stance.items():
            if not group:
                continue

            # Sub-clustering within the stance group using embedding similarity
            sub_groups: List[List[Perspective]] = []
            
            for p in group:
                # Find an existing sub-group where the similarity to the first item (representative) is high
                assigned = False
                p_emb = np.array(p.embedding)
                
                for sg in sub_groups:
                    rep_emb = np.array(sg[0].embedding)
                    sim = self._cosine_similarity(p_emb, rep_emb)
                    
                    if sim > self.cluster_similarity_threshold:
                        sg.append(p)
                        assigned = True
                        break
                
                if not assigned:
                    sub_groups.append([p])

            # Build PerspectiveCluster objects
            for sg in sub_groups:
                # Compute centroid embedding
                embeddings_matrix = np.array([p.embedding for p in sg])
                centroid = np.mean(embeddings_matrix, axis=0).tolist()
                
                # Pick the perspective closest to the centroid as representative
                best_p = sg[0]
                best_dist = -1.0
                centroid_arr = np.array(centroid)
                
                for p in sg:
                    sim = self._cosine_similarity(np.array(p.embedding), centroid_arr)
                    if sim > best_dist:
                        best_dist = sim
                        best_p = p

                label = self.label_cluster(sg, stance)
                
                # Calculate average source confidence
                conf_weights = {"HIGH": 1.0, "MEDIUM": 0.5, "LOW": 0.2}
                avg_conf = float(np.mean([conf_weights.get(p.source_confidence, 0.5) for p in sg]))

                cluster_id = f"C{cluster_counter}"
                clusters.append(PerspectiveCluster(
                    cluster_id=cluster_id,
                    label=label,
                    perspectives=sg,
                    centroid_embedding=centroid,
                    representative_chunk_id=best_p.chunk_id,
                    chunk_count=len(sg),
                    avg_confidence=avg_conf
                ))
                cluster_counter += 1

        # Sort clusters by size (largest stance groups first)
        clusters.sort(key=lambda c: c.chunk_count, reverse=True)
        return clusters
