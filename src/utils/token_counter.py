import logging
from typing import Dict
import tiktoken

# Initialize structured logging
logger = logging.getLogger("rag_system.utils.token_counter")


class TokenCounterError(Exception):
    """Raised when token counting or encoding retrieval fails."""
    pass


def get_encoder(encoding_name: str = "cl100k_base") -> tiktoken.Encoding:
    """Retrieves a tiktoken encoder by name.

    Args:
        encoding_name: Name of the tiktoken encoding to retrieve.

    Returns:
        The tiktoken.Encoding instance.

    Raises:
        TokenCounterError: If the encoding is unknown or failed to load.
    """
    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception as e:
        error_msg = f"Failed to retrieve tiktoken encoding '{encoding_name}': {str(e)}"
        logger.error(error_msg)
        raise TokenCounterError(error_msg) from e


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Calculates the number of tokens in a given text string.

    Args:
        text: The string to tokenize and count.
        encoding_name: Tiktoken encoding name (default: 'cl100k_base').

    Returns:
        The total number of tokens.

    Raises:
        TokenCounterError: If tokenization fails.
    """
    if not isinstance(text, str):
        error_msg = f"Expected string for token counting, got {type(text)}"
        logger.error(error_msg)
        raise TokenCounterError(error_msg)

    try:
        encoder = get_encoder(encoding_name)
        return len(encoder.encode(text))
    except TokenCounterError:
        raise
    except Exception as e:
        error_msg = f"Token count operation failed: {str(e)}"
        logger.error(error_msg)
        raise TokenCounterError(error_msg) from e


def truncate_to_token_limit(text: str, max_tokens: int, encoding_name: str = "cl100k_base") -> str:
    """Truncates a text string so that it fits within a maximum token limit.

    Args:
        text: The input text to truncate.
        max_tokens: The maximum number of tokens allowed.
        encoding_name: Tiktoken encoding name (default: 'cl100k_base').

    Returns:
        The truncated string.

    Raises:
        TokenCounterError: If the truncation/tokenization fails.
    """
    if max_tokens < 0:
        error_msg = f"Max tokens must be non-negative, got {max_tokens}"
        logger.error(error_msg)
        raise TokenCounterError(error_msg)

    try:
        encoder = get_encoder(encoding_name)
        tokens = encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        return encoder.decode(truncated_tokens)
    except TokenCounterError:
        raise
    except Exception as e:
        error_msg = f"Text truncation failed: {str(e)}"
        logger.error(error_msg)
        raise TokenCounterError(error_msg) from e
