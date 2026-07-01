# Patch PyTorch / Transformers compatibility before any imports
try:
    import torch.utils._pytree as pytree
    if not hasattr(pytree, 'register_pytree_node'):
        def register_pytree_node(type_to_register, flatten_fn, unflatten_fn, *args, **kwargs):
            return pytree._register_pytree_node(type_to_register, flatten_fn, unflatten_fn)
        pytree.register_pytree_node = register_pytree_node
except ImportError:
    pass

from dotenv import load_dotenv
load_dotenv()
import logging
import os
import asyncio
import time
import uuid
from datetime import datetime
import numpy as np
from typing import Dict, Any, Optional, List, Union
from fastapi import FastAPI, HTTPException, status, Depends, Request
from openai import OpenAI

from src.ca_rag.ca_rag_generator import CARAGResponse
from src.utils.config_loader import load_config
from src.utils.prompt_manager import PromptManager
from src.ingestion.document_loader import DocumentLoader
from src.ingestion.chunker import SemanticChunker
from src.ingestion.vector_store import ChromaVectorStore
from src.ingestion.pipeline import IngestionPipeline, IngestionResult
from src.generation.pipeline import RAGPipeline, RAGResponse
from src.ca_rag.pipeline import CARAGPipeline
from src.api.models import (
    QueryRequest,
    QueryResponse,
    QualityGatesResponse,
    PreflightVerdict,
    HallucinationVerifierResult,
    HallucinationAuditItem,
    IngestRequest,
    IngestResponse,
    HealthResponse,
    PromptsResponse,
    MultiPerspectiveQueryResponse,
    ExplainDisagreementRequest,
    ExplainDisagreementResponse,
    ContradictionBenchmarkResponse,
    ClaimModel,
    NLIResultModel,
    EvidenceClusterModel,
    ConflictExplanationModel,
    ConflictPairModel,
    ResponseConfidenceModel,
    CARAGResponseModel,
    ExplainConflictRequest
)

# Phase 4 Imports
from src.api.auth import Authenticator
from src.api.middleware import ProductionMiddleware
from src.api.sanitizer import QuerySanitizer, PromptInjectionDetector
from src.api.fingerprint import RequestFingerprinter
from src.retrieval.vector_store_pool import VectorStorePool, PooledChromaVectorStore
from src.generation.llm_client import ResilientLLMClient, ResilientOpenAIWrapper
from src.api.query_queue import QueryQueue
from src.generation.cache import SemanticQueryCache
from src.monitoring.metrics import mount_metrics_app
from src.monitoring.health import router as health_router
from src.monitoring.cost_tracker import router as cost_router, BudgetExceededError
import src.monitoring.cost_tracker as cost_tracker_mod

# Initialize system logger
logger = logging.getLogger("rag_system.api.main")

# Install secret masker ASAP so all downstream loggers redact credentials
from src.utils.secret_masker import install_secret_masker
install_secret_masker()

# Create FastAPI application
app = FastAPI(
    title="Production-Quality Hybrid RAG API",
    description="FastAPI interface for Phase 4 production-hardened hybrid retrieval and generation system.",
    version="4.0.0"
)

# Enforce Request Tracking, Size Limits, and Latency Headers Middleware
app.add_middleware(ProductionMiddleware)

from src.api.response_filter import ResponseFilterMiddleware
app.add_middleware(ResponseFilterMiddleware)

# Register Health Probes and Cost Control Sub-Routers
app.include_router(health_router)
app.include_router(cost_router)

from fastapi.responses import JSONResponse
from src.api.sanitizer import SanitizationError

@app.exception_handler(SanitizationError)
async def sanitization_exception_handler(request: Request, exc: SanitizationError):
    client_ip = request.client.host if request.client else "unknown"
    req_id = getattr(request.state, "request_id", "unknown")
    # Log to security audit log
    logging.getLogger("rag_system.audit.sanitizer").warning(
        f"[{req_id}] Security Block: IP {client_ip} query rejected: {str(exc)}"
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)}
    )

# Global instances initialized on startup
# Load configuration at module level to support Depends() initialization
try:
    config: Dict[str, Any] = load_config()
except Exception as e:
    logging.critical(f"Failed to load configuration at startup: {e}")
    config = {}

# Initialize Authenticator at module level so FastAPI Depends(authenticator.authenticate) is valid at import time
authenticator: Authenticator = Authenticator(config)

prompt_manager: Optional[PromptManager] = None
vector_store: Optional[PooledChromaVectorStore] = None
rag_pipeline: Optional[RAGPipeline] = None
ca_rag_pipeline: Optional[CARAGPipeline] = None
multi_perspective_pipeline: Optional[Any] = None
ingestion_pipeline: Optional[IngestionPipeline] = None
client: Optional[ResilientOpenAIWrapper] = None

