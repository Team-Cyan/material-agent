"""Tests for config_validator.validate_config."""

import pytest
from material_agent.utils.config_validator import normalize_config, sync_omlx_model_selection, validate_config
from material_agent.utils.constants import VISION_DIMS


def _minimal_config():
    return {
        "backend": "ollama",
        "legacy": {"enabled": True},
        "ollama": {
            "base_url": "http://localhost:11434",
            "vision_model": "llava:7b",
            "commentary_model": "llama3.2:3b",
            "timeout": 120,
        },
        "scorers": {},
        "grouping": {},
        "preview": {},
        "scoring": {},
        "scene_weights": {},
    }


def test_valid_config_passes():
    validate_config(_minimal_config())


def test_normalize_config_defaults_commentary_enabled_true():
    cfg = _minimal_config()
    normalized = normalize_config(cfg)
    assert normalized["commentary_enabled"] is True


def test_legacy_backend_requires_explicit_compatibility_gate(capsys):
    cfg = _minimal_config()
    cfg["legacy"]["enabled"] = False

    with pytest.raises(SystemExit):
        validate_config(cfg)

    assert "quarantined" in capsys.readouterr().out


def test_normalize_config_defaults_output_language_to_zh():
    cfg = _minimal_config()
    normalized = normalize_config(cfg)
    assert normalized["output_language"] == "zh"


def test_normalize_config_defaults_review_pipeline_prefetch_window():
    cfg = _minimal_config()
    normalized = normalize_config(cfg)
    assert normalized["review_pipeline"]["score_prefetch_window"] == 2


def test_normalize_config_defaults_screening_backend_to_musiq():
    cfg = _minimal_config()
    cfg["screening"] = {"enabled": True}
    normalized = normalize_config(cfg)
    assert normalized["screening"]["backend"] == "musiq"
    assert normalized["screening"]["musiq"]["metric"] == "musiq"


def test_normalize_config_defaults_inference_enforce_available_false():
    normalized = normalize_config({"backend": "local"})
    assert normalized["inference"]["enforce_available"] is False


def test_normalize_config_sets_omlx_runtime_request_admin_defaults():
    normalized = normalize_config({"backend": "omlx", "omlx": {}})

    assert normalized["omlx"]["runtime"]["required_version"] == ">=0.3.0"
    assert normalized["omlx"]["runtime"]["require_structured_outputs"] is False
    assert normalized["omlx"]["runtime"]["require_xgrammar"] is False
    assert normalized["omlx"]["runtime"]["probe_on_run"] is True
    assert normalized["omlx"]["runtime"]["enforce_dedicated_instance"] is False
    assert normalized["omlx"]["requests"]["fast_vision_schema"] == "material_agent.fast_screening_signals"
    assert normalized["omlx"]["requests"]["vision_schema"] == "material_agent.full_score"
    assert (
        normalized["omlx"]["requests"]["group_commentary_schema"] == "material_agent.group_commentary"
    )
    assert normalized["omlx"]["requests"]["post_commentary_schema"] == "material_agent.post_commentary"
    assert normalized["omlx"]["requests"]["contract_mode"] == "response_format_json_schema"
    assert normalized["omlx"]["requests"]["prompt_preset"] == "qwen3"
    assert normalized["omlx"]["requests"]["model_profile_mode"] == "auto"
    assert normalized["omlx"]["requests"]["enable_thinking"] is False
    assert normalized["omlx"]["requests"]["temperature"] == 0.0
    assert normalized["omlx"]["requests"]["xtc_probability"] == 0.0
    assert normalized["omlx"]["admin"]["base_url"] == "http://localhost:11435"
    assert normalized["omlx"]["base_url"] == normalized["omlx"]["admin"]["base_url"]
    assert (
        normalized["omlx"]["full_vision_model"] == normalized["omlx"]["admin"]["full_vision_model"]
    )
    assert normalized["omlx"]["commentary_model"] == normalized["omlx"]["admin"]["commentary_model"]
    assert normalized["omlx"]["timeout"] == normalized["omlx"]["admin"]["timeout"]
    assert normalized["omlx"]["admin"]["api_key"] == ""
    assert normalized["omlx"]["api_key"] == ""
    assert normalized["omlx"]["vision_image_max_edge"] == 1024
    assert normalized["omlx"]["vision_jpeg_quality"] == 92


