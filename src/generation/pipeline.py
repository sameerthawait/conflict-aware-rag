import time
import os
import logging
from typing import Dict, List, Any, Tuple, Optional
from openai import OpenAI

from src.ingestion.vector_store import SearchResult, ChromaVectorStore
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.query_expander import QueryExpander, ExpandedQuery
from src.retrieval.fusion import ReciprocalRankFusion
from src.retrieval.reranker import Reranker
from src.retrieval.hybrid_retriever import HybridRetriever
from src.generation.citation_gate import CitationPreflightGate, CitationPreflightResult
from src.generation.generator import Generator, GenerationResponse
from src.generation.hallucination_verifier import HallucinationVerifier, HallucinationVerifierResult
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.generation.pipeline")


class PipelineError(Exception):
    """Raised when RAG pipeline coordination fails."""
    pass


class RAGResponse:
    """Structure encapsulating the output of the full RAG pipeline."""

    def __init__(
        self,
        query: str,
        answer: str,
        sources: List[str],
        confidence: str,
        missing_information: str,
        preflight_verdict: str,
        preflight_reason: str,
        preflight_gaps: List[str],
        hallucination_verdict: Optional[str],
        hallucination_audit: List[Dict[str, Any]],
        latencies: Dict[str, float]
    ) -> None:
        """Initializes the RAGResponse.

        Args:
            query: The original user query.
            answer: Generated text response.
            sources: List of citation sources.
            confidence: Confidence classification (High/Medium/Low).
            missing_information: Details of missing search facts.
            preflight_verdict: Evaluation verdict (SUFFICIENT/PARTIAL/INSUFFICIENT).
            preflight_reason: Preflight rationale.
            preflight_gaps: List of gaps identified.
            hallucination_verdict: Verdict (PASS/FAIL/None).
            hallucination_audit: Detailed claim audit items.
            latencies: Breakdown of latencies (ms) per pipeline phase.
        """
        self.query = query
        self.answer = answer
        self.sources = sources
        self.confidence = confidence
        self.missing_information = missing_information
        self.preflight_verdict = preflight_verdict
        self.preflight_reason = preflight_reason
        self.preflight_gaps = preflight_gaps
        self.hallucination_verdict = hallucination_verdict
        self.hallucination_audit = hallucination_audit
        self.latencies = latencies

    def to_dict(self) -> Dict[str, Any]:
        """Converts the response to a dictionary representation."""
        return {
            "query": self.query,
            "answer": self.answer,
            "sources": self.sources,
            "confidence": self.confidence,
            "missing_information": self.missing_information,
            "quality_gates": {
                "preflight": {
                    "verdict": self.preflight_verdict,
                    "reason": self.preflight_reason,
                    "gaps": self.preflight_gaps
                },
                "hallucination_verifier": {
                    "verdict": self.hallucination_verdict,
                    "audit": self.hallucination_audit
                }
            },
            "latencies": self.latencies
        }


