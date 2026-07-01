import os
import logging
from typing import List, Dict, Any, Optional
import chromadb
from sentence_transformers import SentenceTransformer
from src.ingestion.chunker import Chunk

# Initialize structured logging
logger = logging.getLogger("rag_system.ingestion.vector_store")


class VectorStoreError(Exception):
    """Raised when vector store operations (initialization, insertion, query, delete) fail."""
    pass


class SearchResult:
    """Represents a retrieved document chunk with similarity scores and metadata."""

    def __init__(self, chunk_id: str, text: str, score: float, metadata: Dict[str, Any]) -> None:
        """Initializes a SearchResult instance.

        Args:
            chunk_id: The unique ID of the matched chunk.
            text: The text content of the chunk.
            score: The similarity distance score.
            metadata: Metadata associated with the chunk.
        """
        self.chunk_id = chunk_id
        self.text = text
        self.score = score
        self.metadata = metadata

    def __repr__(self) -> str:
        return f"SearchResult(chunk_id={self.chunk_id}, score={self.score:.4f})"


class ChromaVectorStore:
    """Persistent vector database client using ChromaDB and SentenceTransformer embeddings."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initializes the ChromaVectorStore with system settings.

        Args:
            config: System configuration dictionary.
        """
        self.config = config

        vstore_conf = config.get("vector_store", {})
        self.persist_directory: str = vstore_conf.get("persist_directory", "data/chroma")
        self.collection_name: str = vstore_conf.get("collection_name", "rag_documents")

        embed_conf = config.get("embeddings", {})
        self.embedding_model_name: str = embed_conf.get("model_name", "sentence-transformers/all-mpnet-base-v2")

        self.client: Optional[chromadb.PersistentClient] = None
        self.collection: Optional[chromadb.Collection] = None
        self.embedding_model: Optional[SentenceTransformer] = None

    def initialize(self) -> None:
        """Sets up Chroma persistent client, creates collections, and loads the embedding model.

        Raises:
            VectorStoreError: If database or model initialization fails.
        """
        logger.info("Initializing embedding model and Chroma client...")
        try:
            # Load sentence transformer model locally on GPU if available
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Embedding device: {device}")
            self.embedding_model = SentenceTransformer(
                self.config["embeddings"]["model_name"],
                device=device
            )
        except Exception as e:
            error_msg = f"Failed to load sentence-transformers model '{self.embedding_model_name}': {str(e)}"
            logger.error(error_msg)
            raise VectorStoreError(error_msg) from e

        try:
            # Create persistent storage folder if not exists
            os.makedirs(self.persist_directory, exist_ok=True)
            self.client = chromadb.PersistentClient(path=self.persist_directory)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name
            )
        except Exception as e:
            error_msg = f"Failed to initialize ChromaDB client at '{self.persist_directory}': {str(e)}"
            logger.error(error_msg)
            raise VectorStoreError(error_msg) from e

        logger.info("ChromaDB initialization complete.")

    def _ensure_initialized(self) -> None:
        """Helper to assert client and collection are ready before database transactions."""
        if self.client is None or self.collection is None or self.embedding_model is None:
            raise VectorStoreError("Vector store has not been initialized. Call initialize() first.")

    def add_chunks(self, chunks: List[Chunk]) -> None:
        """Computes embeddings and indexes a batch of document chunks.

        Args:
            chunks: A list of Chunk objects to add.

        Raises:
            VectorStoreError: If batch database insertion fails.
        """
        self._ensure_initialized()
        if not chunks:
            logger.warning("No chunks provided to index.")
            return

        logger.info(f"Indexing {len(chunks)} chunks into ChromaDB...")
        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        texts_to_embed: List[str] = []

        for chunk in chunks:
            ids.append(chunk.chunk_id)
            documents.append(chunk.text)
            
            # Populate metadata for storage in Chroma (must be simple types)
            meta = {k: v for k, v in chunk.metadata.items() if isinstance(v, (str, int, float, bool))}
            meta["doc_id"] = chunk.doc_id
            metadatas.append(meta)
            texts_to_embed.append(chunk.text)

        try:
            # Compute embeddings in a batch
            embeddings_list = self.embedding_model.encode(texts_to_embed).tolist()

            # Insert into ChromaDB collection
            self.collection.add(
                ids=ids,
                embeddings=embeddings_list,
                metadatas=metadatas,
                documents=documents
            )
        except Exception as e:
            error_msg = f"Failed to insert chunks into ChromaDB collection: {str(e)}"
            logger.error(error_msg)
            raise VectorStoreError(error_msg) from e

        logger.info("Batch indexing successfully completed.")

    def get_collection_stats(self) -> Dict[str, Any]:
        """Gets count and statistics of elements stored in the collection.

        Returns:
            A dictionary containing stat metrics (e.g. 'count').
        """
        self._ensure_initialized()
        try:
            count = self.collection.count()
            return {"count": count, "collection_name": self.collection_name}
        except Exception as e:
            error_msg = f"Failed to retrieve collection stats: {str(e)}"
            logger.error(error_msg)
            raise VectorStoreError(error_msg) from e

    def delete_document(self, doc_id: str) -> None:
        """Deletes all chunks associated with a given doc_id.

        Args:
            doc_id: The document identifier string.

        Raises:
            VectorStoreError: If deletion transaction fails.
        """
        self._ensure_initialized()
        logger.info(f"Deleting document chunks for doc_id: {doc_id}")
        try:
            # Delete entries matching metadata filter
            self.collection.delete(where={"doc_id": doc_id})
        except Exception as e:
            error_msg = f"Failed to delete document {doc_id} from vector store: {str(e)}"
            logger.error(error_msg)
            raise VectorStoreError(error_msg) from e
        logger.info(f"Document {doc_id} successfully deleted.")

    def similarity_search(self, query: str, k: int) -> List[SearchResult]:
        """Performs nearest-neighbor search for a query string.

        Args:
            query: The user query string.
            k: Number of nearest neighbors to retrieve.

        Returns:
            A list of SearchResult objects sorted by relevance.

        Raises:
            VectorStoreError: If query execution fails.
        """
        self._ensure_initialized()
        logger.info(f"Performing similarity search for query (k={k})...")
        try:
            query_embeddings = self.embedding_model.encode([query]).tolist()
            results = self.collection.query(
                query_embeddings=query_embeddings,
                n_results=k
            )

            search_results: List[SearchResult] = []
            if not results or not results["ids"]:
                return search_results

            # Results shape: {ids: [[id1, id2...]], documents: [[doc1, doc2...]], distances: [[dist1, dist2...]], metadatas: [[m1, m2...]]}
            ids = results["ids"][0]
            documents = results["documents"][0]
            distances = results["distances"][0]
            metadatas = results["metadatas"][0]

            for idx in range(len(ids)):
                # Chroma outputs distances (where lower distance = higher similarity)
                # Convert to simple score representation
                score = float(distances[idx])
                search_results.append(
                    SearchResult(
                        chunk_id=ids[idx],
                        text=documents[idx],
                        score=score,
                        metadata=metadatas[idx]
                    )
                )
            return search_results
        except Exception as e:
            error_msg = f"Similarity search query failed: {str(e)}"
            logger.error(error_msg)
            raise VectorStoreError(error_msg) from e
