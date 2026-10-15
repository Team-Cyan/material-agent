#!/usr/bin/env python3
"""Bounded real CLI/fallback/SQLite-restore diagnostics on isolated public fixtures.

The manifest's revision is an expected image identity, verified by the controller.
This script never asserts that a manifest value proves the running image revision.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import resource
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import time

import yaml

SCHEMA = "material-agent.runtime-acceptance.v1"
MIB = 1024**2
MAX_FILE = 64 * MIB
MAX_INPUT = 512 * MIB
MAX_OUTPUT = 512 * MIB
MAX_RSS = 2560 * MIB
EXTENSIONS = {".jpg", ".jpeg", ".png", ".arw", ".cr3", ".nef", ".raf", ".dng", ".orf", ".rw2"}
RAW_EXTENSIONS = EXTENSIONS - {".jpg", ".jpeg", ".png"}
CLI = [sys.executable, "-c", "from material_agent.shells.cli.main import main; raise SystemExit(main())"]
# Static worker code only; there is no supplied command, shell, device or model option.
FALLBACK_WORKER = """
import asyncio, json, os, sys
from pathlib import Path
import openvino as ov
import yaml
from material_agent.adapters.models.openvino_nima_aesthetic import OpenVinoNimaAestheticAdapter
from material_agent.domain.scoring_engine import decode_raw
p=Path(sys.argv[1]); cfg=yaml.safe_load(p.read_text())['local']['aesthetic']
available=list(ov.Core().available_devices)
if any(d.split('.')[0]=='GPU' for d in available):
    raise RuntimeError('GPU available: fallback isolation precondition failed')
image=Path(sys.argv[2])
if image.suffix.lower() in {'.jpg','.jpeg','.png'}:
    from PIL import Image
    import io
    b=io.BytesIO(); Image.open(image).convert('RGB').save(b,format='JPEG'); data=b.getvalue()
else:
    data=decode_raw(str(image), yaml.safe_load(p.read_text())['preview']).jpeg_bytes
async def run():
    records={}
    for name,device in [('cpu','CPU'),('fallback','GPU')]:
        c={**cfg,'device':device,'fallback_device':'CPU',
           'compiled_cache_dir':str(Path(sys.argv[3]).parent / ('cache-'+name))}
        records[name]=await OpenVinoNimaAestheticAdapter(c).score_image(data)
    return {'available_devices':available, **records}
