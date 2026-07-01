import os
import logging
import time
from typing import Dict, Any, Optional
from fastapi import APIRouter, status, Response, HTTPException
import redis

# Access shared services
router = APIRouter(prefix="/health", tags=["Monitoring & Diagnostics"])
logger = logging.getLogger("rag_system.monitoring.health")


@router.get(
    "/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness probe confirming application process is running."
)
def liveness_check() -> Dict[str, str]:
    """Fast liveness check confirming the process is alive. Returns 200 OK."""
    return {"status": "alive"}


@router.get(
    "/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness probe validating external service connections."
)
def readiness_check(response: Response) -> Dict[str, Any]:
    """Validates connectivity to ChromaDB, embedding models loading, and LLM circuit health."""
    from src.api.main import vector_store, rag_pipeline
    
    degraded = False
    details = {}

    # 1. Check Chroma Vector DB
    if not vector_store:
        degraded = True
        details["chromadb"] = "Offline: Not initialized."
    else:
        try:
            vector_store._ensure_initialized()
            stats = vector_store.get_collection_stats()
            details["chromadb"] = f"Connected. count: {stats.get('count', 0)}"
        except Exception as e:
            degraded = True
            details["chromadb"] = f"Offline: {str(e)}"

    # 2. Check Embedding Model loaded
    if not vector_store or not vector_store.embedding_model:
        degraded = True
        details["embedding_model"] = "Missing: Model not loaded."
    else:
        details["embedding_model"] = f"Loaded. Model name: {vector_store.embedding_model_name}"

    # 3. Check LLM Circuit Breaker status
    if not rag_pipeline or not rag_pipeline.client:
        degraded = True
        details["llm_api"] = "Offline: Client not configured."
    else:
        # Check ResilientLLMClient circuit breaker state
        # In main.py, we will wrap the client with ResilientLLMClient.
        # Let's check its state.
        llm_client = getattr(rag_pipeline, "resilient_llm_client", None)
        if llm_client:
            state = llm_client.state
            if state == "OPEN":
                degraded = True
                details["llm_api"] = f"Circuit Breaker is OPEN."
            else:
                details["llm_api"] = f"Healthy (Circuit: {state})"
        else:
            details["llm_api"] = "Healthy"

    if degraded:
        logger.warning(f"Readiness probe failed degraded states: {details}")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "checks": details}

    return {"status": "ready", "checks": details}


@router.get(
    "/detailed",
    status_code=status.HTTP_200_OK,
    summary="Detailed diagnostic dashboard of all component states and queues."
)
def detailed_diagnostics() -> Dict[str, Any]:
    """Retrieves full diagnostic details of active queues, cache states, and circuits."""
    from src.api.main import (
        config,
        vector_store,
        rag_pipeline,
        query_queue,
        semantic_cache
    )

    import torch
    gpu_status = {
        "available": torch.cuda.is_available(),
        "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU only",
        "vram_total_mb": round(
            torch.cuda.get_device_properties(0).total_memory 
            / 1024 / 1024
        ) if torch.cuda.is_available() else 0,
        "vram_used_mb": round(
            torch.cuda.memory_allocated(0) / 1024 / 1024
        ) if torch.cuda.is_available() else 0,
    }

    details = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "healthy",
        "components": {},
        "gpu": gpu_status,
        "cache": {},
        "queue": {},
        "circuit_breaker": {}
    }

    degraded = False

    # 1. ChromaDB status
    try:
        vector_store._ensure_initialized()
        stats = vector_store.get_collection_stats()
        details["components"]["chromadb"] = {
            "status": "connected",
            "stats": stats
        }
    except Exception as e:
        degraded = True
        details["components"]["chromadb"] = {
            "status": "offline",
            "error": str(e)
        }

    # 2. Redis status
    redis_enabled = config.get("redis", {}).get("enabled", True)
    if redis_enabled:
        try:
            r_client = redis.Redis.from_url(config.get("redis", {}).get("url", os.getenv("REDIS_URL", "redis://localhost:6379/0")), socket_timeout=0.5)
            r_client.ping()
            details["components"]["redis"] = "connected"
        except Exception as e:
            details["components"]["redis"] = f"offline: {str(e)}"
    else:
        details["components"]["redis"] = "disabled"

    # 3. LLM Client Circuit
    if rag_pipeline:
        llm_client = getattr(rag_pipeline, "resilient_llm_client", None)
        if llm_client:
            details["circuit_breaker"] = {
                "state": llm_client.state,
                "consecutive_failures": llm_client.consecutive_failures
            }
            if llm_client.state == "OPEN":
                degraded = True
        else:
            details["circuit_breaker"] = "not_available"

    # 4. Semantic Cache
    if semantic_cache:
        total = semantic_cache.hits + semantic_cache.misses
        hit_rate = (semantic_cache.hits / total) if total > 0 else 0.0
        details["cache"] = {
            "hits": semantic_cache.hits,
            "misses": semantic_cache.misses,
            "hit_rate": f"{hit_rate * 100:.2f}%",
            "active_entries_count": len(semantic_cache._memory_cache)
        }

    # 5. Priority Queue
    if query_queue:
        details["queue"] = {
            "depth": query_queue.get_depth(),
            "limit": query_queue.depth_limit,
            "concurrency_limit": query_queue.concurrency_limit
        }

    if degraded:
        details["status"] = "degraded"

    return details
