"""Safe extraction of JSON objects from noisy LLM text responses."""

import json


def extract_json_object(text):
    """Return the first parseable JSON object from a possibly noisy string.

    OpenAI-compatible proxies may wrap model output in markdown fences or add
    explanatory prose around the JSON. This helper strips those artifacts and
    falls back to a standard parse for already-clean responses.
    """
    if not isinstance(text, str):
        raise ValueError("response content is not a string")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(
            line for line in cleaned.splitlines()
            if not line.strip().startswith("```")
        ).strip()

    start = cleaned.find("{")
    if start == -1:
        return json.loads(cleaned)

    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(cleaned[start:], start=start):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start:index + 1])

    raise ValueError("no balanced JSON object found")
