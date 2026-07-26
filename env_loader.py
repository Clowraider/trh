from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


def load_project_env(path=None, environ=None):
    target_environ = os.environ if environ is None else environ
    env_path = DEFAULT_ENV_PATH if path is None else Path(path)

    if not env_path.exists():
        return False

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            target_environ.setdefault(key, value)

    return True
