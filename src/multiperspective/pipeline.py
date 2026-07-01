import time
import logging
import uuid
from typing import Dict, List, Any, Tuple, Optional
from openai import OpenAI

from src.generation.pipeline import RAGPipeline, RAGResponse
from src.ingestion.vector_store import SearchResult
from src.multiperspective.contradiction_detector import ContradictionDetector, ContradictionMatrix, ContradictionResult
from src.multiperspective.perspective_clusterer import PerspectiveClusterer, PerspectiveCluster, Perspective
from src.multiperspective.disagreement_scorer import DisagreementScorer, DisagreementScore
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.multiperspective.pipeline")


class MultiPerspectiveRAGResponse:
    """Structure encapsulating the output of the Multi-Perspective RAG pipeline."""

    def __init__(
        self,
        mode: str,
        answer: str,
        perspectives: List[PerspectiveCluster],
        contradictions: List[ContradictionResult],
        disagreement_score: DisagreementScore,
        sources: List[Any],
        confidence: str,
        total_latency_ms: int,
        latency_breakdown: Dict[str, float]
    ) -> None:
        self.response_id = str(uuid.uuid4())
        self.mode = mode  # "standard" | "multi_perspective"
        self.answer = answer
        self.perspectives = perspectives
        self.contradictions = contradictions
        self.disagreement_score = disagreement_score
        self.sources = sources
        self.confidence = confidence
        self.total_latency_ms = total_latency_ms
        self.latency_breakdown = latency_breakdown

    def to_dict(self) -> Dict[str, Any]:
        # Formulate sources matching frontend models
        sources_list = []
        for s in self.sources:
            if isinstance(s, SearchResult):
                sources_list.append({
                    "chunk_id": s.chunk_id,
                    "text": s.text,
                    "score": s.score,
                    "metadata": s.metadata
                })
            else:
                sources_list.append(s)

        return {
            "response_id": self.response_id,
            "mode": self.mode,
            "answer": self.answer,
            "perspectives": [p.to_dict() for p in self.perspectives],
            "contradictions": [c.to_dict() for c in self.contradictions],
            "disagreement_score": self.disagreement_score.to_dict() if self.disagreement_score else None,
            "sources": sources_list,
            "confidence": self.confidence,
            "total_latency_ms": self.total_latency_ms,
            "latency_breakdown": self.latency_breakdown
        }


