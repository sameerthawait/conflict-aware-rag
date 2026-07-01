import queue
import logging
import time
from typing import Dict, Any, Generator, Optional
from contextlib import contextmanager
from src.ingestion.vector_store import ChromaVectorStore, VectorStoreError

logger = logging.getLogger("rag_system.retrieval.vector_store_pool")


class VectorStorePoolError(Exception):
    """Raised when acquiring or managing vector store connections in the pool fails."""
    pass


class VectorStorePool:
    """Thread-safe connection pool for ChromaDB database clients."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initializes the VectorStorePool.

        Args:
            config: System configuration dictionary.
        """
        self.config = config
        
        pool_conf = config.get("vector_store_pool", {})
        self.pool_size: int = pool_conf.get("size", 10)
        
        # Thread-safe connection queue
        self._pool: queue.Queue[ChromaVectorStore] = queue.Queue(maxsize=self.pool_size)

        # Pre-initialize embedding model to share across connections to save GPU/CPU RAM
        try:
            logger.info("Pre-loading SentenceTransformer model to share across connection pool...")
            from sentence_transformers import SentenceTransformer
            embed_conf = config.get("embeddings", {})
            model_name = embed_conf.get("model_name", "sentence-transformers/all-mpnet-base-v2")
            self._shared_embedding_model = SentenceTransformer(model_name)
        except Exception as e:
            logger.critical(f"Failed to pre-load embedding model: {str(e)}")
            self._shared_embedding_model = None

        logger.info(f"Initializing ChromaDB connection pool with size={self.pool_size}...")
        for i in range(self.pool_size):
            conn = self._create_connection()
            self._pool.put(conn)

    def _create_connection(self) -> ChromaVectorStore:
        """Creates and initializes a single database connection instance."""
        conn = ChromaVectorStore(self.config)
        
        # Inject the pre-loaded shared embedding model to optimize memory
        if self._shared_embedding_model:
            conn.embedding_model = self._shared_embedding_model

        try:
            conn.initialize()
        except Exception as e:
            logger.warning(f"Failed to initialize pool connection on startup: {str(e)}. Will retry on acquisition.")
            
        return conn

    def _is_healthy(self, conn: ChromaVectorStore) -> bool:
        """Checks if a connection is active and healthy by querying DB collection count."""
        try:
            if conn.client is None or conn.collection is None:
                return False
            # Call simple db transaction
            conn.collection.count()
            return True
        except Exception:
            return False

    @contextmanager
    def get_connection(self, timeout: float = 5.0) -> Generator[ChromaVectorStore, None, None]:
        """Context manager yielding an initialized and healthy database client from the pool.

        Args:
            timeout: Maximum seconds to block waiting for an available connection.

        Yields:
            ChromaVectorStore instance.

        Raises:
            VectorStorePoolError: If pool is exhausted or client cannot reconnect.
        """
        conn: Optional[ChromaVectorStore] = None
        try:
            # Block until connection is free in the queue
            conn = self._pool.get(block=True, timeout=timeout)
        except queue.Empty as e:
            raise VectorStorePoolError(
                f"Connection pool exhausted. Failed to acquire connection within {timeout}s."
            ) from e

        # Validate connection health
        if not self._is_healthy(conn):
            logger.warning("Connection health check failed. Attempting auto-reconnect...")
            try:
                # Re-initialize
                conn.initialize()
                if not self._is_healthy(conn):
                    raise VectorStoreError("Re-initialized connection failed health check.")
                logger.info("Connection successfully reconnected and verified.")
            except Exception as e:
                # Put a new connection back in the pool so queue stays filled, then raise
                logger.error(f"Failed to auto-reconnect: {str(e)}. Replacing connection in pool.")
                replacement_conn = self._create_connection()
                self._pool.put(replacement_conn)
                raise VectorStorePoolError(f"Database connection offline: {str(e)}") from e

        try:
            yield conn
        finally:
            if conn:
                # Return connection to the queue
                self._pool.put(conn)


class PooledCollection:
    """Wrapper that proxies collection actions using connections acquired from the pool."""

    def __init__(self, pool: VectorStorePool) -> None:
        self.pool = pool

    def get(self, *args, **kwargs) -> Dict[str, Any]:
        with self.pool.get_connection() as conn:
            return conn.collection.get(*args, **kwargs)

    def count(self, *args, **kwargs) -> int:
        with self.pool.get_connection() as conn:
            return conn.collection.count(*args, **kwargs)

    def add(self, *args, **kwargs) -> None:
        with self.pool.get_connection() as conn:
            return conn.collection.add(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        with self.pool.get_connection() as conn:
            return conn.collection.delete(*args, **kwargs)

    def query(self, *args, **kwargs) -> Dict[str, Any]:
        with self.pool.get_connection() as conn:
            return conn.collection.query(*args, **kwargs)


class PooledChromaVectorStore:
    """A thread-safe wrapper that presents the ChromaVectorStore interface but routes calls through a pool."""

    def __init__(self, pool: VectorStorePool) -> None:
        self.pool = pool
        self.config = pool.config
        self.collection = PooledCollection(pool)

    @property
    def embedding_model(self):
        return self.pool._shared_embedding_model

    @property
    def embedding_model_name(self) -> str:
        return self.config.get("embeddings", {}).get("model_name", "sentence-transformers/all-mpnet-base-v2")

    def initialize(self) -> None:
        # Pre-warmed by pool
        pass

    def _ensure_initialized(self) -> None:
        # Checked dynamically
        pass

    def add_chunks(self, chunks: list) -> None:
        with self.pool.get_connection() as conn:
            conn.add_chunks(chunks)

    def get_collection_stats(self) -> Dict[str, Any]:
        with self.pool.get_connection() as conn:
            return conn.get_collection_stats()

    def delete_document(self, doc_id: str) -> None:
        with self.pool.get_connection() as conn:
            conn.delete_document(doc_id)

    def similarity_search(self, query: str, k: int) -> list:
        with self.pool.get_connection() as conn:
            return conn.similarity_search(query, k)

