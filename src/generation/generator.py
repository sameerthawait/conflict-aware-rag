import time
import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from openai import OpenAI
from src.ingestion.vector_store import SearchResult
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.generation.generator")


class GeneratorError(Exception):
    """Raised when LLM response generation or parsing fails."""
    pass


class GenerationResponse:
    """Encapsulates the structured outputs parsed from the generator completion."""

    def __init__(
        self,
        answer: str,
        sources_used: List[str],
        confidence: str,
        missing_information: str,
        raw_response: str
    ) -> None:
        """Initializes GenerationResponse.

        Args:
            answer: The main body of the answer.
            sources_used: List of parsed source references.
            confidence: Confidence level classification (High/Medium/Low).
            missing_information: Details of missing data requested.
            raw_response: Complete raw LLM output text.
        """
        self.answer = answer.strip()
        self.sources_used = [s.strip() for s in sources_used if s.strip()]
        self.confidence = confidence.strip().capitalize()
        self.missing_information = missing_information.strip()
        self.raw_response = raw_response

    def __repr__(self) -> str:
        return f"GenerationResponse(confidence={self.confidence}, sources_count={len(self.sources_used)})"


class Generator:
    """Generates structured, citation-based answers from the LLM based on retrieved contexts."""

    def __init__(self, config: Dict[str, Any], prompt_manager: PromptManager, client: Optional[OpenAI] = None) -> None:
        """Initializes the Generator.

        Args:
            config: System configuration dictionary.
            prompt_manager: PromptManager instance.
            client: Optional OpenAI client.
        """
        self.config = config
        self.prompt_manager = prompt_manager
        self.client = client

        llm_conf = config.get("llm", {})
        self.llm_model: str = llm_conf.get("model_name", "meta/llama-3.1-70b-instruct")
        self.temperature: float = llm_conf.get("temperature", 0.0)
        self.max_tokens: int = llm_conf.get("max_tokens_to_sample", 1024)

        gate_conf = config.get("quality_gates", {})
        self.refusal_message: str = gate_conf.get(
            "refusal_message",
            "I am sorry, but I could not find any relevant information in the provided context to answer your query."
        )

    def _format_context(self, results: List[SearchResult]) -> str:
        """Helper to construct context blocks matching prompt format.

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

    def _parse_response(self, text: str) -> GenerationResponse:
        """Robustly parses LLM response into structured blocks using section boundary lookaheads.

        Args:
            text: Raw string output from LLM.

        Returns:
            A GenerationResponse.
        """
        # Parse ANSWER section
        answer_match = re.search(
            r"ANSWER:\s*(.*?)(?=\s*SOURCES USED:|\s*CONFIDENCE:|\s*MISSING INFORMATION:|$)",
            text,
            re.DOTALL | re.IGNORECASE
        )
        # Parse SOURCES USED section
        sources_match = re.search(
            r"SOURCES USED:\s*(.*?)(?=\s*ANSWER:|\s*CONFIDENCE:|\s*MISSING INFORMATION:|$)",
            text,
            re.DOTALL | re.IGNORECASE
        )
        # Parse CONFIDENCE section
        confidence_match = re.search(
            r"CONFIDENCE:\s*(.*?)(?=\s*ANSWER:|\s*SOURCES USED:|\s*MISSING INFORMATION:|$)",
            text,
            re.DOTALL | re.IGNORECASE
        )
        # Parse MISSING INFORMATION section
        missing_match = re.search(
            r"MISSING INFORMATION:\s*(.*?)(?=\s*ANSWER:|\s*SOURCES USED:|\s*CONFIDENCE:|$)",
            text,
            re.DOTALL | re.IGNORECASE
        )

        answer = answer_match.group(1).strip() if answer_match else ""
        
        sources_raw = sources_match.group(1).strip() if sources_match else ""
        sources = [line.strip().lstrip("-* ").strip() for line in sources_raw.split("\n") if line.strip()]
        
        confidence = confidence_match.group(1).strip() if confidence_match else "Low"
        # Validate confidence string
        if confidence.lower() not in ["high", "medium", "low"]:
            confidence = "Low"

        missing_info = missing_match.group(1).strip() if missing_match else "None"

        # Fallback if the parser completely failed to find sections
        if not answer and "ANSWER:" not in text:
            logger.warning("Failed to locate ANSWER section header. Returning unparsed text as answer.")
            answer = text.strip()

        return GenerationResponse(
            answer=answer,
            sources_used=sources,
            confidence=confidence,
            missing_information=missing_info,
            raw_response=text
        )

    def generate(self, query: str, results: List[SearchResult]) -> Tuple[GenerationResponse, float]:
        """Generates RAG answer.

        Args:
            query: The user search query.
            results: Chunks retrieved.

        Returns:
            A tuple of (GenerationResponse, latency_ms).

        Raises:
            GeneratorError: If API call fails.
        """
        start_time = time.perf_counter()
        logger.info(f"Generating structured response for query: '{query}'")

        if not self.client:
            logger.warning("No LLM client configured for Generator. Returning refusal message.")
            latency_ms = (time.perf_counter() - start_time) * 1000
            return GenerationResponse(
                answer=self.refusal_message,
                sources_used=[],
                confidence="Low",
                missing_information="Bypassed due to missing client configuration.",
                raw_response=self.refusal_message
            ), latency_ms

        try:
            # Format context block
            context_text = self._format_context(results)
            
            # Format prompt using PromptManager
            prompt = self.prompt_manager.get_prompt(
                "rag_system_prompt",
                query=query,
                context=context_text,
                refusal_message=self.refusal_message
            )

            # Call LLM
            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            response_text = response.choices[0].message.content or ""

            # Parse segments
            gen_response = self._parse_response(response_text)
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            logger.info(f"LLM Generation completed in {latency_ms:.2f}ms. Parsed {len(gen_response.sources_used)} sources.")
            return gen_response, latency_ms

        except Exception as e:
            error_msg = f"Failed to execute LLM answer generation: {str(e)}"
            logger.error(error_msg)
            raise GeneratorError(error_msg) from e
