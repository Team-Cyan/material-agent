from ..adapters.models.omlx.contracts import (
    build_omlx_response_format_json_schema,
    build_omlx_structured_outputs,
)
from ..utils.constants import SCENE_LIST, VISION_DIMS

_DIMENSION_GUIDANCE = {
    "subject": "subject appeal, moment strength, and whether the main subject is worth keeping or looking at",
    "composition": "frame organization, crop, balance, negative space, and visual guidance",
    "lighting": "light quality, direction, mood support, and how well the light serves the scene",
    "color": "color harmony, palette control, saturation balance, and color expression",
    "clarity": "focus reliability, visible detail retention, motion blur, noise impact, and overall image cleanness",
    "depth": "spatial layering, foreground/background separation, and sense of depth",
    "mood": "overall mood, style consistency, emotional impact, and memorability",
}

_JSON_ONLY_BY_PRESET = {
    "default": "",
    "gemma": (
        "- return exactly one final JSON object and nothing else\n"
        "- no markdown fences, no commentary, no prefatory text, no trailing notes\n"
    ),
    "qwen3": (
        "- output the final JSON object only\n"
        "- do not include reasoning, explanations, or any extra wrapper text\n"
        "- do not add any keys beyond the required schema\n"
        "- do not echo score context or scene metadata as JSON keys\n"
    ),
}

FAST_SIGNAL_KEYS = (
    "technical_ok",
    "subject_clear",
    "composition_ok",
    "usable_for_selection",
)


def _normalize_prompt_preset(prompt_preset: str | None) -> str:
    normalized = (prompt_preset or "default").strip().lower()
    return normalized if normalized in _JSON_ONLY_BY_PRESET else "default"


def _json_only_instruction(prompt_preset: str | None) -> str:
    return _JSON_ONLY_BY_PRESET[_normalize_prompt_preset(prompt_preset)]


def _extra_instructions(extra_instructions: str | None) -> str:
    extra = (extra_instructions or "").strip()
    if not extra:
        return ""
    return f"Additional guidance:\n{extra}\n"


def _build_response_contract(contract_mode: str, schema_name: str, schema: dict) -> dict:
    normalized = str(contract_mode or "structured_outputs").strip().lower()
    if normalized == "response_format_json_schema":
        return build_omlx_response_format_json_schema(schema_name, schema)
    return build_omlx_structured_outputs(schema_name, schema)


def build_fast_prompt(structured_output: bool = False, prompt_preset: str = "default") -> str:
    json_only = _json_only_instruction(prompt_preset) if structured_output else ""
    schema_fields = ", ".join(f'"{key}": 0.0' for key in FAST_SIGNAL_KEYS)
    if structured_output:
        return (
            "You are a strict photography pre-screening assistant.\n"
            "Look at the image and evaluate whether it is worth keeping or reviewing.\n"
            "Return only the requested screening signal object.\n"
            "Do not return an overall, rating, or final total score.\n"
            "Use this schema:\n"
            "{"
            f"{schema_fields}"
            "}\n"
            "Rules:\n"
            f"{json_only}"
            "- every signal must be a number from 0.0 to 1.0\n"
            "- technical_ok reflects quick confidence that exposure, focus, and noise are acceptable\n"
            "- subject_clear reflects quick confidence that the intended subject is readable\n"
            "- composition_ok reflects quick confidence that framing is not obviously weak\n"
            "- usable_for_selection reflects quick confidence that the frame is worth full scoring\n"
            "- keep the judgment concise and schema-aligned\n"
            "- do not turn the answer into a narrative explanation"
        )
    return (
        "You are a strict photography pre-screening assistant.\n"
        "Look at the image and evaluate whether it is worth keeping or reviewing.\n"
        "Return only the requested screening signal object.\n"
        "Do not return an overall, rating, or final total score.\n"
        "Use this schema:\n"
        "{"
        f"{schema_fields}"
        "}\n"
        "Rules:\n"
        "- every signal must be a number from 0.0 to 1.0\n"
        "- technical_ok reflects quick confidence that exposure, focus, and noise are acceptable\n"
        "- subject_clear reflects quick confidence that the intended subject is readable\n"
        "- composition_ok reflects quick confidence that framing is not obviously weak\n"
        "- usable_for_selection reflects quick confidence that the frame is worth full scoring\n"
        "- keep the judgment concise and schema-aligned\n"
        "- do not turn the answer into a narrative explanation"
    )


