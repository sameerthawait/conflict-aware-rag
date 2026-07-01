import os
import re
import pickle
import logging
import time
from typing import List, Dict, Any, Set, Optional
from src.ingestion.vector_store import ChromaVectorStore, SearchResult

# Initialize structured logging
logger = logging.getLogger("rag_system.retrieval.bm25_retriever")


class RetrievalError(Exception):
    """Raised when retrieval operations or index builds fail."""
    pass


# Comprehensive set of common English stopwords to avoid external downloads
STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as", "at",
    "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "few", "for",
    "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's",
    "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm",
    "i've", "if", "in", "into", "is", "isn't", "it", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
    "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some",
    "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there", "there's",
    "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "weren't", "what", "what's",
    "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't",
    "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves"
}


class BM25Okapi:
    """Mathematical implementation of the BM25Okapi scoring algorithm."""

    def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.75) -> None:
        """Initializes the BM25 model parameters and precomputes TF-IDF terms.

        Args:
            corpus: Tokenized documents.
            k1: Term frequency scaling factor.
            b: Document length scaling factor.
        """
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.avgdl = sum(len(doc) for doc in corpus) / self.corpus_size if self.corpus_size > 0 else 0
        self.doc_freqs: List[Dict[str, int]] = []
        self.doc_len: List[int] = []
        self.nd: Dict[str, int] = {}  # Document frequency of each term
        
        for doc in corpus:
            self.doc_len.append(len(doc))
            frequencies: Dict[str, int] = {}
            for term in doc:
                frequencies[term] = frequencies.get(term, 0) + 1
            self.doc_freqs.append(frequencies)
            for term in frequencies:
                self.nd[term] = self.nd.get(term, 0) + 1

        # Precompute IDF values for every term
        import math
        self.idf: Dict[str, float] = {}
        for term, freq in self.nd.items():
            self.idf[term] = math.log(1.0 + (self.corpus_size - freq + 0.5) / (freq + 0.5))

    def get_scores(self, query: List[str]) -> List[float]:
        """Calculates BM25 alignment scores for all documents in the index.

        Args:
            query: Tokenized query terms.

        Returns:
            A list of scores corresponding to each document index.
        """
        scores = [0.0] * self.corpus_size
        for term in query:
            if term not in self.idf:
                continue
            idf = self.idf[term]
            for doc_idx, freq in enumerate(self.doc_freqs):
                if term in freq:
                    f = freq[term]
                    doc_len = self.doc_len[doc_idx]
                    # Okapi BM25 formula
                    score = idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl))
                    scores[doc_idx] += score
        return scores


