from prometheus_client import Counter, Histogram, Gauge, make_asgi_app
from fastapi import FastAPI

# 1. Declare Prometheus Metrics
# Total RAG requests count
rag_requests_total = Counter(
    name="rag_requests_total",
    documentation="Total number of RAG requests processed.",
    labelnames=["status", "intent_type"]
)

# Latency histograms per pipeline stage
rag_request_duration_seconds = Histogram(
    name="rag_request_duration_seconds",
    documentation="Latency of RAG pipeline stages in seconds.",
    labelnames=["stage"]
)

# Quality gate verdicts count
rag_gate_verdicts_total = Counter(
    name="rag_gate_verdicts_total",
    documentation="Verdict counts for preflight and verifier quality gates.",
    labelnames=["gate", "verdict"]
)

# Search similarity score distributions
rag_retrieval_scores = Histogram(
    name="rag_retrieval_scores",
    documentation="Distribution of retrieved chunk similarity scores."
)

# Model token consumption
rag_llm_tokens_used = Counter(
    name="rag_llm_tokens_used",
    documentation="Number of LLM prompt and completion tokens used.",
    labelnames=["prompt_name"]
)

# Semantic Cache hits/misses
rag_cache_hits_total = Counter(
    name="rag_cache_hits_total",
    documentation="Total semantic query cache hits."
)
rag_cache_misses_total = Counter(
    name="rag_cache_misses_total",
    documentation="Total semantic query cache misses."
)

# Request priority queue depth
rag_queue_depth = Gauge(
    name="rag_queue_depth",
    documentation="Current depth of requests queued for execution."
)

# LLM Client Circuit Breaker State (0 = CLOSED / HALF-OPEN, 1 = OPEN)
rag_circuit_breaker_state = Gauge(
    name="rag_circuit_breaker_state",
    documentation="Circuit breaker status (0=Closed/Half-Open, 1=Open)."
)


def mount_metrics_app(app: FastAPI) -> None:
    """Mounts the Prometheus metrics scraper as a FastAPI sub-application under `/metrics`.

    Args:
        app: The parent FastAPI application.
    """
    # Create the ASGI metrics exporter
    metrics_asgi_app = make_asgi_app()
    # Mount under /metrics path
    app.mount("/metrics", metrics_asgi_app)
