import os
import logging

logger = logging.getLogger("rag_system.utils.secret_loader")

def get_secret(env_var_name: str, fallback_env_name: str = None, default: str = "") -> str:
    """Loads a secret from a file path specified by an env var ending in '_FILE' (e.g., Docker Secrets)

    or falls back to direct environment variables.
    """
    # 1. Check for filename environment variable (e.g., NVIDIA_API_KEY_FILE)
    file_path_env = os.environ.get(f"{env_var_name}_FILE")
    if file_path_env:
        if os.path.exists(file_path_env):
            try:
                with open(file_path_env, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                logger.error(f"Failed to read secret from file '{file_path_env}': {str(e)}")
        else:
            logger.warning(f"Secret file path '{file_path_env}' (specified by {env_var_name}_FILE) does not exist.")

    # 2. Check for direct environment variable (e.g., NVIDIA_API_KEY)
    val = os.environ.get(env_var_name)
    if val:
        return val

    # 3. Check for secondary fallback env name (e.g., NVIDIA_NIM_API_KEY)
    if fallback_env_name:
        val = os.environ.get(fallback_env_name)
        if val:
            return val

    return default
