import json
import re
from typing import Any

from ....clients.protocol import FAST_SIGNAL_KEYS
from ....utils.constants import VISION_DIMS


def build_omlx_structured_outputs(schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
    _ = schema_name
    return {"json": schema}


def build_omlx_response_format_json_schema(
    schema_name: str, schema: dict[str, Any]
) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "schema": schema,
            "strict": True,
        },
    }


def build_omlx_vision_messages(
    prompt: str, img_b64: str, *, system_prompt: str
) -> list[dict[str, Any]]:
    user_content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
    ]
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _extract_omlx_message(body: dict) -> dict[str, Any]:
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError(f"Malformed OMLX response payload: {body!r}") from error
    if not isinstance(message, dict):
        raise ValueError(f"Malformed OMLX message payload: {message!r}")
    return message


def _extract_message_text(message: dict[str, Any]) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        ]
        joined = "".join(text_parts)
        if joined:
            return joined
    return None


def _load_strict_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        raise ValueError(
            f"OMLX structured response must be a strict JSON object, got: {stripped[:200]!r}"
        )
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"OMLX structured response must be valid JSON, got: {stripped[:200]!r}"
        ) from error
    if not isinstance(data, dict):
        raise ValueError(
            f"OMLX structured response must decode to a JSON object, got: {type(data).__name__}"
        )
    return data


def extract_omlx_structured_dict(body: dict) -> dict[str, Any]:
    message = _extract_omlx_message(body)

    parsed = message.get("parsed")
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, str):
        return _load_strict_json_object(parsed)

    content = _extract_message_text(message)
    if isinstance(content, str) and content.strip():
        return _load_strict_json_object(content)

    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        raise ValueError(f"OMLX refused structured output: {refusal.strip()}")

    raise ValueError(f"Empty or non-text OMLX structured response: {message!r}")


def extract_omlx_structured_json_text(body: dict) -> str:
    return json.dumps(extract_omlx_structured_dict(body), ensure_ascii=False)


def validate_omlx_fast_score_payload(data: dict[str, Any]) -> None:
    keys = set(data)
    required = set(FAST_SIGNAL_KEYS)
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing or extra:
        raise ValueError(
            "OMLX fast screening payload must contain exactly "
            f"{list(FAST_SIGNAL_KEYS)}, got missing={missing} extra={extra}"
        )
    for key in FAST_SIGNAL_KEYS:
        value = data.get(key)
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"OMLX fast screening payload '{key}' must be numeric, got: {type(value).__name__}"
            )


def validate_omlx_full_score_payload(data: dict[str, Any]) -> None:
    required = {"scene", "scene_raw", *VISION_DIMS}
    keys = set(data)
    missing = sorted(required - keys)
    extra = sorted((keys - required) - {"overall"})
    if missing:
        raise ValueError(f"OMLX full score payload is missing required keys: {missing}")
    if extra:
        raise ValueError(f"OMLX full score payload has unexpected keys: {extra}")

    if not isinstance(data.get("scene"), str) or not data["scene"].strip():
        raise ValueError("OMLX full score payload 'scene' must be a non-empty string")
    if not isinstance(data.get("scene_raw"), str):
        raise ValueError("OMLX full score payload 'scene_raw' must be a string")
    for dim in VISION_DIMS:
        value = data.get(dim)
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"OMLX full score payload '{dim}' must be numeric, got: {type(value).__name__}"
            )


def extract_omlx_message_content(body: dict) -> str:
    message = _extract_omlx_message(body)

    content = _extract_message_text(message)
    if isinstance(content, str):
        stripped = content.strip()
        if stripped:
            return stripped

    parsed = message.get("parsed")
    if parsed is not None:
        return json.dumps(parsed, ensure_ascii=False)

    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        return refusal.strip()

    raise ValueError(f"Empty or non-text vision response: {message!r}")


def omlx_structured_json_present(text: str) -> bool:
    from ....clients.protocol import extract_last_json_object

    try:
        extract_last_json_object(text)
    except ValueError:
        return False
    return True


def extract_post_sentence_from_text(text: str) -> str | None:
    candidates: list[str] = []
    for match in re.findall(r'["“]([^"”\n]{2,120}[。！？])["”]?', text):
        candidates.append(match.strip())
    for match in re.findall(r"[\u4e00-\u9fff][^\n]{1,120}[。！？]", text):
        candidates.append(match.strip())

    filtered: list[str] = []
    for candidate in candidates:
        lowered = candidate.lower()
        if not re.search(r"[\u4e00-\u9fff]", candidate):
            continue
        if any(
            token in candidate
            for token in ("组内问题", "拍摄建议", "Photo score line", "Group context")
        ):
            continue
        if any(
            token in lowered
            for token in ("thinking process", "schema", "string", "todo", "tbd", "n/a", "na")
        ):
            continue
        if "{" in candidate or "}" in candidate or ":" in candidate:
            continue
        filtered.append(candidate)

    if not filtered:
        return None
    return filtered[-1]
