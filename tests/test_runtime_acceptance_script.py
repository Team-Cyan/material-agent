"""Boundary and real SQLite/process checks; these do not claim native target acceptance."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import time

import pytest
import yaml

from material_agent.adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from material_agent.app.dto import JobStage, JobStatus, JobType, SessionKind, SessionStatus

SPEC = importlib.util.spec_from_file_location(
    "runtime_acceptance", Path(__file__).parents[1] / "scripts/verify_runtime_acceptance.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fixture_contract(tmp_path, *, count=1, suffix=".dng"):
    tmp_path = tmp_path.resolve()
    root = tmp_path / "public"
    root.mkdir()
    items = []
    for i in range(count):
        source = root / f"{i}{suffix}"
        source.write_bytes(b"validation only, not a native inference fixture" + str(i).encode())
        source.chmod(0o444)
        items.append({"id": f"public:{i}", "path": source.name, "size": source.stat().st_size,
                      "sha256": module.digest(source)})
    root.chmod(0o555)
    models = {}
    for name in ("aesthetic", "detection", "face"):
        p = tmp_path / (name + ".model")
        p.write_bytes(name.encode())
        models[name] = {"size": p.stat().st_size, "sha256": module.digest(p)}
    config = {"backend": "local", "legacy": {"enabled": False}, "screening": {"enabled": False},
              "local": {name: {"enabled": True, "enforce_available": True, "device": "CPU",
                                "runtime": "openvino", "model_path": str(tmp_path / (name + ".model"))}
                        for name in ("aesthetic", "detection")}}
    config["local"]["detection"]["face_model_path"] = str(tmp_path / "face.model")
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump(config))
    payload = {"schema_version": module.SCHEMA, "source_revision": "a" * 40,
               "profile_sha256": module.digest(profile), "script_sha256": module.digest(Path(module.__file__)),
               "models": models, "items": items,
               "bounds": {"wall_seconds": 10, "rss_bytes": 512 * module.MIB,
                          "output_bytes": 128 * module.MIB}}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload))
    return root, manifest, profile, tmp_path / "out", payload


def test_validate_is_read_only_and_exact_identity(tmp_path):
    root, manifest, profile, output, payload = fixture_contract(tmp_path)
    result, _ = module.validate(manifest, root, profile, output)
    assert result == payload
    assert not output.exists()
    assert module.digest(root / payload["items"][0]["path"]) == payload["items"][0]["sha256"]


def test_original_public_quality_id_is_preserved(tmp_path):
    root, manifest, profile, output, payload = fixture_contract(tmp_path, suffix=".jpg")
    payload["items"][0]["id"] = "koniq:10020766793.jpg"
    manifest.write_text(json.dumps(payload))
    result, _ = module.validate(manifest, root, profile, output, item_limit=256)
    assert result["items"][0]["id"] == "koniq:10020766793.jpg"


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(command="arbitrary"),
    lambda x: x["items"][0].update(path="../escape.dng"),
    lambda x: x["items"][0].update(sha256="0" * 64),
    lambda x: x["items"][0].update(size=True),
    lambda x: x["items"].append(deepcopy(x["items"][0])),
    lambda x: x["bounds"].update(wall_seconds=601),
    lambda x: x["bounds"].update(rss_bytes=module.MAX_RSS + 1),
    lambda x: x["bounds"].update(output_bytes=module.MAX_OUTPUT + 1),
    lambda x: x.update(profile_sha256="0" * 64),
    lambda x: x.update(script_sha256="0" * 64),
    lambda x: x["models"]["face"].update(sha256="0" * 64),
    lambda x: x.update(source_revision="unknown"),
])
def test_bad_contract_never_creates_output(tmp_path, mutate):
    root, manifest, profile, output, payload = fixture_contract(tmp_path)
    mutate(payload)
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        module.validate(manifest, root, profile, output)
    assert not output.exists()


def test_source_mode_hardlink_symlink_and_output_overlap(tmp_path):
    root, manifest, profile, output, payload = fixture_contract(tmp_path)
    p = root / payload["items"][0]["path"]
    p.chmod(0o644)
    with pytest.raises(ValueError, match="write permission"):
        module.validate(manifest, root, profile, output)
    p.chmod(0o444)
    os.link(p, tmp_path / "linked")
    with pytest.raises(ValueError, match="single-link"):
        module.validate(manifest, root, profile, output)
    (tmp_path / "linked").unlink()
    link = tmp_path / "source-link"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        module.validate(manifest, link, profile, output)
    for destination in (root, root / "nested", root.parent):
        with pytest.raises(ValueError, match="disjoint"):
            module.validate(manifest, root, profile, destination)
    assert not output.exists()


def test_raw_only_cli_and_quality_count_boundary(tmp_path):
    root, manifest, profile, output, _ = fixture_contract(tmp_path, count=33, suffix=".jpg")
    with pytest.raises(ValueError, match="1..32"):
        module.validate(manifest, root, profile, output)
    module.validate(manifest, root, profile, output, item_limit=256)
    # Native is deliberately not run; format rejection is before any output creation.
    # Use the 33-item manifest's first item with the same identity contracts.
    payload = json.loads(manifest.read_text())
    payload["items"] = payload["items"][:1]
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="RAW only"):
        module.run_case("full-run", manifest, root, profile, output)
    assert not output.exists()


def test_atomic_checkpoint_never_follows_temporary_symlink(tmp_path):
    destination = tmp_path / "checkpoint.json"
    victim = tmp_path / "victim"
    victim.write_text("preserve")
    destination.with_name("checkpoint.json.part").symlink_to(victim)
    with pytest.raises(FileExistsError):
        module.atomic_json(destination, {"status": "complete"})
    assert victim.read_text() == "preserve"
    destination.with_name("checkpoint.json.part").unlink()
    module.atomic_json(destination, {"status": "running"})
    module.atomic_json(destination, {"status": "complete"})
    assert json.loads(destination.read_text()) == {"status": "complete"}


def actual_repository(db):
    repo = SQLiteRuntimeRepository(db)
    session = repo.create_session(kind=SessionKind.CLI, input_root="/public",
                                  config_snapshot={}, status=SessionStatus.RUNNING)
    job = repo.create_job(session_id=session, job_type=JobType.REVIEW_PHOTOS,
                         stage=JobStage.SCORE, status=JobStatus.RUNNING)
    from material_agent.app.dto import JobFileStatus
    file = repo.upsert_job_file(job_id=job, file_path="/public/a.dng", status=JobFileStatus.SCORED)
    repo.upsert_artifact(job_id=job, job_file_id=file, kind="score_payload", uri="memory://test",
                         metadata={"boundary_test_only": True})
    return repo, job


def test_online_backup_includes_wal_and_real_reconciliation(tmp_path):
    db = tmp_path / "state.db"
    repo, job = actual_repository(db)
    repo.conn.execute("PRAGMA journal_mode=WAL")
    repo.append_event(session_id=repo.get_job_session_id(job), job_id=job,
                      event_type="committed_wal_evidence", payload={"unicode": "公开"})
    assert db.with_name("state.db-wal").exists()
    before = module.backup(db, tmp_path / "backup.db", time.monotonic() + 5)
    assert any(r["event_type"] == "committed_wal_evidence" for r in before["events"])
    restored = tmp_path / "restored.db"
    restored.write_bytes((tmp_path / "backup.db").read_bytes())
    assert module.snapshot(restored) == before
    new = SQLiteRuntimeRepository(restored)
    assert new.reconcile_abandoned_runs() == {"sessions": 1, "jobs": 1}
    after = module.snapshot(restored)
    assert after["jobs"][0]["status"] == "cancelled"
    assert before["artifacts"] == after["artifacts"]
    assert any(r["event_type"] == "job_reconciled_cancelled" for r in after["events"])
    new.close()
    repo.close()


def test_backup_deadline_protects_prior_outputs(tmp_path):
    repo, _ = actual_repository(tmp_path / "state.db")
    with pytest.raises(TimeoutError):
        module.backup(tmp_path / "state.db", tmp_path / "backup.db", time.monotonic() - 1)
    assert not (tmp_path / "backup.db").exists()
    assert not (tmp_path / "backup.db.part").exists()
    repo.close()


def test_watchdog_kills_and_reaps_actual_process(tmp_path):
    pidfile = tmp_path / "child.pid"
    command = [sys.executable, "-c", "import os,sys,time; from pathlib import Path; Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)", str(pidfile)]
    bounds = {"wall_seconds": 5, "rss_bytes": 256 * module.MIB, "output_bytes": 64 * module.MIB}
    with pytest.raises(TimeoutError):
        module.supervise(command, env=dict(os.environ), log=tmp_path / "process.log", output=tmp_path,
                         bound=bounds, deadline=time.monotonic() + 0.5)
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGKILL])
def test_supervisor_sends_real_signal_after_committed_repository_milestone(tmp_path, sig):
    # This checks process/SQLite boundaries, not production inference or acceptance.
    code = """
