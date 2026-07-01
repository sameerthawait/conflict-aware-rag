import time
import logging
import re
import yaml
from typing import Dict, List, Any, Tuple, Optional
from openai import OpenAI
from src.ingestion.vector_store import SearchResult
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.generation.citation_gate")


class CitationGateError(Exception):
    """Raised when citation preflight check fails."""
    pass


class CitationPreflightResult:
    """Encapsulates the verdict and reasons from the citation preflight check."""

    def __init__(self, verdict: str, reason: str, gaps: List[str], proceed: bool) -> None:
        """Initializes the CitationPreflightResult.

        Args:
            verdict: Sufficiency class ('SUFFICIENT', 'PARTIAL', 'INSUFFICIENT').
            reason: Text rationale.
            gaps: List of missing details/points.
            proceed: Boolean indicating whether the RAG pipeline should continue to generation.
        """
        self.verdict = verdict.upper().strip()
        self.reason = reason
        self.gaps = gaps
        self.proceed = proceed

    def __repr__(self) -> str:
        return f"CitationPreflightResult(verdict={self.verdict}, proceed={self.proceed})"


class CitationPreflightGate:
    """Quality gate that checks whether retrieved contexts are sufficient to answer a query."""

    def __init__(self, config: Dict[str, Any], prompt_manager: PromptManager, client: Optional[OpenAI] = None) -> None:
        """Initializes the CitationPreflightGate.

        Args:
            config: System configuration dictionary.
            prompt_manager: PromptManager instance.
            client: Optional OpenAI client.
        """
        self.config = config
        self.prompt_manager = prompt_manager
        self.client = client

        gate_conf = config.get("quality_gates", {})
        self.min_verdict: str = gate_conf.get("preflight_min_verdict", "PARTIAL").upper().strip()

        llm_conf = config.get("llm", {})
        self.llm_model: str = llm_conf.get("model_name", "meta/llama-3.1-70b-instruct")
        self.temperature: float = llm_conf.get("temperature", 0.0)

        # Verdict hierarchy mapping
        self._verdict_levels = {
            "INSUFFICIENT": 1,
            "PARTIAL": 2,
            "SUFFICIENT": 3
        }

    def _format_context(self, results: List[SearchResult]) -> str:
        """Helper to construct context blocks matching prompts format.

        Args:
            results: Chunks retrieved.

        Returns:
            Concatenated formatted context.
        """
        formatted = []
        for i, res in enumerate(results):
            title = res.metadata.get("title", f"Document {i+1}")
            page = res.metadata.get("page_number", "N/A")
            formatted.append(f"Source Title: {title}\nPage: {page}\nContent: {res.text}\n")
        return "\n---\n".join(formatted)

    def _parse_preflight_response(self, response_text: str) -> Tuple[str, str, List[str]]:
        """Parses VERDICT, REASON, and GAPS from the YAML LLM response.

        Args:
            response_text: Raw YAML completion string from LLM.

        Returns:
            Tuple of (verdict, reason, gaps list).
        """
        verdict = "INSUFFICIENT"
        reason = "Parsing failed. Defaulting to insufficient."
        gaps: List[str] = []

        try:
            # Parse YAML response
            parsed = yaml.safe_load(response_text)
            if isinstance(parsed, dict):
                verdict = str(parsed.get("VERDICT", "INSUFFICIENT")).upper().strip()
                reason = str(parsed.get("REASON", ""))
                parsed_gaps = parsed.get("GAPS", [])
                if isinstance(parsed_gaps, list):
                    gaps = [str(g).strip() for g in parsed_gaps if g]
                elif isinstance(parsed_gaps, str) and parsed_gaps.strip():
                    gaps = [parsed_gaps.strip()]
                return verdict, reason, gaps
        except Exception as e:
            logger.warning(f"YAML parsing of citation preflight response failed: {str(e)}. Falling back to regex.")

        # Regex fallbacks
        verdict_match = re.search(r"VERDICT:\s*\"?(SUFFICIENT|PARTIAL|INSUFFICIENT)\"?", response_text, re.IGNORECASE)
        reason_match = re.search(r"REASON:\s*\"?([^\n\"]+)\"?", response_text, re.IGNORECASE)
        gaps_match = re.findall(r"-\s*\"?([^\n\"]+)\"?", response_text)

        if verdict_match:
            verdict = verdict_match.group(1).upper()
        if reason_match:
            reason = reason_match.group(1).strip()
        if gaps_match:
            gaps = [g.strip() for g in gaps_match if g.strip()]

        return verdict, reason, gaps

    def evaluate(self, query: str, results: List[SearchResult]) -> CitationPreflightResult:
        """Evaluates retrieval quality against query constraints.

        Args:
            query: The user search query.
            results: Chunks retrieved.

        Returns:
            A CitationPreflightResult.

        Raises:
            CitationGateError: If API communication or processing fails.
        """
        start_time = time.perf_counter()
        logger.info(f"Running citation preflight gate evaluation for query: '{query}'")

        # Optimization: if no results retrieved, block generation early without calling LLM
        if not results:
            logger.info("Empty retrieval search results. Preflight automatically failed with INSUFFICIENT.")
            return CitationPreflightResult(
                verdict="INSUFFICIENT",
                reason="No context chunks were retrieved by the search system.",
                gaps=["All information is missing. No matching source chunks were found."],
                proceed=False
            )

        if not self.client:
            logger.warning("No LLM client configured. Automatically permitting generation.")
            return CitationPreflightResult(
                verdict="SUFFICIENT",
                reason="Bypassed preflight due to missing LLM client configuration.",
                gaps=[],
                proceed=True
            )

        try:
            # Format context block
            context_text = self._format_context(results)
            
            # Format prompt using PromptManager
            prompt = self.prompt_manager.get_prompt(
                "citation_check_preflight",
                query=query,
                context=context_text
            )

            # Call LLM
            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.config.get("llm", {}).get("max_tokens_to_sample", 1024)
            )
            response_text = (response.choices[0].message.content or "").strip()
            
            # Parse components
            verdict, reason, gaps = self._parse_preflight_response(response_text)
            
            # Normalize verdict
            if verdict not in self._verdict_levels:
                logger.warning(f"Unknown verdict returned: '{verdict}'. Normalizing to INSUFFICIENT.")
                verdict = "INSUFFICIENT"

            # Determine whether to proceed based on hierarchical comparison
            min_lvl = self._verdict_levels.get(self.min_verdict, 2)  # Default min level is PARTIAL (2)
            current_lvl = self._verdict_levels.get(verdict, 1)
            
            proceed = current_lvl >= min_lvl

            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"Citation preflight evaluation completed in {latency_ms:.2f}ms. "
                f"Verdict: '{verdict}' (Proceed: {proceed}). Reason: {reason}"
            )

            return CitationPreflightResult(
                verdict=verdict,
                reason=reason,
                gaps=gaps,
                proceed=proceed
            )

        except Exception as e:
            error_msg = f"Failed to execute preflight gate evaluation: {str(e)}"
            logger.error(error_msg)
            raise CitationGateError(error_msg) from e
