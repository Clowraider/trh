import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

os.environ.setdefault(
    "ARTICLE_WRITER_SYSTEM_PROMPT_FILE",
    str(PROJECT_ROOT / "prompts/article_writer_system_prompt.txt"),
)
os.environ.setdefault(
    "ARTICLE_WRITER_USER_PROMPT_FILE",
    str(PROJECT_ROOT / "prompts/article_writer_user_prompt.txt"),
)
os.environ.setdefault(
    "ARTICLE_CATEGORIES_FILE",
    str(PROJECT_ROOT / "prompts/article_categories.json"),
)
os.environ.setdefault(
    "EDITOR_JEFE_SYSTEM_PROMPT_FILE",
    str(PROJECT_ROOT / "prompts/editor_jefe_system_prompt.txt"),
)
os.environ.setdefault(
    "EDITORIAL_CONTROL_SYSTEM_PROMPT_FILE",
    str(PROJECT_ROOT / "prompts/editorial_control_system_prompt.txt"),
)
os.environ.setdefault(
    "EDITORIAL_CONTROL_RULES_FILE",
    str(PROJECT_ROOT / "prompts/editorial_control_rules.json"),
)
