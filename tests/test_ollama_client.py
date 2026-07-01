import asyncio

import pytest

from material_agent.adapters.models.ollama.contracts import (
    build_vision_prompt as build_ollama_contract_vision_prompt,
)
from material_agent.adapters.models.ollama.contracts import (
    parse_vision_response as parse_ollama_contract_vision_response,
)
from material_agent.adapters.models.omlx.contracts import (
    build_omlx_response_format_json_schema,
    build_omlx_vision_messages,
    build_omlx_structured_outputs,
    extract_omlx_message_content,
)
import material_agent.clients.ollama as ollama_client
from material_agent.clients.ollama import AsyncOllamaClient, parse_vision_response
from material_agent.clients.protocol import parse_fast_score

VALID_RESPONSE = (
    '{"scene":"people","scene_raw":"舞台上的主唱特写","subject":8.0,'
    '"composition":7.0,"lighting":7.0,"color":6.0,"clarity":6.5,"depth":4.0,"mood":5.0}'
)


def test_parse_all_fields():
    result = parse_vision_response(VALID_RESPONSE)
    assert result["scene"] == "people"
    assert result["scene_raw"] == "舞台上的主唱特写"
    assert result["subject"] == 8.0
    assert result["composition"] == 7.0
    assert result["clarity"] == 6.5
    assert result["depth"] == 4.0
    assert result["mood"] == 5.0


def test_ollama_contract_parser_matches_client_parser():
    assert parse_ollama_contract_vision_response(VALID_RESPONSE) == parse_vision_response(
        VALID_RESPONSE
    )


def test_client_parse_vision_response_ignores_legacy_overall():
    raw = (
        '{"overall":9.9,"scene":"people","scene_raw":"舞台上的主唱特写","subject":8.0,'
        '"composition":7.0,"lighting":7.0,"color":6.0,"clarity":6.5,"depth":4.0,"mood":5.0}'
    )
    result = parse_vision_response(raw)

    assert result["scene"] == "people"
    assert result["subject"] == 8.0
    assert "overall" not in result


def test_async_ollama_score_image_ignores_legacy_overall(monkeypatch):
    async def _fake_vision_raw(self, model: str, prompt: str, jpeg_bytes: bytes) -> str:
        return (
            '{"overall":9.9,"scene":"people","scene_raw":"舞台上的主唱特写","subject":8.0,'
            '"composition":7.0,"lighting":7.0,"color":6.0,"clarity":6.5,"depth":4.0,"mood":5.0}'
        )

    monkeypatch.setattr(AsyncOllamaClient, "_vision_raw", _fake_vision_raw)
    client = AsyncOllamaClient(
        {
            "base_url": "http://localhost:11434",
            "vision_model": "llava:7b",
            "commentary_model": "llama3.2:3b",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    result = asyncio.run(client.score_image(b"jpeg"))

    assert result["scene"] == "people"
    assert result["subject"] == 8.0
    assert "overall" not in result


def test_ollama_contract_builds_full_prompt():
    prompt = build_ollama_contract_vision_prompt()
    assert "scene" in prompt
    assert "scene_raw" in prompt
    assert "clarity" in prompt


def test_omlx_contract_builds_text_first_messages():
    messages = build_omlx_vision_messages("Return JSON.", "abcd", system_prompt="You are JSON.")
    assert messages[0] == {"role": "system", "content": "You are JSON."}
    assert messages[1]["role"] == "user"
    assert messages[1]["content"][0] == {"type": "text", "text": "Return JSON."}
    assert messages[1]["content"][1]["type"] == "image_url"
    assert messages[1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_omlx_contract_extracts_message_content_from_parsed_payload():
    body = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "parsed": {"scene": "people", "scene_raw": "舞台上的人物"},
                }
            }
        ]
    }
    text = extract_omlx_message_content(body)
    assert '"scene": "people"' in text


