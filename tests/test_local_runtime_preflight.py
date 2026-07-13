import json
import sys
from types import SimpleNamespace

import pytest

from material_agent.adapters.models.local_runtime import probe_local_runtime
from material_agent.adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from material_agent.app.dto import JobStage, JobStatus, JobType, SessionKind, SessionStatus
from material_agent.commands.scoring import _build_runtime_probe_preflight_hook


def _fake_openvino(monkeypatch, devices: list[str]) -> None:
    fake_module = SimpleNamespace(
        __version__="test-openvino",
        Core=lambda: SimpleNamespace(available_devices=devices),
    )
    monkeypatch.setitem(sys.modules, "openvino", fake_module)
    monkeypatch.setattr(
        "material_agent.adapters.models.local_runtime.util.find_spec",
        lambda name: object() if name == "openvino" else None,
    )


def _create_session_and_job(repo: SQLiteRuntimeRepository) -> tuple[str, str]:
    session_id = repo.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "local"},
        status=SessionStatus.OPEN,
    )
    job_id = repo.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        stage=JobStage.DISCOVER,
        status=JobStatus.QUEUED,
    )
    return session_id, job_id


def test_probe_local_runtime_cpu_runtime_is_valid():
    payload = probe_local_runtime(
        {
            "backend": "local",
            "inference": {
                "runtime": "cpu",
                "device": "CPU",
                "fallback_device": "CPU",
                "provider_tags": ["cpu"],
            },
        }
    )

    assert payload["capability_valid"] is True
    assert payload["runtime"] == "cpu"
    assert payload["available_devices"] == ["CPU"]
    assert payload["heuristic_scoring_active"] is True


def test_probe_local_runtime_parses_string_enforce_available_false():
    payload = probe_local_runtime(
        {
            "backend": "local",
            "inference": {
                "runtime": "cpu",
                "enforce_available": "false",
                "provider_tags": "cpu",
            },
        }
    )

    assert payload["enforce_available"] is False
    assert payload["provider_tags"] == ["cpu"]


def test_openvino_preflight_rejects_missing_requested_device(monkeypatch):
    _fake_openvino(monkeypatch, ["CPU"])

    payload = probe_local_runtime(
        {
            "inference": {
                "runtime": "openvino",
                "device": "GPU",
                "fallback_device": "CPU",
                "enforce_available": True,
            }
        }
    )

    assert payload["capability_valid"] is False
    assert payload["capability_failure"]["code"] == "requested_device_missing"


def test_openvino_preflight_accepts_auto_cpu_fallback(monkeypatch):
    _fake_openvino(monkeypatch, ["CPU"])

    payload = probe_local_runtime(
        {
            "inference": {
                "runtime": "openvino",
                "device": "AUTO:GPU,CPU",
                "fallback_device": "CPU",
                "enforce_available": True,
            }
        }
    )

    assert payload["capability_valid"] is True
    assert payload["accelerator_available"] is False


def test_openvino_preflight_rejects_missing_fallback_device(monkeypatch):
    _fake_openvino(monkeypatch, ["GPU.0"])

    payload = probe_local_runtime(
        {
            "inference": {
                "runtime": "openvino",
                "device": "GPU",
                "fallback_device": "CPU",
                "enforce_available": True,
            }
        }
    )

    assert payload["capability_valid"] is False
    assert payload["capability_failure"]["code"] == "fallback_device_missing"


def test_local_runtime_preflight_records_report_only_warning(monkeypatch, tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_id, job_id = _create_session_and_job(repo)

    monkeypatch.setattr(
        "material_agent.commands.scoring.probe_local_runtime",
        lambda _config: {
            "backend": "local",
            "runtime": "openvino",
            "enforce_available": False,
            "heuristic_scoring_active": True,
            "capability_valid": False,
            "capability_failure": {
                "code": "package_missing",
                "summary": "openvino is not installed.",
            },
        },
    )

    hook = _build_runtime_probe_preflight_hook(repo, {"backend": "local", "inference": {}})
    assert hook is not None
    hook(session_id, job_id)

    event = repo.conn.execute(
        "SELECT event_type, payload_json FROM events WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    artifact = repo.conn.execute(
        "SELECT kind, uri, metadata_json FROM artifacts WHERE job_id = ?",
        (job_id,),
    ).fetchone()

    assert event["event_type"] == "runtime_preflight_warned"
    assert json.loads(event["payload_json"])["capability_failure"]["code"] == "package_missing"
    assert artifact["kind"] == "runtime_preflight"
    assert artifact["uri"] == "runtime://local/openvino/warned"


def test_local_runtime_preflight_raises_when_enforced(monkeypatch, tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_id, job_id = _create_session_and_job(repo)

    monkeypatch.setattr(
        "material_agent.commands.scoring.probe_local_runtime",
        lambda _config: {
            "backend": "local",
            "runtime": "openvino",
            "enforce_available": True,
            "heuristic_scoring_active": True,
            "capability_valid": False,
            "capability_failure": {
                "code": "package_missing",
                "summary": "openvino is not installed.",
            },
        },
    )

    hook = _build_runtime_probe_preflight_hook(repo, {"backend": "local", "inference": {}})
    assert hook is not None
    with pytest.raises(RuntimeError, match="Local runtime preflight failed"):
        hook(session_id, job_id)

    event = repo.conn.execute(
        "SELECT event_type FROM events WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    assert event["event_type"] == "runtime_preflight_warned"
