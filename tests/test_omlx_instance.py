import json
from pathlib import Path

from material_agent.adapters.models.omlx.instance import (
    build_omlx_start_command,
    collect_omlx_runtime_models,
    discover_omlx_api_key,
    find_omlx_command_prefix,
    is_configured_shared_omlx_runtime,
    sync_omlx_shared_runtime,
    setup_omlx_instance,
)


def _base_config(instance_root: Path) -> dict:
    return {
        "backend": "omlx",
        "omlx": {
            "base_url": "http://127.0.0.1:11435",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 120,
            "api_key": "secret",
            "instance_root": str(instance_root),
            "model_dir_mode": "config_union",
            "cache_enabled": True,
        },
        "screening": {
            "enabled": True,
            "backend": "musiq",
            "musiq": {"device": "cpu", "score_divisor": 10.0},
        },
    }


def test_collect_omlx_runtime_models_uses_only_active_omlx_union(tmp_path):
    cfg = _base_config(tmp_path / "instance")
    cfg["omlx"]["full_vision_model"] = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"
    cfg["omlx"]["commentary_model"] = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"
    cfg["omlx"]["fast_vision_model"] = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"

    assert collect_omlx_runtime_models(cfg) == [
        "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
        "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
    ]


def test_is_configured_shared_omlx_runtime_requires_matching_home_server(tmp_path):
    cfg = _base_config(tmp_path / "instance")
    home_settings = tmp_path / "settings.json"
    home_settings.write_text(
        json.dumps({"server": {"host": "127.0.0.1", "port": 11435}}),
        encoding="utf-8",
    )

    assert is_configured_shared_omlx_runtime(cfg, home_settings_path=home_settings) is True

    cfg["omlx"]["base_url"] = "http://127.0.0.1:22445"
    assert is_configured_shared_omlx_runtime(cfg, home_settings_path=home_settings) is False


def test_discover_omlx_api_key_prefers_explicit_config(tmp_path):
    cfg = _base_config(tmp_path / "instance")
    cfg["omlx"]["api_key"] = "explicit-secret"

    assert discover_omlx_api_key(cfg) == "explicit-secret"


def test_discover_omlx_api_key_falls_back_to_home_auth_settings(tmp_path):
    cfg = _base_config(tmp_path / "instance")
    cfg["omlx"]["api_key"] = ""
    home_settings = tmp_path / "home-settings.json"
    home_settings.write_text(
        '{"auth":{"api_key":"home-secret"},"server":{"host":"127.0.0.1","port":11435}}',
        encoding="utf-8",
    )

    assert discover_omlx_api_key(cfg, home_settings_path=home_settings) == "home-secret"


def test_discover_omlx_api_key_does_not_autoload_local_settings_for_remote_base_url(tmp_path):
    cfg = _base_config(tmp_path / "instance")
    cfg["omlx"]["api_key"] = ""
    cfg["omlx"]["base_url"] = "https://remote-omlx.example.com"
    home_settings = tmp_path / "home-settings.json"
    instance_settings = tmp_path / "instance-settings.json"
    home_settings.write_text(
        '{"auth":{"api_key":"home-secret"},"server":{"host":"127.0.0.1","port":11435}}',
        encoding="utf-8",
    )
    instance_settings.write_text(
        '{"auth":{"api_key":"instance-secret"},"server":{"host":"127.0.0.1","port":11436}}',
        encoding="utf-8",
    )

    assert (
        discover_omlx_api_key(
            cfg,
            home_settings_path=home_settings,
            instance_settings_path=instance_settings,
        )
        == ""
    )


