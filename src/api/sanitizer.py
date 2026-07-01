import re
import logging
from typing import Dict, Any, Optional

# Define audit logging stream
audit_logger = logging.getLogger("rag_system.audit.sanitizer")
logger = logging.getLogger("rag_system.api.sanitizer")

# Patterns indicating typical prompt injection attempts to override context instructions
INJECTION_PATTERNS = [
    r"ignore (previous|prior|all) instructions",
    r"you are now",
    r"act as (DAN|admin|root|system)",
    r"developer mode",
    r"jailbreak",
    r"reveal (all|every|previous) (queries|conversations|keys)",
    r"print (your|the) (system prompt|instructions)",
    r"repeat (everything|all) (above|before)",
    r"SYSTEM\s*:",
    r"<\|system\|>",
    r"\[INST\]",
    r"###\s*instruction",
]


class SanitizationError(Exception):
    """Raised when user input fails security sanitization gates."""
    pass


class QuerySanitizer:
    """Sanitizes user input queries by stripping script/HTML tags, limiting lengths, and checking for injections."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initializes the QuerySanitizer.

        Args:
            config: System configuration dictionary.
        """
        self.config = config
        sec_conf = config.get("security", {})
        self.max_query_length: int = sec_conf.get("max_query_length", 500)

        # Precompile regex injection patterns for execution speed
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

    def _strip_html(self, text: str) -> str:
        """Strips HTML tags and script elements from a string using regex."""
        # Strip script tags and content
        clean = re.sub(r"<script.*?>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Strip generic HTML tags
        clean = re.sub(r"<[^>]*>", "", clean)
        return clean

    def sanitize_query(self, query: str, request_id: str = "N/A", client_ip: str = "unknown") -> str:
        """Validates and cleans a user query string.

        Args:
            query: The raw query input.
            request_id: Request tracking ID.
            client_ip: Requester IP address.

        Returns:
            Sanitized query string.

        Raises:
            SanitizationError: If query contains injection indicators or is blank.
        """
        if not query or not query.strip():
            raise SanitizationError("Query string cannot be empty.")

        # 1. Strip HTML and script tags
        sanitized = self._strip_html(query.strip())
        
        # Check if stripping changed text and log audit event
        if sanitized != query.strip():
            audit_logger.warning(
                f"[{request_id}] IP {client_ip} sent query with HTML/Script tags. Original: '{query}' | Sanitized: '{sanitized}'"
            )

        # 2. Check for Prompt Injection / Instruction Override attempts
        for pattern in self._compiled_patterns:
            if pattern.search(sanitized):
                audit_logger.warning(
                    f"[{request_id}] Security Block: IP {client_ip} attempted prompt injection! Pattern: '{pattern.pattern}' | Query: '{sanitized}'"
                )
                raise SanitizationError("Query contains disallowed patterns.")

        # 3. Enforce maximum query length
        if len(sanitized) > self.max_query_length:
            logger.info(
                f"[{request_id}] IP {client_ip} query length ({len(sanitized)}) exceeded limit ({self.max_query_length}). Truncating."
            )
            sanitized = sanitized[:self.max_query_length].strip()

        return sanitized


class PromptInjectionDetector:
    """Detects prompt injection attempts in user queries."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initializes the PromptInjectionDetector."""
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

    def detect_injection(self, query: str) -> bool:
        """Returns True if any prompt injection pattern matches the query."""
        for pattern in self._compiled_patterns:
            if pattern.search(query):
                return True
        return False


# Maintain backward compatibility alias
InputSanitizer = QuerySanitizer
