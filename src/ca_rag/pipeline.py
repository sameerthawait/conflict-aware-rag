import time
import os
import logging
import asyncio
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional, Union
from openai import OpenAI

from src.generation.pipeline import RAGPipeline, RAGResponse
from src.ca_rag.claim_extractor import ClaimExtractor, Claim
from src.ca_rag.nli_detector import NLIContradictionDetector, NLIMatrix
from src.ca_rag.evidence_clusterer import EvidenceClusterer, EvidenceCluster
from src.ca_rag.conflict_graph import ConflictGraphBuilder, ConflictGraph
from src.ca_rag.confidence_scorer import ConfidenceScorer, ResponseConfidence
from src.ca_rag.ca_rag_generator import CARAGGenerator, CARAGResponse
from src.utils.prompt_manager import PromptManager
from src.generation.citation_gate import CitationPreflightResult

logger = logging.getLogger("rag_system.ca_rag.pipeline")

class CARAGPipeline(RAGPipeline):
    """Conflict-Aware RAG Pipeline that detects and exposes factual/temporal contradictions among sources."""

    def __init__(
        self,
        config: Dict[str, Any],
        prompt_manager: PromptManager,
        vector_store: Any,
        client: OpenAI,
        cache: Optional[Any] = None,
        cost_tracker: Optional[Any] = None
    ) -> None:
        super().__init__(config, prompt_manager, vector_store, client, cache, cost_tracker)
        
        # Instantiate ca_rag modules
        self.claim_extractor = ClaimExtractor(config, prompt_manager, self.vector_store, client)
        self.nli_detector = NLIContradictionDetector(config, self.vector_store, client)
        self.evidence_clusterer = EvidenceClusterer(config, prompt_manager, self.vector_store, client)
        self.conflict_graph_builder = ConflictGraphBuilder(config)
        self.confidence_scorer = ConfidenceScorer(config)
        self.ca_rag_generator = CARAGGenerator(config, prompt_manager, client, self.verifier)
        
        ca_config = config.get("ca_rag", {})
        self.min_claims = ca_config.get("min_claims_for_carag", 3)
        self.contra_density_threshold = ca_config.get("contradiction_density_threshold", 0.1)

    def _get_query_hash(self, query: str) -> str:
        return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()

    def query(self, user_query: str) -> Union[CARAGResponse, RAGResponse]:
        """Runs Conflict-Aware RAG pipeline, falling back to standard RAG if contradiction triggers are unmet."""
        pipeline_start = time.perf_counter()
        latencies = {}
        query_hash = self._get_query_hash(user_query)

        # 1. Budget Verification (via auth session info if available)
        try:
            from src.api.auth import current_key_info
            key_info = current_key_info.get()
            if key_info and self.cost_tracker:
                self.cost_tracker.verify_budget(key_info["hash"], key_info["name"])
        except Exception:
            pass

        # 2. Retrieve top-k chunks using Hybrid Retriever
        retrieval_start = time.perf_counter()
        results, retrieval_latencies = self.hybrid_retriever.retrieve(user_query)
        latencies.update(retrieval_latencies)
        latencies["retrieval_ms"] = int((time.perf_counter() - retrieval_start) * 1000)

        # 3. Extract atomic claims in parallel
        claim_start = time.perf_counter()
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # FastAPI async thread-safe run handler
            import threading
            from concurrent.futures import ThreadPoolExecutor
            
            def run_async():
                new_loop = asyncio.new_event_loop()
                try:
                    return new_loop.run_until_complete(self.claim_extractor.batch_extract(results))
                finally:
                    new_loop.close()
                    
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async)
                claims_map = future.result()
        else:
            claims_map = loop.run_until_complete(self.claim_extractor.batch_extract(results))
            
        all_claims: List[Claim] = []
        for claim_list in claims_map.values():
            all_claims.extend(claim_list)
            
        claim_latency = int((time.perf_counter() - claim_start) * 1000)
        latencies["claim_extraction_ms"] = claim_latency

        # Fallback Trigger 1: Insufficient claim count
        if len(all_claims) < self.min_claims:
            logger.info(f"CA-RAG Fallback: Extracted claim count ({len(all_claims)}) is below minimum ({self.min_claims}). Triggering standard RAG.")
            fallback_res = super().run_pipeline(user_query)
            fallback_res.latencies["fallback_reason"] = "insufficient_claims"
            return fallback_res

        # 4. Perform NLI Contradiction Detection
        nli_start = time.perf_counter()
        nli_matrix = self.nli_detector.classify_all(all_claims)
        nli_latency = int((time.perf_counter() - nli_start) * 1000)
        latencies["nli_classification_ms"] = nli_latency

        # Fallback Trigger 2: No contradictions detected
        if not nli_matrix.has_contradictions:
            logger.info("CA-RAG Fallback: No contradictions found among claims. Triggering standard RAG.")
            fallback_res = super().run_pipeline(user_query)
            fallback_res.latencies["fallback_reason"] = "no_contradictions"
            return fallback_res

        # Fallback Trigger 3: Contradiction density below threshold
        if nli_matrix.contradiction_density < self.contra_density_threshold:
            logger.info(f"CA-RAG Fallback: Contradiction density ({nli_matrix.contradiction_density:.2f}) below threshold ({self.contra_density_threshold}). Triggering standard RAG.")
            fallback_res = super().run_pipeline(user_query)
            fallback_res.latencies["fallback_reason"] = "low_contradiction_density"
            return fallback_res

        # 5. Stance Clustering
        cluster_start = time.perf_counter()
        clusters = self.evidence_clusterer.cluster(user_query, all_claims, nli_matrix)
        cluster_latency = int((time.perf_counter() - cluster_start) * 1000)
        latencies["clustering_ms"] = cluster_latency

        # Fallback Trigger 4: Less than 2 stance clusters generated
        if len(clusters) < 2:
            logger.info(f"CA-RAG Fallback: Generated cluster count ({len(clusters)}) is below 2. Triggering standard RAG.")
            fallback_res = super().run_pipeline(user_query)
            fallback_res.latencies["fallback_reason"] = "insufficient_clusters"
            return fallback_res

        # 6. Build Conflict Graph
        graph_start = time.perf_counter()
        conflict_graph = self.conflict_graph_builder.build(all_claims, nli_matrix, clusters)
        graph_latency = int((time.perf_counter() - graph_start) * 1000)
        latencies["graph_building_ms"] = graph_latency

        # Asynchronously persist graph data to Neo4j database (non-blocking)
        try:
            if loop.is_running():
                loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(
                        asyncio.to_thread(self.conflict_graph_builder.persist_to_neo4j, conflict_graph, query_hash)
                    )
                )
            else:
                loop.run_until_complete(
                    asyncio.to_thread(self.conflict_graph_builder.persist_to_neo4j, conflict_graph, query_hash)
                )
        except Exception as e:
            logger.warning(f"Failed to submit Neo4j background task: {str(e)}")

        # 7. Multi-dimensional Confidence Scoring
        score_start = time.perf_counter()
        # Pre-compute retrieval scores mapping
        retrieval_scores = {res.chunk_id: res.score for res in results}
        chunk_metadata_map = {res.chunk_id: res.metadata for res in results}
        
        claim_confidences = {}
        for claim in all_claims:
            score_val = retrieval_scores.get(claim.chunk_id, 5.0)
            meta = chunk_metadata_map.get(claim.chunk_id, {})
            claim_confidences[claim.claim_id] = self.confidence_scorer.score_claim(claim, nli_matrix, score_val, meta)

        response_confidence = self.confidence_scorer.score_response(clusters, conflict_graph, claim_confidences)
        
        # Inject computed freshness values back into clusters
        for cl in clusters:
            freshness_scores = []
            for claim in cl.claims:
                claim_conf = claim_confidences.get(claim.claim_id)
                if claim_conf:
                    freshness_scores.append(claim_conf.freshness)
            cl.avg_source_freshness = float(np.mean(freshness_scores)) if freshness_scores else 1.0

        score_latency = int((time.perf_counter() - score_start) * 1000)
        latencies["confidence_scoring_ms"] = score_latency

        # 8. Evaluate citation sufficiency gate (Citation Preflight Check)
        preflight_start = time.perf_counter()
        preflight_res: CitationPreflightResult = self.preflight_gate.evaluate(user_query, results)
        preflight_latency = int((time.perf_counter() - preflight_start) * 1000)
        latencies["preflight_evaluation_ms"] = preflight_latency

        if not preflight_res.proceed:
            refusal_msg = self.config.get("quality_gates", {}).get(
                "refusal_message",
                "I am sorry, but I could not find any relevant information in the provided context to answer your query."
            )
            total_latency = int((time.perf_counter() - pipeline_start) * 1000)
            latencies["total_pipeline_ms"] = total_latency
            logger.warning(f"CA-RAG blocked by preflight gate sufficiency checks.")
            return RAGResponse(
                query=user_query,
                answer=refusal_msg,
                sources=[],
                confidence="Low",
                missing_information=preflight_res.reason,
                preflight_verdict=preflight_res.verdict,
                preflight_reason=preflight_res.reason,
                preflight_gaps=preflight_res.gaps,
                hallucination_verdict=None,
                hallucination_audit=[],
                latencies=latencies
            )

        # 9. Generate Conflict-Aware structured response
        ca_rag_resp = self.ca_rag_generator.generate(
            user_query=user_query,
            clusters=clusters,
            conflict_graph=conflict_graph,
            response_confidence=response_confidence,
            nli_matrix=nli_matrix,
            all_chunks=results
        )
        
        # Merge latencies
        latencies.update(ca_rag_resp.latency_breakdown)
        total_latency = int((time.perf_counter() - pipeline_start) * 1000)
        latencies["total_pipeline_ms"] = total_latency
        ca_rag_resp.total_latency_ms = total_latency
        ca_rag_resp.latency_breakdown = latencies

        logger.info(f"CA-RAG response successfully generated in {total_latency}ms.")
        return ca_rag_resp
