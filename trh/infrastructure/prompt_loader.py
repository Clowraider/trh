import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_configured_path(configured_path):
    path = Path(configured_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _required_path(env_var_name, env):
    source_env = os.environ if env is None else env
    configured_path = source_env.get(env_var_name)
    if not configured_path:
        raise RuntimeError(
            f"Missing required environment variable {env_var_name} for prompt/rules file"
        )
    return _resolve_configured_path(configured_path)


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
