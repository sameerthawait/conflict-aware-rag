import os
import time
import json
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple
import redis

# Initialize loggers
logger = logging.getLogger("rag_system.generation.cache")


class CacheError(Exception):
    """Raised when caching operations fail."""
    pass


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes the cosine similarity between two float vectors."""
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = sum(a * a for a in v1) ** 0.5
    norm_b = sum(b * b for b in v2) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


class SemanticQueryCache:
    """Semantic cache mapping user query embeddings to structured responses with similarity thresholds and TTL."""

    def __init__(self, config: Dict[str, Any], embedding_model: Any) -> None:
        """Initializes the SemanticQueryCache.

        Args:
            config: System configuration dictionary.
            embedding_model: Loaded SentenceTransformer or similar embedding model.
        """
        self.config = config
        self.embedding_model = embedding_model

        cache_conf = config.get("cache", {})
        self.cosine_threshold: float = cache_conf.get("cosine_threshold", 0.95)
        self.ttl_seconds: int = cache_conf.get("ttl_seconds", 3600)

        # Redis connection setup
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
                logger.info("Semantic cache successfully connected to Redis.")
            except Exception as e:
                logger.warning(f"Semantic cache failed to connect to Redis: {str(e)}. Falling back to in-memory cache.")
                self.redis_client = None

        # Local in-memory cache index
        # Structure: {cache_id: {"query": query_text, "embedding": List[float], "timestamp": float, "response": Dict[str, Any], "doc_ids": List[str]}}
        self._memory_cache: Dict[str, Dict[str, Any]] = {}

        # Cache stats metrics
        self.hits = 0
        self.misses = 0

    def _get_active_entries(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Cleans and returns non-expired cache entries from memory/Redis."""
        current_time = time.time()
        active_entries = []

        expired_ids = []
        for cid, entry in list(self._memory_cache.items()):
            if current_time - entry["timestamp"] >= self.ttl_seconds:
                expired_ids.append(cid)
                continue
            
            # If Redis is active, sync check if key still exists
            if self.redis_client:
                try:
                    redis_exists = self.redis_client.exists(f"cache:entry:{cid}")
                    if not redis_exists:
                        expired_ids.append(cid)
                        continue
                except Exception:
                    pass
            active_entries.append((cid, entry))

        # Evict expired entries from index
        for cid in expired_ids:
            self._memory_cache.pop(cid, None)

        return active_entries

    def get(self, query: str) -> Optional[Dict[str, Any]]:
        """Checks if a semantically similar query is cached and non-expired.

        Args:
            query: Raw user query string.

        Returns:
            Cached response dictionary, or None if a cache miss occurs.
        """
        if not query.strip() or not self.embedding_model:
            return None

        # 1. Embed query
        try:
            query_vector = self.embedding_model.encode([query])[0].tolist()
        except Exception as e:
            logger.error(f"Failed to embed query for cache lookup: {str(e)}")
            return None

        # 2. Match against active entries
        active_entries = self._get_active_entries()
        best_similarity = -1.0
        best_entry = None
        best_cid = None

        for cid, entry in active_entries:
            sim = cosine_similarity(query_vector, entry["embedding"])
            if sim > best_similarity:
                best_similarity = sim
                best_entry = entry
                best_cid = cid

        # 3. Check if similarity meets threshold
        if best_similarity >= self.cosine_threshold and best_entry and best_cid:
            # Cache HIT!
            self.hits += 1
            logger.info(
                f"Semantic cache HIT for query: '{query}' -> matched '{best_entry['query']}' "
                f"(Similarity: {best_similarity:.4f} >= Threshold: {self.cosine_threshold})"
            )

            # Retrieve response payload
            if self.redis_client:
                try:
                    payload = self.redis_client.get(f"cache:entry:{best_cid}")
                    if payload:
                        return json.loads(str(payload))
                except Exception as e:
                    logger.error(f"Failed to fetch cached entry from Redis: {str(e)}. Using memory fallback.")

            # Fallback to local memory payload
            return best_entry["response"]

        # Cache MISS
        self.misses += 1
        logger.info(f"Semantic cache MISS for query: '{query}' (Best Similarity: {best_similarity:.4f})")
        return None

    def put(self, query: str, response: Dict[str, Any], doc_ids: List[str]) -> None:
        """Stores a generated query response in both the local index and Redis cache.

        Args:
            query: The original query text.
            response: Dict representation of RAGResponse.
            doc_ids: List of document IDs associated with the source chunks.
        """
        if not query.strip() or not self.embedding_model:
            return

        try:
            query_vector = self.embedding_model.encode([query])[0].tolist()
        except Exception as e:
            logger.error(f"Failed to embed query for caching: {str(e)}")
            return

        cache_id = str(uuid.uuid4())
        current_time = time.time()

        entry = {
            "query": query,
            "embedding": query_vector,
            "timestamp": current_time,
            "response": response,
            "doc_ids": doc_ids
        }

        # Save to memory index
        self._memory_cache[cache_id] = entry

        # Save to Redis
        if self.redis_client:
            try:
                self.redis_client.setex(
                    name=f"cache:entry:{cache_id}",
                    time=self.ttl_seconds,
                    value=json.dumps(response)
                )
                logger.debug(f"Cached response to Redis key cache:entry:{cache_id} (TTL: {self.ttl_seconds}s)")
            except Exception as e:
                logger.error(f"Failed to write cache entry to Redis: {str(e)}")

        logger.info(f"Successfully cached query '{query}' under cache_id '{cache_id}' (Source doc IDs: {doc_ids})")

    def invalidate_by_document(self, doc_id: str) -> int:
        """Invalidates and evicts all cache entries referencing a specific document ID.

        Args:
            doc_id: The document ID string to evict.

        Returns:
            Number of evicted cache entries.
        """
        logger.info(f"Invalidating cache entries referencing doc_id: '{doc_id}'")
        evicted_count = 0

        # Scan and find matches
        for cid, entry in list(self._memory_cache.items()):
            if doc_id in entry["doc_ids"]:
                # Evict from memory
                self._memory_cache.pop(cid, None)
                evicted_count += 1
                
                # Evict from Redis
                if self.redis_client:
                    try:
                        self.redis_client.delete(f"cache:entry:{cid}")
                    except Exception as e:
                        logger.error(f"Failed to delete cached key {cid} from Redis: {str(e)}")

        logger.info(f"Evicted {evicted_count} cache entries referencing doc_id: '{doc_id}'")
        return evicted_count

    def clear(self) -> None:
        """Clears all entries from both memory and Redis cache store."""
        logger.info("Clearing semantic query cache...")
        
        # Clear Redis keys
        if self.redis_client:
            try:
                keys = list(self.redis_client.keys("cache:entry:*"))  # type: ignore[arg-type]
                if keys:
                    self.redis_client.delete(*keys)
                logger.info("Successfully flushed Redis cache entries.")
            except Exception as e:
                logger.error(f"Failed to clear Redis cache: {str(e)}")

        # Clear memory
        self._memory_cache.clear()
        self.hits = 0
        self.misses = 0
        logger.info("Successfully flushed memory cache index.")