import sys,time
from pathlib import Path
from material_agent.adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from material_agent.app.dto import JobStage,JobStatus,JobType,SessionKind,SessionStatus,JobFileStatus
r=SQLiteRuntimeRepository(Path(sys.argv[1]))
s=r.create_session(kind=SessionKind.CLI,input_root='/public',config_snapshot={},status=SessionStatus.RUNNING)
j=r.create_job(session_id=s,job_type=JobType.REVIEW_PHOTOS,stage=JobStage.SCORE,status=JobStatus.RUNNING)
f=r.upsert_job_file(job_id=j,file_path='/public/a.dng',status=JobFileStatus.SCORED)
r.upsert_artifact(job_id=j,job_file_id=f,kind='score_payload',uri='memory://boundary',metadata={'boundary_only':True})
time.sleep(30)
"""
    db = tmp_path / "state.db"
    result = module.supervise([sys.executable, "-c", code, str(db)], env=dict(os.environ),
                              log=tmp_path / "process.log", output=tmp_path,
                              bound={"wall_seconds": 10, "rss_bytes": 256 * module.MIB,
                                     "output_bytes": 64 * module.MIB},
                              deadline=time.monotonic() + 5, interrupt=sig, db=db,
                              backup_path=tmp_path / "backup.db")
    assert result["signal_sent"] == signal.Signals(sig).name
    assert result["exit_code"] == -sig
    assert result["milestone"]["committed_score_artifacts"] == 1
    assert module.snapshot(tmp_path / "backup.db") == result["backup_snapshot"]


def test_too_fast_process_cannot_pass_interruption(tmp_path):
    with pytest.raises(ValueError, match="without an interruptible"):
        module.supervise([sys.executable, "-c", "pass"], env=dict(os.environ),
                         log=tmp_path / "process.log", output=tmp_path,
                         bound={"wall_seconds": 5, "rss_bytes": 128 * module.MIB,
                                "output_bytes": 64 * module.MIB}, deadline=time.monotonic() + 5,
                         interrupt=signal.SIGTERM, db=tmp_path / "state.db",
                         backup_path=tmp_path / "backup.db")


def test_status_is_read_only_and_disallows_execution_arguments(tmp_path, capsys):
    module.atomic_json(tmp_path / "checkpoint.json", {"status": "failed", "case": "recovery", "stage": "sigkill", "error": "bounded failure"})
    before = module.digest(tmp_path / "checkpoint.json")
    module.main(["--case", "status", "--output", str(tmp_path)])
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
    assert module.digest(tmp_path / "checkpoint.json") == before
    with pytest.raises(SystemExit):
        module.main(["--case", "status", "--output", str(tmp_path), "--root", str(tmp_path)])


def test_actual_cli_raw_telemetry_and_simulated_artifacts(tmp_path):
    """Real local heuristic CLI evidence only; native target cases remain unverified."""
    source = Path(__file__).parents[1] / ".local/raw-fixtures/blackmagic-micro-cinema-camera-12bit-16-9.dng"
    if not source.exists():
        pytest.skip("existing ignored public RAW absent; no download")
    import shutil
    if not shutil.which("exiftool"):
        pytest.skip("ExifTool unavailable")
    inputs = tmp_path / "input"
    inputs.mkdir()
    shutil.copyfile(source, inputs / "public.dng")
    work = tmp_path / "work"
    work.mkdir()
    config = tmp_path / "config.yaml"
    baseline = yaml.safe_load((Path(__file__).parents[1] / "config.yaml").read_text())
    baseline.update(backend="local", commentary_enabled=False)
    baseline["grouping"]["enabled"] = True
    baseline["screening"]["enabled"] = False
    config.write_text(yaml.safe_dump(baseline))
    env = module.runtime_environment(work, config)
    result = module.supervise([*module.CLI, "run", str(inputs), "--config", str(config), "--dry-run"],
                              env=env, log=tmp_path / "process.log", output=tmp_path,
                              bound={"wall_seconds": 30, "rss_bytes": 1024 * module.MIB,
                                     "output_bytes": 64 * module.MIB}, deadline=time.monotonic() + 30)
    assert result["exit_code"] == 0, (tmp_path / "process.log").read_text()[-1500:]
    outcome = module.final_records(module.snapshot(work / "state.db"), 1)
    assert outcome["summary"]["written_files"] == 0
    assert outcome["summary"]["simulated_files"] == 1
    telemetry = module.telemetry(work / "run.log")
    assert telemetry["grouping"][0]["files"] == 1
    assert telemetry["preparation_memory"][0]["status"] == "complete"
    with pytest.raises(ValueError, match="no actual native"):
        module.verify_native(outcome["native_records"])


def native_contract_record():
    """Literal validator fixture, not an inference result or execution claim."""
    return {"status": "model", "runtime": "openvino", "requested_device": "CPU",
            "compiled_device": "CPU", "execution_devices": ["CPU"],
            "execution_device_readback": "actual", "fallback_used": False,
            "score": 5.5, "distribution": [0.1] * 10}


def test_quality_requires_native_provenance_for_every_item():
    one = {"aesthetic": native_contract_record(), "detection": native_contract_record()}
    assert module.verify_native([one, deepcopy(one)], require_all=True) == {"aesthetic": 2, "detection": 2}
    missing = deepcopy(one)
    missing.pop("detection")
    with pytest.raises(ValueError, match="not every quality"):
        module.verify_native([one, missing], require_all=True)
    broken = deepcopy(one)
    broken["aesthetic"]["execution_device_readback"] = "unknown"
    with pytest.raises(ValueError, match="provenance invalid"):
        module.verify_native([one, broken], require_all=True)


@pytest.mark.parametrize("change", [
    lambda x: x["fallback"].update(execution_device_readback_error="unknown property"),
    lambda x: x["fallback"].update(score=float("nan")),
    lambda x: x["fallback"].update(score=True),
    lambda x: x["fallback"].update(fallback_used=False),
    lambda x: x.update(available_devices=["CPU", "GPU.0"]),
])
def test_fallback_validator_rejects_missing_or_nonfinite_execution_evidence(change):
    data = {"available_devices": ["CPU"], "cpu": native_contract_record(), "fallback": native_contract_record()}
    data["fallback"].update(requested_device="GPU", fallback_used=True,
                             fallback_reason="requested_device_unavailable")
    module.verify_fallback(data)
    change(data)
    with pytest.raises(ValueError):
        module.verify_fallback(data)


def test_real_forkserver_socket_uses_ephemeral_tmp_not_owned_work(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    (work / "retained.txt").write_text("persistent evidence")
    monkeypatch.setenv("TMPDIR", str(work))
    env = module.runtime_environment(work, tmp_path / "config.yaml")
    assert all(env[key] == "/tmp" for key in ("TMPDIR", "TEMP", "TMP"))
    assert env["MATERIAL_AGENT_WORK_DIR"] == str(work)
    assert env["XDG_CACHE_HOME"] == str(work / "cache")
    assert env.get("HOME") == os.environ.get("HOME")
    code = """