x=asyncio.run(run())
t=Path(sys.argv[3]+'.part'); t.write_text(json.dumps(x,allow_nan=False)); os.replace(t,sys.argv[3])
"""


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(MIB), b""):
            h.update(block)
    return h.hexdigest()


def strict_json(path: Path, limit=MIB):
    if path.stat().st_size > limit:
        raise ValueError("JSON size exceeds bound")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def atomic_json(path: Path, value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2).encode()
    if len(data) > 32 * MIB:
        raise ValueError("report exceeds 32 MiB")
    temporary = path.with_name(path.name + ".part")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if path.is_symlink():
            raise ValueError("refuse symlink report")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def no_symlink(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for ancestor in [*reversed(path.parents), path]:
        if ancestor.is_symlink():
            raise ValueError("symlink path component")
    return path


def regular(path: Path, limit: int, *, readonly=False):
    no_symlink(path)
    s = path.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or not 0 < s.st_size <= limit:
        raise ValueError("expected bounded single-link regular file")
    if readonly and s.st_mode & 0o222:
        raise ValueError("source fixture must have no write permission bits")
    return s


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("unexpected contract keys")


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("integer outside frozen bounds")
    return value


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("invalid SHA256")
    return value


def validate(manifest: Path, root: Path, profile: Path, output: Path, *, item_limit=32):
    if any(not p.is_absolute() for p in (manifest, root, profile, output)):
        raise ValueError("control paths must be absolute")
    manifest, root, profile, output = map(no_symlink, (manifest, root, profile, output))
    regular(manifest, MIB)
    regular(profile, 64 * 1024)
    if not root.is_dir() or root.stat().st_mode & 0o222:
        raise ValueError("source root must be a read-only directory")
    if output.exists() or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("output must be new and disjoint from source root")
    if manifest.is_relative_to(output) or profile.is_relative_to(output):
        raise ValueError("output overlaps control input")
    payload = strict_json(manifest)
    exact(payload, {"schema_version", "source_revision", "profile_sha256", "script_sha256",
                    "models", "items", "bounds"})
    if payload["schema_version"] != SCHEMA or not re.fullmatch(r"[0-9a-f]{40}", str(payload["source_revision"])):
        raise ValueError("invalid schema or expected revision")
    if digest(profile) != sha(payload["profile_sha256"]) or digest(Path(__file__)) != sha(payload["script_sha256"]):
        raise ValueError("profile/script identity mismatch")
    exact(payload["bounds"], {"wall_seconds", "rss_bytes", "output_bytes"})
    integer(payload["bounds"]["wall_seconds"], 5, 600)
    integer(payload["bounds"]["rss_bytes"], 64 * MIB, MAX_RSS)
    integer(payload["bounds"]["output_bytes"], 64 * MIB, MAX_OUTPUT)
    items = payload["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= item_limit:
        raise ValueError(f"fixture count must be 1..{item_limit}")
    ids, paths, total = set(), set(), 0
    for item in items:
        exact(item, {"id", "path", "size", "sha256"})
        if (not isinstance(item["id"], str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_:.-]{0,63}", item["id"])
                or ".." in item["id"] or item["id"] in ids):
            raise ValueError("invalid or duplicate fixture id")
        if not isinstance(item["path"], str):
            raise ValueError("fixture path must be a string")
        rel = PurePosixPath(item["path"])
        if (str(rel) != item["path"] or rel.is_absolute() or not rel.parts
                or any(p in {".", ".."} or p.startswith(".") for p in rel.parts)
                or rel.suffix.lower() not in EXTENSIONS or item["path"] in paths):
            raise ValueError("invalid fixture path")
        file = root / rel
        s = regular(file, MAX_FILE, readonly=True)
        if s.st_size != integer(item["size"], 1, MAX_FILE) or digest(file) != sha(item["sha256"]):
            raise ValueError("fixture identity mismatch")
        ids.add(item["id"])
        paths.add(item["path"])
        total += s.st_size
    if total > MAX_INPUT or total + 64 * MIB > payload["bounds"]["output_bytes"]:
        raise ValueError("input copies leave insufficient output budget")
    config = yaml.safe_load(profile.read_text())
    if not isinstance(config, dict) or config.get("backend") != "local":
        raise ValueError("expected baked local CPU profile")
    for name in ("aesthetic", "detection"):
        c = config.get("local", {}).get(name, {})
        if not c.get("enabled") or not c.get("enforce_available") or c.get("device") != "CPU" or c.get("runtime") != "openvino":
            raise ValueError("expected enforced native CPU stack")
    if config.get("legacy", {}).get("enabled") or config.get("screening", {}).get("enabled"):
        raise ValueError("unexpected legacy/screening profile")
    exact(payload["models"], {"aesthetic", "detection", "face"})
    assets = {"aesthetic": config["local"]["aesthetic"]["model_path"],
              "detection": config["local"]["detection"]["model_path"],
              "face": config["local"]["detection"]["face_model_path"]}
    for name, filename in assets.items():
        exact(payload["models"][name], {"size", "sha256"})
        path = no_symlink(Path(filename))
        if path.is_relative_to(output) or path.is_relative_to(root):
            raise ValueError("model overlaps fixture/output root")
        s = regular(path, 128 * MIB)
        if s.st_size != integer(payload["models"][name]["size"], 1, 128 * MIB) or digest(path) != sha(payload["models"][name]["sha256"]):
            raise ValueError("model identity mismatch")
    return payload, config


def tree_size(root: Path):
    total, count = 0, 0
    for path in root.rglob("*"):
        s = path.lstat()
        if stat.S_ISLNK(s.st_mode) or not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)):
            raise ValueError("unsafe experiment output entry")
        if stat.S_ISREG(s.st_mode):
            total += s.st_size
            count += 1
    if count > 10000:
        raise ValueError("output file count exceeds bound")
    return total


def snapshot(db: Path):
    regular(db, 128 * MIB)
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=0.2) as c:
        c.row_factory = sqlite3.Row
        if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity failure")
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        result = {}
        for table in tables:
            if not re.fullmatch(r"[A-Za-z0-9_]+", table):
                raise ValueError("invalid SQLite table name")
            rows = c.execute(f'SELECT * FROM "{table}" LIMIT 10001').fetchall()
            if len(rows) > 10000:
                raise ValueError("SQLite row bound exceeded")
            result[table] = sorted([dict(r) for r in rows], key=lambda row: json.dumps(row, sort_keys=True))
    if len(json.dumps(result).encode()) > 32 * MIB:
        raise ValueError("SQLite snapshot bound exceeded")
    return result


def backup(db: Path, destination: Path, deadline: float):
    if destination.exists():
        raise ValueError("backup exists")
    temporary = destination.with_name(destination.name + ".part")
    if temporary.exists():
        raise ValueError("backup temporary exists")
    def progress(*_):
        if time.monotonic() >= deadline:
            raise TimeoutError("SQLite backup deadline")
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=0.2) as source:
            with sqlite3.connect(temporary) as target:
                source.backup(target, pages=64, progress=progress, sleep=0.01)
        captured = snapshot(temporary)
        os.replace(temporary, destination)
        return captured
    finally:
        temporary.unlink(missing_ok=True)


def milestone(db: Path):
    if not db.exists():
        return None
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=0.02) as c:
            rows = c.execute("SELECT id,status FROM jobs ORDER BY rowid").fetchall()
            scored = c.execute("SELECT count(*) FROM artifacts WHERE kind='score_payload'").fetchone()[0]
            if len(rows) == 1 and rows[0][1] == "running" and scored > 0:
                return {"job_id": rows[0][0], "committed_score_artifacts": scored}
    except sqlite3.OperationalError:
        pass
    return None


def child_rss(pid):
    # Runner owns its process group; sum its processes, never unrelated jobs.
    if sys.platform == "linux":
        total = 0
        for process in Path("/proc").iterdir():
            if not process.name.isdecimal():
                continue
            try:
                tail = (process / "stat").read_text().rsplit(")", 1)[1].split()
                if int(tail[2]) == pid:  # field 5 is pgrp, after (comm) + state/ppid
                    pages = int((process / "statm").read_text().split()[1])
                    total += pages * os.sysconf("SC_PAGE_SIZE")
            except (FileNotFoundError, ProcessLookupError):
                continue
        return total
    result = subprocess.run(["ps", "-axo", "pid=,pgid=,rss="], capture_output=True,
                            text=True, timeout=2, check=True)
    values = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == str(pid):
            values.append(int(parts[2]) * 1024)
    return sum(values) if values else 0


def limits(bound):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (bound["wall_seconds"], bound["wall_seconds"] + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (bound["output_bytes"], bound["output_bytes"]))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))


def supervise(command, *, env, log, output, bound, deadline, interrupt=None, db=None,
              backup_path=None, on_phase=None):
    """Own and always reap a fixed child group, including failure/interruption paths."""
    started = time.monotonic()
    result = {"signal_sent": None, "milestone": None, "observed_peak_rss_bytes": 0}
    with log.open("xb") as stream:
        child = subprocess.Popen(command, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                 start_new_session=True, preexec_fn=lambda: limits(bound))
        result["pid"] = child.pid
        try:
            if on_phase:
                on_phase("child_started", result)
            while child.poll() is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError("outer process deadline")
                result["observed_peak_rss_bytes"] = max(result["observed_peak_rss_bytes"], child_rss(child.pid))
                if result["observed_peak_rss_bytes"] > bound["rss_bytes"]:
                    raise ValueError("child process-group RSS exceeds bound")
                if tree_size(output) > bound["output_bytes"]:
                    raise ValueError("experiment output exceeds bound")
                if interrupt is not None and result["signal_sent"] is None:
                    mark = milestone(db)
                    if mark:
                        captured = backup(db, backup_path, deadline)
                        # Backup may take time: never signal a completed job to claim interruption.
                        current = milestone(db)
                        if child.poll() is not None or current is None:
                            raise ValueError("job completed before actual interruption")
                        result["milestone"] = mark
                        result["backup_snapshot"] = captured
                        if on_phase:
                            on_phase("online_backup_complete", {k: v for k, v in result.items() if k != "backup_snapshot"})
                        os.killpg(child.pid, interrupt)
                        result["signal_sent"] = signal.Signals(interrupt).name
                        if on_phase:
                            on_phase("signal_sent", {k: v for k, v in result.items() if k != "backup_snapshot"})
                time.sleep(0.025)
            result["exit_code"] = child.returncode
            if interrupt is not None and result["signal_sent"] is None:
                raise ValueError("job completed without an interruptible committed milestone")
            if tree_size(output) > bound["output_bytes"]:
                raise ValueError("experiment output exceeds bound")
        finally:
            # Kill/reap descendants even if the leader already exited.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=5)
            result["lifecycle"] = "reaped"
            result["exit_code"] = child.returncode
            if on_phase:
                on_phase("child_reaped", {k: v for k, v in result.items() if k != "backup_snapshot"})
    result["elapsed_seconds"] = round(time.monotonic() - started, 6)
    return result


def telemetry(log: Path):
    regular(log, 32 * MIB)
    grouping, preparation = [], []
    for line in log.read_text(errors="replace").splitlines():
        if "Grouping complete: " in line:
            grouping.append(ast.literal_eval(line.split("Grouping complete: ", 1)[1]))
        if "Preparation memory diagnostics: " in line:
            preparation.append(json.loads(line.split("Preparation memory diagnostics: ", 1)[1]))
    if not grouping or not preparation:
        raise ValueError("missing production A1/A2 telemetry")
    return {"grouping": grouping, "preparation_memory": preparation,
            "finalization": "real CLI artifact output; conditional refinement coverage not inferred"}


def final_records(state, expected_count):
    jobs = state["jobs"]
    finished = [r for r in jobs if r["status"] == "finished"]
    if not finished:
        raise ValueError("no finished job")
    job = finished[-1]
    summary = json.loads(job["summary_json"])
    if summary.get("written_files") != 0 or summary.get("error_files") != 0 or summary.get("simulated_files") != expected_count:
        raise ValueError("full dry-run did not simulate every fixture without writes/errors")
    files = [r for r in state["job_files"] if r["job_id"] == job["id"]]
    if len(files) != expected_count or len({r["file_path"] for r in files}) != expected_count or any(r["status"] != "simulated" for r in files):
        raise ValueError("missing/duplicate/non-SIMULATED fixture outcomes")
    artifacts = [r for r in state["artifacts"] if r["job_id"] == job["id"] and r["kind"] == "score_payload"]
    if len(artifacts) != expected_count or len({r["job_file_id"] for r in artifacts}) != expected_count:
        raise ValueError("missing/duplicate score artifacts")
    by_id = {r["id"]: r for r in files}
    # Declared semantic projection; full immutable DB retains omitted native timings/provenance.
    fields = ("score_total", "scores", "scene", "scene_raw", "decision", "decision_reasons",
              "screening_prior", "visible_breakdown", "policy_version", "group_commentary",
              "instructions", "signals", "boosted")
    records = {}
    native = []
    for row in artifacts:
        file = by_id[row["job_file_id"]]
        value = json.loads(row["metadata_json"])
        record = {k: value.get(k) for k in fields}
        record.update({k: file[k] for k in ("group_id", "rank", "status")})
        meta = value.get("meta", {})
        record["native_predictions"] = {}
        for key in ("aesthetic", "detection"):
            r = meta.get(key)
            if isinstance(r, dict):
                record["native_predictions"][key] = {k: r.get(k) for k in (
                    "status", "runtime", "requested_device", "compiled_device", "execution_devices",
                    "fallback_used", "model_digest", "face_model_digest", "model_name", "model_version",
                    "score", "distribution", "objects", "faces", "primary_index", "scene")}
        records[file["file_path"]] = record
        native.append({"file_path": file["file_path"], **{
            key: meta.get(key) for key in ("aesthetic", "detection", "input_decode_format",
                                          "preview_source", "original_size", "preview_size")}})
    return {"job_id": job["id"], "summary": summary, "semantic_records": records,
            "native_records": native}


def verify_native(records, models=None, *, require_all=False):
    counts = {"aesthetic": 0, "detection": 0}
    for record in records:
        for key in counts:
            r = record.get(key)
            if not isinstance(r, dict) or r.get("status") != "model":
                continue
            if (r.get("runtime") != "openvino" or r.get("requested_device") != "CPU"
                    or r.get("compiled_device") != "CPU" or r.get("fallback_used") is not False
                    or not r.get("execution_devices")
                    or any(d.split(".")[0] != "CPU" for d in r["execution_devices"])
                    or r.get("execution_device_readback") != "actual"
                    or r.get("execution_device_readback_error")):
                raise ValueError("full CLI native CPU execution provenance invalid")
            if models is not None and r.get("model_digest") != models[key]["sha256"]:
                raise ValueError("native model digest differs from frozen input")
            if key == "detection" and models is not None and r.get("face_model_digest") != models["face"]["sha256"]:
                raise ValueError("native face model digest differs from frozen input")
            counts[key] += 1
    if not all(counts.values()):
        raise ValueError("no actual native NIMA/detection execution in full CLI artifacts")
    if require_all and any(n != len(records) for n in counts.values()):
        raise ValueError("not every quality item has native execution evidence")
    return counts


def verify_fallback(records):
    if any(d.split(".")[0] == "GPU" for d in records["available_devices"]):
        raise ValueError("GPU available: isolation failed")
    for name, requested in (("cpu", "CPU"), ("fallback", "GPU")):
        r = records[name]
        if (r.get("runtime") != "openvino" or r.get("requested_device") != requested
                or r.get("compiled_device") != "CPU" or not r.get("execution_devices")
                or any(d.split(".")[0] != "CPU" for d in r["execution_devices"])
                or r.get("execution_device_readback") != "actual"
                or r.get("execution_device_readback_error")
                or r.get("fallback_used") is not (name == "fallback")):
            raise ValueError("actual native CPU/fallback provenance missing")
        values = r.get("distribution", [])
        if len(values) != 10 or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("invalid native distribution")
        if (abs(sum(values) - 1) > 0.00001 or type(r.get("score")) not in (int, float)
                or not math.isfinite(r["score"]) or not 1 <= r["score"] <= 10):
            raise ValueError("invalid native score")
    if not records["fallback"].get("fallback_reason"):
        raise ValueError("fallback reason missing")
    if abs(records["cpu"]["score"] - records["fallback"]["score"]) > 0.000001:
        raise ValueError("CPU/fallback score mismatch")
    if any(abs(a-b) > 0.000001 for a, b in zip(records["cpu"]["distribution"], records["fallback"]["distribution"], strict=True)):
        raise ValueError("CPU/fallback distribution mismatch")


def run_case(case, manifest, root, profile, output):
    if case not in {"quality", "full-run", "fallback", "recovery"}:
        raise ValueError("unsupported execution case")
    payload, config = validate(manifest, root, profile, output,
                               item_limit=256 if case == "quality" else 32)
    if case in {"full-run", "recovery"} and any(
        Path(i["path"]).suffix.lower() not in RAW_EXTENSIONS for i in payload["items"]
    ):
        raise ValueError("production CLI decoder supports RAW only; JPEG/PNG diagnostic unsupported")
    if case == "quality" and any(Path(i["path"]).suffix.lower() not in {".jpg", ".jpeg", ".png"}
                                  for i in payload["items"]):
        raise ValueError("quality case requires JPEG/PNG public fixtures")
    output = no_symlink(output)
    output.mkdir(mode=0o700, parents=False)
    deadline = time.monotonic() + payload["bounds"]["wall_seconds"]
    report = {"schema_version": SCHEMA, "case": case, "status": "running",
              "expected_source_revision": payload["source_revision"],
              "runtime_revision_verified_by_runner": False,
              "manifest_sha256": digest(manifest), "script_sha256": digest(Path(__file__)),
              "profile_sha256": digest(profile), "results": {},
              "limits": ["diagnostic public fixtures; no directed-coverage acceptance",
                         "dry-run SIMULATED outcomes, no WRITTEN/completed metadata resume claim"]}
    def checkpoint(stage):
        report["stage"] = stage
        atomic_json(output / "checkpoint.json", report)
    def track_phase(name):
        def callback(stage, receipt):
            report["active_process"] = {"case": name, **receipt}
            checkpoint(name + "_" + stage)
        return callback
    def unchanged():
        for item in payload["items"]:
            path = root / item["path"]
            regular(path, MAX_FILE, readonly=True)
            if digest(path) != item["sha256"]:
                raise ValueError("original source changed")
        if digest(profile) != payload["profile_sha256"] or digest(manifest) != report["manifest_sha256"]:
            raise ValueError("control input identity changed")
        for name, path in (("aesthetic", config["local"]["aesthetic"]["model_path"]),
                           ("detection", config["local"]["detection"]["model_path"]),
                           ("face", config["local"]["detection"]["face_model_path"])):
            if digest(Path(path)) != payload["models"][name]["sha256"]:
                raise ValueError("model input identity changed")
    try:
        checkpoint("validated")
        inputs = output / "input"
        inputs.mkdir()
        for item in payload["items"]:
            target = inputs / (item["id"] + Path(item["path"]).suffix.lower())
            shutil.copyfile(root / item["path"], target)
            if digest(target) != item["sha256"]:
                raise ValueError("copied input identity mismatch")
            target.chmod(0o444)
        inputs.chmod(0o555)
        checkpoint("fixtures_copied")
        def setup(name):
            directory = output / name
            directory.mkdir()
            work = directory / "work"
            work.mkdir()
            c = deepcopy(config)
            c["raw_extensions"] = sorted({Path(i["path"]).suffix[1:].upper() for i in payload["items"]})
            c.setdefault("review_pipeline", {})["max_files"] = len(payload["items"])
            for block in c.get("local", {}).values():
                if isinstance(block, dict) and "compiled_cache_dir" in block:
                    block["compiled_cache_dir"] = str(work / "openvino-cache")
            c.setdefault("model_management", {})["registry_dir"] = str(work / "models")
            path = directory / "config.yaml"
            path.write_text(yaml.safe_dump(c, sort_keys=True))
            env = dict(os.environ, MATERIAL_AGENT_WORK_DIR=str(work), MATERIAL_AGENT_CONFIG=str(path),
                       PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(work), XDG_CACHE_HOME=str(work / "cache"))
            return directory, work, path, env
        def full(name, *, restore=None, interrupt=None):
            directory, work, path, env = setup(name)
            if restore is not None:
                shutil.copyfile(restore[0], work / "state.db")
                original_config = restore[0].parent / "config.yaml"
                shutil.copyfile(original_config, directory / "restored-config-original.yaml")
                restored_config = yaml.safe_load(original_config.read_text())
                original_work = original_config.parent / "work"
                for block in restored_config.get("local", {}).values():
                    if isinstance(block, dict) and "compiled_cache_dir" in block:
                        if block["compiled_cache_dir"] != str(original_work / "openvino-cache"):
                            raise ValueError("restored config has an unowned cache")
                        block["compiled_cache_dir"] = str(work / "openvino-cache")
                restored_config["model_management"]["registry_dir"] = str(work / "models")
                if restored_config != yaml.safe_load(path.read_text()):
                    raise ValueError("restored config settings changed beyond owned paths")
                path.write_text(yaml.safe_dump(restored_config, sort_keys=True))
                captured = snapshot(work / "state.db")
                if captured != restore[1]:
                    raise ValueError("restored committed DB rows differ before fresh CLI")
                atomic_json(directory / "restored-before-cli.json", captured)
                checkpoint(name + "_db_restored_before_cli")
            result = supervise([*CLI, "run", str(inputs), "--config", str(path), "--dry-run"],
                               env=env, log=directory / "process.log", output=output,
                               bound=payload["bounds"], deadline=deadline, interrupt=interrupt,
                               db=work / "state.db", backup_path=directory / "backup.db",
                               on_phase=track_phase(name))
            state = snapshot(work / "state.db")
            atomic_json(directory / "after-db.json", state)
            result["state"] = state
            if interrupt is None:
                if result["exit_code"] != 0:
                    raise ValueError("real CLI failed; inspect retained process.log")
                result["outcome"] = final_records(state, len(payload["items"]))
                result["native_cpu_counts"] = verify_native(result["outcome"]["native_records"], payload["models"])
                result["native_observation_scope"] = {
                    "fixture_count": len(payload["items"]),
                    "items_without_model_evidence": {
                        key: [r["file_path"] for r in result["outcome"]["native_records"]
                              if not isinstance(r.get(key), dict) or r[key].get("status") != "model"]
                        for key in ("aesthetic", "detection")},
                    "exclusion_reason": "no per-item model status; possible business short-circuit, cause not independently classified",
                    "claim": "actual observed native counts; no blanket per-fixture inference coverage claim"}
                result["telemetry"] = telemetry(work / "run.log")
            else:
                job = next(r for r in state["jobs"] if r["id"] == result["milestone"]["job_id"])
                expected = "cancelled" if interrupt == signal.SIGTERM else "running"
                if job["status"] != expected:
                    raise ValueError("actual interrupted job state does not match contract")
                if interrupt == signal.SIGKILL and result["exit_code"] != -signal.SIGKILL:
                    raise ValueError("SIGKILL did not terminate actual child")
                if interrupt == signal.SIGTERM and result["exit_code"] != 130:
                    raise ValueError("SIGTERM did not exit through real CLI cancellation")
                atomic_json(directory / "backup-receipt.json", {
                    "database_sha256": digest(directory / "backup.db"),
                    "snapshot": result["backup_snapshot"], "config_sha256": digest(path),
                    "restored_scope": "consistent SQLite all tables/artifacts; exact saved config with owned path remapping",
                    "excluded": "compiled caches and process logs retained as evidence, not durable completion"})
            # Keep full DB snapshots in bounded separate evidence, not duplicated checkpoints.
            result.pop("state", None)
            result.pop("backup_snapshot", None)
            report.pop("active_process", None)
            return result
        if case == "quality":
            directory, work, path, env = setup("quality")
            local_manifest = {"schema_version": "material-agent.local-benchmark.v1",
                              "name": "public-native-runtime-diagnostic", "version": 1,
                              "items": [{"id": i["id"], "path": str(inputs / (i["id"] + Path(i["path"]).suffix.lower())),
                                         "group": i["id"]} for i in payload["items"]]}
            fixture_manifest = directory / "benchmark-manifest.yaml"
            fixture_manifest.write_text(yaml.safe_dump(local_manifest, sort_keys=True))
            result = supervise([*CLI, "benchmark-local", "--manifest", str(fixture_manifest),
                                "--config", str(path), "--output-dir", str(directory / "benchmark"),
                                "--repeat-count", "2"], env=env, log=directory / "process.log",
                               output=output, bound=payload["bounds"], deadline=deadline,
                               on_phase=track_phase("quality"))
            if result["exit_code"] != 0:
                raise ValueError("real native benchmark-local failed; inspect retained log")
            benchmark_path = directory / "benchmark/benchmark-report.json"
            benchmark = strict_json(benchmark_path, 32 * MIB)
            rows = benchmark.get("items", [])
            if (benchmark.get("schema_version") != "material-agent.local-benchmark.v1"
                    or benchmark.get("runtime", {}).get("repeat_count") != 2
                    or benchmark.get("metrics", {}).get("deterministic_scores") is not True
                    or len(rows) != len(payload["items"])
                    or {r["id"] for r in rows} != {i["id"] for i in payload["items"]}
                    or any(not math.isfinite(r["score"]) for r in rows)):
                raise ValueError("native quality report incomplete/nondeterministic")
            result["native_cpu_counts"] = verify_native(rows, payload["models"], require_all=True)
            result["benchmark_sha256"] = digest(benchmark_path)
            result["benchmark"] = benchmark
            result["quality_contract"] = "native benchmark-local scoring; external MOS/DMOS join required; not RAW full-pipeline rating"
            if any(work.rglob("state.db")):
                raise ValueError("quality benchmark unexpectedly created runtime state")
            report["results"]["quality"] = result
            report.pop("active_process", None)
            checkpoint("quality_complete")
        elif case == "fallback":
            directory, work, path, env = setup("fallback")
            selected = payload["items"][0]
            selected_input = inputs / (selected["id"] + Path(selected["path"]).suffix.lower())
            result = supervise([sys.executable, "-c", FALLBACK_WORKER, str(path),
                                str(selected_input), str(directory / "native.json")],
                               env=env, log=directory / "process.log", output=output,
                               bound=payload["bounds"], deadline=deadline,
                               on_phase=track_phase("fallback"))
            if result["exit_code"] != 0:
                raise ValueError("real fallback worker failed; inspect retained log")
            records = strict_json(directory / "native.json")
            verify_fallback(records)
            if any(records[n].get("model_digest") != payload["models"]["aesthetic"]["sha256"]
                   for n in ("cpu", "fallback")):
                raise ValueError("fallback model identity mismatch")
            report["results"]["fallback"] = {**result, "selected_id": selected["id"], "native": records}
            report.pop("active_process", None)
            checkpoint("fallback_verified")
        else:
            report["results"]["control"] = full("control")
            checkpoint("control_complete")
            if case == "recovery":
                for name, sig in (("sigterm", signal.SIGTERM), ("sigkill", signal.SIGKILL)):
                    report["results"][name] = full(name, interrupt=sig)
                    checkpoint(name + "_interrupted")
                    backup_path = output / name / "backup.db"
                    before = snapshot(backup_path)
                    restored = full(name + "-restored", restore=(backup_path, before))
                    state = snapshot(output / (name + "-restored") / "work/state.db")
                    old_id = report["results"][name]["milestone"]["job_id"]
                    reconciled = [r for r in state["events"] if r["job_id"] == old_id and r["event_type"] == "job_reconciled_cancelled"]
                    if len(reconciled) != 1 or restored["outcome"]["job_id"] == old_id:
                        raise ValueError("actual abandoned reconciliation/new-job contract missing")
                    # Before-CLI exact equality was checked; old score artifacts must also survive new run.
                    for table in ("job_files", "artifacts"):
                        old = [r for r in before[table] if r["job_id"] == old_id]
                        now = [r for r in state[table] if r["job_id"] == old_id]
                        if old != now:
                            raise ValueError("restored old committed artifacts changed or duplicated")
                    control = report["results"]["control"]["outcome"]["semantic_records"]
                    if restored["outcome"]["semantic_records"] != control:
                        raise ValueError("fresh CLI reprocessing differs from uninterrupted semantic control")
                    restored["recovery_contract"] = "actual SQLite restore + abandoned reconciliation + fresh CLI new-job reprocessing"
                    report["results"][name + "-restored"] = restored
                    checkpoint(name + "_restored")
        unchanged()
        report["copied_input_hashes_unchanged"] = all(
            digest(inputs / (i["id"] + Path(i["path"]).suffix.lower())) == i["sha256"]
            for i in payload["items"])
        if not report["copied_input_hashes_unchanged"]:
            raise ValueError("read-only copied input changed")
        report["output_bytes"] = tree_size(output)
        report["original_source_hashes_unchanged"] = True
        report["status"] = "complete"
        checkpoint("complete")
        atomic_json(output / "report.json", report)
        if tree_size(output) > payload["bounds"]["output_bytes"]:
            raise ValueError("final reports exceed output budget")
        return report
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = type(error).__name__ + ": " + str(error)
        try:
            unchanged()
            report["original_source_hashes_unchanged"] = True
        except Exception:
            report["original_source_hashes_unchanged"] = False
        checkpoint("failed")
        if (output / "report.json").exists():
            atomic_json(output / "report.json", report)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--case", choices=("full-run", "fallback", "recovery", "quality", "status"), required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.case == "status":
        if any((args.manifest, args.root, args.profile)):
            parser.error("status accepts only --case and --output")
        if not args.output.is_absolute():
            parser.error("status output must be absolute")
        checkpoint = no_symlink(args.output / "checkpoint.json")
        regular(checkpoint, 32 * MIB)
        result = strict_json(checkpoint, 32 * MIB)
        print(json.dumps({k: result.get(k) for k in ("status", "case", "stage", "error")}))
        return
    if not all((args.manifest, args.root, args.profile)):
        parser.error("execution requires --manifest --root --profile --output")
    def cancelled(*_):
        raise KeyboardInterrupt("acceptance supervisor interrupted")
    previous = signal.signal(signal.SIGTERM, cancelled)
    try:
        result = run_case(args.case, args.manifest, args.root, args.profile, args.output)
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(json.dumps({"status": result["status"], "case": args.case, "report": str(args.output / "report.json")}))


if __name__ == "__main__":
    main()
