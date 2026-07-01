import json
import logging
import os
from typing import Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, StreamingResponse

logger = logging.getLogger("rag_system.api.response_filter")

class ResponseFilterMiddleware(BaseHTTPMiddleware):
    """Middleware that intercepts and sanitizes outgoing JSON responses to prevent data leaks.

    It strips internal chunk IDs, database doc IDs, absolute file paths, and raw embeddings.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # Only process JSON responses
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type or isinstance(response, StreamingResponse):
            return response

        # Read the response body
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        try:
            data = json.loads(body.decode("utf-8"))
            sanitized_data = self.sanitize_data(data)
            new_body = json.dumps(sanitized_data).encode("utf-8")
            
            # Reconstruct response with updated content
            response.headers["content-length"] = str(len(new_body))
            return Response(
                content=new_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )
        except Exception as e:
            logger.warning(f"Response filter failed to sanitize response: {str(e)}")
            # Return original on any parser failure
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )

    def sanitize_data(self, data: Any) -> Any:
        """Recursively sanitizes dict or list fields to remove internal details."""
        if isinstance(data, dict):
            # 1. Strip raw embeddings
            data.pop("embedding", None)
            data.pop("embeddings", None)

            # 2. Strip internal database IDs
            data.pop("chunk_id", None)
            data.pop("doc_id", None)

            # 3. Strip absolute file system paths (only expose base file names)
            if "file_path" in data and isinstance(data["file_path"], str):
                data["file_path"] = os.path.basename(data["file_path"])

            # Recurse
            return {k: self.sanitize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.sanitize_data(item) for item in data]
        return data
