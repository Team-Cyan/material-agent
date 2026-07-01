import re
from typing import Protocol, runtime_checkable

from ..utils.json_extract import extract_last_json_object


@runtime_checkable
class BackendClient(Protocol):
    async def score_image(self, jpeg_bytes: bytes) -> dict: ...

    async def score_image_fast(self, jpeg_bytes: bytes) -> float | dict[str, float]: ...

    async def generate_group_commentary(self, group_data: str) -> str: ...

    async def generate_post_commentary(self, score_line: str, group_commentary: str) -> str: ...


def drop_legacy_full_score_overall(data: dict) -> dict:
    if "overall" not in data:
        return data
    return {key: value for key, value in data.items() if key != "overall"}


FAST_SIGNAL_KEYS = (
    "technical_ok",
    "subject_clear",
    "composition_ok",
    "usable_for_selection",
)


def _clamp_score01(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(1.0, score))


def parse_fast_screening(text: str | dict[str, object]) -> dict[str, float]:
    data = extract_last_json_object(text) if isinstance(text, str) else text
    if not isinstance(data, dict):
        raise ValueError("No reliable fast score")
    missing = [key for key in FAST_SIGNAL_KEYS if key not in data]
    extra = [key for key in data if key not in FAST_SIGNAL_KEYS]
    if missing or extra:
        raise ValueError("No reliable fast score")
    return {key: _clamp_score01(data.get(key)) for key in FAST_SIGNAL_KEYS}


def parse_fast_score(text: str) -> float:
    try:
        data = extract_last_json_object(text)
        if "overall" in data:
            val = data["overall"]
        elif "score" in data:
            val = data["score"]
        elif "rating" in data:
            val = data["rating"]
        else:
            raise ValueError("No reliable fast score")
        score = float(val)
        if 0 < score < 1.0:
            score *= 10
        return max(0.0, min(10.0, score))
    except (ValueError, TypeError):
        pass

    labeled = re.search(
        r'(?i)(?:[`"\']?(?:overall|score|rating)[`"\']?)\s*[:=]\s*(-?\d+(?:\.\d+)?)',
        text,
    )
    if labeled:
        score = float(labeled.group(1))
        if 0 < score < 1.0:
            score *= 10
        return max(0.0, min(10.0, score))

    narrative = re.search(
        r"(?is)\b(?:overall|score|rating)\b.{0,120}?\b(?:is|was|be|looks\s+like|estimated\s+at|likely|around|approximately|about|maybe|roughly)\s*(-?\d+(?:\.\d+)?)\b",
        text,
    )
    if narrative:
        span = narrative.group(0)
        if re.search(r"\bscale\s+of\s+-?\d+(?:\.\d+)?\s+to\s+-?\d+(?:\.\d+)?\b", span, re.I):
            raise ValueError("No reliable fast score")
        score = float(narrative.group(1))
        if 0 < score < 1.0:
            score *= 10
        return max(0.0, min(10.0, score))

    stripped = text.strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", stripped):
        score = float(stripped)
        if 0 < score < 1.0:
            score *= 10
        return max(0.0, min(10.0, score))

    raise ValueError("No reliable fast score")
