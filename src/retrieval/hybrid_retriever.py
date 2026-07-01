import time
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple
from src.ingestion.vector_store import ChromaVectorStore, SearchResult
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.query_expander import QueryExpander, ExpandedQuery
from src.retrieval.fusion import ReciprocalRankFusion
from src.retrieval.reranker import Reranker

# Initialize structured logging
logger = logging.getLogger("rag_system.retrieval.hybrid_retriever")


class HybridRetrieverError(Exception):
    """Raised when hybrid retrieval coordination fails."""
    pass


class HybridRetriever:
    """Orchestrates query expansion, parallel vector/keyword searches, fusion, and reranking."""

    def __init__(
        self,
        config: Dict[str, Any],
        query_expander: QueryExpander,
        vector_store: ChromaVectorStore,
        bm25_retriever: BM25Retriever,
        fusion: ReciprocalRankFusion,
        reranker: Reranker
    ) -> None:
        """Initializes the HybridRetriever.

        Args:
            config: System configuration dictionary.
            query_expander: Initialized QueryExpander.
            vector_store: Initialized ChromaVectorStore.
            bm25_retriever: Initialized BM25Retriever.
            fusion: Initialized ReciprocalRankFusion.
            reranker: Initialized Reranker.
        """
        self.config = config
        self.query_expander = query_expander
        self.vector_store = vector_store
        self.bm25_retriever = bm25_retriever
        self.fusion = fusion
        self.reranker = reranker

        ret_conf = config.get("retrieval", {})
        self.vector_top_k: int = ret_conf.get("vector_top_k", 10)
        self.bm25_top_k: int = ret_conf.get("bm25_top_k", 10)
        self.final_top_k: int = ret_conf.get("final_top_k", 5)

    def retrieve(self, query: str) -> Tuple[List[SearchResult], Dict[str, Any]]:
        """Executes the full hybrid retrieval pipeline.

        Args:
            query: The raw user query.

        Returns:
            A tuple containing:
                - List of final reranked SearchResult objects.
                - Dict containing detailed latency metrics per sub-stage.

        Raises:
            HybridRetrieverError: If any stage of the pipeline fails.
        """
        total_start = time.perf_counter()
        latencies: Dict[str, float] = {}

        logger.info(f"Initiating hybrid retrieval pipeline for query: '{query}'")

        # 1. Query Expansion & Intent Classification
        try:
            exp_start = time.perf_counter()
            expanded_query: ExpandedQuery = self.query_expander.expand_query(query)
            latencies["expansion_ms"] = (time.perf_counter() - exp_start) * 1000
            
            logger.info(f"Intent classified: '{expanded_query.intent}'. Routing note: {expanded_query.routing_note}")
        except Exception as e:
            error_msg = f"Query expansion phase failed: {str(e)}"
            logger.error(error_msg)
            raise HybridRetrieverError(error_msg) from e

        # If the intent is non-RAG, bypass document retrieval
        if expanded_query.intent == "GENERAL_CONVERSATION":
            latencies["total_retrieval_ms"] = (time.perf_counter() - total_start) * 1000
            logger.info("General conversation intent detected. Bypassing search retrieval.")
            return [], latencies

        # 2. Parallel Search Queries (Vector & BM25)
        vector_results: List[SearchResult] = []
        bm25_results: List[SearchResult] = []
        
        search_start = time.perf_counter()
        
        def run_vector_search() -> List[SearchResult]:
            v_start = time.perf_counter()
            # Vector search uses the semantic reformulated query
            res = self.vector_store.similarity_search(expanded_query.semantic_query, self.vector_top_k)
            latencies["vector_search_ms"] = (time.perf_counter() - v_start) * 1000
            logger.info(f"Vector search returned {len(res)} candidate chunks.")
            return res

        def run_bm25_search() -> List[SearchResult]:
            b_start = time.perf_counter()
            # BM25 search uses the original query text for keyword indexing
            res = self.bm25_retriever.search(expanded_query.original, self.bm25_top_k)
            latencies["bm25_search_ms"] = (time.perf_counter() - b_start) * 1000
            logger.info(f"BM25 search returned {len(res)} candidate chunks.")
            return res

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                vector_future = executor.submit(run_vector_search)
                bm25_future = executor.submit(run_bm25_search)
                
                # Fetch results from threads
                vector_results = vector_future.result()
                bm25_results = bm25_future.result()
                
            latencies["parallel_searches_total_ms"] = (time.perf_counter() - search_start) * 1000
        except Exception as e:
            error_msg = f"Parallel retrieval execution failed: {str(e)}"
            logger.error(error_msg)
            raise HybridRetrieverError(error_msg) from e

        # 3. Reciprocal Rank Fusion (RRF)
        try:
            fusion_start = time.perf_counter()
            fused_results = self.fusion.fuse([vector_results, bm25_results])
            latencies["fusion_ms"] = (time.perf_counter() - fusion_start) * 1000
            logger.info(f"Reciprocal Rank Fusion merged candidate pools into {len(fused_results)} deduplicated chunks.")
        except Exception as e:
            error_msg = f"Reciprocal rank fusion phase failed: {str(e)}"
            logger.error(error_msg)
            raise HybridRetrieverError(error_msg) from e

        # 4. Cross-Encoder / LLM Reranking
        try:
            rerank_start = time.perf_counter()
            reranked_results = self.reranker.rerank(expanded_query.original, fused_results)
            latencies["reranking_ms"] = (time.perf_counter() - rerank_start) * 1000
        except Exception as e:
            error_msg = f"Reranking phase failed: {str(e)}"
            logger.error(error_msg)
            raise HybridRetrieverError(error_msg) from e

        # 5. Extract Final Top-K Results and Deprioritize Injection Risks
        safe_results = []
        flagged_results = []
        for r in reranked_results:
            if r.metadata and r.metadata.get("injection_risk") is True:
                logger.warning(f"Deprioritizing chunk '{r.chunk_id}' due to prompt injection risk in metadata.")
                flagged_results.append(r)
            else:
                safe_results.append(r)
        
        final_results = (safe_results + flagged_results)[:self.final_top_k]
        
        latencies["total_retrieval_ms"] = (time.perf_counter() - total_start) * 1000
        logger.info(
            f"Hybrid retrieval finished in {latencies['total_retrieval_ms']:.2f}ms. "
            f"Returned {len(final_results)} chunks to generator."
        )

        return final_results, latencies