def test_setup_omlx_instance_links_only_config_union_models_and_enables_cache(tmp_path):
    source_root = tmp_path / "source-models"
    source_root.mkdir()
    active_model = source_root / "mlx-community" / "Qwen2.5-VL-7B-Instruct-4bit"
    active_model.mkdir(parents=True)
    stale_model = source_root / "mlx-community" / "Qwen3.5-9B-MLX-4bit"
    stale_model.mkdir(parents=True)

    home_settings = tmp_path / "home-settings.json"
    home_settings.write_text(
        '{"model":{"model_dirs":["%s"]},"cache":{"enabled":false},"server":{"host":"127.0.0.1","port":11435}}'
        % source_root.as_posix(),
        encoding="utf-8",
    )
    home_model_settings = tmp_path / "home-model-settings.json"
    home_model_settings.write_text('{"version":1,"models":{}}', encoding="utf-8")

    cfg = _base_config(tmp_path / "instance")
    summary = setup_omlx_instance(
        cfg,
        home_settings_path=home_settings,
        home_model_settings_path=home_model_settings,
    )

    model_dir = Path(summary["model_dir"])
    linked = sorted(path.name for path in model_dir.iterdir())
    assert linked == ["Qwen2.5-VL-7B-Instruct-4bit"]
    assert (model_dir / "Qwen2.5-VL-7B-Instruct-4bit").is_symlink()
    assert Path(summary["cache_dir"]).exists()

    generated_settings = Path(summary["instance_root"]) / "settings.generated.json"
    assert generated_settings.exists()
    assert '"enabled": true' in generated_settings.read_text(encoding="utf-8").lower()
    assert (Path(summary["instance_root"]) / "settings.json").exists()
    assert (Path(summary["instance_root"]) / "model_settings.json").exists()

    model_settings_text = home_model_settings.read_text(encoding="utf-8")
    assert model_settings_text == '{"version":1,"models":{}}'

    dedicated_model_settings = (Path(summary["instance_root"]) / "model_settings.json").read_text(encoding="utf-8")
    assert '"Qwen2.5-VL-7B-Instruct-4bit"' in dedicated_model_settings
    assert '"is_default": true' in dedicated_model_settings.lower()
    assert '"is_pinned": true' in dedicated_model_settings.lower()


def test_setup_omlx_instance_resolves_model_repo_prefix_against_basename_dirs(tmp_path):
    source_root = tmp_path / "source-models"
    source_root.mkdir()
    (source_root / "Qwen2.5-VL-7B-Instruct-4bit").mkdir()

    home_settings = tmp_path / "home-settings.json"
    home_settings.write_text(
        '{"model":{"model_dirs":["%s"]},"cache":{"enabled":false},"server":{"host":"127.0.0.1","port":11435}}'
        % source_root.as_posix(),
        encoding="utf-8",
    )
    home_model_settings = tmp_path / "home-model-settings.json"
    home_model_settings.write_text('{"version":1,"models":{}}', encoding="utf-8")

    cfg = _base_config(tmp_path / "instance")
    summary = setup_omlx_instance(
        cfg,
        home_settings_path=home_settings,
        home_model_settings_path=home_model_settings,
    )

    model_dir = Path(summary["model_dir"])
    assert sorted(path.name for path in model_dir.iterdir()) == ["Qwen2.5-VL-7B-Instruct-4bit"]


def test_setup_omlx_instance_links_distinct_fast_vision_model(tmp_path):
    source_root = tmp_path / "source-models"
    source_root.mkdir()
    (source_root / "Qwen2.5-VL-3B-Instruct-4bit").mkdir()
    (source_root / "Qwen2.5-VL-7B-Instruct-4bit").mkdir()

    home_settings = tmp_path / "home-settings.json"
    home_settings.write_text(
        '{"model":{"model_dirs":["%s"]},"server":{"host":"127.0.0.1","port":11435}}'
        % source_root.as_posix(),
        encoding="utf-8",
    )
    home_model_settings = tmp_path / "home-model-settings.json"
    home_model_settings.write_text('{"version":1,"models":{}}', encoding="utf-8")

    cfg = _base_config(tmp_path / "instance")
    cfg["omlx"]["fast_vision_model"] = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
    summary = setup_omlx_instance(
        cfg,
        home_settings_path=home_settings,
        home_model_settings_path=home_model_settings,
    )

    assert summary["active_models"] == [
        "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
        "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
    ]
    assert sorted(path.name for path in Path(summary["model_dir"]).iterdir()) == [
        "Qwen2.5-VL-3B-Instruct-4bit",
        "Qwen2.5-VL-7B-Instruct-4bit",
    ]


