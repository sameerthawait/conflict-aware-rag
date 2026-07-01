import os
import logging
import re
from typing import Any, Dict, Set
import yaml

# Initialize structured logging
logger = logging.getLogger("rag_system.utils.prompt_manager")


class PromptLoadError(Exception):
    """Raised when prompt configurations cannot be loaded or parsed."""
    pass


class PromptFormatError(Exception):
    """Raised when formatting a prompt fails due to missing or mismatched variables."""
    pass


class PromptManager:
    """Manages system prompt loading, version verification, and template formatting."""

    def __init__(self, prompts_path: str = "prompts/prompts.yaml") -> None:
        """Initializes PromptManager by loading configuration from prompts.yaml.

        Args:
            prompts_path: Path to the prompts configuration file.

        Raises:
            PromptLoadError: If the prompts file is missing or invalid.
        """
        self.prompts_path = prompts_path
        self._prompts: Dict[str, Dict[str, Any]] = {}
        self._load_prompts()

    def _load_prompts(self) -> None:
        """Loads prompt specifications from the prompts YAML file."""
        if not os.path.exists(self.prompts_path):
            error_msg = f"Prompts file not found at: {self.prompts_path}"
            logger.error(error_msg)
            raise PromptLoadError(error_msg)

        try:
            with open(self.prompts_path, "r", encoding="utf-8") as f:
                self._prompts = yaml.safe_load(f) or {}
        except Exception as e:
            error_msg = f"Failed to parse prompts configuration: {str(e)}"
            logger.error(error_msg)
            raise PromptLoadError(error_msg) from e

        logger.info(f"Successfully loaded prompts from {self.prompts_path}")

    def get_prompt(self, prompt_name: str, **kwargs: Any) -> str:
        """Formats and returns a specific prompt template.

        Args:
            prompt_name: Name of the prompt to retrieve (e.g., 'rag_system_prompt').
            **kwargs: Template variables and values for formatting.

        Returns:
            The formatted prompt string.

        Raises:
            PromptLoadError: If the requested prompt does not exist.
            PromptFormatError: If required placeholders are missing from arguments.
        """
        if prompt_name not in self._prompts:
            error_msg = f"Requested prompt '{prompt_name}' is not configured in prompts.yaml"
            logger.error(error_msg)
            raise PromptLoadError(error_msg)

        prompt_config = self._prompts[prompt_name]
        template: str = prompt_config.get("template", "")
        version: str = prompt_config.get("version", "unknown")

        logger.debug(f"Formatting prompt '{prompt_name}' (version: {version})")

        # Validate variables in template
        required_vars = self._extract_placeholders(template)
        provided_vars = set(kwargs.keys())
        missing_vars = required_vars - provided_vars

        if missing_vars:
            error_msg = (
                f"Cannot format prompt '{prompt_name}'. Missing required template variables: {missing_vars}. "
                f"Required: {required_vars}, Provided: {provided_vars}"
            )
            logger.error(error_msg)
            raise PromptFormatError(error_msg)

        try:
            formatted_prompt = template.format(**kwargs)
        except Exception as e:
            error_msg = f"Failed to format prompt '{prompt_name}' due to error: {str(e)}"
            logger.error(error_msg)
            raise PromptFormatError(error_msg) from e

        logger.info(f"Prompt '{prompt_name}' (v{version}) formatted successfully.")
        return formatted_prompt

    def get_version(self, prompt_name: str) -> str:
        """Retrieves the version of a specific prompt template.

        Args:
            prompt_name: Name of the prompt to check.

        Returns:
            The version string (e.g., '1.0.0').
        """
        if prompt_name not in self._prompts:
            raise PromptLoadError(f"Prompt '{prompt_name}' not found.")
        return str(self._prompts[prompt_name].get("version", "unknown"))

    def _extract_placeholders(self, template: str) -> Set[str]:
        """Extracts placeholder names within single braces from a string template."""
        # Finds matches of type {variable_name} while ignoring double-braced JSON constructs
        return set(re.findall(r"(?<!\{)\{([a-zA-Z0-9_]+)\}(?!\})", template))
