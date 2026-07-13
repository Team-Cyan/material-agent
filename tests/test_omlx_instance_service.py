import json
from argparse import Namespace

import pytest

from material_agent.app.omlx_instance_service import OMLXInstanceService


def _config() -> dict:
    return {
        "backend": "omlx",
        "omlx": {
            "base_url": "http://127.0.0.1:11435",
            "full_vision_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "commentary_model": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
            "timeout": 120,
            "api_key": "secret",
            "instance_root": "/tmp/material-agent-omlx",
            "model_dir_mode": "config_union",
            "cache_enabled": True,
        },
        "screening": {
            "enabled": True,
            "backend": "musiq",
            "musiq": {"device": "cpu", "score_divisor": 10.0},
        },
    }


def test_omlx_instance_service_status_reports_layout_without_requiring_server(tmp_path):
    cfg = _config()
    cfg["omlx"]["instance_root"] = str(tmp_path / "instance")
    cfg["omlx"]["base_url"] = "http://127.0.0.1:9"
    service = OMLXInstanceService(
        home_settings_path=tmp_path / "settings.json",
        home_model_settings_path=tmp_path / "model_settings.json",
    )

    status = service.status(cfg)

    assert status["instance_root"] == str(tmp_path / "instance")
    assert status["reachable"] is False
    assert status["active_models"] == ["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"]
    assert status["capability_profile"]["reachable"] is False
    assert status["capability_valid"] is False
    assert status["capability_failure"]["code"] == "omlx_unreachable"
    assert "material-agent omlx-start --dedicated" in status["failure_guidance"]


def test_cli_shell_excludes_legacy_omlx_management_commands():
    from material_agent.shells.cli.main import build_parser

    parser = build_parser()
    subparsers_action = next(
        action for action in parser._actions if getattr(action, "dest", None) == "command"
    )

    assert {"omlx-setup", "omlx-start", "omlx-status"}.isdisjoint(
        set(subparsers_action.choices)
    )


def test_cmd_setup_omlx_delegates_to_service(monkeypatch, capsys):
    from material_agent.commands.omlx_runtime import cmd_setup_omlx

    called = {}

    class _FakeService:
        def setup(self, config):
            called["config"] = config
            return {"instance_root": "/tmp/pj-omlx", "linked_models": ["Qwen2.5-VL-7B-Instruct-4bit"]}

    monkeypatch.setattr("material_agent.commands.omlx_runtime.OMLXInstanceService", lambda: _FakeService())

    cmd_setup_omlx(Namespace(config="config.yaml"), _config())
    out = capsys.readouterr().out

    assert called["config"]["backend"] == "omlx"
    assert "/tmp/pj-omlx" in out


def test_cmd_start_omlx_opens_shared_desktop_app_by_default(monkeypatch, capsys):
    from material_agent.commands.omlx_runtime import cmd_start_omlx

    called = {}

    def _fake_open():
        called["opened"] = True

    class _FakeService:
        def sync_shared(self, config):
            called["config"] = config
            return {
                "active_models": ["Qwen3-VL-4B-Instruct-4bit"],
                "inactive_models": ["gemma-4-e2b-it-4bit"],
                "changed": True,
            }

        def wait_until_ready(self, config, timeout_seconds=30.0):
            called["waited"] = (config, timeout_seconds)
            return {"reachable": True}

    monkeypatch.setattr("material_agent.commands.omlx_runtime._open_omlx_app", _fake_open)
    monkeypatch.setattr("material_agent.commands.omlx_runtime.OMLXInstanceService", lambda: _FakeService())

    cmd_start_omlx(Namespace(config="config.yaml", dedicated=False, restart_shared=False), _config())
    out = capsys.readouterr().out

    assert called["opened"] is True
    assert called["config"]["backend"] == "omlx"
    assert called["waited"][0]["backend"] == "omlx"
    assert "active models: Qwen3-VL-4B-Instruct-4bit" in out
    assert "inactive models: gemma-4-e2b-it-4bit" in out
    assert "--restart-shared" in out
    assert "shared desktop runtime" in out
    assert "--dedicated" in out


