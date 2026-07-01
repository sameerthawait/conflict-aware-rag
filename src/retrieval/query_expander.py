import time
import logging
import re
import yaml
from typing import Dict, List, Tuple, Any, Optional
from openai import OpenAI
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.retrieval.query_expander")


class QueryExpanderError(Exception):
    """Raised when query expansion or intent classification fails."""
    pass


class ExpandedQuery:
    """Represents the output of the query expansion and classification stage."""

    def __init__(
        self,
        original: str,
        keywords: List[str],
        semantic_query: str,
        intent: str,
        routing_note: str
    ) -> None:
        """Initializes the ExpandedQuery.

        Args:
            original: The raw user query.
            keywords: List of expanded search key terms.
            semantic_query: Optimized semantic reformulation of the query.
            intent: Query intent class (e.g. 'RAG_REQUIRED', 'GENERAL_CONVERSATION').
            routing_note: Brief note detailing how the query is routed.
        """
        self.original = original
        self.keywords = keywords
        self.semantic_query = semantic_query
        self.intent = intent
        self.routing_note = routing_note

    def __repr__(self) -> str:
        return f"ExpandedQuery(intent={self.intent}, keywords_count={len(self.keywords)})"


class QueryExpander:
    """Handles query reformulation, keyword extraction, and routing intent classification using LLM prompts."""

    def __init__(self, config: Dict[str, Any], prompt_manager: PromptManager, client: Optional[OpenAI] = None) -> None:
        """Initializes the QueryExpander.

        Args:
            config: System configuration dictionary.
            prompt_manager: PromptManager instance.
            client: OpenAI API client.
        """
        self.config = config
        self.prompt_manager = prompt_manager
        self.client = client

        llm_conf = config.get("llm", {})
        self.llm_model: str = llm_conf.get("model_name", "meta/llama-3.1-70b-instruct")
        self.temperature: float = llm_conf.get("temperature", 0.0)
        self.max_tokens_to_sample: int = llm_conf.get("max_tokens_to_sample", 1024)

        # 5-minute TTL cache mapping query -> (timestamp, ExpandedQuery)
        self._cache: Dict[str, Tuple[float, ExpandedQuery]] = {}
        self.cache_ttl = 300.0  # 5 minutes in seconds

    def _get_from_cache(self, query: str) -> Optional[ExpandedQuery]:
        """Retrieves non-expired ExpandedQuery from cache.

        Args:
            query: The original query key.

        Returns:
            The cached ExpandedQuery or None if expired/missing.
        """
        if query in self._cache:
            timestamp, cached_result = self._cache[query]
            if time.time() - timestamp < self.cache_ttl:
                logger.info(f"Query expansion cache HIT for: '{query}'")
                return cached_result
            else:
                logger.info(f"Query expansion cache EXPIRED for: '{query}'")
                del self._cache[query]
        return None

    def _save_to_cache(self, query: str, result: ExpandedQuery) -> None:
        """Stores result in cache with current timestamp.

        Args:
            query: Original query string.
            result: ExpandedQuery object.
        """
        self._cache[query] = (time.time(), result)

    def _call_llm(self, prompt: str) -> str:
        """Executes LLM call with prompt.

        Args:
            prompt: Formatted prompt string.

        Returns:
            The raw text response from the model.

        Raises:
            QueryExpanderError: If API call fails.
        """
        if not self.client:
            logger.warning("No LLM client configured. Returning empty string.")
            return ""

        try:
            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens_to_sample
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            error_msg = f"LLM API request failed: {str(e)}"
            logger.error(error_msg)
            raise QueryExpanderError(error_msg) from e

    def _parse_expansion(self, response_text: str) -> Tuple[List[str], str]:
        """Parses KEYWORDS and SEMANTIC_QUERY from the LLM query expansion response.

        Args:
            response_text: Raw string output from the LLM.

        Returns:
            Tuple of (keywords list, semantic query string).
        """
        keywords: List[str] = []
        semantic_query = ""

        # Try standard YAML parsing
        try:
            parsed = yaml.safe_load(response_text)
            if isinstance(parsed, dict):
                kw_str = parsed.get("KEYWORDS", "")
                semantic_query = parsed.get("SEMANTIC_QUERY", "")
                
                # Split comma-separated keywords
                if kw_str:
                    keywords = [k.strip() for k in kw_str.split(",") if k.strip()]
        except Exception as e:
            logger.warning(f"YAML parsing of query expansion failed: {str(e)}. Falling back to regex.")

        # Fallback to regex if parsing failed
        if not keywords or not semantic_query:
            kw_match = re.search(r"KEYWORDS:\s*\"?([^\n\"]+)\"?", response_text, re.IGNORECASE)
            sem_match = re.search(r"SEMANTIC_QUERY:\s*\"?([^\n\"]+)\"?", response_text, re.IGNORECASE)
            
            if kw_match:
                kw_str = kw_match.group(1)
                keywords = [k.strip() for k in kw_str.split(",") if k.strip()]
            if sem_match:
                semantic_query = sem_match.group(1).strip()

        # Final checks
        if not semantic_query:
            logger.warning("Could not extract semantic query. Using original query.")
            semantic_query = ""

        return keywords, semantic_query

    def expand_query(self, query: str) -> ExpandedQuery:
        """Processes the query by classifying intent and generating keyword/semantic expansions.

        Args:
            query: The raw user query.

        Returns:
            An ExpandedQuery instance.

        Raises:
            QueryExpanderError: If API communication or parsing fails.
        """
        if not query.strip():
            return ExpandedQuery(original="", keywords=[], semantic_query="", intent="GENERAL_CONVERSATION", routing_note="Empty query.")

        # Check Cache
        cached = self._get_from_cache(query)
        if cached:
            return cached

        logger.info(f"Expanding query: '{query}'")

        # 1. Query Intent Classification
        try:
            intent_prompt = self.prompt_manager.get_prompt("query_intent_classifier", query=query)
            intent_response = self._call_llm(intent_prompt) if self.client else "RAG_REQUIRED"
        except Exception as e:
            raise QueryExpanderError(f"Failed during intent classification: {str(e)}") from e

        # Standardize intent
        intent = "RAG_REQUIRED"
        if "GENERAL_CONVERSATION" in intent_response.upper():
            intent = "GENERAL_CONVERSATION"

        # If general conversation, bypass expansion to save latency
        if intent == "GENERAL_CONVERSATION":
            result = ExpandedQuery(
                original=query,
                keywords=[],
                semantic_query=query,
                intent=intent,
                routing_note="Chit-chat intent. Direct generation bypasses document retrieval."
            )
            self._save_to_cache(query, result)
            return result

        # 2. Query Expansion (Keywords & Semantic Reformulation)
        try:
            expansion_prompt = self.prompt_manager.get_prompt("hybrid_retrieval_query_expansion", query=query)
            expansion_response = self._call_llm(expansion_prompt) if self.client else f"KEYWORDS: {query}\nSEMANTIC_QUERY: {query}"
        except Exception as e:
            raise QueryExpanderError(f"Failed during query expansion: {str(e)}") from e

        keywords, semantic_query = self._parse_expansion(expansion_response)
        
        # If semantic query extraction was empty, fallback to original
        if not semantic_query:
            semantic_query = query
        if not keywords:
            keywords = [query]

        routing_note = f"Search routed with {len(keywords)} keyword expansion terms and 1 semantic query."

        result = ExpandedQuery(
            original=query,
            keywords=keywords,
            semantic_query=semantic_query,
            intent=intent,
            routing_note=routing_note
        )

        self._save_to_cache(query, result)
        return result
