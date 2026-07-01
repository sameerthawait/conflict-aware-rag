import uuid
import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Initialize structured logger
logger = logging.getLogger("rag_system.api.middleware")
audit_logger = logging.getLogger("rag_system.audit.security")


class ProductionMiddleware(BaseHTTPMiddleware):
    """Enforces request tracking IDs, size limits, security headers, and latency tracking."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Request ID Injection
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # 2. Enforce Request Size Limit (Reject payloads > 10KB)
        # 10KB = 10240 bytes
        max_payload_size = 10240
        content_length = request.headers.get("content-length")

        if content_length:
            try:
                size_bytes = int(content_length)
                if size_bytes > max_payload_size:
                    audit_logger.warning(
                        f"[{request_id}] Blocked request payload (size: {size_bytes} bytes) from IP {request.client.host if request.client else 'unknown'} exceeding 10KB limit."
                    )
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Payload too large. Maximum allowed size is 10KB."}
                    )
            except ValueError:
                # Malformed content-length header
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header."}
                )

        # 3. Track response latency
        start_time = time.perf_counter()
        
        try:
            response: Response = await call_next(request)
        except Exception as e:
            # Handle unhandled errors by logging and formatting JSON responses
            logger.error(f"[{request_id}] Unhandled error inside request chain: {str(e)}")
            response = JSONResponse(
                status_code=500,
                content={"detail": f"Internal server error: {str(e)}"}
            )

        process_time_ms = (time.perf_counter() - start_time) * 1000

        # 4. Inject Response Headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{process_time_ms / 1000:.4f}s"
        
        # Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Relaxed CSP for docs
        if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
                "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
                "img-src 'self' https://fastapi.tiangolo.com data:; "
                "connect-src 'self';"
            )
        else:
            # Strict CSP for all other routes
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data:; "
                "connect-src 'self';"
            )

        # Log request latency stats
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            f"[{request_id}] Client IP: {client_ip} | Method: {request.method} | Path: {request.url.path} | "
            f"Status: {response.status_code} | Latency: {process_time_ms:.2f}ms"
        )

        return response