import json,multiprocessing,os,stat,tempfile
from multiprocessing import forkserver
from pathlib import Path
worker=multiprocessing.get_context('forkserver').Process(target=os.getpid)
worker.start();worker.join(5)
if worker.is_alive():
    worker.kill();worker.join();raise RuntimeError('forkserver worker timed out')
assert worker.exitcode==0
address=Path(forkserver._forkserver._forkserver_address)
assert stat.S_ISSOCK(address.lstat().st_mode)
assert address.resolve().is_relative_to(Path('/tmp').resolve())
assert not address.resolve().is_relative_to(Path(os.environ['MATERIAL_AGENT_WORK_DIR']).resolve())
print(json.dumps({'tempdir':tempfile.gettempdir(),'socket_type':stat.S_IFMT(address.lstat().st_mode)}))
"""
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                            text=True, timeout=15, check=True)
    evidence = json.loads(result.stdout)
    assert Path(evidence["tempdir"]).resolve() == Path("/tmp").resolve()
    assert evidence["socket_type"] == stat.S_IFSOCK
    assert module.tree_size(work) == len("persistent evidence")
    assert sorted(p.name for p in work.iterdir()) == ["retained.txt"]


def test_persistent_output_still_rejects_real_unix_socket_and_symlink(tmp_path):
    owned = tmp_path / "work"
    owned.mkdir()
    endpoint = owned / "ipc.sock"
    # macOS Unix socket paths have a short limit; tmp_path can be too long.
    # Bind using a short directory-relative path while preserving the real entry.
    before = Path.cwd()
    try:
        os.chdir(owned)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind("ipc.sock")
            assert stat.S_ISSOCK(endpoint.lstat().st_mode)
            with pytest.raises(ValueError, match=r"ipc\.sock stat_type=49152"):
                module.tree_size(tmp_path)
        endpoint.unlink()
        (owned / "linked").symlink_to("missing-target")
        with pytest.raises(ValueError, match=r"work/linked stat_type=40960"):
            module.tree_size(tmp_path)
    finally:
        os.chdir(before)


def test_fresh_native_child_receives_fixed_thread_controls_before_imports(tmp_path, monkeypatch):
    expected = {"OMP_NUM_THREADS": "1", "OMP_THREAD_LIMIT": "1", "OPENBLAS_NUM_THREADS": "1"}
    for key in expected:
        monkeypatch.setenv(key, "128")
    env = module.runtime_environment(tmp_path, tmp_path / "config.yaml")
    assert {k: env[k] for k in expected} == expected
    # A fresh interpreter observes the controls before loading real native modules.
    # This tests transport of the budget, not OpenMP effect on a non-OpenMP Mac wheel.
    code = """
import json,os
keys=('OMP_NUM_THREADS','OMP_THREAD_LIMIT','OPENBLAS_NUM_THREADS')
before={k:os.environ[k] for k in keys}
import rawpy,numpy
print(json.dumps({'before_native_imports':before,'after_native_imports':{k:os.environ[k] for k in keys},
                  'rawpy_openmp':rawpy.flags['OPENMP'],'numpy_version':numpy.__version__}))
"""
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                            text=True, timeout=15, check=True)
    observed = json.loads(result.stdout)
    assert observed["before_native_imports"] == expected
    assert observed["after_native_imports"] == expected
    assert type(observed["rawpy_openmp"]) is bool
    assert observed["numpy_version"]
    assert all(os.environ[k] == "128" for k in expected)
