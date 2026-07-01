from material_agent.clients.ollama import parse_vision_response
from material_agent.utils.constants import ALL_DIMS, VISION_DIMS


def test_new_dimension_sets_are_exposed():
    assert VISION_DIMS == [
        "subject",
        "composition",
        "lighting",
        "color",
        "clarity",
        "depth",
        "mood",
    ]
    assert ALL_DIMS == ["exposure", "sharpness"] + VISION_DIMS


def test_parse_vision_response_accepts_new_schema_only():
    raw = (
        '{"scene":"people","scene_raw":"舞台上的主唱特写","subject":8.0,'
        '"composition":7.0,"lighting":6.5,"color":6.0,"clarity":5.5,'
        '"depth":4.0,"mood":7.5}'
    )
    result = parse_vision_response(raw)
    assert result["scene"] == "people"
    assert result["scene_raw"] == "舞台上的主唱特写"
    assert result["subject"] == 8.0
    assert result["clarity"] == 5.5
    assert result["mood"] == 7.5


def test_parse_vision_response_missing_new_dims_defaults_to_zero():
    result = parse_vision_response('{"scene":"city","scene_raw":"雨夜街头"}')
    for dim in VISION_DIMS:
        assert result[dim] == 0.0


def test_shared_prompt_builders_use_english_keys_and_cn_scene_raw():
    from material_agent.clients.prompts import build_fast_prompt, build_full_prompt

    fast_prompt = build_fast_prompt()
    full_prompt = build_full_prompt()

    assert '"technical_ok"' in fast_prompt
    assert '"usable_for_selection"' in fast_prompt
    assert '"overall"' not in fast_prompt
    assert "scene_raw" in full_prompt
    assert "must be a short Chinese sentence" in full_prompt
    assert "subject" in full_prompt
    assert "clarity" in full_prompt
    assert "mood" in full_prompt
    assert '"aesthetics"' not in full_prompt
    assert '"focus"' not in full_prompt
    assert '"noise"' not in full_prompt
    assert '"texture"' not in full_prompt
    assert "subject clarity" not in full_prompt
    assert "exposure usefulness" not in full_prompt
    assert "Do not double-count a technical flaw across multiple dimensions." in full_prompt
    assert (
        "If there is no human face, do not lower any score just because eyes, expression, or faces are absent."
        in full_prompt
    )
    assert "Your first character must be {" not in full_prompt
    assert "do not add any extra keys" not in full_prompt


def test_full_prompt_can_request_english_scene_raw_output():
    from material_agent.clients.prompts import build_full_prompt

    full_prompt = build_full_prompt(output_language="en")

    assert "scene_raw must be a short English sentence" in full_prompt
    assert "Chinese sentence" not in full_prompt


def test_structured_full_prompt_keeps_layered_dimension_guidance():
    from material_agent.clients.prompts import build_full_prompt

    full_prompt = build_full_prompt(structured_output=True)

    assert "subject appeal" in full_prompt
    assert "focus reliability" in full_prompt
    assert "Do not double-count a technical flaw across multiple dimensions." in full_prompt
    assert "Your first character must be {" not in full_prompt


def test_structured_full_prompt_discourages_bucketed_dimension_scores():
    from material_agent.clients.prompts import build_full_prompt

    full_prompt = build_full_prompt(structured_output=True, prompt_preset="qwen3")

    assert "avoid reusing the same canned score ladder across similar frames" in full_prompt
    assert "use one decimal place when the visible difference is real" in full_prompt
    assert (
        "do not mechanically reuse the same score steps unless the visible evidence is genuinely similar"
        in full_prompt
    )


def test_commentary_prompts_stay_english_while_output_language_is_configurable():
    from material_agent.clients.prompts import (
        build_group_commentary_prompt,
        build_post_commentary_prompt,
    )

    zh_group = build_group_commentary_prompt("1. a.jpg total=7.0", output_language="zh")
    en_group = build_group_commentary_prompt("1. a.jpg total=7.0", output_language="en")
    zh_post = build_post_commentary_prompt("subj=8.0", "", output_language="zh")
    en_post = build_post_commentary_prompt("subj=8.0", "", output_language="en")

    assert "Review the following photo group." in zh_group
    assert "Review the following photo group." in en_group
    assert "Chinese" in zh_group
    assert "English" in en_group
    assert "post-processing suggestion" in zh_post
    assert "post-processing suggestion" in en_post
    assert "Chinese" in zh_post
    assert "English" in en_post
    assert 'Return exactly: {"post":"..."}' in zh_post
    assert "Return a single compact JSON object only." not in zh_group
    assert "Return a single compact JSON object only." not in zh_post


def test_gemma_prompt_preset_adds_json_only_constraints():
    from material_agent.clients.prompts import build_full_prompt, build_post_commentary_prompt

    full_prompt = build_full_prompt(structured_output=True, prompt_preset="gemma")
    post_prompt = build_post_commentary_prompt("subj=8.0", "", prompt_preset="gemma")

    assert "return exactly one final JSON object and nothing else" in full_prompt
    assert "no markdown fences" in full_prompt
    assert "Return constraints:" in post_prompt
