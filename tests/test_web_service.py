import json
import os
import signal
import subprocess
import sys
import time
import sqlite3
import stat
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from material_agent.app.web_service import (
    MaterialWebServer,
    WebLibraryRepository,
    WebTaskManager,
    _restore_redacted,
)


def test_library_index_bootstraps_runtime_schema_and_lists_unscored_files(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "one.ARW").write_bytes(b"raw")
    (photos / "two.jpg").write_bytes(b"jpeg")
    repository = WebLibraryRepository(tmp_path / "config" / "state.db", photos)

    assert repository.summary() == {
        "indexed": 0,
        "scored": 0,
        "score_records": 0,
        "errors": 0,
        "average_score": None,
        "scenes": [],
    }
    result = repository.refresh_index(["ARW", "JPG"])
    listing = repository.list_items({"page_size": ["10"]})

    assert result["indexed"] == 2
    assert listing["total"] == 2
    assert {item["relative_path"] for item in listing["items"]} == {"one.ARW", "two.jpg"}
    assert all(item["score_total"] is None for item in listing["items"])


def test_library_returns_latest_complete_score_payload(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    source = photos / "portrait.ARW"
    source.write_bytes(b"raw")
    db_path = tmp_path / "config" / "state.db"
    repository = WebLibraryRepository(db_path, photos)
    repository.refresh_index(["ARW"])
    payload = {
        "decision": "keep",
        "star_rating": 4,
        "tags": ["person", "portrait"],
        "description": "sharp portrait",
        "meta": {"subject_focus": {"primary_target": {"label": "person"}}},
    }
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO sessions(id, kind, input_root, config_snapshot, status) "
            "VALUES('session', 'review', ?, '{}', 'finished')",
            (str(photos),),
        )
        connection.execute(
            "INSERT INTO jobs(id, session_id, type, stage, status) "
            "VALUES('job', 'session', 'review', 'score', 'finished')"
        )
        connection.execute(
            "INSERT INTO job_files(id, job_id, file_path, status, score_total, scene) "
            "VALUES('file', 'job', ?, 'finished', 7.4, 'portrait')",
            (str(source.resolve()),),
        )
        connection.execute(
            "INSERT INTO artifacts(id, job_id, job_file_id, kind, uri, metadata_json) "
            "VALUES('artifact', 'job', 'file', 'score_payload', 'db://score', ?)",
            (json.dumps(payload),),
        )

    listing = repository.list_items({"scored": ["yes"]})
    detail = repository.detail(listing["items"][0]["id"])

    assert listing["items"][0]["target"] == "person"
    assert listing["items"][0]["decision"] == "keep"
    assert detail["score"] == payload
    assert repository.summary()["average_score"] == 7.4


def test_redacted_config_values_preserve_existing_secrets():
    existing = {"api": {"token": "secret", "timeout": 30}, "items": [{"password": "p"}]}
    proposed = {
        "api": {"token": "[REDACTED]", "timeout": 45},
        "items": [{"password": "[REDACTED]"}],
    }
    assert _restore_redacted(existing, proposed) == {
        "api": {"token": "secret", "timeout": 45},
        "items": [{"password": "p"}],
    }


def test_web_tasks_are_always_dry_run_and_can_remove_sample_limit(tmp_path, monkeypatch):
    photos = tmp_path / "photos"
    photos.mkdir()
    config_path = tmp_path / "config.yaml"
    config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    config["review_pipeline"]["max_files"] = 128
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    captured = {}

    class FakeProcess:
        pid = 12345

        def __init__(self, command, **_kwargs):
            captured["command"] = command

        def wait(self):
            return 0

        def poll(self):
            return None

    monkeypatch.setattr("material_agent.app.web_service.subprocess.Popen", FakeProcess)
    manager = WebTaskManager(
        input_root=photos,
        config_path=config_path,
        work_dir=tmp_path / "work",
    )
    task = manager.start(max_files=None, reprocess=False, no_visual_merge=False)

    assert "--dry-run" in task["command"]
    assert "material_agent.app.web_worker" in captured["command"]
    task_config = yaml.safe_load(Path(task["config_path"]).read_text(encoding="utf-8"))
    assert "max_files" not in task_config["review_pipeline"]
    private_paths = [
        config_path,
        Path(task["config_path"]),
        Path(task["log_path"]),
        manager.state_path,
    ]
    assert {stat.S_IMODE(path.stat().st_mode) for path in private_paths} == {0o600}
    assert stat.S_IMODE(manager.web_dir.stat().st_mode) == 0o700