def _language_name(output_language: str) -> str:
    return "English" if output_language == "en" else "Chinese"


def _scene_raw_example(output_language: str) -> str:
    return "short English sentence" if output_language == "en" else "中文短句"


def build_full_prompt(
    structured_output: bool = False,
    output_language: str = "zh",
    prompt_preset: str = "default",
    extra_instructions: str | None = None,
) -> str:
    scene_values = ", ".join(SCENE_LIST)
    dim_lines = "\n".join(f"- {dim}: {_DIMENSION_GUIDANCE[dim]}" for dim in VISION_DIMS)
    schema_fields = ", ".join(f'"{dim}": 0.0' for dim in VISION_DIMS)
    language_name = _language_name(output_language)
    scene_raw_example = _scene_raw_example(output_language)
    json_only = _json_only_instruction(prompt_preset) if structured_output else ""
    extra = _extra_instructions(extra_instructions)
    if structured_output:
        return (
            "You are a strict photography evaluator.\n"
            "Analyze the image using the provided scoring contract.\n"
            "Return only the requested scene label and per-dimension scores.\n"
            "Do not return an overall, rating, or final total score.\n"
            "Use this schema:\n"
            "{"
            f'"scene": "one of [{scene_values}]", '
            f'"scene_raw": "{scene_raw_example}", '
            f"{schema_fields}"
            "}\n"
            "Rules:\n"
            f"{json_only}"
            f"- scene must be exactly one of: [{scene_values}]\n"
            "- scene must use English canonical keys only\n"
            f"- scene_raw must be a short {language_name} sentence\n"
            '- if uncertain, use scene="other"\n'
            "- every score must be a number from 0.0 to 10.0\n"
            "- use one decimal place when the visible difference is real\n"
            "- avoid reusing the same canned score ladder across similar frames\n"
            "- do not mechanically reuse the same score steps unless the visible evidence is genuinely similar\n"
            "- Do not double-count a technical flaw across multiple dimensions.\n"
            "- Keep focus, motion blur, noise, and image cleanness mainly in clarity, not in subject or lighting.\n"
            "- If there is no human face, do not lower any score just because eyes, expression, or faces are absent.\n"
            "- similar burst frames may share a scene, but still score the actual visible differences in focus, light, timing, and separation\n"
            "- keep the evaluation concise and schema-aligned\n"
            "- focus on scoring semantics rather than repeating the prompt\n"
            f"{extra}"
            "Dimension definitions:\n"
            f"{dim_lines}"
        )
    return (
        "You are a strict photography evaluator.\n"
        "Analyze the image using the provided scoring contract.\n"
        "Return only the requested scene label and per-dimension scores.\n"
        "Do not return an overall, rating, or final total score.\n"
        "Use this schema:\n"
        "{"
        f'"scene": "one of [{scene_values}]", '
        f'"scene_raw": "{scene_raw_example}", '
        f"{schema_fields}"
        "}\n"
        "Rules:\n"
        f"- scene must be exactly one of: [{scene_values}]\n"
        "- scene must use English canonical keys only\n"
        f"- scene_raw must be a short {language_name} sentence\n"
        '- if uncertain, use scene="other"\n'
        "- every score must be a number from 0.0 to 10.0\n"
        "- use one decimal place when the visible difference is real\n"
        "- avoid reusing the same canned score ladder across similar frames\n"
        "- do not mechanically reuse the same score steps unless the visible evidence is genuinely similar\n"
        "- Do not double-count a technical flaw across multiple dimensions.\n"
        "- Keep focus, motion blur, noise, and image cleanness mainly in clarity, not in subject or lighting.\n"
        "- If there is no human face, do not lower any score just because eyes, expression, or faces are absent.\n"
        "- similar burst frames may share a scene, but still score the actual visible differences in focus, light, timing, and separation\n"
        "- keep the evaluation concise and schema-aligned\n"
        "- focus on scoring semantics rather than repeating the prompt\n"
        f"{extra}"
        "Dimension definitions:\n"
        f"{dim_lines}"
    )


def _build_fast_score_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            key: {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            }
            for key in FAST_SIGNAL_KEYS
        },
        "required": list(FAST_SIGNAL_KEYS),
        "additionalProperties": False,
    }


