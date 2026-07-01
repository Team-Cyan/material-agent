import json
import re

from ....utils.constants import LEGACY_SCENE_MIGRATIONS, SCENE_LABELS, SCENE_LIST, VISION_DIMS

_SCENE_SET = set(SCENE_LIST)
_SCENE_LABEL_SET = set(SCENE_LABELS.values())
_LEGACY_SCENE_SET = {scene.lower() for scene in LEGACY_SCENE_MIGRATIONS}


def _extract_last_number_for_label(text: str, label: str) -> float | None:
    pattern = re.compile(
        rf'(?is)(?:\*\*)?[`"\']?{re.escape(label)}[`"\']?(?:\*\*)?\s*[:=]\s*(-?\d+(?:\.\d+)?)'
    )
    matches = [float(match.group(1)) for match in pattern.finditer(text)]
    return matches[-1] if matches else None


def _extract_section_score(text: str, label: str) -> float | None:
    pattern = re.compile(
        rf'(?is)(?:^|\n)\s*\d+\.\s*(?:\*\*)?[`"\']?{re.escape(label)}[`"\']?(?:\*\*)?\s*:'
        rf'.{{0,400}}?\bscore\b\s*[:=]\s*(-?\d+(?:\.\d+)?)'
    )
    matches = [float(match.group(1)) for match in pattern.finditer(text)]
    return matches[-1] if matches else None


def _extract_scene_from_prose(text: str) -> str:
    explicit_pattern = re.compile(
        r'(?is)(?:\*\*)?[`"\']?scene[`"\']?(?:\*\*)?\s*[:=]\s*["“]?([a-z_]+)["”]?'
    )
    explicit = [match.group(1).lower() for match in explicit_pattern.finditer(text)]
    explicit = [scene for scene in explicit if scene in _SCENE_SET]
    if explicit:
        return explicit[-1]

    decision_pattern = re.compile(
        rf'(?is)["“]?({"|".join(re.escape(scene) for scene in SCENE_LIST)})["”]?\s+'
        r'(?:fits best|is the correct category|is correct|is the most appropriate|is most appropriate)'
    )
    decisions = [match.group(1).lower() for match in decision_pattern.finditer(text)]
    if decisions:
        return decisions[-1]

    return "other"


def _extract_scene_raw_from_prose(text: str) -> str:
    patterns = [
        re.compile(r'(?is)(?:\*\*)?[`"\']?scene_raw[`"\']?(?:\*\*)?\s*[:=]\s*["“]([^"”\n]+)["”]'),
        re.compile(r'(?is)(?:\*\*)?[`"\']?scene_raw[`"\']?(?:\*\*)?\s*[:=]\s*([^\n(]+)'),
    ]
    for pattern in patterns:
        matches = [match.group(1).strip() for match in pattern.finditer(text)]
        matches = [value for value in matches if value]
        if matches:
            return matches[-1]

    chinese_quotes = re.findall(r'["“]([\u4e00-\u9fff][^"”\n]+)["”]', text)
    if chinese_quotes:
        return chinese_quotes[-1].strip()
    return ""


def _extract_prose_vision_response(text: str) -> dict | None:
    scene = _extract_scene_from_prose(text)
    scene_raw = _extract_scene_raw_from_prose(text)
    scores = {}
    for dim in VISION_DIMS:
        value = _extract_last_number_for_label(text, dim)
        if value is None:
            value = _extract_section_score(text, dim)
        scores[dim] = value
    if all(value is None for value in scores.values()):
        return None

    data = {"scene": scene, "scene_raw": scene_raw}
    for dim, value in scores.items():
        if value is not None:
            data[dim] = value
    return data


def clamp_scores(data: dict) -> dict:
    for dim in VISION_DIMS:
        try:
            data[dim] = round(max(0.0, min(10.0, float(data.get(dim, 0)))), 2)
        except (TypeError, ValueError):
            data[dim] = 0.0
    return data


def parse_vision_response(text: str) -> dict:
    from ....clients.protocol import extract_last_json_object

    arr_match = re.search(r"\[\s*([\d.,\s]+)\]", text)
    if arr_match and text.find("{") == -1:
        nums = [float(x) for x in re.findall(r"[\d.]+", arr_match.group(1))]
        nums = (nums + [0.0] * len(VISION_DIMS))[: len(VISION_DIMS)]
        if nums and max(nums) <= 1.0:
            nums = [n * 10 for n in nums]
        result = dict(zip(VISION_DIMS, nums))
        result["scene"] = "other"
        result["scene_raw"] = ""
        return clamp_scores(result)

    try:
        data = extract_last_json_object(text)
    except ValueError:
        prose_data = _extract_prose_vision_response(text)
        if prose_data is not None:
            return clamp_scores(prose_data)
        text = re.sub(r"<(\d+(?:\.\d+)?)>", r"\1", text)
        text = re.sub(r",\s*([}\]])", r"\1", text)
        start = text.find("{")
        if start != -1:
            candidate = text[start:] + "}"
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError as error:
                raise ValueError(f"Cannot parse JSON from: {candidate[:500]!r}") from error
        else:
            raise

    scene = data.get("scene", "other")
    if scene not in _SCENE_SET:
        scene = "other"
    data["scene"] = scene
    data["scene_raw"] = data.get("scene_raw", "") or ""
    normalized_scene_raw = data["scene_raw"].strip()
    if (
        normalized_scene_raw.lower() in _SCENE_SET
        or normalized_scene_raw.lower() in _LEGACY_SCENE_SET
        or normalized_scene_raw in _SCENE_LABEL_SET
    ):
        data["scene_raw"] = ""
    return clamp_scores(data)


def build_vision_prompt(output_language: str = "zh") -> str:
    from ....clients.prompts import build_full_prompt

    return build_full_prompt(output_language=output_language)
