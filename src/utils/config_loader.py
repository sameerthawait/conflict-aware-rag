import os
import re
import logging
from functools import lru_cache
from typing import Any, Dict
import yaml
from dotenv import load_dotenv

load_dotenv()

# Initialize structured logging
logger = logging.getLogger("rag_system.utils.config_loader")


class ConfigLoadError(Exception):
    """Raised when the configuration fails to load or parse."""
    pass


def _resolve_env_vars(val: Any) -> Any:
    """Recursively replaces ${VAR:-default} and ${VAR} placeholders with environment variables or secrets."""
    from src.utils.secret_loader import get_secret
    if isinstance(val, str):
        # Match pattern like ${VAR:-default} or ${VAR}
        pattern = re.compile(r'\$\{(\w+)(?::-([^}]+))?\}')
        match = pattern.match(val)
        if match:
            var_name = match.group(1)
            default_val = match.group(2) or ""
            fallback_var = "NVIDIA_NIM_API_KEY" if var_name == "NVIDIA_API_KEY" else ("NVIDIA_API_KEY" if var_name == "NVIDIA_NIM_API_KEY" else None)
            return get_secret(var_name, fallback_env_name=fallback_var, default=default_val)
        
        # Replace occurrences of ${VAR} inside a string
        def replace(m):
            var = m.group(1)
            default = m.group(2) or ""
            fallback_var = "NVIDIA_NIM_API_KEY" if var == "NVIDIA_API_KEY" else ("NVIDIA_API_KEY" if var == "NVIDIA_NIM_API_KEY" else None)
            return get_secret(var, fallback_env_name=fallback_var, default=default)
        
        return pattern.sub(replace, val)
    elif isinstance(val, dict):
        return {k: _resolve_env_vars(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_resolve_env_vars(item) for item in val]
    return val


@lru_cache(maxsize=1)
def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """Loads configuration from YAML file and applies environment variable overrides.

    Args:
        config_path: Absolute or relative path to the configuration file.

    Returns:
        A dictionary containing all system configuration settings.

    Raises:
        ConfigLoadError: If the file is missing, corrupt, or invalid.
    """
    logger.info(f"Loading configuration from: {config_path}")
    if not os.path.exists(config_path):
        error_msg = f"Configuration file not found at path: {config_path}"
        logger.error(error_msg)
        raise ConfigLoadError(error_msg)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config: Dict[str, Any] = yaml.safe_load(f) or {}
    except Exception as e:
        error_msg = f"Failed to parse YAML configuration: {str(e)}"
        logger.error(error_msg)
        raise ConfigLoadError(error_msg) from e

    # Apply environment variable substitutions
    config = _resolve_env_vars(config)

    # Apply environment variable overrides
    _apply_overrides(config)

    # Validate mandatory structure
    _validate_config(config)

    return config


def _apply_overrides(config: Dict[str, Any]) -> None:
    """Modifies configuration in-place based on defined environment variables."""
    from src.utils.secret_loader import get_secret
    # Check LOG_LEVEL
    log_level = get_secret("LOG_LEVEL")
    if log_level:
        config.setdefault("system", {})["log_level"] = log_level
        logger.info(f"Overrode system.log_level: {log_level}")

    # Check CHROMA_DB_PATH
    chroma_db_path = get_secret("CHROMA_DB_PATH")
    if chroma_db_path:
        config.setdefault("vector_store", {})["persist_directory"] = chroma_db_path
        logger.info(f"Overrode vector_store.persist_directory: {chroma_db_path}")

    # Check LLM_MODEL_NAME
    llm_model_name = get_secret("LLM_MODEL_NAME")
    if llm_model_name:
        config.setdefault("llm", {})["model_name"] = llm_model_name
        logger.info(f"Overrode llm.model_name: {llm_model_name}")

    # Check EMBEDDING_MODEL_NAME
    embedding_model_name = get_secret("EMBEDDING_MODEL_NAME")
    if embedding_model_name:
        config.setdefault("embeddings", {})["model_name"] = embedding_model_name
        logger.info(f"Overrode embeddings.model_name: {embedding_model_name}")

    # Check REDIS_URL
    redis_url = get_secret("REDIS_URL")
    if redis_url:
        config.setdefault("redis", {})["url"] = redis_url
        logger.info(f"Overrode redis.url: {redis_url}")


def _validate_config(config: Dict[str, Any]) -> None:
    """Validates presence of core configuration blocks."""
    required_blocks = ["chunking", "embeddings", "vector_store", "llm", "retrieval"]
    for block in required_blocks:
        if block not in config:
            error_msg = f"Missing mandatory configuration block: '{block}'"
            logger.error(error_msg)
            raise ConfigLoadError(error_msg)