def test_omlx_contract_builds_structured_outputs_payload():
    schema = {
        "type": "object",
        "properties": {
            "technical_ok": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "subject_clear": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "composition_ok": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "usable_for_selection": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["technical_ok", "subject_clear", "composition_ok", "usable_for_selection"],
        "additionalProperties": False,
    }
    payload = build_omlx_structured_outputs("material_agent.fast_screening_signals", schema)

    assert payload == {"json": schema}


def test_omlx_contract_builds_response_format_json_schema_payload():
    schema = {
        "type": "object",
        "properties": {
            "technical_ok": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "subject_clear": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "composition_ok": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "usable_for_selection": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["technical_ok", "subject_clear", "composition_ok", "usable_for_selection"],
        "additionalProperties": False,
    }
    payload = build_omlx_response_format_json_schema("material_agent.fast_screening_signals", schema)

    assert payload["type"] == "json_schema"
    assert payload["json_schema"]["name"] == "material_agent.fast_screening_signals"
    assert payload["json_schema"]["schema"] == schema
    assert payload["json_schema"]["strict"] is True


def test_invalid_scene_falls_back_to_other():
    raw = VALID_RESPONSE.replace('"people"', '"unknown_thing"')
    result = parse_vision_response(raw)
    assert result["scene"] == "other"


def test_missing_scene_falls_back_to_other():
    raw = (
        '{"subject":8.0,"composition":7.0,"lighting":7.0,'
        '"color":6.0,"clarity":6.5,"depth":4.0,"mood":5.0}'
    )
    result = parse_vision_response(raw)
    assert result["scene"] == "other"
    assert result["scene_raw"] == ""


def test_scores_clamped_to_0_10():
    raw = VALID_RESPONSE.replace('"clarity":6.5', '"clarity":15.0')
    result = parse_vision_response(raw)
    assert result["clarity"] == 10.0


def test_trailing_comma_handled():
    raw = (
        '{"scene":"detail","scene_raw":"寿司特写","subject":8.0,"composition":7.0,'
        '"lighting":7.0,"color":6.0,"clarity":6.5,"depth":4.0,"mood":5.0,}'
    )
    result = parse_vision_response(raw)
    assert result["scene"] == "detail"


def test_array_response_handled():
    raw = "[8.0, 7.0, 7.0, 6.0, 6.5, 4.0, 5.0]"
    result = parse_vision_response(raw)
    assert result["scene"] == "other"
    assert result["subject"] == 8.0
    assert result["composition"] == 7.0
    assert result["clarity"] == 6.5


# ---------------------------------------------------------------------------
# New regression tests
# ---------------------------------------------------------------------------


def test_scene_raw_equals_scene_name_is_cleared():
    """If LLM echoes a scene label as scene_raw, it should be cleared to ''."""
    raw = VALID_RESPONSE.replace('"舞台上的主唱特写"', '"people"')
    result = parse_vision_response(raw)
    assert result["scene_raw"] == ""


def test_scene_raw_equals_scene_name_case_insensitive():
    """Case-insensitive match: 'Concert' should also be cleared."""
    raw = VALID_RESPONSE.replace('"舞台上的主唱特写"', '"People"')
    result = parse_vision_response(raw)
    assert result["scene_raw"] == ""


def test_missing_dims_default_to_zero():
    """Dimensions absent from LLM JSON should come out as 0.0."""
    raw = '{"scene": "people", "scene_raw": "舞台上的人物"}'
    result = parse_vision_response(raw)
    for dim in ["subject", "composition", "lighting", "color", "clarity", "depth", "mood"]:
        assert result[dim] == 0.0


def test_parse_truncated_json_recovers():
    """A response truncated mid-object should still parse what's there."""
    raw = '{"scene":"landscape","scene_raw":"山景日落","subject":6.0,"composition":8.0,"color":7.0'
    raw_recoverable = raw + "}"
    result = parse_vision_response(raw_recoverable)
    assert result["scene"] == "landscape"
    assert result["composition"] == 8.0
    assert result["depth"] == 0.0


def test_placeholder_syntax_handled():
    """<N.N> placeholder syntax from some llava versions should be replaced."""
    raw = (
        '{"scene":"city","scene_raw":"夜晚城市街景","subject":<8.0>,'
        '"composition":<7.5>,"lighting":<7.0>,"color":<6.0>,'
        '"clarity":<6.5>,"depth":<4.0>,"mood":<5.0>}'
    )
    result = parse_vision_response(raw)
    assert result["composition"] == 7.5
    assert result["scene"] == "city"


def test_negative_score_clamped_to_zero():
    raw = VALID_RESPONSE.replace('"clarity":6.5', '"clarity":-3.0')
    result = parse_vision_response(raw)
    assert result["clarity"] == 0.0


def test_async_ollama_client_exposes_prompt_registry_for_fast_score():
    client = AsyncOllamaClient(
        {
            "base_url": "http://localhost:11434",
            "vision_model": "llava:7b",
            "fast_vision_model": "llava:7b",
            "commentary_model": "llama3.2:3b",
            "timeout": 30,
        }
    )

    bundle = client.prompt_registry.resolve("fast_score", model=client.fast_vision_model)

    assert bundle.task == "fast_score"
    assert '"technical_ok": 0.0' in bundle.prompt


def test_async_ollama_client_exposes_prompt_registry_for_post_commentary():
    client = AsyncOllamaClient(
        {
            "base_url": "http://localhost:11434",
            "vision_model": "llava:7b",
            "fast_vision_model": "llava:7b",
            "commentary_model": "llama3.2:3b",
            "timeout": 30,
        }
    )

    bundle = client.prompt_registry.resolve(
        "post_commentary",
        model=client.commentary_model,
        score_line="subject=8.0",
        group_commentary="【组内问题】整体偏暗。",
    )

    assert bundle.task == "post_commentary"
    assert 'Return exactly: {"post":"..."}' in bundle.prompt


@pytest.mark.anyio
async def test_async_ollama_score_image_uses_registry_prompt(monkeypatch):
    captured = {}

    async def _fake_generate_vision_async(
        *,
        base_url: str,
        model: str,
        prompt: str,
        jpeg_bytes: bytes,
        temperature: float,
        timeout,
    ) -> str:
        captured["prompt"] = prompt
        return VALID_RESPONSE

    monkeypatch.setattr(ollama_client, "generate_vision_async", _fake_generate_vision_async)

    client = AsyncOllamaClient(
        {
            "base_url": "http://localhost:11434",
            "vision_model": "llava:7b",
            "commentary_model": "llama3.2:3b",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    result = await client.score_image(b"jpeg")

    assert result["scene"] == "people"
    assert "Analyze the image using the provided scoring contract." in captured["prompt"]
    assert "Do not return an overall, rating, or final total score." in captured["prompt"]


@pytest.mark.anyio
async def test_async_ollama_score_image_fast_uses_registry_prompt(monkeypatch):
    captured = {}

    async def _fake_generate_vision_async(
        *,
        base_url: str,
        model: str,
        prompt: str,
        jpeg_bytes: bytes,
        temperature: float,
        timeout,
    ) -> str:
        captured["prompt"] = prompt
        return (
            '{"technical_ok": 0.2, "subject_clear": 0.4, '
            '"composition_ok": 0.3, "usable_for_selection": 0.1}'
        )

    monkeypatch.setattr(ollama_client, "generate_vision_async", _fake_generate_vision_async)

    client = AsyncOllamaClient(
        {
            "base_url": "http://localhost:11434",
            "vision_model": "llava:7b",
            "fast_vision_model": "llava:7b",
            "commentary_model": "llama3.2:3b",
            "timeout": 30,
            "vision_retries": 1,
        }
    )

    result = await client.score_image_fast(b"jpeg")

    assert result == {
        "technical_ok": 0.2,
        "subject_clear": 0.4,
        "composition_ok": 0.3,
        "usable_for_selection": 0.1,
    }
    assert "Return only the requested screening signal object." in captured["prompt"]
    assert "Do not return an overall, rating, or final total score." in captured["prompt"]


def test_no_json_raises_value_error():
    import pytest

    with pytest.raises(ValueError, match="No JSON"):
        parse_vision_response("totally plain text with no braces")


def test_multiple_json_objects_prefers_last_valid_answer():
    raw = (
        'Schema example: {"scene":"other","scene_raw":"short Chinese sentence"}\n'
        'Final answer: {"scene":"people","scene_raw":"舞台上的主唱特写","subject":8.0,'
        '"composition":7.0,"lighting":7.0,"color":6.0,"clarity":6.5,"depth":4.0,"mood":5.0}'
    )
    result = parse_vision_response(raw)
    assert result["scene"] == "people"
    assert result["scene_raw"] == "舞台上的主唱特写"
    assert result["subject"] == 8.0


def test_parse_prose_dimension_breakdown_fallback():
    raw = """
1. **Scene**: "other" fits best.
2. **Scene_raw**: "简单的图标设计"
- **Subject**: 4.0
- **Composition**: 2.0
- **Lighting**: 1.0
- **Color**: 3.0
- **Clarity**: 9.0
- **Depth**: 0.0
- **Mood**: 2.0
"""
    result = parse_vision_response(raw)
    assert result["scene"] == "other"
    assert result["scene_raw"] == "简单的图标设计"
    assert result["clarity"] == 9.0
    assert result["mood"] == 2.0


def test_parse_prose_backtick_scoring_format():
    raw = """
1. **Scene**: The image features a kitten walking. This falls under the "animals" category.
    *   `scene`: "animals"
    *   `scene_raw`: "一只虎斑猫在行走"
    *   `subject`: 8.0
    *   `composition`: 6.0
    *   `lighting`: 7.0
    *   `color`: 6.0
    *   `clarity`: 8.0
    *   `depth`: 7.0
    *   `mood`: 7.0
"""
    result = parse_vision_response(raw)
    assert result["scene"] == "animals"
    assert result["scene_raw"] == "一只虎斑猫在行走"
    assert result["subject"] == 8.0
    assert result["depth"] == 7.0


def test_parse_prose_section_with_embedded_score_lines():
    raw = """
1. **Scene**: The image shows a musician performing. "people" is the most appropriate category.
2. **Scene Raw**: "舞台上的绿发乐手"
3. **Subject**: The musician is the clear focal point. Score: 8.5.
4. **Composition**: Dynamic low-angle composition. Score: 7.0.
5. **Lighting**: Strong stage lighting. Score: 7.5.
6. **Color**: Blue-green dominant. Score: 6.0.
7. **Clarity**: Subject is reasonably clear. Score: 7.0.
8. **Depth**: Good foreground/background separation. Score: 8.0.
9. **Mood**: Energetic concert atmosphere. Score: 8.0.
"""
    result = parse_vision_response(raw)
    assert result["scene"] == "people"
    assert result["scene_raw"] == "舞台上的绿发乐手"
    assert result["subject"] == 8.5
    assert result["composition"] == 7.0
    assert result["lighting"] == 7.5
    assert result["color"] == 6.0
    assert result["clarity"] == 7.0
    assert result["depth"] == 8.0
    assert result["mood"] == 8.0


def test_parse_fast_score_supports_narrative_estimate():
    raw = "The score should be very low, likely 0.0, because it is not a photograph."
    assert parse_fast_score(raw) == 0.0


def test_parse_fast_score_supports_truncated_jsonish_label():
    raw = '{"overall":7.5'
    assert parse_fast_score(raw) == 7.5


def test_parse_fast_score_rejects_scale_description_without_actual_score():
    import pytest

    raw = (
        "The user wants a rating for the provided photo on a scale of 0.0 to 10.0. "
        "The rating should cover overall quality and usefulness. "
        "The output must be a JSON object with a single key."
    )
    with pytest.raises(ValueError, match="No reliable fast score"):
        parse_fast_score(raw)


def test_parse_fast_score_rejects_unrelated_json_without_score_key():
    import pytest

    raw = '{"image_id":"8b03d9f3793148e76c50","malicious_content":"False","tactical_jailbreak":"False"}'
    with pytest.raises(ValueError, match="No reliable fast score"):
        parse_fast_score(raw)