def _build_full_score_schema() -> dict:
    properties: dict[str, dict] = {
        "scene": {"type": "string", "enum": SCENE_LIST},
        "scene_raw": {"type": "string", "minLength": 1},
    }
    for dim in VISION_DIMS:
        properties[dim] = {
            "type": "number",
            "minimum": 0.0,
            "maximum": 10.0,
        }

    return {
        "type": "object",
        "properties": properties,
        "required": ["scene", "scene_raw", *VISION_DIMS],
        "additionalProperties": False,
    }


def _build_group_commentary_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "group_issues": {"type": "string", "minLength": 1},
            "shooting": {"type": "string", "minLength": 1},
        },
        "required": ["group_issues", "shooting"],
        "additionalProperties": False,
    }


def _build_post_commentary_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "post": {"type": "string", "minLength": 1},
        },
        "required": ["post"],
        "additionalProperties": False,
    }


def build_fast_response_format(
    schema_name: str = "material_agent.fast_screening_signals",
    *,
    contract_mode: str = "structured_outputs",
) -> dict:
    return _build_response_contract(contract_mode, schema_name, _build_fast_score_schema())


def build_full_response_format(
    schema_name: str = "material_agent.full_score",
    *,
    contract_mode: str = "structured_outputs",
) -> dict:
    return _build_response_contract(contract_mode, schema_name, _build_full_score_schema())


def build_json_object_response_format() -> dict:
    return {"type": "json_object"}


def build_group_commentary_prompt(
    group_data: str,
    output_language: str = "zh",
    prompt_preset: str = "default",
    extra_instructions: str | None = None,
) -> str:
    sentence_language = "English" if output_language == "en" else "Chinese"
    json_only = _json_only_instruction(prompt_preset)
    extra = _extra_instructions(extra_instructions)
    rules = ""
    if json_only:
        rules = f"Return constraints:\n{json_only}\n"
    return (
        f"Review the following photo group. Write one short {sentence_language} sentence for the main group issue "
        f"and one short {sentence_language} sentence for the most useful shooting improvement. "
        "Keep both concise, concrete, and directly actionable.\n\n"
        "Rules:\n"
        "- base the issue on recurring weak dimensions or repeated failures shown in the supplied group data\n"
        "- do not default to exposure unless exposure or lighting repeatedly appear among the weak signals\n"
        "- use scene hints and weak/strong fields when they help you choose the most useful advice\n"
        "- avoid generic canned advice that could fit any unrelated photo set\n\n"
        f"{rules}"
        f"{extra}"
        f"{group_data}"
    )


def build_group_commentary_response_format(
    schema_name: str = "material_agent.group_commentary",
    *,
    contract_mode: str = "structured_outputs",
) -> dict:
    return _build_response_contract(contract_mode, schema_name, _build_group_commentary_schema())


def build_post_commentary_prompt(
    score_line: str,
    group_commentary: str,
    output_language: str = "zh",
    prompt_preset: str = "default",
    extra_instructions: str | None = None,
) -> str:
    group_context = f"Group context: {group_commentary}\n" if group_commentary else ""
    sentence_language = "English" if output_language == "en" else "Chinese"
    json_only = _json_only_instruction(prompt_preset)
    extra = _extra_instructions(extra_instructions)
    rules = ""
    if json_only:
        rules = f"Return constraints:\n{json_only}\n"
    return (
        f"Write 1 to 3 concise {sentence_language} post-processing suggestion sentences for this photo. "
        "Make them concrete, practical, and directly actionable.\n\n"
        'Return exactly: {"post":"..."}\n'
        "Rules:\n"
        '- return one JSON object with one key only: "post"\n'
        '- do not add keys such as "scene", "scene_raw", "decision", "detail", "visible breakdown", or score fields\n'
        "- prioritize the weakest dimensions in the provided score context\n"
        "- if exposure or lighting are not among the weak signals, do not default to exposure edits\n"
        "- use scene, scene detail, decision, and visible breakdown only when they change edit priority\n"
        "- avoid generic template wording that could apply to any random photo\n\n"
        'Valid example: {"post":"Lift the shadows slightly, then hold back the brightest highlights."}\n'
        'Invalid example: {"scene":"people","post":"Lift the shadows slightly."}\n\n'
        f"{rules}"
        f"{extra}"
        f"Photo score line: {score_line}\n"
        f"{group_context}"
    )


def build_post_commentary_response_format(
    schema_name: str = "material_agent.post_commentary",
    *,
    contract_mode: str = "structured_outputs",
) -> dict:
    return _build_response_contract(contract_mode, schema_name, _build_post_commentary_schema())
