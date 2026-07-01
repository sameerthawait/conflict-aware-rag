import hashlib
import time
import logging
from typing import Dict, Any, Optional
import redis

# Audit logging streams
audit_logger = logging.getLogger("rag_system.audit.fingerprint")
logger = logging.getLogger("rag_system.api.fingerprint")

class RequestFingerprinter:
    """Fingerprints incoming requests based on network and headers to detect API key rotation

    and bottiming patterns, blocking high-risk requests.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        redis_conf = config.get("redis", {})
        self.redis_enabled = redis_conf.get("enabled", True)
        self.redis_url = redis_conf.get("url", "redis://localhost:6379/0")
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
                logger.info("Request fingerprinter connected to Redis.")
            except Exception as e:
                logger.warning(f"Request fingerprinter failed to connect to Redis: {str(e)}. Local checks only.")
                self.redis_client = None

    def compute_fingerprint(self, ip: str, user_agent: str, accept_lang: str) -> str:
        """Generates a SHA-256 fingerprint hash of the client headers."""
        raw_str = f"{ip}|{user_agent or ''}|{accept_lang or ''}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def process_request(self, ip: str, user_agent: str, accept_lang: str, api_key_hash: str) -> bool:
        """Processes the request headers.

        Returns False if the client exhibits malicious/abnormal activity and should be blocked, True otherwise.
        """
        if not self.redis_client:
            return True

        fingerprint = self.compute_fingerprint(ip, user_agent, accept_lang)
        current_time = time.time()

        # Redis state keys
        block_key = f"fp:blocked:{fingerprint}"
        flag_key = f"fp:flags:{fingerprint}"
        key_mapping_key = f"fp:key:{fingerprint}"
        timing_key = f"fp:timing:{fingerprint}"

        try:
            # 1. Check block status
            if self.redis_client.get(block_key):
                audit_logger.warning(f"Security Block: Request from blocked fingerprint {fingerprint} (IP: {ip}).")
                return False

            pipe = self.redis_client.pipeline()
            pipe.get(key_mapping_key)
            pipe.get(flag_key)
            pipe.lrange(timing_key, 0, -1)
            last_key, flags_str, timings = pipe.execute()

            flags = int(flags_str or 0)

            # Anomaly 1: Key Sharing / Rotation Detection
            # If same fingerprint rotates multiple different API keys within 1 hour, increment flags
            if last_key and last_key != api_key_hash:
                flags += 1
                audit_logger.warning(
                    f"Security Alert: Fingerprint {fingerprint} (IP: {ip}) is rotating API keys. "
                    f"Old Hash: {last_key[:10]}... | New Hash: {api_key_hash[:10]}..."
                )
                self.redis_client.incr(flag_key)
                self.redis_client.expire(flag_key, 3600)

            # Update mapping
            self.redis_client.set(key_mapping_key, api_key_hash, ex=3600)

            # Anomaly 2: Bot-like rapid request timings
            # Filter timestamps to within the last 60 seconds
            valid_timings = [float(t) for t in timings if current_time - float(t) < 60]
            valid_timings.append(current_time)

            # Save updated timings list
            self.redis_client.delete(timing_key)
            if valid_timings:
                self.redis_client.rpush(timing_key, *valid_timings)
                self.redis_client.expire(timing_key, 60)

            # If request count in last 60s exceeds 30, flag bot behavior
            if len(valid_timings) > 30:
                flags += 1
                audit_logger.warning(
                    f"Security Alert: Fingerprint {fingerprint} (IP: {ip}) showing bot timing volume "
                    f"({len(valid_timings)} req/min)."
                )
                self.redis_client.incr(flag_key)
                self.redis_client.expire(flag_key, 3600)

            # 3. Block check
            if flags >= 3:
                # Block fingerprint for 24 hours
                self.redis_client.set(block_key, "1", ex=86400)
                audit_logger.critical(
                    f"Security Block: Fingerprint {fingerprint} (IP: {ip}) blocked for 24 hours due to {flags} safety flags."
                )
                return False

        except Exception as e:
            logger.warning(f"Error executing fingerprinter check: {str(e)}")

        return True