class MultiPerspectiveRAGPipeline(RAGPipeline):
    """Extends standard RAGPipeline to identify conflicts, segment perspectives, and synthesize balanced views."""

    def __init__(
        self,
        config: Dict[str, Any],
        prompt_manager: PromptManager,
        vector_store: Any,
        client: Optional[OpenAI] = None,
        cache: Optional[Any] = None,
        cost_tracker: Optional[Any] = None
    ) -> None:
        super().__init__(config, prompt_manager, vector_store, client, cache, cost_tracker)
        
        self.contradiction_detector = ContradictionDetector(config, prompt_manager, vector_store, self.client)
        self.perspective_clusterer = PerspectiveClusterer(config, prompt_manager, vector_store, self.client)
        self.disagreement_scorer = DisagreementScorer(config)
        
        mp_conf = config.get("multiperspective", {})
        self.disagreement_score_trigger = mp_conf.get("disagreement_score_trigger", 3)
        self.max_perspectives = mp_conf.get("max_perspectives", 4)
        
        # Local state storage to persist responses for explanation lookups
        self._responses_store: Dict[str, MultiPerspectiveRAGResponse] = {}

    async def query(self, user_query: str) -> MultiPerspectiveRAGResponse:
        """Executes the Multi-Perspective RAG workflow."""
        start_time = time.perf_counter()
        latencies: Dict[str, float] = {}

        logger.info(f"Multi-Perspective query initiated: '{user_query}'")

        # Step 1: Run standard retriever to fetch candidate passages
        ret_start = time.perf_counter()
        results, retrieval_latencies = self.hybrid_retriever.retrieve(user_query)
        latencies["retrieval_ms"] = (time.perf_counter() - ret_start) * 1000
        latencies.update(retrieval_latencies)

        if not results:
            # Fall back to standard response formatting (no sources retrieved)
            refusal_msg = self.config.get("quality_gates", {}).get(
                "refusal_message",
                "I am sorry, but I could not find any relevant information in the provided context to answer your query."
            )
            total_ms = int((time.perf_counter() - start_time) * 1000)
            return MultiPerspectiveRAGResponse(
                mode="standard",
                answer=refusal_msg,
                perspectives=[],
                contradictions=[],
                disagreement_score=DisagreementScore(0.0, 0, "No sources retrieved", "", ""),
                sources=[],
                confidence="Low",
                total_latency_ms=total_ms,
                latency_breakdown=latencies
            )

        # Step 2: Run Contradiction Detector on candidate chunks
        contra_start = time.perf_counter()
        contradiction_matrix: ContradictionMatrix = await self.contradiction_detector.detect_all(
            results, user_query
        )
        latencies["contradiction_detection_ms"] = (time.perf_counter() - contra_start) * 1000

        # Step 3: Trigger check
        if not contradiction_matrix.has_contradictions:
            logger.info("No contradictions detected. Routing query to standard RAG pipeline.")
            
            # Execute standard pipeline synchronously
            std_start = time.perf_counter()
            std_resp: RAGResponse = self.run_pipeline(user_query)
            latencies["standard_generation_ms"] = (time.perf_counter() - std_start) * 1000
            
            total_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Formulate final response object
            response_obj = MultiPerspectiveRAGResponse(
                mode="standard",
                answer=std_resp.answer,
                perspectives=[],
                contradictions=[],
                disagreement_score=DisagreementScore(0.0, 0, "Sources agree", "", ""),
                sources=results,
                confidence=std_resp.confidence,
                total_latency_ms=total_ms,
                latency_breakdown=latencies
            )
            
            self._responses_store[response_obj.response_id] = response_obj
            return response_obj

        # Step 4: Extract perspectives in parallel
        extract_start = time.perf_counter()
        perspectives: List[Perspective] = await self.perspective_clusterer.extract_perspectives(
            results, user_query
        )
        latencies["perspective_extraction_ms"] = (time.perf_counter() - extract_start) * 1000

        # Step 5: Cluster extracted perspectives
        cluster_start = time.perf_counter()
        clusters: List[PerspectiveCluster] = self.perspective_clusterer.cluster_perspectives(
            perspectives
        )
        latencies["perspective_clustering_ms"] = (time.perf_counter() - cluster_start) * 1000

        # Step 6: Compute Disagreement score
        score_start = time.perf_counter()
        disagreement_score: DisagreementScore = self.disagreement_scorer.compute_score(
            contradiction_matrix, clusters
        )
        latencies["disagreement_scoring_ms"] = (time.perf_counter() - score_start) * 1000

        # Check score threshold to determine if standard RAG fallback is required
        if disagreement_score.display_score < self.disagreement_score_trigger or len(clusters) < 2:
            logger.info(
                f"Disagreement score ({disagreement_score.display_score}) below trigger threshold "
                f"({self.disagreement_score_trigger}) or insufficient clusters. Routing to standard RAG."
            )
            std_start = time.perf_counter()
            std_resp = self.run_pipeline(user_query)
            latencies["standard_generation_ms"] = (time.perf_counter() - std_start) * 1000
            
            total_ms = int((time.perf_counter() - start_time) * 1000)
            
            response_obj = MultiPerspectiveRAGResponse(
                mode="standard",
                answer=std_resp.answer,
                perspectives=[],
                contradictions=contradiction_matrix.contradictions,
                disagreement_score=disagreement_score,
                sources=results,
                confidence=std_resp.confidence,
                total_latency_ms=total_ms,
                latency_breakdown=latencies
            )
            self._responses_store[response_obj.response_id] = response_obj
            return response_obj

        # Step 7: Synthesize Multi-Perspective balanced response
        synth_start = time.perf_counter()
        
        # Build map to lookup full SearchResult structures by ID
        chunks_map = {c.chunk_id: c for c in results}
        
        # Format Perspective A
        p_a = clusters[0]
        perspective_a_chunks_list = []
        for p in p_a.perspectives:
            chunk_ref = chunks_map.get(p.chunk_id)
            if chunk_ref:
                perspective_a_chunks_list.append(
                    f"[Doc: {p.source} | Chunk: {p.chunk_id}]\n{chunk_ref.text}"
                )
        perspective_a_chunks = "\n\n".join(perspective_a_chunks_list)

        # Format Perspective B
        p_b = clusters[1]
        perspective_b_chunks_list = []
        for p in p_b.perspectives:
            chunk_ref = chunks_map.get(p.chunk_id)
            if chunk_ref:
                perspective_b_chunks_list.append(
                    f"[Doc: {p.source} | Chunk: {p.chunk_id}]\n{chunk_ref.text}"
                )
        perspective_b_chunks = "\n\n".join(perspective_b_chunks_list)

        # Format additional perspectives if they exist
        additional_perspectives_list = []
        additional_sections_list = []
        
        # Cap cluster exploration to max_perspectives config
        for idx in range(2, min(len(clusters), self.max_perspectives)):
            cluster = clusters[idx]
            label_char = chr(65 + idx) # C, D...
            additional_perspectives_list.append(
                f"Perspective {label_char} ({cluster.label}):\n" +
                "\n\n".join([
                    f"[Doc: {p.source} | Chunk: {p.chunk_id}]\n{chunks_map[p.chunk_id].text}"
                    for p in cluster.perspectives if p.chunk_id in chunks_map
                ])
            )
            additional_sections_list.append(
                f"PERSPECTIVE {label_char} — {cluster.label}:\n"
                f"<Balanced summary of stance with inline citations matching [Doc: title | Chunk: chunk_id]>"
            )

        additional_perspectives = "\n\n".join(additional_perspectives_list)
        additional_perspective_sections = "\n\n".join(additional_sections_list)

        prompt_text = self.prompt_manager.get_prompt(
            "multi_perspective_synthesizer",
            user_query=user_query,
            perspective_a_label=p_a.label,
            perspective_a_chunks=perspective_a_chunks,
            perspective_b_label=p_b.label,
            perspective_b_chunks=perspective_b_chunks,
            additional_perspectives=additional_perspectives,
            additional_perspective_sections=additional_perspective_sections,
            disagreement_score=disagreement_score.display_score
        )

        llm_model = self.config.get("llm", {}).get("model_name", "meta/llama-3.1-70b-instruct")
        temperature = self.config.get("llm", {}).get("temperature", 0.0)

        response = self.client.chat.completions.create(
            model=llm_model,
            messages=[{"role": "user", "content": prompt_text}],
            temperature=temperature
        )
        
        answer_text = response.choices[0].message.content.strip()
        latencies["multi_perspective_synthesis_ms"] = (time.perf_counter() - synth_start) * 1000

        # Step 8: Hallucination Verification
        verify_start = time.perf_counter()
        verifier_res, verify_latency_ms = self.verifier.verify(answer_text, results)
        latencies["hallucination_verification_ms"] = verify_latency_ms

        total_ms = int((time.perf_counter() - start_time) * 1000)

        # Construct response object
        response_obj = MultiPerspectiveRAGResponse(
            mode="multi_perspective",
            answer=answer_text,
            perspectives=clusters[:self.max_perspectives],
            contradictions=contradiction_matrix.contradictions,
            disagreement_score=disagreement_score,
            sources=results,
            confidence="High", # Multi-perspective synthesis presents balanced facts
            total_latency_ms=total_ms,
            latency_breakdown=latencies
        )
        
        self._responses_store[response_obj.response_id] = response_obj
        return response_obj

    async def explain_disagreement(self, user_query: str, response_id: str) -> str:
        """Explains why sources conflict on a given query based on the cached response details."""
        response_obj = self._responses_store.get(response_id)
        if not response_obj:
            logger.warning(f"Response ID {response_id} not found in local store. Generating explanation from query.")
            return "Unable to explain disagreement: Original response metadata expired or not found."

        # Compile source summaries
        summaries = []
        for idx, cluster in enumerate(response_obj.perspectives):
            label_char = chr(65 + idx)
            summaries.append(f"Perspective {label_char} ({cluster.label}):")
            for p in cluster.perspectives:
                summaries.append(
                    f"- Source: {p.source} (Confidence: {p.source_confidence}). Position: {p.position}"
                )
        source_summaries_text = "\n".join(summaries)

        # Compile contradiction details
        contradictions_text = "\n".join([
            f"- Passage A claims: {c.claim_a} | Passage B claims: {c.claim_b}. Reason: {c.explanation}"
            for c in response_obj.contradictions
        ])

        try:
            prompt_text = self.prompt_manager.get_prompt(
                "disagreement_explainer",
                user_query=user_query,
                source_summaries=source_summaries_text,
                contradiction_explanation=contradictions_text
            )

            llm_model = self.config.get("llm", {}).get("model_name", "meta/llama-3.1-70b-instruct")
            temperature = self.config.get("llm", {}).get("temperature", 0.0)

            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=llm_model,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=temperature
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Failed to generate disagreement explanation: {str(e)}")
            return f"Failed to generate analysis of conflict due to LLM error: {str(e)}"
