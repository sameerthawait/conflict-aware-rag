import time
import logging
import re
import yaml
from typing import Dict, List, Any, Tuple, Optional
from openai import OpenAI
from src.ingestion.vector_store import SearchResult
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.generation.hallucination_verifier")


class VerifierError(Exception):
    """Raised when hallucination verification fails."""
    pass


class ClaimAudit:
    """Represents a single audited claim from the generation answer."""

    def __init__(self, claim: str, supported: bool, evidence: str) -> None:
        """Initializes the ClaimAudit.

        Args:
            claim: The statement or assertion being audited.
            supported: Boolean indicating if it is supported by the context.
            evidence: Context citation or description of the discrepancy.
        """
        self.claim = claim
        self.supported = supported
        self.evidence = evidence

    def __repr__(self) -> str:
        return f"ClaimAudit(claim='{self.claim[:20]}...', supported={self.supported})"


class HallucinationVerifierResult:
    """Encapsulates the complete response from the anti-hallucination audit."""

    def __init__(self, verdict: str, claims_audit: List[ClaimAudit], inferred_flags: str) -> None:
        """Initializes the HallucinationVerifierResult.

        Args:
            verdict: Audit verdict ('PASS' or 'FAIL').
            claims_audit: List of ClaimAudit items.
            inferred_flags: List of flagged claims or reasoning.
        """
        self.verdict = verdict.upper().strip()
        self.claims_audit = claims_audit
        self.inferred_flags = inferred_flags

    def __repr__(self) -> str:
        return f"HallucinationVerifierResult(verdict={self.verdict}, audited_claims={len(self.claims_audit)})"


class HallucinationVerifier:
    """Audits generated answers against context documents to check for unsupported claims."""

    def __init__(self, config: Dict[str, Any], prompt_manager: PromptManager, client: Optional[OpenAI] = None) -> None:
        """Initializes the HallucinationVerifier.

        Args:
            config: System configuration dictionary.
            prompt_manager: PromptManager instance.
            client: Optional OpenAI client.
        """
        self.config = config
        self.prompt_manager = prompt_manager
        self.client = client

        gate_conf = config.get("quality_gates", {})
        self.enabled: bool = gate_conf.get("enable_hallucination_verifier", True)
        self.refusal_message: str = gate_conf.get(
            "refusal_message",
            "I am sorry, but I could not find any relevant information in the provided context to answer your query."
        )

        llm_conf = config.get("llm", {})
        self.llm_model: str = llm_conf.get("model_name", "meta/llama-3.1-70b-instruct")
        self.temperature: float = llm_conf.get("temperature", 0.0)

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

    def _parse_verification_response(self, response_text: str) -> Tuple[str, List[ClaimAudit], str]:
        """Parses VERDICT, CLAIMS_AUDIT, and INFERRED_FLAGS from YAML response.

        Args:
            response_text: Raw YAML completion string from LLM.

        Returns:
            Tuple of (verdict, list of claim audits, inferred flags).
        """
        verdict = "PASS"
        claims_audit: List[ClaimAudit] = []
        inferred_flags = "None"

        try:
            # Parse YAML response
            parsed = yaml.safe_load(response_text)
            if isinstance(parsed, dict):
                verdict = str(parsed.get("VERDICT", "PASS")).upper().strip()
                inferred_flags = str(parsed.get("INFERRED_FLAGS", "None"))
                
                raw_audits = parsed.get("CLAIMS_AUDIT", [])
                if isinstance(raw_audits, list):
                    for audit in raw_audits:
                        if isinstance(audit, dict):
                            claim = str(audit.get("claim", ""))
                            supported = bool(audit.get("supported", True))
                            evidence = str(audit.get("evidence", ""))
                            claims_audit.append(ClaimAudit(claim, supported, evidence))
                return verdict, claims_audit, inferred_flags
        except Exception as e:
            logger.warning(f"YAML parsing of hallucination verifier response failed: {str(e)}. Falling back to regex.")

        # Regex fallbacks
        verdict_match = re.search(r"VERDICT:\s*\"?(PASS|FAIL)\"?", response_text, re.IGNORECASE)
        flags_match = re.search(r"INFERRED_FLAGS:\s*\"?([^\n\"]+)\"?", response_text, re.IGNORECASE)
        
        if verdict_match:
            verdict = verdict_match.group(1).upper()
        if flags_match:
            inferred_flags = flags_match.group(1).strip()

        # Extract audit checklist
        claim_blocks = re.findall(
            r"-\s*claim:\s*\"?([^\n\"]+)\"?\s*\n\s*supported:\s*(true|false)\s*\n\s*evidence:\s*\"?([^\n\"]+)\"?",
            response_text,
            re.IGNORECASE
        )
        for c, s, ev in claim_blocks:
            claims_audit.append(ClaimAudit(c, s.lower() == "true", ev.strip()))

        return verdict, claims_audit, inferred_flags

    def verify(self, answer: str, results: List[SearchResult]) -> Tuple[Optional[HallucinationVerifierResult], float]:
        """Audits the generated answer against retrieval context.

        Args:
            answer: Generated response answer.
            results: Chunks retrieved.

        Returns:
            A tuple of (HallucinationVerifierResult (or None if disabled), latency_ms).

        Raises:
            VerifierError: If API communication or processing fails.
        """
        start_time = time.perf_counter()
        
        # Check if disabled
        if not self.enabled:
            logger.info("Hallucination verifier is disabled. Skipping.")
            return None, 0.0

        # Optimization: Bypass audit if answer is empty or matches the refusal message
        if not answer.strip() or answer.strip() == self.refusal_message.strip():
            logger.info("Answer is empty or matches the refusal message. Bypassing hallucination audit.")
            latency_ms = (time.perf_counter() - start_time) * 1000
            return HallucinationVerifierResult(
                verdict="PASS",
                claims_audit=[],
                inferred_flags="Refusal message bypassed."
            ), latency_ms

        if not self.client:
            logger.warning("No LLM client configured for Verifier. Bypassing check.")
            latency_ms = (time.perf_counter() - start_time) * 1000
            return HallucinationVerifierResult(
                verdict="PASS",
                claims_audit=[],
                inferred_flags="Bypassed due to missing client configuration."
            ), latency_ms

        logger.info("Executing anti-hallucination verification audit...")

        try:
            # Format context block
            context_text = self._format_context(results)
            
            # Format prompt using PromptManager
            prompt = self.prompt_manager.get_prompt(
                "anti_hallucination_verifier",
                context=context_text,
                answer=answer
            )

            # Call LLM
            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.config.get("llm", {}).get("max_tokens_to_sample", 1024)
            )
            response_text = response.choices[0].message.content

            # Parse results
            verdict, claims_audit, inferred_flags = self._parse_verification_response(response_text)
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"Hallucination audit completed in {latency_ms:.2f}ms. "
                f"Verdict: '{verdict}' (Claims Audited: {len(claims_audit)})."
            )

            return HallucinationVerifierResult(
                verdict=verdict,
                claims_audit=claims_audit,
                inferred_flags=inferred_flags
            ), latency_ms

        except Exception as e:
            error_msg = f"Failed to execute anti-hallucination verification audit: {str(e)}"
            logger.error(error_msg)
            raise VerifierError(error_msg) from e