def test_sync_omlx_shared_runtime_sets_active_models_without_deleting_inactive_entries(tmp_path):
    models_dir = tmp_path / "models"
    for model_name in (
        "Qwen3-VL-4B-Instruct-4bit",
        "Qwen3-VL-8B-Instruct-4bit",
        "gemma-4-e2b-it-4bit",
        "gemma-4-e4b-it-4bit",
    ):
        model_dir = models_dir / model_name
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text("{}", encoding="utf-8")

    home_settings = tmp_path / "settings.json"
    home_settings.write_text(
        json.dumps(
            {
                "version": "1.0",
                "model": {
                    "model_dirs": [str(models_dir)],
                    "model_dir": str(models_dir),
                },
                "active_models": ["gemma-4-e2b-it-4bit"],
            }
        ),
        encoding="utf-8",
    )
    home_model_settings = tmp_path / "model_settings.json"
    home_model_settings.write_text(
        json.dumps(
            {
                "version": 1,
                "models": {
                    "gemma-4-e2b-it-4bit": {"is_default": True, "is_pinned": True},
                    "Qwen3-VL-4B-Instruct-4bit": {"is_default": False, "is_pinned": False},
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = _base_config(tmp_path / "instance")
    cfg["omlx"]["full_vision_model"] = "Qwen3-VL-8B-Instruct-4bit"
    cfg["omlx"]["commentary_model"] = "Qwen3-VL-8B-Instruct-4bit"
    cfg["omlx"]["fast_vision_model"] = "Qwen3-VL-4B-Instruct-4bit"

    summary = sync_omlx_shared_runtime(
        cfg,
        home_settings_path=home_settings,
        home_model_settings_path=home_model_settings,
    )

    assert summary["active_models"] == [
        "Qwen3-VL-4B-Instruct-4bit",
        "Qwen3-VL-8B-Instruct-4bit",
    ]
    assert "gemma-4-e2b-it-4bit" in summary["inactive_models"]
    assert "gemma-4-e4b-it-4bit" in summary["inactive_models"]

    synced_settings = json.loads(home_settings.read_text(encoding="utf-8"))
    assert synced_settings["active_models"] == [
        "Qwen3-VL-4B-Instruct-4bit",
        "Qwen3-VL-8B-Instruct-4bit",
    ]

    synced_model_settings = json.loads(home_model_settings.read_text(encoding="utf-8"))
    assert synced_model_settings["models"]["Qwen3-VL-4B-Instruct-4bit"]["is_pinned"] is True
    assert synced_model_settings["models"]["Qwen3-VL-4B-Instruct-4bit"]["is_default"] is True
    assert synced_model_settings["models"]["Qwen3-VL-8B-Instruct-4bit"]["is_pinned"] is True
    assert synced_model_settings["models"]["Qwen3-VL-8B-Instruct-4bit"]["is_default"] is False
    assert synced_model_settings["models"]["gemma-4-e2b-it-4bit"]["is_pinned"] is False
    assert synced_model_settings["models"]["gemma-4-e2b-it-4bit"]["is_default"] is False
    assert synced_model_settings["models"]["gemma-4-e4b-it-4bit"]["is_pinned"] is False
    assert synced_model_settings["models"]["gemma-4-e4b-it-4bit"]["is_default"] is False


def test_build_omlx_start_command_uses_dedicated_model_and_cache_dirs(tmp_path):
    cfg = _base_config(tmp_path / "instance")

    command = build_omlx_start_command(
        cfg,
        omlx_command_prefix=["/opt/homebrew/bin/omlx"],
        instance_root=tmp_path / "instance",
        model_dir=tmp_path / "instance" / "models",
        cache_dir=tmp_path / "instance" / "cache",
    )

    assert command[:2] == ["/opt/homebrew/bin/omlx", "serve"]
    assert "--model-dir" in command
    assert str(tmp_path / "instance" / "models") in command
    assert "--paged-ssd-cache-dir" in command
    assert str(tmp_path / "instance" / "cache") in command
    assert "--base-path" in command
    assert str(tmp_path / "instance") in command
    assert "--port" in command
    assert "11435" in command


def test_build_omlx_start_command_wraps_app_cli_with_pythonnouserite(tmp_path):
    cfg = _base_config(tmp_path / "instance")

    command = build_omlx_start_command(
        cfg,
        omlx_command_prefix=["/Applications/oMLX.app/Contents/MacOS/omlx-cli"],
        instance_root=tmp_path / "instance",
        model_dir=tmp_path / "instance" / "models",
        cache_dir=tmp_path / "instance" / "cache",
    )

    assert command[:4] == [
        "/usr/bin/env",
        "PYTHONNOUSERSITE=1",
        "/Applications/oMLX.app/Contents/MacOS/omlx-cli",
        "serve",
    ]


def test_find_omlx_command_prefix_supports_app_cli_wrapper(monkeypatch):
    monkeypatch.setattr("material_agent.adapters.models.omlx.instance.shutil.which", lambda _: None)
    monkeypatch.setattr(
        "material_agent.adapters.models.omlx.instance.Path.exists",
        lambda self: str(self) == "/Applications/oMLX.app/Contents/MacOS/omlx-cli",
    )

    prefix = find_omlx_command_prefix()

    assert prefix == ["/Applications/oMLX.app/Contents/MacOS/omlx-cli"]