def test_normalize_config_defaults_omlx_to_qwen3_vl_4b_dual_call():
    normalized = normalize_config({"backend": "omlx", "omlx": {}})

    assert normalized["omlx"]["full_vision_model"] == "Qwen3-VL-4B-Instruct-4bit"
    assert normalized["omlx"]["commentary_model"] == "Qwen3-VL-4B-Instruct-4bit"
    assert normalized["omlx"]["fast_vision_model"] == "Qwen3-VL-4B-Instruct-4bit"


def test_invalid_omlx_model_profile_mode_exits(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "omlx"
    cfg["omlx"] = {
        "base_url": "http://localhost:11435",
        "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "timeout": 120,
        "requests": {"model_profile_mode": "always-on"},
    }

    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "model_profile_mode" in capsys.readouterr().out


def test_invalid_omlx_model_profiles_shape_exits(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "omlx"
    cfg["omlx"] = {
        "base_url": "http://localhost:11435",
        "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "timeout": 120,
        "model_profiles": {
            "mlx-community/Qwen2.5-VL-7B-Instruct-4bit": {
                "request_overrides": "qwen3",
            }
        },
    }

    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "request_overrides" in capsys.readouterr().out


def test_normalize_config_prefers_grouped_omlx_admin_over_flat_keys():
    cfg = {
        "backend": "omlx",
        "omlx": {
            "base_url": "http://flat.example.invalid",
            "full_vision_model": "flat-full",
            "commentary_model": "flat-commentary",
            "timeout": 120,
            "model_dir_mode": "config_union",
            "api_key": "flat-secret",
            "admin": {
                "base_url": "http://grouped.example.invalid",
                "full_vision_model": "grouped-full",
                "commentary_model": "grouped-commentary",
                "timeout": 240,
                "model_dir_mode": "config_union",
                "api_key": "grouped-secret",
            },
        },
    }

    normalized = normalize_config(cfg)

    assert normalized["omlx"]["admin"]["base_url"] == "http://grouped.example.invalid"
    assert normalized["omlx"]["admin"]["full_vision_model"] == "grouped-full"
    assert normalized["omlx"]["admin"]["commentary_model"] == "grouped-commentary"
    assert normalized["omlx"]["admin"]["timeout"] == 240
    assert normalized["omlx"]["admin"]["api_key"] == "grouped-secret"
    assert normalized["omlx"]["base_url"] == "http://grouped.example.invalid"
    assert normalized["omlx"]["full_vision_model"] == "grouped-full"
    assert normalized["omlx"]["commentary_model"] == "grouped-commentary"
    assert normalized["omlx"]["timeout"] == 240
    assert normalized["omlx"]["api_key"] == "grouped-secret"


def test_sync_omlx_model_selection_updates_grouped_admin_and_root_keys():
    config = {
        "backend": "omlx",
        "full_vision_model": "root-old",
        "commentary_model": "root-old-commentary",
        "fast_vision_model": "root-old-fast",
        "omlx": {
            "full_vision_model": "flat-old",
            "commentary_model": "flat-old-commentary",
            "fast_vision_model": "flat-old-fast",
            "admin": {
                "full_vision_model": "admin-old",
                "commentary_model": "admin-old-commentary",
                "fast_vision_model": "admin-old-fast",
            },
        },
    }

    sync_omlx_model_selection(
        config,
        full_vision_model="gemma-full",
        commentary_model="gemma-commentary",
        fast_vision_model="gemma-fast",
    )

    assert config["full_vision_model"] == "gemma-full"
    assert config["commentary_model"] == "gemma-commentary"
    assert config["fast_vision_model"] == "gemma-fast"
    assert config["omlx"]["full_vision_model"] == "gemma-full"
    assert config["omlx"]["commentary_model"] == "gemma-commentary"
    assert config["omlx"]["fast_vision_model"] == "gemma-fast"
    assert config["omlx"]["admin"]["full_vision_model"] == "gemma-full"
    assert config["omlx"]["admin"]["commentary_model"] == "gemma-commentary"
    assert config["omlx"]["admin"]["fast_vision_model"] == "gemma-fast"


def test_invalid_output_language_exits(capsys):
    cfg = _minimal_config()
    cfg["output_language"] = "jp"
    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "output_language" in capsys.readouterr().out


def test_invalid_log_level_exits(capsys):
    cfg = _minimal_config()
    cfg["log_level"] = "verbose"
    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "log_level" in capsys.readouterr().out


def test_invalid_backend_message_lists_supported_backends(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "fast_vlm"
    with pytest.raises(SystemExit):
        validate_config(cfg)
    out = capsys.readouterr().out
    assert "['local', 'ollama', 'omlx']" in out


def test_local_backend_rejects_commentary_enabled(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "local"
    cfg["commentary_enabled"] = True
    with pytest.raises(SystemExit):
        validate_config(cfg)
    out = capsys.readouterr().out
    assert "commentary_enabled is not supported" in out


def test_invalid_review_pipeline_prefetch_window_exits(capsys):
    cfg = _minimal_config()
    cfg["review_pipeline"] = {"score_prefetch_window": 0}
    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "score_prefetch_window" in capsys.readouterr().out


def test_invalid_inference_enforce_available_exits(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "local"
    cfg["inference"] = {"enforce_available": "sometimes"}
    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "inference.enforce_available" in capsys.readouterr().out


def test_missing_ollama_exits(capsys):
    cfg = _minimal_config()
    del cfg["ollama"]
    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "ollama" in capsys.readouterr().out


def test_missing_ollama_key_exits(capsys):
    cfg = _minimal_config()
    del cfg["ollama"]["timeout"]
    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "timeout" in capsys.readouterr().out


def test_invalid_max_concurrent_exits(capsys):
    cfg = _minimal_config()
    cfg["ollama"]["max_concurrent"] = 0
    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "max_concurrent" in capsys.readouterr().out


def test_normalize_config_adds_local_semantic_defaults():
    normalized = normalize_config(_minimal_config())

    assert normalized["local"]["semantic"] == {
        "enabled": False,
        "enforce_available": False,
        "model_name": "MobileCLIP2-S0",
        "pretrained": "dfndr2b",
        "device": "cpu",
        "min_confidence": 0.30,
    }


def test_invalid_local_semantic_confidence_exits(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "local"
    cfg["commentary_enabled"] = False
    cfg["local"] = {"semantic": {"min_confidence": 1.5}}

    with pytest.raises(SystemExit):
        validate_config(cfg)

    assert "local.semantic.min_confidence" in capsys.readouterr().out


def test_invalid_screening_backend_exits(capsys):
    cfg = _minimal_config()
    cfg["screening"] = {"enabled": True, "backend": "fast_vlm"}
    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "screening.backend" in capsys.readouterr().out


def test_missing_omlx_section_exits(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "omlx"
    with pytest.raises(SystemExit):
        validate_config(cfg)
    out = capsys.readouterr().out
    assert "omlx" in out


def test_missing_omlx_essential_keys_exits(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "omlx"
    cfg["omlx"] = {
        "model_dir_mode": "config_union",
        "admin": {
            "base_url": "http://localhost:11435",
        },
    }
    with pytest.raises(SystemExit):
        validate_config(cfg)
    out = capsys.readouterr().out
    assert "full_vision_model" in out
    assert "commentary_model" in out
    assert "timeout" in out


def test_invalid_omlx_model_dir_mode_exits(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "omlx"
    cfg["omlx"] = {
        "base_url": "http://localhost:11435",
        "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "timeout": 120,
        "model_dir_mode": "all_models",
    }
    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "model_dir_mode" in capsys.readouterr().out


def test_invalid_omlx_contract_mode_exits(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "omlx"
    cfg["omlx"] = {
        "base_url": "http://localhost:11435",
        "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "timeout": 120,
        "requests": {"contract_mode": "response_format"},
    }

    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "contract_mode" in capsys.readouterr().out


def test_response_format_json_schema_contract_mode_is_allowed():
    cfg = _minimal_config()
    cfg["backend"] = "omlx"
    cfg["omlx"] = {
        "base_url": "http://localhost:11435",
        "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "timeout": 120,
        "requests": {"contract_mode": "response_format_json_schema"},
    }

    validate_config(cfg)


def test_normalize_config_coerces_omlx_runtime_boolean_strings():
    cfg = _minimal_config()
    cfg["backend"] = "omlx"
    cfg["omlx"] = {
        "base_url": "http://localhost:11435",
        "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "timeout": 120,
        "runtime": {
            "probe_on_run": "false",
            "require_structured_outputs": "true",
            "require_xgrammar": "false",
            "enforce_dedicated_instance": "false",
        },
        "requests": {
            "enable_thinking": "false",
        },
        "cache_enabled": "false",
    }

    normalized = normalize_config(cfg)

    assert normalized["omlx"]["runtime"]["probe_on_run"] is False
    assert normalized["omlx"]["runtime"]["require_structured_outputs"] is True
    assert normalized["omlx"]["runtime"]["require_xgrammar"] is False
    assert normalized["omlx"]["runtime"]["enforce_dedicated_instance"] is False
    assert normalized["omlx"]["requests"]["enable_thinking"] is False
    assert normalized["omlx"]["cache_enabled"] is False


def test_invalid_omlx_runtime_boolean_string_exits(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "omlx"
    cfg["omlx"] = {
        "base_url": "http://localhost:11435",
        "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "timeout": 120,
        "runtime": {
            "probe_on_run": "sometimes",
        },
    }

    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "probe_on_run" in capsys.readouterr().out


def test_invalid_omlx_image_constraints_exit(capsys):
    cfg = _minimal_config()
    cfg["backend"] = "omlx"
    cfg["omlx"] = {
        "base_url": "http://localhost:11435",
        "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        "timeout": 120,
        "vision_image_max_edge": 0,
        "vision_jpeg_quality": 101,
    }

    with pytest.raises(SystemExit):
        validate_config(cfg)
    out = capsys.readouterr().out
    assert "vision_image_max_edge" in out
    assert "vision_jpeg_quality" in out


def test_scene_profiles_unknown_dimension_exits(capsys):
    cfg = _minimal_config()
    cfg["scene_profiles"] = {
        "people": {
            "aesthetic_weights": {
                "composition": 0.5,
                "clarity": 0.5,
            }
        }
    }
    with pytest.raises(SystemExit):
        validate_config(cfg)
    assert "unknown dimensions" in capsys.readouterr().out


def test_scene_weights_correct_sum_passes():
    cfg = _minimal_config()
    weights = {d: 0.0 for d in VISION_DIMS}
    weights["clarity"] = 1.0
    cfg["scene_weights"]["detail"] = weights
    validate_config(cfg)  # should not raise


def test_normalize_config_promotes_scene_weights_to_scene_profiles():
    cfg = _minimal_config()
    cfg["scene_weights"] = {
        "default": {
            "subject": 0.20,
            "composition": 0.20,
            "lighting": 0.20,
            "color": 0.20,
            "clarity": 0.10,
            "depth": 0.05,
            "mood": 0.05,
        }
    }

    normalized = normalize_config(cfg)

    assert "scene_profiles" in normalized
    assert normalized["scene_profiles"]["default"]["aesthetic_weights"] == {
        "subject_moment": 0.2222,
        "composition": 0.2222,
        "lighting": 0.2222,
        "color": 0.2222,
        "depth_separation": 0.0556,
        "mood_story": 0.0556,
    }


def test_normalize_config_sets_layered_decision_defaults():
    normalized = normalize_config(_minimal_config())

    assert normalized["focus_integrity"]["enabled"] is True
    assert normalized["focus_integrity"]["mode"] == "preview_proxy"
    assert normalized["focus_integrity"]["high_resolution_roi"] is False
    assert normalized["portrait_face_eye"]["enabled"] is False
    assert normalized["decision_policy"]["keep_threshold"] == 7.5
    assert normalized["decision_policy"]["review_threshold"] == 5.5


def test_normalize_config_sets_preview_and_xmp_defaults():
    normalized = normalize_config(_minimal_config())

    assert normalized["preview"]["prefer_embedded"] is True
    assert normalized["preview"]["fallback_decode"] == "half_size"
    assert normalized["xmp"]["write_mode"] == "sidecar"
    assert normalized["xmp"]["machine_tag_target"] == "identifier"