def test_cmd_start_omlx_can_restart_shared_desktop_runtime(monkeypatch, capsys):
    from material_agent.commands.omlx_runtime import cmd_start_omlx

    called = {}

    class _FakeService:
        def restart_shared(self, config):
            called["config"] = config
            return {
                "active_models": ["Qwen3-VL-4B-Instruct-4bit"],
                "inactive_models": ["gemma-4-e2b-it-4bit", "gemma-4-e4b-it-4bit"],
                "terminated_pids": [111, 222],
                "changed": True,
            }

    monkeypatch.setattr("material_agent.commands.omlx_runtime.OMLXInstanceService", lambda: _FakeService())

    cmd_start_omlx(Namespace(config="config.yaml", dedicated=False, restart_shared=True), _config())
    out = capsys.readouterr().out

    assert called["config"]["backend"] == "omlx"
    assert "restarted /Applications/oMLX.app" in out
    assert "terminated shared desktop pids: 111, 222" in out
    assert "inactive models: gemma-4-e2b-it-4bit, gemma-4-e4b-it-4bit" in out


def test_cmd_start_omlx_can_start_dedicated_runtime(monkeypatch, capsys):
    from material_agent.commands.omlx_runtime import cmd_start_omlx

    class _FakeService:
        def start(self, config):
            assert config["backend"] == "omlx"
            return {
                "started": True,
                "pid": 4321,
                "base_url": "http://127.0.0.1:11435",
                "served_models": ["Qwen2.5-VL-7B-Instruct-4bit"],
            }

    monkeypatch.setattr("material_agent.commands.omlx_runtime.OMLXInstanceService", lambda: _FakeService())

    cmd_start_omlx(Namespace(config="config.yaml", dedicated=True, restart_shared=False), _config())
    out = capsys.readouterr().out

    assert "pid=4321" in out
    assert "served models: Qwen2.5-VL-7B-Instruct-4bit" in out


def test_omlx_instance_service_restart_shared_terminates_desktop_processes(tmp_path, monkeypatch):
    cfg = _config()
    service = OMLXInstanceService(
        home_settings_path=tmp_path / "settings.json",
        home_model_settings_path=tmp_path / "model_settings.json",
    )
    killed = []
    opened = []

    monkeypatch.setattr(
        service,
        "sync_shared",
        lambda config: {
            "active_models": ["Qwen3-VL-4B-Instruct-4bit"],
            "inactive_models": ["gemma-4-e2b-it-4bit"],
            "changed": True,
        },
    )
    monkeypatch.setattr(service, "_shared_desktop_pids", lambda config: [321, 654])
    monkeypatch.setattr(service, "_wait_for_pids_to_exit", lambda pids: opened.append(("waited", pids)))
    monkeypatch.setattr(service, "_wait_until_ready", lambda config, timeout_seconds=30.0: opened.append(("ready", timeout_seconds)))
    monkeypatch.setattr("material_agent.app.omlx_instance_service.os.kill", lambda pid, sig: killed.append((pid, sig)))

    def _fake_run(command, check):
        opened.append(tuple(command))
        assert check is True
        return None

    monkeypatch.setattr("material_agent.app.omlx_instance_service.subprocess.run", _fake_run)

    summary = service.restart_shared(cfg)

    assert [pid for pid, _sig in killed] == [321, 654]
    assert ("waited", [321, 654]) in opened
    assert ("ready", 30.0) in opened
    assert ("open", "-a", "/Applications/oMLX.app") in opened
    assert summary["terminated_pids"] == [321, 654]
    assert summary["restarted"] is True