def test_web_api_is_available_without_token_on_trusted_lan(tmp_path):
    server = MaterialWebServer(
        ("127.0.0.1", 0),
        library=MagicMock(),
        tasks=MagicMock(),
        model_service=MagicMock(),
        config_path=tmp_path / "config.yaml",
        thumbnail_dir=tmp_path / "thumbs",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert b"material-agent" in urllib.request.urlopen(base + "/").read()
        assert json.loads(urllib.request.urlopen(base + "/health").read()) == {"status": "ok"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_web_config_rejects_invalid_policy_without_replacing_active_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    original = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    config_path.write_text(yaml.safe_dump(original), encoding="utf-8")
    server = MaterialWebServer(
        ("127.0.0.1", 0),
        library=MagicMock(),
        tasks=MagicMock(),
        model_service=MagicMock(),
        config_path=config_path,
        thumbnail_dir=tmp_path / "thumbs",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    proposed = json.loads(json.dumps(original))
    proposed["decision_policy"]["keep_threshold"] = "invalid"
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/api/config",
        data=json.dumps({"config": proposed}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 400
        assert "keep_threshold" in error.value.read().decode("utf-8")
        assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == original
        assert not config_path.with_suffix(".web.tmp").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _until(predicate, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.025)
    raise AssertionError("timed out waiting for controlled Web worker")


@pytest.fixture
def worker_manager(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text(Path("config.yaml").read_text())
    executable = tmp_path / "dummy-run"
    executable.write_text(
        f"#!{sys.executable}\n"
        + """
import os
import sys
import time
from pathlib import Path
from material_agent.utils.run_control import exclusive_run_lock, sigterm_as_cancellation
from material_agent.app.errors import RunCancelled
work = Path(os.environ["MATERIAL_AGENT_WORK_DIR"])
try:
    with sigterm_as_cancellation(), exclusive_run_lock(work / "run.lock"):
        (work / "ready").write_text(str(os.getpid()))
        while not (work / "finish").exists():
            time.sleep(0.025)
        sys.exit(int((work / "finish").read_text()))
except RunCancelled:
    sys.exit(130)
"""
    )
    executable.chmod(0o700)
    managers = []
    supervisors = []

    def create():
        manager = WebTaskManager(
            input_root=photos,
            config_path=config,
            work_dir=tmp_path / "work",
            executable=str(executable),
        )
        managers.append(manager)
        return manager

    yield create
    # Exit through the fixture-owned marker even when a deliberately damaged
    # receipt prevents discovering/cancelling the child through normal APIs.
    for manager in managers:
        (manager.work_dir / "finish").write_text("0")
    for manager in managers:
        for task in manager._tasks.values():
            try:
                manager.cancel(task.id)
            except OSError, ValueError:
                pass
        supervisors.extend(manager._processes.values())
    for process in supervisors:
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def _start_worker(manager):
    manager.start(max_files=1, reprocess=False, no_visual_merge=False)
    _until(lambda: manager.active() and manager.active()["status"] == "running")
    _until(lambda: (manager.work_dir / "ready").exists())
    return manager.active()


def test_web_worker_survives_restart_and_verified_cancel_releases_lease(worker_manager):
    manager = worker_manager()
    task = _start_worker(manager)
    restarted = worker_manager()
    assert restarted.active()["id"] == task["id"]
    assert restarted.active()["status"] == "running"
    assert "worker_token" not in restarted.list()[0]
    with pytest.raises(ValueError, match="already active"):
        restarted.start(max_files=1, reprocess=False, no_visual_merge=False)
    restarted.cancel(task["id"])
    restarted.cancel(task["id"])
    _until(lambda: restarted.active() is None)
    assert restarted.list()[0]["status"] == "cancelled"
    assert restarted.list()[0]["exit_code"] == 130
    assert worker_manager().list()[0]["status"] == "cancelled"
    assert restarted._runtime_busy() is False
    (manager.work_dir / "finish").write_text("0")
    next_task = restarted.start(max_files=1, reprocess=True, no_visual_merge=True)
    _until(lambda: restarted.active() is None)
    assert (
        next(item for item in restarted.list() if item["id"] == next_task["id"])["status"]
        == "finished"
    )


@pytest.mark.parametrize("exit_kind", ["success", "failure", "external_sigterm", "exit130"])
def test_web_worker_restart_preserves_actual_terminal_result(worker_manager, exit_kind):
    manager = worker_manager()
    task = _start_worker(manager)
    restarted = worker_manager()
    if exit_kind == "external_sigterm":
        os.kill(task["pid"], signal.SIGTERM)
    else:
        (manager.work_dir / "finish").write_text(
            {"success": "0", "failure": "9", "exit130": "130"}[exit_kind]
        )
    _until(lambda: restarted.active() is None)
    result = restarted.list()[0]
    assert result["status"] == {"success": "finished", "failure": "failed"}.get(
        exit_kind, "cancelled"
    )
    assert result["exit_code"] == {"success": 0, "failure": 9}.get(exit_kind, 130)
    assert result["finished_at"] is not None


def test_web_worker_child_keeps_lease_after_supervisor_death(worker_manager):
    manager = worker_manager()
    task = _start_worker(manager)
    supervisor = manager._processes[task["id"]]
    supervisor.kill()
    supervisor.wait(timeout=3)
    restarted = worker_manager()
    assert restarted.active()["status"] == "unknown"
    with pytest.raises(ValueError, match="controller is unavailable"):
        restarted.cancel(task["id"])
    assert restarted._runtime_busy()
    with pytest.raises(ValueError, match="already active"):
        restarted.start(max_files=1, reprocess=False, no_visual_merge=False)
    # The receipt is not a terminal authority while the child retains its FD.
    (manager.work_dir / "finish").write_text("0")
    _until(lambda: restarted.active() is None)
    assert restarted.list()[0]["status"] == "interrupted"
    assert restarted.list()[0]["exit_code"] is None


@pytest.mark.parametrize("damage", ["missing", "replaced", "symlink", "bad_receipt", "wrong_token"])
def test_web_worker_unverifiable_lease_or_receipt_blocks_start(worker_manager, damage):
    manager = worker_manager()
    task = _start_worker(manager)
    internal = manager._tasks[task["id"]]
    lease = manager._worker_path(internal, "lease")
    if damage in {"missing", "replaced", "symlink"}:
        lease.rename(lease.with_suffix(".original"))
        if damage == "replaced":
            lease.touch()
        if damage == "symlink":
            lease.symlink_to(lease.with_suffix(".original"))
    else:
        manager._worker_path(internal, "receipt").write_text(
            "invalid" if damage == "bad_receipt" else '{"token":"other","status":"running"}'
        )
    restarted = worker_manager()
    assert restarted.active()["status"] == "unknown"
    with pytest.raises(ValueError, match="already active"):
        restarted.start(max_files=1, reprocess=False, no_visual_merge=False)


@pytest.mark.parametrize("pid_kind", ["live", "absent", "queued", "interrupted_live"])
def test_web_legacy_pid_is_never_signal_authority(worker_manager, monkeypatch, pid_kind):
    manager = worker_manager()
    from material_agent.app.web_service import WebTask

    task = WebTask(
        "legacy",
        "queued"
        if pid_kind == "queued"
        else "interrupted"
        if pid_kind == "interrupted_live"
        else "running",
        time.time(),
        [],
        "",
        "",
        None,
        pid=os.getpid()
        if pid_kind in {"live", "interrupted_live"}
        else 99999999
        if pid_kind == "absent"
        else None,
    )
    manager._tasks[task.id] = task
    manager._persist()
    signaled = []
    monkeypatch.setattr("os.killpg", lambda *args: signaled.append(args))
    restarted = worker_manager()
    if pid_kind == "absent":
        assert restarted.active() is None
        assert restarted.list()[0]["status"] == "interrupted"
    else:
        assert restarted.active()["status"] == "unknown"
        with pytest.raises(ValueError, match="unverified legacy"):
            restarted.cancel(task.id)
    assert not signaled


def test_web_start_rejects_occupied_or_unreadable_runtime_lock(worker_manager, monkeypatch):
    from material_agent.utils.run_control import exclusive_run_lock

    manager = worker_manager()
    with exclusive_run_lock(manager.work_dir / "run.lock"):
        original = (manager.work_dir / "run.lock").read_text()
        with pytest.raises(ValueError, match="runtime lock"):
            manager.start(max_files=1, reprocess=False, no_visual_merge=False)
        assert (manager.work_dir / "run.lock").read_text() == original
    monkeypatch.setattr(
        "material_agent.app.web_service.lease_busy",
        MagicMock(side_effect=PermissionError("denied")),
    )
    with pytest.raises(ValueError, match="unable to verify"):
        manager.start(max_files=1, reprocess=False, no_visual_merge=False)


def test_web_supervisor_creation_failure_is_durable(worker_manager, monkeypatch):
    manager = worker_manager()
    monkeypatch.setattr(
        "material_agent.app.web_service.subprocess.Popen",
        MagicMock(side_effect=OSError("spawn refused")),
    )
    with pytest.raises(ValueError, match="spawn refused"):
        manager.start(max_files=1, reprocess=False, no_visual_merge=False)
    assert manager.active() is None
    assert worker_manager().list()[0]["status"] == "failed"
    task = next(iter(manager._tasks.values()))
    from material_agent.app.web_worker import lease_busy

    assert lease_busy(manager._worker_path(task, "lease"), task.lease_identity) is False


def test_web_persist_failure_prevents_process_creation_and_releases_lease(
    worker_manager, monkeypatch
):
    from material_agent.app.web_worker import lease_busy

    manager = worker_manager()
    spawn = MagicMock()
    monkeypatch.setattr("material_agent.app.web_service.subprocess.Popen", spawn)
    monkeypatch.setattr(manager, "_persist", MagicMock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        manager.start(max_files=1, reprocess=False, no_visual_merge=False)
    spawn.assert_not_called()
    assert not manager._tasks
    assert all(not lease_busy(path) for path in manager.worker_dir.glob("*.lease"))


def test_web_worker_executable_failure_and_private_control_files(worker_manager):
    manager = worker_manager()
    manager.executable = str(manager.work_dir / "no-such-executable")
    task = manager.start(max_files=1, reprocess=False, no_visual_merge=False)
    _until(lambda: manager.active() is None)
    result = worker_manager().list()[0]
    assert result["id"] == task["id"]
    assert result["status"] == "failed"
    assert "No such file" in result["error"]
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in manager.worker_dir.iterdir())
    assert stat.S_IMODE(manager.worker_dir.stat().st_mode) == 0o700


def test_web_queued_lease_blocks_start_and_cancel_is_consumed_before_spawn(
    worker_manager, monkeypatch
):
    from material_agent.app.web_worker import lease_busy

    manager = worker_manager()
    real_spawn = subprocess.Popen
    captured = {}

    def delay_spawn(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        # Simulate a supervisor not scheduled yet while retaining the inherited
        # open-file-description lease in this controlled launcher.
        captured["lease_fd"] = os.dup(kwargs["pass_fds"][0])
        captured["control_fd"] = os.dup(kwargs["pass_fds"][1])
        return MagicMock(wait=lambda: None)

    with monkeypatch.context() as scoped:
        scoped.setattr("material_agent.app.web_service.subprocess.Popen", delay_spawn)
        task = manager.start(max_files=1, reprocess=False, no_visual_merge=False)
    try:
        restarted = worker_manager()
        assert restarted.active()["status"] == "unknown"
        with pytest.raises(ValueError, match="already active"):
            restarted.start(max_files=1, reprocess=False, no_visual_merge=False)
        restarted.cancel(task["id"])
        command = captured["command"]
        command[-2] = str(captured["lease_fd"])
        command[-1] = str(captured["control_fd"])
        kwargs = {
            **captured["kwargs"],
            "pass_fds": (captured["lease_fd"], captured["control_fd"]),
            "stdout": subprocess.DEVNULL,
        }
        process = real_spawn(command, **kwargs)
    finally:
        os.close(captured["lease_fd"])
        os.close(captured["control_fd"])
    process.wait(timeout=5)
    _until(lambda: restarted.active() is None)
    assert restarted.list()[0]["status"] == "cancelled"
    assert not (manager.work_dir / "ready").exists()
    internal = manager._tasks[task["id"]]
    assert lease_busy(manager._worker_path(internal, "lease"), internal.lease_identity) is False


def test_web_terminal_receipt_waits_for_lease_release(worker_manager):
    from material_agent.app.web_worker import write_private_json

    manager = worker_manager()
    task = _start_worker(manager)
    internal = manager._tasks[task["id"]]
    write_private_json(
        manager._worker_path(internal, "receipt"),
        {
            "token": internal.worker_token,
            "status": "finished",
            "exit_code": 0,
        },
    )
    restarted = worker_manager()
    assert restarted.active()["status"] == "unknown"
    assert restarted.active()["finished_at"] is None
    # Real supervisor overwrites the injected receipt with its actual result.
    restarted.cancel(task["id"])
    _until(lambda: restarted.active() is None)
    assert restarted.list()[0]["status"] == "cancelled"


def test_web_corrupt_snapshot_is_preserved_and_rejected(worker_manager):
    manager = worker_manager()
    manager.state_path.write_text("broken")
    with pytest.raises(ValueError, match="unable to load Web task state"):
        worker_manager()
    assert manager.state_path.read_text() == "broken"


def test_web_protocol_read_failure_releases_control_but_retains_child_lease(worker_manager):
    manager = worker_manager()
    task = _start_worker(manager)
    internal = manager._tasks[task["id"]]
    manager._worker_path(internal, "cancel").write_text("broken")
    _until(lambda: manager.active()["status"] == "unknown")
    assert manager._runtime_busy()
    with pytest.raises(ValueError, match="controller is unavailable"):
        manager.cancel(task["id"])
    (manager.work_dir / "finish").write_text("0")
    _until(lambda: manager.active() is None)
    assert manager.list()[0]["status"] == "interrupted"


def test_web_control_files_reject_symlinks_and_special_files(tmp_path):
    from material_agent.app.web_worker import lease_busy, read_private_json, write_private_json

    target = tmp_path / "target"
    target.write_text('{"token":"keep"}')
    link = tmp_path / "link"
    link.symlink_to(target)
    for read in (read_private_json, lease_busy):
        with pytest.raises(OSError):
            read(link)
    with pytest.raises(ValueError, match="regular control file"):
        write_private_json(link, {"changed": True})
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    for read in (read_private_json, lease_busy):
        with pytest.raises(ValueError, match="regular"):
            read(fifo)
    assert target.read_text() == '{"token":"keep"}'


def test_web_missing_expected_lease_permission_is_unknown(worker_manager, monkeypatch):
    manager = worker_manager()
    task = _start_worker(manager)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            "material_agent.app.web_service.lease_busy",
            MagicMock(side_effect=PermissionError("denied")),
        )
        restarted = worker_manager()
        assert restarted.active()["status"] == "unknown"
        assert "denied" in restarted.active()["error"]
        with pytest.raises(ValueError, match="already active"):
            restarted.start(max_files=1, reprocess=False, no_visual_merge=False)
    manager.cancel(task["id"])
    _until(lambda: manager.active() is None)


def test_web_broken_snapshot_symlink_is_preserved_and_rejected(worker_manager):
    manager = worker_manager()
    manager.state_path.unlink()
    manager.state_path.symlink_to(manager.web_dir / "missing")
    with pytest.raises(ValueError, match="unable to load Web task state"):
        worker_manager()
    assert manager.state_path.is_symlink()


@pytest.mark.parametrize(
    ("exit_code", "requested", "expected_status"),
    [
        (0, True, "finished"),
        (9, True, "failed"),
        (130, True, "cancelled"),
        (-signal.SIGTERM, True, "cancelled"),
        (-signal.SIGKILL, True, "failed"),
        (-signal.SIGTERM, False, "failed"),
        (0, False, "finished"),
        (9, False, "failed"),
        (130, False, "cancelled"),
    ],
)
def test_web_worker_cancellation_race_preserves_actual_exit(
    tmp_path, monkeypatch, exit_code, requested, expected_status
):
    from material_agent.app import web_worker

    spec_path = tmp_path / "task.json"
    receipt_path = spec_path.with_suffix(".receipt")
    token = "owned-test-attempt"
    web_worker.write_private_json(
        spec_path, {"token": token, "command": ["controlled-child"], "work_dir": str(tmp_path)}
    )

    class ControlledChild:
        pid = 12345
        result = None

        def poll(self):
            return self.result

    child = ControlledChild()
    actual_write = web_worker.write_private_json
    statuses = []
    signals = []

    def publish(path, value):
        actual_write(path, value)
        if path != receipt_path:
            return
        statuses.append(value["status"])
        if value["status"] == "running":
            if requested:
                actual_write(spec_path.with_suffix(".cancel"), {"token": token})
            else:
                child.result = exit_code
        elif value["status"] == "cancelling":
            # Child exits between poll(None) and the attempted signal, during
            # receipt publication. Signaling its zombie has no effect on exit.
            child.result = exit_code

    def signal_owned_child(pid, sig):
        assert child.result == exit_code
        signals.append((pid, sig))
        raise ProcessLookupError

    monkeypatch.setattr(web_worker.subprocess, "Popen", lambda *_args, **_kwargs: child)
    monkeypatch.setattr(web_worker, "write_private_json", publish)
    monkeypatch.setattr(web_worker.os, "killpg", signal_owned_child)
    monkeypatch.setattr(web_worker.time, "sleep", lambda _seconds: None)
    web_worker.supervise(spec_path, -1, -1)

    receipt = web_worker.read_private_json(receipt_path)
    assert receipt["status"] == expected_status
    assert receipt["exit_code"] == exit_code
    expected_statuses = (
        ["running", "cancelling", expected_status] if requested else ["running", expected_status]
    )
    expected_signals = [(child.pid, signal.SIGTERM)] if requested else []
    assert statuses == expected_statuses
    assert signals == expected_signals