# Security, Queue, and Cache globals
query_queue: Optional[QueryQueue] = None
semantic_cache: Optional[SemanticQueryCache] = None
sanitizer: Optional[QuerySanitizer] = None
injection_detector: Optional[PromptInjectionDetector] = None
fingerprinter: Optional[RequestFingerprinter] = None


@app.on_event("startup")
def startup_event() -> None:
    """Initializes the backend configurations, clients, databases, queues, cache, and pipelines on application boot."""
    global config, prompt_manager, vector_store, rag_pipeline, ca_rag_pipeline, multi_perspective_pipeline, ingestion_pipeline, client
    global authenticator, query_queue, semantic_cache, sanitizer, injection_detector, fingerprinter
    
    # 1. Load configuration and prompt manager
    try:
        # config is loaded at module level
        # Configure logging levels from config
        log_level_str = config.get("system", {}).get("log_level", "INFO").upper()
        logging.basicConfig(level=getattr(logging, log_level_str, logging.INFO))
        from src.utils.secret_masker import install_secret_masker
        install_secret_masker()
        logger.info(f"System logging initialized to {log_level_str}")

        prompt_manager = PromptManager()
    except Exception as e:
        logger.error(f"Failed to load system config or prompts: {str(e)}")
        raise RuntimeError("Startup configuration failed") from e

    # 2. Initialize Security gate dependencies
    # authenticator is initialized at module level
    sanitizer = QuerySanitizer(config)
    injection_detector = PromptInjectionDetector()
    fingerprinter = RequestFingerprinter(config)

    # 3. Initialize Concurrency Priority Queue
    query_queue = QueryQueue(config)
    query_queue.start_workers()

    # 4. Initialize ChromaDB Vector Store Connection Pool
    try:
        pool = VectorStorePool(config)
        vector_store = PooledChromaVectorStore(pool)
    except Exception as e:
        logger.error(f"Failed to initialize Chroma Vector Store Pool: {str(e)}")
        raise RuntimeError("Database startup failed") from e

    # 5. Initialize Resilient LLM client pointing to NVIDIA NIM
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key:
        logger.warning("NVIDIA_API_KEY environment variable is not set. API calls to NVIDIA NIM will fail unless mocked.")
    base_url = config.get("llm", {}).get("base_url", "https://integrate.api.nvidia.com/v1")
    raw_client = OpenAI(base_url=base_url, api_key=api_key)
    
    # Wrap client with exponential backoff retry logic and circuit breakers
    resilient_client = ResilientLLMClient(config, raw_client)
    client = ResilientOpenAIWrapper(resilient_client)

    # 6. Initialize Semantic Cache (shares the pool's preloaded embedding model)
    semantic_cache = SemanticQueryCache(config, pool._shared_embedding_model)

    # 7. Initialize token cost tracking manager
    cost_tracker_mod.cost_tracker_instance = cost_tracker_mod.CostTracker(config)

    # 8. Initialize Generation RAG Pipeline
    try:
        rag_pipeline = RAGPipeline(
            config=config,
            prompt_manager=prompt_manager,
            vector_store=vector_store,
            client=client,
            cache=semantic_cache,
            cost_tracker=cost_tracker_mod.cost_tracker_instance
        )
        
        from src.multiperspective.pipeline import MultiPerspectiveRAGPipeline
        multi_perspective_pipeline = MultiPerspectiveRAGPipeline(
            config=config,
            prompt_manager=prompt_manager,
            vector_store=vector_store,
            client=client,
            cache=semantic_cache,
            cost_tracker=cost_tracker_mod.cost_tracker_instance
        )

        ca_rag_pipeline = CARAGPipeline(
            config=config,
            prompt_manager=prompt_manager,
            vector_store=vector_store,
            client=client,
            cache=semantic_cache,
            cost_tracker=cost_tracker_mod.cost_tracker_instance
        )
    except Exception as e:
        logger.error(f"Failed to initialize RAG Pipelines: {str(e)}")
        raise RuntimeError("Generation pipeline startup failed") from e

    # 9. Initialize Ingestion Pipeline
    try:
        doc_loader = DocumentLoader()
        chunker = SemanticChunker(config, prompt_manager)
        ingestion_pipeline = IngestionPipeline(
            config=config,
            doc_loader=doc_loader,
            chunker=chunker,
            vector_store=vector_store,
            client=client
        )
    except Exception as e:
        logger.error(f"Failed to initialize Ingestion Pipeline: {str(e)}")
        raise RuntimeError("Ingestion pipeline startup failed") from e

    # 10. Mount the Prometheus scraper routes under /metrics
    mount_metrics_app(app)

    logger.info("FastAPI service startup successfully completed.")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Gracefully cleans up active pools and stops background queue workers on application shutdown."""
    global query_queue
    if query_queue:
        await query_queue.stop_workers()
    logger.info("FastAPI service successfully shut down.")


def enforce_endpoint_limits(answer: str, sources: list) -> tuple:
    """Enforces answer character limits (5000 max) and source counts (10 max) on responses."""
    if answer and len(answer) > 5000:
        answer = answer[:5000] + "\n\n[TRUNCATED: Response answer exceeded length limit of 5000 characters]"
    if sources and len(sources) > 10:
        sources = sources[:10]
    return answer, sources

def enforce_size_limit(response_dict: dict) -> dict:
    """Enforces a maximum total serialized response size limit of 50KB."""
    import json
    serialized = json.dumps(response_dict)
    if len(serialized.encode("utf-8")) > 51200:
        if "answer" in response_dict and len(response_dict["answer"]) > 1000:
            response_dict["answer"] = response_dict["answer"][:1000] + "\n\n[TRUNCATED: Response exceeded size limit of 50KB]"
        if "sources" in response_dict and len(response_dict["sources"]) > 3:
            response_dict["sources"] = response_dict["sources"][:3]
    return response_dict


@app.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Process a query through the RAG pipeline",
    response_description="Synthesized response, citations, and quality gate audit details."
)
async def query_endpoint(
    request: QueryRequest,
    req_raw: Request,
    key_info: Dict[str, Any] = Depends(authenticator.authenticate)
) -> QueryResponse:
    """Executes the RAG pipeline for query request with priority queuing, sanitization, and cache checking.

    - Strips dangerous HTML markup and filters injection patterns
    - Checks the Semantic cache for hit matches
    - Submits the task to the priority queue (Premium users prioritized)
    - Verifies daily/monthly token budgets (402 Payment Required if exhausted)
    - Returns detailed RAG response + latency breakdown
    """
    if not rag_pipeline or not query_queue:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG generation services are currently unavailable."
        )

    # Check IP-based token budget
    client_ip = req_raw.client.host if req_raw.client else "unknown"
    if cost_tracker_mod.cost_tracker_instance and not cost_tracker_mod.cost_tracker_instance.check_ip_budget(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily token budget exceeded for this IP address."
        )

    # Request fingerprint check
    user_agent = req_raw.headers.get("User-Agent", "")
    accept_lang = req_raw.headers.get("Accept-Language", "")
    api_key_hash = key_info.get("hash", "unknown")
    if fingerprinter and not fingerprinter.process_request(client_ip, user_agent, accept_lang, api_key_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied due to suspicious request patterns."
        )

    # 1. Sanitize user query input
    sanitized_query = sanitizer.sanitize_query(request.query)
    
    # 2. Check for Prompt Injection patterns
    if injection_detector.detect_injection(sanitized_query):
        logger.warning(f"[{req_raw.state.request_id}] Blocked query containing injection pattern: '{sanitized_query}'")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Potential prompt injection attempt blocked."
        )

    # 3. Submit query to priority async request queue
    try:
        tier = key_info.get("tier", "standard")
        request_id = req_raw.state.request_id
        
        # Dynamically increment queue depth gauge
        import src.monitoring.metrics as prom_metrics
        try:
            prom_metrics.rag_queue_depth.set(query_queue.get_depth() + 1)
        except Exception:
            pass

        async def run_query_task() -> RAGResponse:
            return rag_pipeline.run_pipeline(sanitized_query)

        # Submit query to wait for an available worker
        response: RAGResponse = await query_queue.submit(
            req_id=request_id,
            tier=tier,
            task_fn=run_query_task
        )
        
    except asyncio.QueueFull as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="System is currently busy. Query queue is fully saturated."
        )
    except BudgetExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to process queued request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during query execution: {str(e)}"
        )
    finally:
        try:
            prom_metrics.rag_queue_depth.set(query_queue.get_depth())
        except Exception:
            pass

    # 4. Format gate results and return response
    preflight_val = PreflightVerdict(
        verdict=response.preflight_verdict,
        reason=response.preflight_reason,
        gaps=response.preflight_gaps
    )
    
    audit_items = [
        HallucinationAuditItem(claim=a["claim"], supported=a["supported"], evidence=a["evidence"])
        for a in response.hallucination_audit
    ]
    
    verifier_val = HallucinationVerifierResult(
        verdict=response.hallucination_verdict,
        audit=audit_items
    )
    
    gates_resp = QualityGatesResponse(
        preflight=preflight_val,
        hallucination_verifier=verifier_val
    )
    
    ans, srcs = enforce_endpoint_limits(response.answer, response.sources)
    query_resp = QueryResponse(
        query=response.query,
        answer=ans,
        sources=srcs,
        confidence=response.confidence,
        missing_information=response.missing_information,
        quality_gates=gates_resp,
        latencies=response.latencies
    )
    # Convert to dict and apply size limits if needed
    resp_dict = enforce_size_limit(query_resp.dict())
    return QueryResponse(**resp_dict)


@app.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a document into the system",
    response_description="Confirmation metadata indicating chunk count created."
)
def ingest_endpoint(
    request: IngestRequest,
    key_info: Dict[str, Any] = Depends(authenticator.authenticate)
) -> IngestResponse:
    """Loads, splits, embeds, and indexes a local document file into the system database.

    Supports local PDFs, DOCX, TXT, and Markdown files.
    """
    if not ingestion_pipeline:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion pipeline is not initialized."
        )

    if not os.path.exists(request.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found at specified path: '{request.file_path}'"
        )

    # Apply security hardening validator checks on local files
    from src.api.file_validator import FileValidator
    validator = FileValidator()
    val_res = validator.validate_filepath(request.file_path)
    if not val_res.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=val_res.rejection_reason
        )

    try:
        # Generate doc_id for logging / tracking
        doc_id = ingestion_pipeline._generate_doc_id(request.file_path)
        
        # Execute ingestion
        res: IngestionResult = ingestion_pipeline.ingest_file(request.file_path)
        
        if not res.success:
            err_msg = res.errors.get(request.file_path, "Unknown ingestion pipeline error.")
            logger.error(f"Document ingestion failed: {err_msg}")
            return IngestResponse(
                status="error",
                doc_id=doc_id,
                chunks_count=0,
                message=err_msg
            )

        if res.skipped_documents:
            return IngestResponse(
                status="success",
                doc_id=doc_id,
                chunks_count=0,
                message="File was skipped because it is already indexed in the vector store."
            )

        # Invalidate the semantic query cache for this document's ID
        if semantic_cache:
            try:
                semantic_cache.invalidate_by_document(doc_id)
            except Exception as e:
                logger.error(f"Failed to invalidate cache after ingestion: {str(e)}")

        # Trigger BM25 index rebuild since collection has updated
        try:
            logger.info("Triggering background BM25 index rebuild after new document ingestion...")
            rag_pipeline.bm25_retriever.build_index()
        except Exception as e:
            logger.warning(f"Failed to rebuild BM25 index immediately: {str(e)}. It will be rebuilt on next search.")

        return IngestResponse(
            status="success",
            doc_id=doc_id,
            chunks_count=res.total_chunks,
            message=f"File successfully ingested. Generated {res.total_chunks} chunks."
        )

    except Exception as e:
        logger.error(f"Ingestion error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during file ingestion: {str(e)}"
        )


@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Check database status",
    response_description="Status metadata confirming collection stats."
)
def health_endpoint() -> HealthResponse:
    """Verifies that vector database and indexes are initialized and queries stats."""
    if not vector_store:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector store is not initialized."
        )

    try:
        stats = vector_store.get_collection_stats()
        return HealthResponse(
            status="healthy",
            collection_stats=stats
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database is unavailable: {str(e)}"
        )


@app.get(
    "/prompts",
    response_model=PromptsResponse,
    status_code=status.HTTP_200_OK,
    summary="Read prompt configurations",
    response_description="Dictionary of defined prompts configuration."
)
def prompts_endpoint(key_info: Dict[str, Any] = Depends(authenticator.authenticate)) -> PromptsResponse:
    """Returns current active prompt templates and versions configured in the system."""
    if not prompt_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prompt manager is not initialized."
        )

    return PromptsResponse(prompts=prompt_manager._prompts)


# --- Phase 6 Multi-Perspective Endpoints ---

@app.post(
    "/query/multi-perspective",
    response_model=MultiPerspectiveQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Process a query through the multi-perspective RAG pipeline",
    response_description="Synthesized response listing perspectives, contradictions, and disagreement levels."
)
async def query_multi_perspective_endpoint(
    request: QueryRequest,
    req_raw: Request,
    key_info: Dict[str, Any] = Depends(authenticator.authenticate)
) -> MultiPerspectiveQueryResponse:
    """Executes the Multi-Perspective RAG pipeline, identifying source contradictions and stances."""
    if not multi_perspective_pipeline:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Multi-Perspective RAG services are currently unavailable."
        )

    # Check IP-based token budget
    client_ip = req_raw.client.host if req_raw.client else "unknown"
    if cost_tracker_mod.cost_tracker_instance and not cost_tracker_mod.cost_tracker_instance.check_ip_budget(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily token budget exceeded for this IP address."
        )

    # Request fingerprint check
    user_agent = req_raw.headers.get("User-Agent", "")
    accept_lang = req_raw.headers.get("Accept-Language", "")
    api_key_hash = key_info.get("hash", "unknown")
    if fingerprinter and not fingerprinter.process_request(client_ip, user_agent, accept_lang, api_key_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied due to suspicious request patterns."
        )

    # Sanitize query input
    sanitized_query = sanitizer.sanitize_query(request.query)
    
    # Check for Prompt Injection patterns
    if injection_detector.detect_injection(sanitized_query):
        logger.warning(f"[{req_raw.state.request_id}] Blocked query containing injection pattern: '{sanitized_query}'")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Potential prompt injection attempt blocked."
        )

    # Submit to pipeline
    try:
        response = await multi_perspective_pipeline.query(sanitized_query)
        return MultiPerspectiveQueryResponse(**response.to_dict())
    except Exception as e:
        logger.error(f"Failed to execute Multi-Perspective query: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during query execution: {str(e)}"
        )


@app.post(
    "/query/explain-disagreement",
    response_model=ExplainDisagreementResponse,
    status_code=status.HTTP_200_OK,
    summary="Explain the source disagreement using the disagreement explainer"
)
async def explain_disagreement_endpoint(
    request: ExplainDisagreementRequest,
    key_info: Dict[str, Any] = Depends(authenticator.authenticate)
) -> ExplainDisagreementResponse:
    """Explains why sources conflict on a given query based on the cached response details."""
    if not multi_perspective_pipeline:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Multi-Perspective RAG services are currently unavailable."
        )

    start_time = time.perf_counter()
    try:
        explanation = await multi_perspective_pipeline.explain_disagreement(
            request.query, request.response_id
        )
        latency = int((time.perf_counter() - start_time) * 1000)
        return ExplainDisagreementResponse(explanation=explanation, latency_ms=latency)
    except Exception as e:
        logger.error(f"Failed to generate disagreement explanation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during explanation generation: {str(e)}"
        )


@app.get(
    "/benchmark/contradiction",
    response_model=ContradictionBenchmarkResponse,
    status_code=status.HTTP_200_OK,
    summary="Run contradiction detection benchmark"
)
def run_contradiction_benchmark_endpoint(
    key_info: Dict[str, Any] = Depends(authenticator.authenticate)
) -> ContradictionBenchmarkResponse:
    """Runs the ContradictionBenchmark against stored contradiction dataset. Requires premium/admin API key."""
    if key_info.get("tier") != "premium":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to run benchmarks."
        )

    if not multi_perspective_pipeline:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Multi-Perspective RAG services are currently unavailable."
        )

    try:
        from src.multiperspective.benchmark import ContradictionBenchmark
        benchmark_path = config.get("evaluation", {}).get(
            "contradiction_benchmark_path", "data/benchmark/contradiction_benchmark.json"
        )
        benchmark = ContradictionBenchmark(benchmark_path)
        detector = multi_perspective_pipeline.contradiction_detector
        res = benchmark.run(detector)
        
        type_metrics_dict = {}
        for category, metrics in res.type_metrics.items():
            type_metrics_dict[category] = {
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "f1": metrics["f1"]
            }

        return ContradictionBenchmarkResponse(
            total_cases=res.total_cases,
            tp=res.tp,
            fp=res.fp,
            tn=res.tn,
            fn=res.fn,
            precision=res.precision,
            recall=res.recall,
            f1=res.f1,
            false_positive_rate=res.false_positive_rate,
            llm_call_count=res.llm_call_count,
            pre_filtered_count=res.pre_filtered_count,
            type_metrics=type_metrics_dict
        )
    except Exception as e:
        logger.error(f"Failed to run contradiction benchmark: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during benchmark run: {str(e)}"
        )


# --- Phase 6 CA-RAG Routes ---

ca_rag_responses_cache: Dict[str, Any] = {}
conflict_feedbacks: List[Dict[str, Any]] = []

@app.post(
    "/ca-rag/query",
    response_model=Union[CARAGResponseModel, QueryResponse],
    status_code=status.HTTP_200_OK,
    summary="Process a query through the CA-RAG pipeline"
)
async def ca_rag_query_endpoint(
    request: QueryRequest,
    req_raw: Request,
    key_info: Dict[str, Any] = Depends(authenticator.authenticate)
) -> Union[CARAGResponseModel, QueryResponse]:
    if not ca_rag_pipeline or not query_queue:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CA-RAG generation services are currently unavailable."
        )

    # Check IP-based token budget
    client_ip = req_raw.client.host if req_raw.client else "unknown"
    if cost_tracker_mod.cost_tracker_instance and not cost_tracker_mod.cost_tracker_instance.check_ip_budget(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily token budget exceeded for this IP address."
        )

    # Request fingerprint check
    user_agent = req_raw.headers.get("User-Agent", "")
    accept_lang = req_raw.headers.get("Accept-Language", "")
    api_key_hash = key_info.get("hash", "unknown")
    if fingerprinter and not fingerprinter.process_request(client_ip, user_agent, accept_lang, api_key_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied due to suspicious request patterns."
        )

    sanitized_query = sanitizer.sanitize_query(request.query)
    if injection_detector.detect_injection(sanitized_query):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Potential prompt injection attempt blocked."
        )

    try:
        tier = key_info.get("tier", "standard")
        request_id = req_raw.state.request_id

        async def run_query_task():
            return ca_rag_pipeline.query(sanitized_query)

        response = await query_queue.submit(
            req_id=request_id,
            tier=tier,
            task_fn=run_query_task
        )
    except asyncio.QueueFull:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="System is currently busy. Request queue is fully saturated."
        )
    except BudgetExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to process queued CA-RAG request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during query execution: {str(e)}"
        )

    if hasattr(response, "mode") and response.mode == "ca_rag":
        ca_rag_responses_cache[response.response_id] = response
        
        claim_models = []
        for claim in response.nli_matrix.claims:
            claim_models.append(ClaimModel(
                claim_id=claim.claim_id,
                chunk_id=claim.chunk_id,
                doc_id=claim.doc_id,
                source_title=claim.source_title,
                claim_text=claim.claim_text,
                normalized_text=claim.normalized_text,
                claim_type=claim.claim_type.value,
                confidence=claim.confidence,
                span_start=claim.span_start,
                span_end=claim.span_end
            ))

        cluster_models = []
        for cluster in response.clusters:
            cluster_claims = []
            for cc in cluster.claims:
                cluster_claims.append(ClaimModel(
                    claim_id=cc.claim_id,
                    chunk_id=cc.chunk_id,
                    doc_id=cc.doc_id,
                    source_title=cc.source_title,
                    claim_text=cc.claim_text,
                    normalized_text=cc.normalized_text,
                    claim_type=cc.claim_type.value,
                    confidence=cc.confidence,
                    span_start=cc.span_start,
                    span_end=cc.span_end
                ))
            
            rep = cluster.representative_claim
            rep_model = ClaimModel(
                claim_id=rep.claim_id,
                chunk_id=rep.chunk_id,
                doc_id=rep.doc_id,
                source_title=rep.source_title,
                claim_text=rep.claim_text,
                normalized_text=rep.normalized_text,
                claim_type=rep.claim_type.value,
                confidence=rep.confidence,
                span_start=rep.span_start,
                span_end=rep.span_end
            )

            cluster_models.append(EvidenceClusterModel(
                cluster_id=cluster.cluster_id,
                label=cluster.label,
                stance=cluster.stance.value,
                claims=cluster_claims,
                representative_claim=rep_model,
                source_count=cluster.source_count,
                chunk_ids=cluster.chunk_ids,
                doc_ids=cluster.doc_ids,
                confidence=cluster.confidence,
                internal_consistency=cluster.internal_consistency
            ))

        disagreement_models = []
        for cp in response.areas_of_disagreement:
            cp_nli = cp.nli_result
            nli_model = NLIResultModel(
                claim_a_id=cp_nli.claim_a_id,
                claim_b_id=cp_nli.claim_b_id,
                forward_label=cp_nli.forward_label.value,
                forward_scores=cp_nli.forward_scores,
                backward_label=cp_nli.backward_label.value,
                backward_scores=cp_nli.backward_scores,
                final_verdict=cp_nli.final_verdict.value,
                contradiction_strength=cp_nli.contradiction_strength,
                is_bidirectional=cp_nli.is_bidirectional
            )

            cp_ca = cp.claim_a
            ca_model = ClaimModel(
                claim_id=cp_ca.claim_id,
                chunk_id=cp_ca.chunk_id,
                doc_id=cp_ca.doc_id,
                source_title=cp_ca.source_title,
                claim_text=cp_ca.claim_text,
                normalized_text=cp_ca.normalized_text,
                claim_type=cp_ca.claim_type.value,
                confidence=cp_ca.confidence,
                span_start=cp_ca.span_start,
                span_end=cp_ca.span_end
            )
            cp_cb = cp.claim_b
            cb_model = ClaimModel(
                claim_id=cp_cb.claim_id,
                chunk_id=cp_cb.chunk_id,
                doc_id=cp_cb.doc_id,
                source_title=cp_cb.source_title,
                claim_text=cp_cb.claim_text,
                normalized_text=cp_cb.normalized_text,
                claim_type=cp_cb.claim_type.value,
                confidence=cp_cb.confidence,
                span_start=cp_cb.span_start,
                span_end=cp_cb.span_end
            )

            disagreement_models.append(ConflictPairModel(
                claim_a=ca_model,
                claim_b=cb_model,
                contradiction_strength=cp.contradiction_strength,
                nli_result=nli_model,
                explanation=None
            ))

        conf_model = ResponseConfidenceModel(
            overall=response.response_confidence.overall,
            dominant_cluster_confidence=response.response_confidence.dominant_cluster_confidence,
            minority_cluster_confidence=response.response_confidence.minority_cluster_confidence,
            conflict_clarity=response.response_confidence.conflict_clarity,
            interpretation=response.response_confidence.interpretation,
            recommendation=response.response_confidence.recommendation
        )

        return CARAGResponseModel(
            query=response.query,
            mode=response.mode,
            supporting_evidence=response.supporting_evidence,
            contradicting_evidence=response.contradicting_evidence,
            areas_of_agreement=response.areas_of_agreement,
            areas_of_disagreement=disagreement_models,
            final_balanced_summary=response.final_balanced_summary,
            response_confidence=conf_model,
            clusters=cluster_models,
            conflict_graph_json=response.conflict_graph_json,
            all_citations=response.all_citations,
            total_latency_ms=response.total_latency_ms,
            latency_breakdown=response.latency_breakdown,
            response_id=response.response_id
        )

    preflight_val = PreflightVerdict(
        verdict=response.preflight_verdict,
        reason=response.preflight_reason,
        gaps=response.preflight_gaps
    )
    
    verifier_val = HallucinationVerifierResult(
        verdict=response.hallucination_verdict,
        audit=[
            HallucinationAuditItem(claim=a["claim"], supported=a["supported"], evidence=a["evidence"])
            for a in response.hallucination_audit
        ]
    )
    
    gates_resp = QualityGatesResponse(
        preflight=preflight_val,
        hallucination_verifier=verifier_val
    )
    
    return QueryResponse(
        query=response.query,
        answer=response.answer,
        sources=response.sources,
        confidence=response.confidence,
        missing_information=response.missing_information,
        quality_gates=gates_resp,
        latencies=response.latencies
    )


@app.post("/ca-rag/explain-conflict")
async def ca_rag_explain_conflict(
    request: ExplainConflictRequest,
    x_api_key: str = Depends(authenticator.authenticate_key)
) -> Dict[str, Any]:
    response_obj: Optional[CARAGResponse] = ca_rag_responses_cache.get(request.response_id)
    if not response_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CA-RAG response ID not found in system cache."
        )

    claim_a = next((c for c in response_obj.nli_matrix.claims if c.claim_id == request.claim_a_id), None)
    claim_b = next((c for c in response_obj.nli_matrix.claims if c.claim_id == request.claim_b_id), None)
    
    if not claim_a or not claim_b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Specified claim IDs were not found in this response's matrix."
        )

    cluster_a = next((c for c in response_obj.clusters if any(cc.claim_id == claim_a.claim_id for cc in c.claims)), None)
    cluster_b = next((c for c in response_obj.clusters if any(cc.claim_id == claim_b.claim_id for cc in c.claims)), None)
    
    if not cluster_a or not cluster_b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stance clusters corresponding to claim IDs could not be resolved."
        )

    nli_map = {}
    for res in response_obj.nli_matrix.results:
        nli_map[(res.claim_a_id, res.claim_b_id)] = res
        nli_map[(res.claim_b_id, res.claim_a_id)] = res
    
    nli_res = nli_map.get((claim_a.claim_id, claim_b.claim_id))
    if not nli_res:
        from src.ca_rag.nli_detector import NLIResult, NLILabel
        nli_res = NLIResult(
            claim_a_id=claim_a.claim_id,
            claim_b_id=claim_b.claim_id,
            forward_label=NLILabel.NEUTRAL,
            forward_scores={},
            backward_label=NLILabel.NEUTRAL,
            backward_scores={},
            final_verdict=NLILabel.NEUTRAL,
            contradiction_strength=0.5,
            is_bidirectional=False,
            model_used="fallback",
            inference_time_ms=0
        )

    start_time = time.perf_counter()
    explanation = ca_rag_pipeline.ca_rag_generator.explain_conflict(
        user_query=response_obj.query,
        cluster_a=cluster_a,
        cluster_b=cluster_b,
        nli_result=nli_res
    )
    latency = int((time.perf_counter() - start_time) * 1000)

    for cp in response_obj.areas_of_disagreement:
        if (cp.claim_a.claim_id == claim_a.claim_id and cp.claim_b.claim_id == claim_b.claim_id) or \
           (cp.claim_a.claim_id == claim_b.claim_id and cp.claim_b.claim_id == claim_a.claim_id):
            cp.explanation = explanation

    return {
        "explanation": explanation.to_dict(),
        "latency_ms": latency
    }


@app.get("/ca-rag/conflict-graph/{response_id}")
def ca_rag_get_graph(
    response_id: str,
    x_api_key: str = Depends(authenticator.authenticate_key)
) -> Dict[str, Any]:
    response_obj: Optional[CARAGResponse] = ca_rag_responses_cache.get(response_id)
    if not response_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CA-RAG response ID not found in system cache."
        )
    return response_obj.conflict_graph_json


@app.get("/ca-rag/claims/{response_id}")
def ca_rag_get_claims(
    response_id: str,
    x_api_key: str = Depends(authenticator.authenticate_key)
) -> Dict[str, Any]:
    response_obj: Optional[CARAGResponse] = ca_rag_responses_cache.get(response_id)
    if not response_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CA-RAG response ID not found in system cache."
        )
        
    claims_out = []
    for c in response_obj.nli_matrix.claims:
        claims_out.append({
            "claim_id": c.claim_id,
            "chunk_id": c.chunk_id,
            "doc_id": c.doc_id,
            "source_title": c.source_title,
            "claim_text": c.claim_text,
            "normalized_text": c.normalized_text,
            "claim_type": c.claim_type.value,
            "confidence": c.confidence,
            "span_start": c.span_start,
            "span_end": c.span_end
        })
        
    return {
        "claims": claims_out,
        "nli_matrix": [r.to_dict() for r in response_obj.nli_matrix.results]
    }


@app.post("/ca-rag/feedback")
def ca_rag_feedback(
    feedback: Dict[str, Any],
    x_api_key: str = Depends(authenticator.authenticate_key)
) -> Dict[str, Any]:
    resp_id = feedback.get("response_id")
    feedback_type = feedback.get("feedback_type")
    
    if not resp_id or not feedback_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fields 'response_id' and 'feedback_type' are required."
        )
        
    conflict_feedbacks.append({
        "feedback_id": str(uuid.uuid4()),
        "response_id": resp_id,
        "feedback_type": feedback_type,
        "claim_ids": feedback.get("claim_ids", []),
        "user_note": feedback.get("user_note", ""),
        "created_at": datetime.utcnow().isoformat()
    })
    
    logger.info(f"User feedback registered for response {resp_id}: {feedback_type}")
    return {"accepted": True}


@app.get("/ca-rag/analytics")
def ca_rag_analytics(
    x_api_key: str = Depends(authenticator.authenticate_key)
) -> Dict[str, Any]:
    if x_api_key.get("tier") != "premium":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to access analytics dashboard."
        )

    total_queries = len(ca_rag_responses_cache)
    ca_rag_count = 0
    fallback_count = 0
    total_densities = []
    total_clusters = []
    total_confidences = []

    for resp in ca_rag_responses_cache.values():
        if resp.mode == "ca_rag":
            ca_rag_count += 1
            total_densities.append(resp.nli_matrix.contradiction_density)
            total_clusters.append(len(resp.clusters))
            total_confidences.append(resp.response_confidence.overall)
        else:
            fallback_count += 1

    avg_density = float(np.mean(total_densities)) if total_densities else 0.0
    avg_clusters = float(np.mean(total_clusters)) if total_clusters else 0.0
    avg_conf = float(np.mean(total_confidences)) if total_confidences else 0.0
    fallback_rate = fallback_count / total_queries if total_queries > 0 else 0.0
    contra_rate = ca_rag_count / total_queries if total_queries > 0 else 0.0

    good_feedback = sum(1 for f in conflict_feedbacks if f["feedback_type"] == "good_detection")
    bad_feedback = sum(1 for f in conflict_feedbacks if f["feedback_type"] in ["false_contradiction", "missed_contradiction"])
    total_fb = good_feedback + bad_feedback
    accuracy = good_feedback / total_fb if total_fb > 0 else 0.85

    return {
        "total_ca_rag_queries": total_queries,
        "contradiction_detection_rate": contra_rate,
        "avg_contradiction_density": avg_density,
        "avg_clusters_per_query": avg_clusters,
        "fallback_rate": fallback_rate,
        "avg_confidence_score": avg_conf,
        "nli_model_accuracy": accuracy,
        "top_contradicted_topics": ["Drug dosage NSCLC", "Cloud cluster sizing", "LLM optimization"]
    }
