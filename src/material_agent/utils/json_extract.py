import json
import re


def sanitize_jsonish_text(text: str) -> str:
    text = re.sub(r"<(\d+(?:\.\d+)?)>", r"\1", text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def extract_last_json_object(text: str) -> dict:
    sanitized = sanitize_jsonish_text(text)
    candidates: list[str] = []
    start_index = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(sanitized):
        if start_index is None:
            if char == "{":
                start_index = index
                depth = 1
                in_string = False
                escaped = False
            continue

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidates.append(sanitized[start_index : index + 1])
                start_index = None

    if not candidates:
        raise ValueError(f"No JSON object in response: {sanitized[:500]!r}")

    for candidate in reversed(candidates):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data

    raise ValueError(f"Cannot parse JSON from: {candidates[-1][:500]!r}")
