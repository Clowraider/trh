import json
import os
from pathlib import Path


def _required_path(env_var_name, env):
    source_env = os.environ if env is None else env
    configured_path = source_env.get(env_var_name)
    if not configured_path:
        raise RuntimeError(
            f"Missing required environment variable {env_var_name} for prompt/rules file"
        )
    return Path(configured_path)


def load_prompt_text(env_var_name, logger, env=None):
    configured_path = _required_path(env_var_name, env)

    try:
        return configured_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Prompt file configured by {env_var_name} does not exist: {configured_path}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Failed to read prompt file configured by {env_var_name}: {configured_path} ({exc})"
        ) from exc


def load_json_file(env_var_name, logger, validator, env=None):
    configured_path = _required_path(env_var_name, env)

    try:
        raw_value = configured_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"JSON file configured by {env_var_name} does not exist: {configured_path}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Failed to read JSON file configured by {env_var_name}: {configured_path} ({exc})"
        ) from exc

    try:
        loaded_value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"JSON file configured by {env_var_name} contains invalid JSON: {configured_path} ({exc})"
        ) from exc

    try:
        return validator(loaded_value)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            f"JSON file configured by {env_var_name} contains an invalid value: {configured_path} ({exc})"
        ) from exc
