from material_agent.clients.prompting.registry import PromptRegistry
import pytest


def _omlx_config() -> dict:
    return {
        "full_vision_model": "Qwen3-VL-4B-Instruct-4bit",
        "fast_vision_model": "Qwen3-VL-4B-Instruct-4bit",
        "commentary_model": "Qwen3-VL-4B-Instruct-4bit",
        "output_language": "zh",
        "vision_temperature": 0.0,
        "vision_max_tokens": 192,
        "fast_vision_max_tokens": 96,
        "requests": {
            "contract_mode": "response_format_json_schema",
            "prompt_preset": "qwen3",
            "fast_vision_schema": "material_agent.fast_screening_signals",
            "vision_schema": "material_agent.full_score",
            "model_profile_mode": "auto",
        },
        "model_profiles": {
            "Qwen3-VL-4B-Instruct-4bit": {
                "request_overrides": {
                    "vision_max_tokens": 224,
                    "prompt_preset": "qwen3",
                },
                "prompt_overrides": {
                    "full_prompt_extra": (
                        "Prefer visible subject separation evidence over abstract style praise."
                    )
                },
            }
        },
    }


def test_prompt_registry_resolves_full_score_bundle_with_profile_overrides():
    bundle = PromptRegistry(_omlx_config()).resolve(
        "full_score",
        model="Qwen3-VL-4B-Instruct-4bit",
    )

    assert bundle.task == "full_score"
    assert bundle.model == "Qwen3-VL-4B-Instruct-4bit"
    assert bundle.request_options["max_tokens"] == 224
    assert bundle.request_options["temperature"] == 0.0
    assert bundle.evaluation_policy.name == "scoring.full.phase1"
    assert "Prefer visible subject separation evidence" in bundle.prompt
    schema = bundle.response_format["json_schema"]["schema"]
    assert schema["required"] == [
        "scene",
        "scene_raw",
        "subject",
        "composition",
        "lighting",
        "color",
        "clarity",
        "depth",
        "mood",
    ]


def test_prompt_registry_resolves_fast_score_bundle_with_signal_contract():
    bundle = PromptRegistry(_omlx_config()).resolve(
        "fast_score",
        model="Qwen3-VL-4B-Instruct-4bit",
    )

    assert bundle.task == "fast_score"
    assert bundle.request_options["max_tokens"] == 96
    assert bundle.evaluation_policy.name == "scoring.fast.phase1"
    assert "Do not return an overall, rating, or final total score." in bundle.prompt
    schema = bundle.response_format["json_schema"]["schema"]
    assert schema["required"] == [
        "technical_ok",
        "subject_clear",
        "composition_ok",
        "usable_for_selection",
    ]


def test_prompt_registry_rejects_mismatched_task_model():
    config = _omlx_config()
    config["full_vision_model"] = "Qwen3-VL-8B-Instruct-4bit"

    with pytest.raises(ValueError, match="expects model 'Qwen3-VL-8B-Instruct-4bit'"):
        PromptRegistry(config).resolve(
            "full_score",
            model="Qwen3-VL-4B-Instruct-4bit",
        )


def test_prompt_registry_resolves_group_commentary_bundle_with_profile_overrides():
    cfg = _omlx_config()
    cfg["model_profiles"]["Qwen3-VL-4B-Instruct-4bit"]["request_overrides"].update(
        {"group_commentary_max_tokens": 188}
    )
    cfg["model_profiles"]["Qwen3-VL-4B-Instruct-4bit"]["prompt_overrides"].update(
        {"group_prompt_extra": "Prefer concrete repeated failure language."}
    )

    bundle = PromptRegistry(cfg).resolve(
        "group_commentary",
        model="Qwen3-VL-4B-Instruct-4bit",
        group_data="1. a.jpg total=7.0",
    )

    assert bundle.task == "group_commentary"
    assert bundle.request_options["max_tokens"] == 188
    assert bundle.evaluation_policy.name == "commentary.group.phase2"
    assert "Prefer concrete repeated failure language." in bundle.prompt
    schema = bundle.response_format["json_schema"]["schema"]
    assert schema["required"] == ["group_issues", "shooting"]


def test_prompt_registry_commentary_tasks_fall_back_to_shared_commentary_max_tokens():
    cfg = _omlx_config()
    cfg["commentary_max_tokens"] = 199

    group = PromptRegistry(cfg).resolve(
        "group_commentary",
        model="Qwen3-VL-4B-Instruct-4bit",
        group_data="1. a.jpg total=7.0",
    )
    post = PromptRegistry(cfg).resolve(
        "post_commentary",
        model="Qwen3-VL-4B-Instruct-4bit",
        score_line="subject=8.0 composition=7.0",
        group_commentary="【组内问题】整体偏暗。",
    )

    assert group.request_options["max_tokens"] == 199
    assert post.request_options["max_tokens"] == 199


def test_prompt_registry_resolves_post_commentary_bundle_with_group_context():
    cfg = _omlx_config()
    cfg["model_profiles"]["Qwen3-VL-4B-Instruct-4bit"]["request_overrides"].update(
        {"post_commentary_max_tokens": 177}
    )
    cfg["model_profiles"]["Qwen3-VL-4B-Instruct-4bit"]["prompt_overrides"].update(
        {"post_prompt_extra": "Stay specific to the provided frame."}
    )

    bundle = PromptRegistry(cfg).resolve(
        "post_commentary",
        model="Qwen3-VL-4B-Instruct-4bit",
        score_line="subject=8.0 composition=7.0",
        group_commentary="【组内问题】整体偏暗。",
    )

    assert bundle.task == "post_commentary"
    assert bundle.request_options["max_tokens"] == 177
    assert bundle.evaluation_policy.name == "commentary.post.phase2"
    assert "Stay specific to the provided frame." in bundle.prompt
    assert "Group context:" in bundle.prompt
    schema = bundle.response_format["json_schema"]["schema"]
    assert schema["required"] == ["post"]