class BM25Retriever:
    """Manages the lifecycle, loading, and searching of a disk-persisted BM25 document index."""

    def __init__(self, config: Dict[str, Any], vector_store: ChromaVectorStore) -> None:
        """Initializes the BM25Retriever.

        Args:
            config: System configuration dictionary.
            vector_store: Initialized ChromaVectorStore instance.
        """
        self.config = config
        self.vector_store = vector_store

        ret_conf = config.get("retrieval", {})
        self.index_path: str = ret_conf.get("bm25_index_path", "data/bm25_index.pkl")

        self.bm25_model: Optional[BM25Okapi] = None
        self.chunk_ids: List[str] = []
        self.documents: List[str] = []
        self.metadatas: List[Dict[str, Any]] = []
        self.indexed_chunk_count = 0

    def tokenize(self, text: str) -> List[str]:
        """Splits string text, filters special characters, and removes common stopwords.

        Args:
            text: Raw input string.

        Returns:
            List of processed tokens.
        """
        words = re.findall(r"\b\w+\b", text.lower())
        return [w for w in words if w not in STOPWORDS]

    def _is_stale(self) -> bool:
        """Checks if the disk-persisted index matches ChromaDB collection count.

        Returns:
            True if stale or missing, False otherwise.
        """
        if not os.path.exists(self.index_path):
            return True

        try:
            chroma_count = self.vector_store.get_collection_stats()["count"]
            return chroma_count != self.indexed_chunk_count
        except Exception as e:
            logger.warning(f"Failed to query database count: {str(e)}. Defaulting to rebuild.")
            return True

    def build_index(self) -> None:
        """Downloads all active chunks from ChromaDB, compiles vocabulary TF-IDFs, and persists to disk.

        Raises:
            RetrievalError: If indexing or serialization fails.
        """
        logger.info("Rebuilding BM25 Search Index from ChromaDB...")
        start_time = time.perf_counter()

        try:
            self.vector_store._ensure_initialized()
            # Fetch all stored records from ChromaDB
            assert self.vector_store.collection is not None
            results = self.vector_store.collection.get(include=["documents", "metadatas"])
        except Exception as e:
            raise RetrievalError(f"Failed to fetch chunks from ChromaDB to build BM25 index: {str(e)}") from e

        ids = results.get("ids", [])
        docs = results.get("documents", [])
        metas = results.get("metadatas", []) or [{} for _ in range(len(ids))]

        if not ids:
            logger.warning("No records found in ChromaDB. BM25 Index initialized empty.")
            self.bm25_model = BM25Okapi([])
            self.chunk_ids = []
            self.documents = []
            self.metadatas = []
            self.indexed_chunk_count = 0
            return

        tokenized_corpus = [self.tokenize(doc) for doc in docs]
        self.bm25_model = BM25Okapi(tokenized_corpus)
        self.chunk_ids = ids
        self.documents = docs
        self.metadatas = metas
        self.indexed_chunk_count = len(ids)

        # Save to disk
        try:
            os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
            with open(self.index_path, "wb") as f:
                pickle.dump({
                    "chunk_ids": self.chunk_ids,
                    "documents": self.documents,
                    "metadatas": self.metadatas,
                    "indexed_chunk_count": self.indexed_chunk_count,
                    "bm25_model": self.bm25_model
                }, f)
        except Exception as e:
            raise RetrievalError(f"Failed to serialize BM25 index file to disk at '{self.index_path}': {str(e)}") from e

        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"BM25 Index compiled successfully. {len(ids)} documents indexed in {latency_ms:.2f}ms.")

    def _load_index_from_disk(self) -> None:
        """Loads serialized BM25 index from disk."""
        logger.info(f"Loading BM25 index from file: {self.index_path}")
        try:
            with open(self.index_path, "rb") as f:
                data = pickle.load(f)
                self.chunk_ids = data["chunk_ids"]
                self.documents = data["documents"]
                self.metadatas = data["metadatas"]
                self.indexed_chunk_count = data["indexed_chunk_count"]
                self.bm25_model = data["bm25_model"]
        except Exception as e:
            logger.error(f"Failed to deserialize index file: {str(e)}")
            raise RetrievalError(f"Corrupt or unreadable BM25 index file: {str(e)}") from e

    def search(self, query: str, k: int) -> List[SearchResult]:
        """Calculates matches and retrieves top-k chunks aligned with query terms.

        Args:
            query: User search query.
            k: Top-k matches count.

        Returns:
            List of SearchResult objects sorted by scores descending.

        Raises:
            RetrievalError: If search execution fails.
        """
        start_time = time.perf_counter()
        
        # Validate or rebuild index state if stale
        if self.bm25_model is None or self._is_stale():
            if os.path.exists(self.index_path) and not self._is_stale():
                self._load_index_from_disk()
            else:
                self.build_index()

        if not self.chunk_ids or self.bm25_model is None:
            return []

        tokenized_query = self.tokenize(query)
        if not tokenized_query:
            # Query is empty or composed entirely of stopwords. Return top items arbitrarily or empty
            logger.warning("Empty tokenized query. Returning empty search results.")
            return []

        try:
            scores = self.bm25_model.get_scores(tokenized_query)
        except Exception as e:
            raise RetrievalError(f"Okapi BM25 scoring failed: {str(e)}") from e

        # Pair scores with document metadata
        results = []
        for idx in range(len(self.chunk_ids)):
            score = scores[idx]
            if score > 0:  # Only return chunks with non-zero keyword overlap
                results.append((score, idx))

        # Sort descending by score
        results.sort(key=lambda x: x[0], reverse=True)
        top_results = results[:k]

        search_results: List[SearchResult] = []
        for score, idx in top_results:
            search_results.append(
                SearchResult(
                    chunk_id=self.chunk_ids[idx],
                    text=self.documents[idx],
                    score=score,
                    metadata=self.metadatas[idx]
                )
            )

        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"BM25 Search completed in {latency_ms:.2f}ms. Found {len(search_results)} results.")
        return search_results