class RAGPipeline:
    """End-to-end RAG Pipeline orchestrating query intent routing, retrieval, preflight gating, generation, and verification."""

    def __init__(
        self,
        config: Dict[str, Any],
        prompt_manager: PromptManager,
        vector_store: ChromaVectorStore,
        client: Optional[OpenAI] = None,
        cache: Optional[Any] = None,
        cost_tracker: Optional[Any] = None
    ) -> None:
        """Initializes the RAGPipeline components.

        Args:
            config: System configuration dictionary.
            prompt_manager: PromptManager instance.
            vector_store: Initialized ChromaVectorStore.
            client: Optional pre-configured OpenAI API client.
            cache: Optional semantic cache cache.
            cost_tracker: Optional token cost tracker.
        """
        self.config = config
        self.prompt_manager = prompt_manager
        self.vector_store = vector_store
        self.cache = cache
        self.cost_tracker = cost_tracker
        
        # Instantiate OpenAI compatible LLM client pointing to NVIDIA NIM
        if client is not None:
            self.client = client
        else:
            api_key = os.environ.get("NVIDIA_API_KEY", "")
            base_url = config.get("llm", {}).get("base_url", "https://integrate.api.nvidia.com/v1")
            self.client = OpenAI(base_url=base_url, api_key=api_key)

        # Initialize sub-components
        self.bm25_retriever = BM25Retriever(config, vector_store)
        self.query_expander = QueryExpander(config, prompt_manager, self.client)
        self.fusion = ReciprocalRankFusion(config)
        self.reranker = Reranker(config, prompt_manager, self.client)
        
        self.hybrid_retriever = HybridRetriever(
            config=config,
            query_expander=self.query_expander,
            vector_store=self.vector_store,
            bm25_retriever=self.bm25_retriever,
            fusion=self.fusion,
            reranker=self.reranker
        )

        self.preflight_gate = CitationPreflightGate(config, prompt_manager, self.client)
        self.generator = Generator(config, prompt_manager, self.client)
        self.verifier = HallucinationVerifier(config, prompt_manager, self.client)

    def run_pipeline(self, query: str) -> RAGResponse:
        """Runs the entire RAG pipeline from query to verified answer.

        Args:
            query: The user search query.

        Returns:
            A RAGResponse containing answer, citations, quality scores, and latency stats.

        Raises:
            PipelineError: If any coordinate stage raises an unhandled error.
        """
        pipeline_start = time.perf_counter()
        latencies: Dict[str, float] = {}

        logger.info(f"Pipeline started for query: '{query}'")

        # 1. Try Semantic Cache first
        if self.cache:
            try:
                cached_val = self.cache.get(query)
                if cached_val:
                    # Update cache hits metric
                    import src.monitoring.metrics as prom_metrics
                    try:
                        prom_metrics.rag_cache_hits_total.inc()
                        prom_metrics.rag_requests_total.labels(status="success", intent_type="cached").inc()
                    except Exception:
                        pass

                    # Reconstruct RAGResponse from cached dictionary
                    q_gates = cached_val.get("quality_gates", {})
                    preflight = q_gates.get("preflight", {})
                    verifier = q_gates.get("hallucination_verifier", {})
                    
                    cached_res = RAGResponse(
                        query=cached_val["query"],
                        answer=cached_val["answer"],
                        sources=cached_val["sources"],
                        confidence=cached_val["confidence"],
                        missing_information=cached_val["missing_information"],
                        preflight_verdict=preflight.get("verdict", "SUFFICIENT"),
                        preflight_reason=preflight.get("reason", ""),
                        preflight_gaps=preflight.get("gaps", []),
                        hallucination_verdict=verifier.get("verdict", "PASS"),
                        hallucination_audit=verifier.get("audit", []),
                        latencies=cached_val["latencies"]
                    )
                    logger.info("RAG Response successfully fetched from Semantic Cache.")
                    return cached_res
            except Exception as e:
                logger.error(f"Semantic Cache retrieval failed: {str(e)}")

        # Increment Cache Misses
        if self.cache:
            try:
                import src.monitoring.metrics as prom_metrics
                prom_metrics.rag_cache_misses_total.inc()
            except Exception:
                pass

        # 2. Verify Token Budgets before invoking LLM
        from src.api.auth import current_key_info, current_request_id
        key_info = current_key_info.get()
        req_id = current_request_id.get()

        if key_info and self.cost_tracker:
            # Raises BudgetExceededError if daily/monthly budgets are exhausted
            self.cost_tracker.verify_budget(key_info["hash"], key_info["name"])

        try:
            # 1. Expand Query to retrieve Intent (cached and fast)
            exp_start = time.perf_counter()
            expanded_query: ExpandedQuery = self.query_expander.expand_query(query)
            expansion_ms = (time.perf_counter() - exp_start) * 1000
            latencies["expansion_ms"] = expansion_ms
            
            # Observe latency in Prometheus
            import src.monitoring.metrics as prom_metrics
            try:
                prom_metrics.rag_request_duration_seconds.labels(stage="expansion").observe(expansion_ms / 1000.0)
            except Exception:
                pass

            # 2. General Conversation Route (Bypass Retrieval & Gates)
            if expanded_query.intent == "GENERAL_CONVERSATION":
                logger.info("Routing query to direct generator chat (general conversation intent).")
                
                gen_start = time.perf_counter()
                llm_model = self.config.get("llm", {}).get("model_name", "meta/llama-3.1-70b-instruct")
                temperature = self.config.get("llm", {}).get("temperature", 0.0)
                max_tokens = self.config.get("llm", {}).get("max_tokens_to_sample", 1024)

                response = self.client.chat.completions.create(
                    model=llm_model,
                    messages=[
                        {"role": "system", "content": "You are a helpful and polite conversational assistant."},
                        {"role": "user", "content": query}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                answer_text = (response.choices[0].message.content or "").strip()
                generation_ms = (time.perf_counter() - gen_start) * 1000
                latencies["generation_ms"] = generation_ms
                
                total_ms = (time.perf_counter() - pipeline_start) * 1000
                latencies["total_pipeline_ms"] = total_ms

                try:
                    prom_metrics.rag_request_duration_seconds.labels(stage="generation").observe(generation_ms / 1000.0)
                    prom_metrics.rag_request_duration_seconds.labels(stage="total").observe(total_ms / 1000.0)
                    prom_metrics.rag_requests_total.labels(status="success", intent_type="conversational").inc()
                except Exception:
                    pass

                return RAGResponse(
                    query=query,
                    answer=answer_text,
                    sources=[],
                    confidence="High",
                    missing_information="None",
                    preflight_verdict="SUFFICIENT",
                    preflight_reason="Direct generation. Bypassed document retrieval.",
                    preflight_gaps=[],
                    hallucination_verdict="PASS",
                    hallucination_audit=[],
                    latencies=latencies
                )

            # 3. RAG Required Route
            # 3a. Retrieve context
            results, retrieval_latencies = self.hybrid_retriever.retrieve(query)
            latencies.update(retrieval_latencies)

            try:
                # Observe scores and retrieve latencies
                retrieval_ms = retrieval_latencies.get("total_retrieval_ms", 0.0)
                prom_metrics.rag_request_duration_seconds.labels(stage="retrieval").observe(retrieval_ms / 1000.0)
                for res in results:
                    prom_metrics.rag_retrieval_scores.observe(res.score)
            except Exception:
                pass

            # 3b. Evaluate citation sufficiency gate
            preflight_start = time.perf_counter()
            preflight_res: CitationPreflightResult = self.preflight_gate.evaluate(query, results)
            preflight_ms = (time.perf_counter() - preflight_start) * 1000
            latencies["preflight_evaluation_ms"] = preflight_ms

            try:
                prom_metrics.rag_request_duration_seconds.labels(stage="preflight").observe(preflight_ms / 1000.0)
                prom_metrics.rag_gate_verdicts_total.labels(gate="preflight", verdict=preflight_res.verdict).inc()
            except Exception:
                pass

            # If preflight blocks progression
            if not preflight_res.proceed:
                refusal_msg = self.config.get("quality_gates", {}).get(
                    "refusal_message",
                    "I am sorry, but I could not find any relevant information in the provided context to answer your query."
                )
                total_ms = (time.perf_counter() - pipeline_start) * 1000
                latencies["total_pipeline_ms"] = total_ms
                logger.warning(f"Citation preflight BLOCKED generation. Verdict: '{preflight_res.verdict}'. Reason: {preflight_res.reason}")

                try:
                    prom_metrics.rag_request_duration_seconds.labels(stage="total").observe(total_ms / 1000.0)
                    prom_metrics.rag_requests_total.labels(status="success", intent_type="refusal").inc()
                except Exception:
                    pass

                return RAGResponse(
                    query=query,
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

            # 3c. Generate structured answer
            gen_response, gen_latency_ms = self.generator.generate(query, results)
            latencies["generation_ms"] = gen_latency_ms

            try:
                prom_metrics.rag_request_duration_seconds.labels(stage="generation").observe(gen_latency_ms / 1000.0)
            except Exception:
                pass

            # 3d. Audit facts via Anti-Hallucination Verifier
            verify_start = time.perf_counter()
            verifier_res, verify_latency_ms = self.verifier.verify(gen_response.answer, results)
            latencies["hallucination_verification_ms"] = verify_latency_ms

            total_ms = (time.perf_counter() - pipeline_start) * 1000
            latencies["total_pipeline_ms"] = total_ms
            logger.info(f"Pipeline executed successfully in {latencies['total_pipeline_ms']:.2f}ms.")

            try:
                prom_metrics.rag_request_duration_seconds.labels(stage="verification").observe(verify_latency_ms / 1000.0)
                prom_metrics.rag_gate_verdicts_total.labels(
                    gate="hallucination_verifier", 
                    verdict=verifier_res.verdict if verifier_res else "PASS"
                ).inc()
                prom_metrics.rag_request_duration_seconds.labels(stage="total").observe(total_ms / 1000.0)
                prom_metrics.rag_requests_total.labels(status="success", intent_type="rag").inc()
            except Exception:
                pass

            audit_list = []
            if verifier_res:
                for audit in verifier_res.claims_audit:
                    audit_list.append({
                        "claim": audit.claim,
                        "supported": audit.supported,
                        "evidence": audit.evidence
                    })

            rag_response_obj = RAGResponse(
                query=query,
                answer=gen_response.answer,
                sources=gen_response.sources_used,
                confidence=gen_response.confidence,
                missing_information=gen_response.missing_information,
                preflight_verdict=preflight_res.verdict,
                preflight_reason=preflight_res.reason,
                preflight_gaps=preflight_res.gaps,
                hallucination_verdict=verifier_res.verdict if verifier_res else "PASS",
                hallucination_audit=audit_list,
                latencies=latencies
            )

            # Store computed response in cache
            if self.cache:
                try:
                    # Extract document ids referenced in search result metadata
                    doc_ids = list(set(res.metadata.get("doc_id", "") for res in results if res.metadata.get("doc_id")))
                    self.cache.put(query, rag_response_obj.to_dict(), doc_ids)
                except Exception as e:
                    logger.error(f"Failed to cache generated response: {str(e)}")

            return rag_response_obj

        except Exception as e:
            try:
                import src.monitoring.metrics as prom_metrics
                prom_metrics.rag_requests_total.labels(status="error", intent_type="rag").inc()
            except Exception:
                pass
            error_msg = f"RAG Pipeline execution failed: {str(e)}"
            logger.error(error_msg)
            raise PipelineError(error_msg) from e