def test_omlx_instance_service_sync_shared_rejects_non_desktop_local_runtime(tmp_path):
    cfg = _config()
    cfg["omlx"]["base_url"] = "http://127.0.0.1:22445"
    home_settings = tmp_path / "settings.json"
    home_settings.write_text(
        json.dumps({"server": {"host": "127.0.0.1", "port": 11435}}),
        encoding="utf-8",
    )
    service = OMLXInstanceService(
        home_settings_path=home_settings,
        home_model_settings_path=tmp_path / "model_settings.json",
    )

    try:
        service.sync_shared(cfg)
    except RuntimeError as exc:
        assert "Shared desktop oMLX management requires" in str(exc)
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("sync_shared should reject non-desktop local runtime configs")


def test_omlx_instance_service_normalizes_instance_root_before_setup(tmp_path, monkeypatch):
    cfg = _config()
    cfg["omlx"]["instance_root"] = "~/.material-agent/test-omlx-instance"
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    source_root = tmp_path / "source-models"
    source_root.mkdir()
    (source_root / "Qwen2.5-VL-7B-Instruct-4bit").mkdir()
    cfg["omlx"]["source_model_dirs"] = [str(source_root)]
    service = OMLXInstanceService(
        home_settings_path=tmp_path / "settings.json",
        home_model_settings_path=tmp_path / "model_settings.json",
    )

    summary = service.setup(cfg)

    assert summary["instance_root"] == str((fake_home / ".material-agent" / "test-omlx-instance").resolve())


def test_omlx_instance_service_status_detects_shared_server_conflict(tmp_path, monkeypatch):
    cfg = _config()
    cfg["omlx"]["instance_root"] = str(tmp_path / "instance")
    model_dir = tmp_path / "instance" / "models"
    model_dir.mkdir(parents=True)
    (model_dir / "Qwen2.5-VL-7B-Instruct-4bit").mkdir()

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"id": "Qwen3.5-9B-MLX-4bit"},
                ]
            }

    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.get", lambda *args, **kwargs: _FakeResponse())

    status = OMLXInstanceService().status(cfg)

    assert status["reachable"] is True
    assert status["instance_matches"] is False
    assert status["capability_valid"] is False
    assert status["capability_failure"]["code"] == "instance_mismatch"
    assert "served_models" in status["capability_profile"]
    assert "configured models" in status["failure_guidance"]


