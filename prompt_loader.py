import json
import os
from pathlib import Path


def load_prompt_text(env_var_name, fallback_text, logger, env=None):
    source_env = os.environ if env is None else env
    configured_path = source_env.get(env_var_name)
    if not configured_path:
        return fallback_text

    try:
        return Path(configured_path).read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "Failed to load prompt file from %s=%s: %s. Using fallback prompt.",
            env_var_name,
            configured_path,
            exc,
        )
        return fallback_text


def load_json_file(env_var_name, fallback_value, logger, validator, env=None):
    source_env = os.environ if env is None else env
    configured_path = source_env.get(env_var_name)
    if not configured_path:
        return fallback_value

    try:
        loaded_value = json.loads(Path(configured_path).read_text(encoding="utf-8"))
        return validator(loaded_value)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning(
            "Failed to load JSON file from %s=%s: %s. Using fallback value.",
            env_var_name,
            configured_path,
            exc,
        )
        return fallback_value
