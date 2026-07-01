import os
import time
import hashlib
import logging
import contextvars
from typing import Dict, Any, Optional, Tuple
from fastapi import Request, Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
import redis

# Request-scoped context variables to avoid threading auth details deep into pipelines
current_key_info: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar("current_key_info", default=None)
current_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_request_id", default="N/A")
current_client_ip: contextvars.ContextVar[str] = contextvars.ContextVar("current_client_ip", default="unknown")

# Define audit logging stream
audit_logger = logging.getLogger("rag_system.audit.auth")
logger = logging.getLogger("rag_system.api.auth")

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


class RateLimiter:
    """Manages API key rate limits (requests per minute and tokens per day) using Redis or in-memory fallback."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initializes the RateLimiter.

        Args:
            config: System configuration dictionary.
        """
        self.config = config
        
        # Redis setup
        redis_conf = config.get("redis", {})
        self.redis_enabled: bool = redis_conf.get("enabled", True)
        self.redis_url: str = redis_conf.get("url", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        
        self.redis_client: Optional[redis.Redis] = None
        if self.redis_enabled:
            try:
                self.redis_client = redis.Redis.from_url(
                    self.redis_url, 
                    socket_timeout=1.0, 
                    socket_connect_timeout=1.0, 
                    decode_responses=True
                )
                self.redis_client.ping()
                logger.info("Rate limiter successfully connected to Redis.")
            except Exception as e:
                logger.warning(f"Rate limiter failed to connect to Redis: {str(e)}. Falling back to in-memory limits.")
                self.redis_client = None

        # In-memory fallbacks
        # Structure: {key_hash: [timestamp1, timestamp2, ...]}
        self._in_memory_rpm_hits: Dict[str, list] = {}
        # Structure: {key_hash: (day_date_str, token_count)}
        self._in_memory_tpd_usage: Dict[str, Tuple[str, int]] = {}

    def _get_current_day_str(self) -> str:
        """Returns the current day date string (YYYY-MM-DD)."""
        return time.strftime("%Y-%m-%d", time.gmtime())

    def check_rate_limits(self, key_hash: str, key_info: Dict[str, Any]) -> Tuple[bool, str, int]:
        """Checks request per minute (RPM) and token per day (TPD) limits.

        Args:
            key_hash: Hash string of the key.
            key_info: Key metadata (rate limits config).

        Returns:
            Tuple of:
                - is_allowed (bool)
                - error_message (str)
                - retry_after (int)
        """
        rpm_limit = key_info.get("rate_limit_rpm", 20)
        tpd_limit = key_info.get("token_limit_tpd", 100000)

        # 1. Try checking via Redis
        if self.redis_client:
            try:
                # RPM Check
                rpm_key = f"ratelimit:{key_hash}:rpm"
                # Pipeline transactional increment
                pipe = self.redis_client.pipeline()
                pipe.incr(rpm_key)
                pipe.ttl(rpm_key)
                current_rpm, ttl = pipe.execute()

                if current_rpm == 1:
                    # Set expire if first request in window
                    self.redis_client.expire(rpm_key, 60)
                    ttl = 60

                if current_rpm > rpm_limit:
                    retry_after = max(int(ttl), 1)
                    return False, "Rate limit exceeded (Requests Per Minute).", retry_after

                # TPD Check (will be updated with token counts post-completion, checked here as soft ceiling)
                tpd_key = f"ratelimit:{key_hash}:tpd"
                current_tpd = self.redis_client.get(tpd_key)
                current_tpd_val = int(current_tpd) if current_tpd else 0
                
                if current_tpd_val >= tpd_limit:
                    return False, "Daily token limit budget exhausted.", 3600  # Default retry after 1 hour

                return True, "", 0
            except Exception as e:
                logger.error(f"Redis rate limiter failed: {str(e)}. Falling back to in-memory check.")

        # 2. Fall back to In-Memory
        current_time = time.time()
        
        # RPM check
        timestamps = self._in_memory_rpm_hits.setdefault(key_hash, [])
        # Clean timestamps older than 60 seconds
        timestamps = [t for t in timestamps if current_time - t < 60]
        self._in_memory_rpm_hits[key_hash] = timestamps

        if len(timestamps) >= rpm_limit:
            retry_after = max(int(60 - (current_time - timestamps[0])), 1)
            return False, "Rate limit exceeded (Requests Per Minute).", retry_after

        # Increment RPM hit
        self._in_memory_rpm_hits[key_hash].append(current_time)

        # TPD check
        day_str = self._get_current_day_str()
        cached_day, tokens_used = self._in_memory_tpd_usage.get(key_hash, (day_str, 0))

        if cached_day != day_str:
            # New day, reset
            tokens_used = 0
            self._in_memory_tpd_usage[key_hash] = (day_str, 0)

        if tokens_used >= tpd_limit:
            return False, "Daily token limit budget exhausted.", 3600

        return True, "", 0

    def record_token_usage(self, key_hash: str, token_count: int) -> None:
        """Records token consumption post-completion.

        Args:
            key_hash: Hash string of the key.
            token_count: Number of tokens to increment.
        """
        if self.redis_client:
            try:
                tpd_key = f"ratelimit:{key_hash}:tpd"
                self.redis_client.incrby(tpd_key, token_count)
                # Set TTL to end of day (86400 seconds) on first write
                self.redis_client.expire(tpd_key, 86400)
                return
            except Exception as e:
                logger.error(f"Redis token recording failed: {str(e)}.")

        # In-memory fallback
        day_str = self._get_current_day_str()
        cached_day, tokens_used = self._in_memory_tpd_usage.get(key_hash, (day_str, 0))
        if cached_day == day_str:
            self._in_memory_tpd_usage[key_hash] = (day_str, tokens_used + token_count)
        else:
            self._in_memory_tpd_usage[key_hash] = (day_str, token_count)


class Authenticator:
    """Handles verification of request API headers against config hashes."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initializes the Authenticator.

        Args:
            config: System configuration dictionary.
        """
        self.config = config
        self.rate_limiter = RateLimiter(config)

    def _hash_key(self, api_key: str) -> str:
        """Computes the SHA-256 hash of the API key string."""
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    async def authenticate(self, request: Request, api_key: Optional[str] = Security(API_KEY_HEADER)) -> Dict[str, Any]:
        """Dependency function validating API keys and enforcing rate limit checks.

        Args:
            request: The raw FastAPI Request.
            api_key: Passed api key from headers.

        Returns:
            Dictionary with key information (metadata, tier, hash).

        Raises:
            HTTPException: 401 on missing/invalid keys, 429 on rate limit hits.
        """
        req_id = getattr(request.state, "request_id", "N/A")
        client_ip = request.client.host if request.client else "unknown"

        if not api_key:
            audit_logger.warning(
                f"[{req_id}] IP {client_ip} attempted request without API Key header."
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API Key. Provide 'X-API-Key' header."
            )

        key_hash = self._hash_key(api_key)
        
        # Look up key hash in config (dynamic key rotation checks config loaded at runtime)
        hashed_keys = self.config.get("security", {}).get("hashed_api_keys", {})

        if key_hash not in hashed_keys:
            audit_logger.warning(
                f"[{req_id}] IP {client_ip} provided invalid API Key (Hashed: {key_hash[:10]}...)"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API Key."
            )

        key_info = hashed_keys[key_hash]
        key_name = key_info.get("name", "unnamed")
        tier = key_info.get("tier", "standard")

        # Check rate limits
        allowed, err_msg, retry_after = self.rate_limiter.check_rate_limits(key_hash, key_info)

        if not allowed:
            audit_logger.warning(
                f"[{req_id}] Key '{key_name}' (Tier: {tier}) blocked: {err_msg} | IP: {client_ip}"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=err_msg,
                headers={"Retry-After": str(retry_after)}
            )

        # Log successful auth event in audit stream
        audit_logger.info(
            f"[{req_id}] Authenticated Key '{key_name}' (Tier: {tier}) | IP: {client_ip}"
        )

        key_data = {
            "name": key_name,
            "tier": tier,
            "hash": key_hash,
            "rate_limiter": self.rate_limiter
        }
        
        # Set context variables for request-level tracing
        current_request_id.set(req_id)
        current_key_info.set(key_data)
        current_client_ip.set(client_ip)

        return key_data

    async def authenticate_key(self, request: Request, api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
        """Dependency function validating API key and returning the key string itself."""
        await self.authenticate(request, api_key)
        return api_key or ""