def test_omlx_instance_service_status_uses_shared_active_models_for_shared_runtime(tmp_path, monkeypatch):
    cfg = _config()
    cfg["omlx"]["base_url"] = "http://127.0.0.1:11435"
    cfg["omlx"]["full_vision_model"] = "Qwen3-VL-4B-Instruct-4bit"
    cfg["omlx"]["commentary_model"] = "Qwen3-VL-4B-Instruct-4bit"
    cfg["omlx"]["fast_vision_model"] = "Qwen3-VL-4B-Instruct-4bit"
    cfg["omlx"]["runtime"] = {
        "required_version": ">=0.3.0",
        "require_structured_outputs": False,
        "require_xgrammar": False,
        "probe_on_run": True,
        "enforce_dedicated_instance": False,
    }
    cfg["omlx"]["instance_root"] = str(tmp_path / "instance")
    model_dir = tmp_path / "instance" / "models"
    model_dir.mkdir(parents=True)
    (model_dir / "Qwen3-VL-8B-Instruct-4bit").mkdir()
    home_settings = tmp_path / "settings.json"
    home_settings.write_text(
        json.dumps(
            {
                "server": {"host": "127.0.0.1", "port": 11435},
                "active_models": ["Qwen3-VL-4B-Instruct-4bit"],
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def _fake_probe(**kwargs):
        captured.update(kwargs)

        class _Profile:
            reachable = True
            instance_matches = True
            served_models = ["Qwen3-VL-4B-Instruct-4bit"]
            error = None
            version = "0.3.4"
            structured_outputs = False
            xgrammar = False
            settings_drift = []

            def to_dict(self):
                return {
                    "reachable": True,
                    "instance_matches": True,
                    "served_models": ["Qwen3-VL-4B-Instruct-4bit"],
                    "settings_drift": [],
                }

        return _Profile()

    monkeypatch.setattr("material_agent.app.omlx_instance_service.probe_omlx_capabilities", _fake_probe)
    monkeypatch.setattr(
        "material_agent.app.omlx_instance_service.validate_omlx_capability",
        lambda *args, **kwargs: (True, None),
    )
    monkeypatch.setattr(
        "material_agent.app.omlx_instance_service.build_omlx_failure_guidance",
        lambda *args, **kwargs: "ok",
    )
    monkeypatch.setattr(
        OMLXInstanceService,
        "_shared_desktop_pids",
        lambda self, config: [111, 222],
    )

    status = OMLXInstanceService(home_settings_path=home_settings).status(cfg)

    assert captured["linked_models"] == ["Qwen3-VL-4B-Instruct-4bit"]
    assert status["linked_models"] == ["Qwen3-VL-4B-Instruct-4bit"]
    assert status["runtime_mode"] == "shared_desktop"
    assert status["shared_desktop_running"] is True
    assert status["shared_desktop_pids"] == [111, 222]


def test_omlx_instance_service_status_falls_back_to_pinned_model_settings_for_shared_runtime(
    tmp_path, monkeypatch
):
    cfg = _config()
    cfg["omlx"]["base_url"] = "http://127.0.0.1:11435"
    cfg["omlx"]["full_vision_model"] = "Qwen3-VL-4B-Instruct-4bit"
    cfg["omlx"]["commentary_model"] = "Qwen3-VL-4B-Instruct-4bit"
    cfg["omlx"]["fast_vision_model"] = "Qwen3-VL-4B-Instruct-4bit"
    cfg["omlx"]["runtime"] = {
        "required_version": ">=0.3.0",
        "require_structured_outputs": False,
        "require_xgrammar": False,
        "probe_on_run": True,
        "enforce_dedicated_instance": False,
    }
    home_settings = tmp_path / "settings.json"
    home_settings.write_text(
        json.dumps({"server": {"host": "127.0.0.1", "port": 11435}}),
        encoding="utf-8",
    )
    home_model_settings = tmp_path / "model_settings.json"
    home_model_settings.write_text(
        json.dumps(
            {
                "models": {
                    "Qwen3-VL-4B-Instruct-4bit": {"is_pinned": True, "is_default": True},
                    "Qwen3-VL-8B-Instruct-4bit": {"is_pinned": False, "is_default": False},
                }
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def _fake_probe(**kwargs):
        captured.update(kwargs)

        class _Profile:
            reachable = True
            instance_matches = True
            served_models = ["Qwen3-VL-4B-Instruct-4bit"]
            error = None
            version = "0.3.4"
            structured_outputs = False
            xgrammar = False
            settings_drift = []

            def to_dict(self):
                return {
                    "reachable": True,
                    "instance_matches": True,
                    "served_models": ["Qwen3-VL-4B-Instruct-4bit"],
                    "settings_drift": [],
                }

        return _Profile()

    monkeypatch.setattr("material_agent.app.omlx_instance_service.probe_omlx_capabilities", _fake_probe)
    monkeypatch.setattr(
        "material_agent.app.omlx_instance_service.validate_omlx_capability",
        lambda *args, **kwargs: (True, None),
    )
    monkeypatch.setattr(
        "material_agent.app.omlx_instance_service.build_omlx_failure_guidance",
        lambda *args, **kwargs: "ok",
    )

    status = OMLXInstanceService(
        home_settings_path=home_settings,
        home_model_settings_path=home_model_settings,
    ).status(cfg)

    assert captured["linked_models"] == ["Qwen3-VL-4B-Instruct-4bit"]
    assert status["linked_models"] == ["Qwen3-VL-4B-Instruct-4bit"]


def test_omlx_instance_service_status_can_skip_dedicated_instance_enforcement(tmp_path, monkeypatch):
    cfg = _config()
    cfg["omlx"]["instance_root"] = str(tmp_path / "instance")
    cfg["omlx"]["runtime"] = {
        "required_version": ">=0.3.0",
        "require_structured_outputs": True,
        "require_xgrammar": True,
        "probe_on_run": True,
        "enforce_dedicated_instance": False,
    }
    model_dir = tmp_path / "instance" / "models"
    model_dir.mkdir(parents=True)
    (model_dir / "Qwen2.5-VL-7B-Instruct-4bit").mkdir()

    payloads = {
        "http://127.0.0.1:11435/v1/models": {
            "data": [
                {"id": "Qwen2.5-VL-7B-Instruct-4bit"},
                {"id": "Qwen3.5-9B-MLX-4bit"},
            ]
        },
        "http://127.0.0.1:11435/version": {"version": "0.3.7"},
        "http://127.0.0.1:11435/admin/settings": {
            "capabilities": {
                "structured_outputs": True,
                "xgrammar": True,
            }
        },
    }

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _fake_get(url, **kwargs):
        payload = payloads.get(url)
        if payload is None:
            raise RuntimeError("missing endpoint")
        return _FakeResponse(payload)

    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.get", _fake_get)

    status = OMLXInstanceService().status(cfg)

    assert status["reachable"] is True
    assert status["instance_matches"] is False
    assert status["capability_valid"] is True
    assert status["capability_failure"] is None


def test_omlx_instance_service_start_rejects_shared_server_conflict(tmp_path, monkeypatch):
    cfg = _config()
    cfg["omlx"]["instance_root"] = str(tmp_path / "instance")
    service = OMLXInstanceService()

    def _fake_setup(config):
        return {
            "instance_root": str(tmp_path / "instance"),
            "model_dir": str(tmp_path / "instance" / "models"),
            "cache_dir": str(tmp_path / "instance" / "cache"),
            "logs_dir": str(tmp_path / "instance" / "logs"),
            "run_dir": str(tmp_path / "instance" / "run"),
            "active_models": ["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
            "linked_models": ["Qwen2.5-VL-7B-Instruct-4bit"],
            "cache_enabled": True,
            "base_url": "http://127.0.0.1:11435",
        }

    def _fake_status(config):
        return {
            "instance_root": str(tmp_path / "instance"),
            "model_dir": str(tmp_path / "instance" / "models"),
            "cache_dir": str(tmp_path / "instance" / "cache"),
            "active_models": ["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
            "linked_models": ["Qwen2.5-VL-7B-Instruct-4bit"],
            "pid": None,
            "pid_alive": False,
            "reachable": True,
            "served_models": ["Qwen3.5-9B-MLX-4bit"],
            "base_url": "http://127.0.0.1:11435",
            "cache_enabled": True,
            "error": None,
            "instance_matches": False,
            "capability_profile": {"instance_matches": False},
            "capability_valid": False,
            "capability_failure": {
                "code": "instance_mismatch",
                "summary": "Reachable OMLX server does not match the dedicated instance model set.",
            },
            "failure_guidance": "Stop the shared server or change omlx.base_url.",
        }

    monkeypatch.setattr(service, "setup", _fake_setup)
    monkeypatch.setattr(service, "status", _fake_status)

    try:
        service.start(cfg)
    except RuntimeError as exc:
        assert "does not match the dedicated instance model set" in str(exc)
        assert "change omlx.base_url" in str(exc)
    else:  # pragma: no cover - red path
        raise AssertionError("expected RuntimeError for shared server conflict")


def test_omlx_instance_service_start_rejects_reachable_runtime_with_invalid_capabilities(tmp_path, monkeypatch):
    cfg = _config()
    cfg["omlx"]["instance_root"] = str(tmp_path / "instance")
    service = OMLXInstanceService()

    def _fake_setup(config):
        return {
            "instance_root": str(tmp_path / "instance"),
            "model_dir": str(tmp_path / "instance" / "models"),
            "cache_dir": str(tmp_path / "instance" / "cache"),
            "logs_dir": str(tmp_path / "instance" / "logs"),
            "run_dir": str(tmp_path / "instance" / "run"),
            "active_models": ["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
            "linked_models": ["Qwen2.5-VL-7B-Instruct-4bit"],
            "cache_enabled": True,
            "base_url": "http://127.0.0.1:11435",
        }

    def _fake_status(config):
        return {
            "instance_root": str(tmp_path / "instance"),
            "model_dir": str(tmp_path / "instance" / "models"),
            "cache_dir": str(tmp_path / "instance" / "cache"),
            "active_models": ["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
            "linked_models": ["Qwen2.5-VL-7B-Instruct-4bit"],
            "pid": 4321,
            "pid_alive": True,
            "reachable": True,
            "served_models": ["Qwen2.5-VL-7B-Instruct-4bit"],
            "base_url": "http://127.0.0.1:11435",
            "cache_enabled": True,
            "error": None,
            "instance_matches": True,
            "capability_profile": {
                "reachable": True,
                "instance_matches": True,
                "structured_outputs": False,
                "xgrammar": True,
            },
            "capability_valid": False,
            "capability_failure": {
                "code": "structured_outputs_missing",
                "summary": "Structured outputs are required but unavailable.",
            },
            "failure_guidance": "Upgrade OMLX to a build with structured output support.",
        }

    monkeypatch.setattr(service, "setup", _fake_setup)
    monkeypatch.setattr(service, "status", _fake_status)

    try:
        service.start(cfg)
    except RuntimeError as exc:
        assert "Structured outputs are required but unavailable." in str(exc)
        assert "Upgrade OMLX" in str(exc)
    else:  # pragma: no cover - red path
        raise AssertionError("expected RuntimeError for invalid reachable runtime")


def test_omlx_instance_service_start_refuses_discovered_api_key_before_process_args(
    tmp_path,
    monkeypatch,
):
    cfg = _config()
    cfg["omlx"]["api_key"] = ""
    cfg["omlx"]["instance_root"] = str(tmp_path / "instance")
    discovered_secret = "settings-file-secret"
    home_settings = tmp_path / "settings.json"
    home_settings.write_text(
        json.dumps({"auth": {"api_key": discovered_secret}}),
        encoding="utf-8",
    )
    service = OMLXInstanceService(home_settings_path=home_settings)
    summary = {
        "instance_root": str(tmp_path / "instance"),
        "model_dir": str(tmp_path / "instance" / "models"),
        "cache_dir": str(tmp_path / "instance" / "cache"),
        "logs_dir": str(tmp_path / "instance" / "logs"),
        "run_dir": str(tmp_path / "instance" / "run"),
    }
    monkeypatch.setattr(service, "setup", lambda _config: summary)
    monkeypatch.setattr(
        service,
        "status",
        lambda _config: {"reachable": False, "capability_valid": False},
    )
    monkeypatch.setattr(
        "material_agent.app.omlx_instance_service.find_omlx_command_prefix",
        lambda: pytest.fail("command discovery must not run with authenticated start"),
    )

    with pytest.raises(RuntimeError) as exc_info:
        service.start(cfg)

    assert "process arguments" in str(exc_info.value)
    assert discovered_secret not in str(exc_info.value)


def test_cmd_status_omlx_surfaces_capability_diagnostics(monkeypatch, capsys):
    from material_agent.commands.omlx_runtime import cmd_status_omlx

    class _FakeService:
        def status(self, config):
            return {
                "instance_root": "/tmp/material-agent-omlx",
                "runtime_mode": "shared_desktop",
                "reachable": True,
                "instance_matches": False,
                "effective_model_set_matches": True,
                "served_models_catalog_superset": True,
                "pid_alive": True,
                "shared_desktop_running": True,
                "shared_desktop_pids": [111, 222],
                "active_models": ["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
                "linked_models": ["Qwen2.5-VL-7B-Instruct-4bit"],
                "served_models": ["Qwen3.5-9B-MLX-4bit"],
                "error": None,
                "capability_profile": {
                    "version": "0.3.1",
                    "structured_outputs": False,
                    "xgrammar": True,
                    "settings_drift": ["served models do not include linked models"],
                },
                "capability_valid": False,
                "capability_failure": {
                    "code": "structured_outputs_missing",
                    "summary": "Structured outputs are required but unavailable.",
                },
                "failure_guidance": "Enable structured output support or upgrade oMLX.",
            }

    monkeypatch.setattr("material_agent.commands.omlx_runtime.OMLXInstanceService", lambda: _FakeService())

    cmd_status_omlx(Namespace(config="config.yaml"), _config())
    out = capsys.readouterr().out

    assert "active models: mlx-community/Qwen2.5-VL-7B-Instruct-4bit" in out
    assert "linked models: Qwen2.5-VL-7B-Instruct-4bit" in out
    assert "runtime_mode: shared_desktop" in out
    assert "shared_desktop_running: True" in out
    assert "shared_desktop_pids: 111, 222" in out
    assert "pid_alive:" not in out
    assert "effective_model_set_matches: True" in out
    assert "served_models_catalog_superset: true" in out
    assert "installed-model catalog" in out
    assert "version: 0.3.1" in out
    assert "structured_outputs: False" in out
    assert "xgrammar: True" in out
    assert "capability_valid: False" in out
    assert "capability_failure: structured_outputs_missing" in out
    assert "guidance: Enable structured output support or upgrade oMLX." in out


def test_cmd_status_omlx_json_emits_status_summary(monkeypatch, capsys):
    from material_agent.commands.omlx_runtime import cmd_status_omlx

    summary = {
        "instance_root": "/tmp/material-agent-omlx",
        "model_dir": "/tmp/material-agent-omlx/models",
        "cache_dir": "/tmp/material-agent-omlx/cache",
        "runtime_mode": "shared_desktop",
        "reachable": True,
        "instance_matches": True,
        "effective_model_set_matches": True,
        "served_models_catalog_superset": False,
        "pid_alive": True,
        "shared_desktop_running": True,
        "shared_desktop_pids": [111, 222],
        "active_models": ["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        "linked_models": ["Qwen2.5-VL-7B-Instruct-4bit"],
        "served_models": ["Qwen2.5-VL-7B-Instruct-4bit"],
        "base_url": "http://127.0.0.1:11435",
        "cache_enabled": True,
        "error": None,
        "version": "0.3.1",
        "structured_outputs": True,
        "xgrammar": False,
        "settings_drift": [],
        "capability_profile": {
            "reachable": True,
            "instance_matches": True,
            "effective_model_set_matches": True,
            "served_models_catalog_superset": False,
            "served_models": ["Qwen2.5-VL-7B-Instruct-4bit"],
            "version": "0.3.1",
            "structured_outputs": True,
            "xgrammar": False,
            "settings_drift": [],
        },
        "capability_valid": True,
        "capability_failure": None,
        "failure_guidance": None,
    }

    class _FakeService:
        def status(self, config):
            return summary

    monkeypatch.setattr("material_agent.commands.omlx_runtime.OMLXInstanceService", lambda: _FakeService())

    cmd_status_omlx(Namespace(config="config.yaml", json=True), _config())
    out = capsys.readouterr().out

    assert out.endswith("\n")
    assert json.loads(out) == summary


def test_wait_until_ready_requires_capability_valid_before_returning(monkeypatch):
    service = OMLXInstanceService()
    statuses = iter(
        [
            {"reachable": False, "capability_valid": False},
            {
                "reachable": True,
                "capability_valid": False,
                "capability_failure": {"summary": "Structured outputs are required but unavailable."},
                "failure_guidance": "Upgrade OMLX.",
            },
            {"reachable": True, "capability_valid": True},
        ]
    )
    calls = {"count": 0}

    def _fake_status(_config):
        calls["count"] += 1
        return next(statuses)

    monkeypatch.setattr(service, "status", _fake_status)
    monkeypatch.setattr("material_agent.app.omlx_instance_service.time.sleep", lambda _seconds: None)

    service._wait_until_ready(_config(), timeout_seconds=1.0)

    assert calls["count"] == 3
