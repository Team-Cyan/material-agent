#!/usr/bin/env python3
"""Frozen offline CPU MUSIQ diagnostic; never download, calibrate or promote scores."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib
import importlib.metadata
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import signal
import socket
import sys
import threading
import tempfile
import time
import urllib.request
from unittest.mock import patch

# The isolated runtime must not create bytecode beside imported repository/package sources.
sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "public_musiq_nima_helpers", REPO / "scripts/benchmark_public_nima.py")
nima = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nima)
base = nima.base
read_json, hash_file = nima.read_json, nima.hash_file
SCHEMA = "material-agent.public-musiq-protocol.v1"
FROZEN_PROTOCOL_SHA = "a73c197c2216c99a8038c320309c8837d0f7a9417a21c6f20bb6459ca735861a"
MODEL_SHA = "e95806b9eae5f3814c410f574ba8e552362bd5bc63d758ed5b97860f5d6185aa"
MODEL_SIZE = 108610983
MODEL_REVISION = "pyiqa-musiq-koniq-e95806b9"
CONFIG = {"batch_size": 1, "device": "cpu", "max_pixels": 1000000, "offline": True,
          "preprocessing": "native corpus resolution RGB float32 NCHW [0,1]; PyIQA default "
                           "original/224/384 scales; no resize, calibration or score fusion",
          "seed": 0, "threads": 4}
LIMITS = {"max_failure_count": 8, "max_images": 2048, "max_model_bytes": 150000000,
          "max_peak_rss_bytes": 2500000000, "process_budget_seconds": 1800}
STATISTICS = {"confidence_level": 0.95,
              "method": "paired percentile bootstrap delta SROCC and PLCC versus fixed heuristic",
              "replicates": 2000,
              "resampling_units": {"kadid": "whole native reference families",
                                   "koniq": "image IDs; semantic dependence unaudited"},
              "scope": "conditional fixed-corpus sampling uncertainty; no training-overlap or "
                       "promotion claim", "seed": 20261003}
EXPOSURE = {"kadid": "cross-dataset diagnostic; source-image training overlap unaudited",
            "koniq": "KonIQ-trained weights; exact train/test overlap unaudited; "
                     "training-exposed diagnostic only"}
VERSIONS = ("pyiqa", "torch", "torchvision", "timm", "transformers", "numpy", "Pillow", "scipy")
PREPROCESS = {"patch_size": 32, "patch_stride": 32, "hse_grid_size": 10,
              "longer_side_lengths": [224, 384], "max_seq_len_from_original_res": -1}


def preflight(root, manifest, baseline, protocol, model_path, reference_protocol,
              reference_model, output):
    """Validate all frozen assets before creating any output or loading Torch."""
    plan = read_json(protocol)
    if hash_file(protocol) != FROZEN_PROTOCOL_SHA:
        raise ValueError("MUSIQ protocol differs from the reviewed frozen SHA256")
    if (not model_path.is_file() or model_path.stat().st_size != MODEL_SIZE
            or MODEL_SIZE > LIMITS["max_model_bytes"] or hash_file(model_path) != MODEL_SHA):
        raise ValueError("missing, corrupt or different frozen MUSIQ weights")
    base.reject_symlinks(output.absolute(), descendants=True)
    output = output.resolve()
    protected = (model_path, protocol, reference_protocol, reference_model)
    if any(p.resolve().is_relative_to(output) for p in protected):
        raise ValueError("output overlaps protected MUSIQ/reference asset")
    state = nima.preflight(root, manifest, baseline, reference_protocol, reference_model, output)
    expected = {"schema_version": SCHEMA, "metric": "musiq", "config": CONFIG,
                "limits": LIMITS, "statistics": STATISTICS, "training_exposure": EXPOSURE,
                "model_revision": MODEL_REVISION, "model_sha256": MODEL_SHA,
                "model_size_bytes": MODEL_SIZE,
                "parent_baseline_identity": state["parent"]["identity"],
                "parent_manifest_sha256": state["manifest_sha256"],
                "reference_protocol_sha256": state["protocol_sha256"],
                "items": state["plan"]["items"]}
    if plan != expected or len(plan["items"]) > LIMITS["max_images"]:
        raise ValueError("MUSIQ protocol differs from the frozen cohort/settings")
    state.update(plan=plan, protocol_sha256=FROZEN_PROTOCOL_SHA, model_sha256=MODEL_SHA)
    state["frozen_files"] = {str(p.resolve()): hash_file(p) for p in
                             (manifest, baseline, protocol, model_path,
                              reference_protocol, reference_model)}
    # Parent feature bytes are also immutable during inference.
    for item in state["items"]:
        path = baseline.parent / "features" / (base.digest(item["id"].encode()) + ".json")
        state["frozen_files"][str(path.resolve())] = hash_file(path)
    return state


def denied(*args, **kwargs):
    raise RuntimeError("network/download forbidden by frozen offline MUSIQ protocol")


@contextmanager
def offline_guard():
    """Deny Python socket/URL traffic before imports and restore original APIs afterwards."""
    from contextlib import ExitStack
    with ExitStack() as stack:
        for obj, names in ((socket.socket, ("connect", "connect_ex", "sendto", "sendmsg")),
                           (socket, ("create_connection", "getaddrinfo")),
                           (urllib.request, ("urlopen", "urlretrieve"))):
            for name in names:
                if hasattr(obj, name):
                    stack.enter_context(patch.object(obj, name, denied))
        yield stack


def block_download_helpers(stack):
    """Cover copied aliases in imported Torch/PyIQA/HuggingFace modules, not just originals."""
    names = {"load_file_from_url", "download_url_to_file", "load_state_dict_from_url",
             "download_file_from_google_drive", "download_url", "hf_hub_download",
             "snapshot_download", "cached_download", "download_and_extract_archive"}
    for module_name, module in list(sys.modules.items()):
        if module is not None and module_name.startswith(
                ("torch", "pyiqa", "huggingface_hub", "timm")):
            for name in names & vars(module).keys():
                if callable(getattr(module, name)):
                    stack.enter_context(patch.object(module, name, denied))


@contextmanager
def isolated_homes(output):
    home = output.resolve() / "runtime-home"
    names = {"XDG_CACHE_HOME": home / "cache", "TORCH_HOME": home / "torch",
             "HF_HOME": home / "hf", "HF_HUB_CACHE": home / "hf/hub",
             "TRANSFORMERS_CACHE": home / "hf/transformers", "MPLCONFIGDIR": home / "mpl",
             "NUMBA_CACHE_DIR": home / "numba", "TMPDIR": home / "tmp",
             "TMP": home / "tmp", "TEMP": home / "tmp"}
    for path in names.values():
        path.mkdir(parents=True, exist_ok=True)
    env = {k: str(v) for k, v in names.items()}
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    with patch.dict(os.environ, env), patch.object(tempfile, "tempdir", str(home / "tmp")):
        yield


def source_hashes():
    paths = {Path(__file__).resolve(), REPO / "scripts/benchmark_public_nima.py",
             REPO / "scripts/benchmark_public_composite.py"}
    # Includes MUSIQ architecture, multiscale preprocessing, inference wrapper,
    # load helper, defaults, registry/build factory and their actually imported helpers.
    for name, module in list(sys.modules.items()):
        if name == "pyiqa" or name.startswith("pyiqa."):
            filename = getattr(module, "__file__", None)
            if filename and Path(filename).is_file():
                paths.add(Path(filename).resolve())
    return {str(p): hash_file(p) for p in sorted(paths)}


class CpuMusiq:
    def __init__(self, model_path, stack):
        self.torch = importlib.import_module("torch")
        self.np = importlib.import_module("numpy")
        self.pil = importlib.import_module("PIL.Image")
        self.pyiqa = importlib.import_module("pyiqa")
        block_download_helpers(stack)
        self.torch.set_num_threads(CONFIG["threads"])
        self.torch.set_num_interop_threads(CONFIG["threads"])
        random.seed(CONFIG["seed"])
        self.np.random.seed(CONFIG["seed"])
        self.torch.manual_seed(CONFIG["seed"])
        self.torch.use_deterministic_algorithms(True)
        self.metric = self.pyiqa.create_metric("musiq", device="cpu", seed=CONFIG["seed"],
                                               pretrained_model_path=str(model_path.resolve()))
        self.metric.eval()
        self.evidence = self.validate()

    def validate(self):
        m = self.metric
        devices = {str(t.device) for t in list(m.parameters()) + list(m.buffers())}
        defaults = importlib.import_module("pyiqa.default_model_configs").DEFAULT_CONFIGS["musiq"]
        if (devices != {"cpu"} or str(m.device) != "cpu" or m.lower_better is not False
                or m.metric_name != "musiq" or m.metric_mode != "NR" or m.as_loss
                or not m.check_input_range or m.training or m.net.training
                or type(m.net).__name__ != "MUSIQ" or m.net.head.out_features != 1
                or m.net.data_preprocess_opts != PREPROCESS
                or defaults["metric_opts"] != {"type": "MUSIQ", "pretrained": "koniq10k"}
                or m.seed != CONFIG["seed"] or not self.torch.are_deterministic_algorithms_enabled()
                or self.torch.get_num_threads() != CONFIG["threads"]
                or self.torch.get_num_interop_threads() != CONFIG["threads"]):
            raise ValueError("actual CPU MUSIQ model/settings evidence differs from protocol")
        return {"execution_devices": ["CPU"], "lower_better": False,
                "execution_status": "success", "preprocess": dict(PREPROCESS),
                "torch_threads": self.torch.get_num_threads(),
                "torch_interop_threads": self.torch.get_num_interop_threads(),
                "seed": m.seed, "deterministic_algorithms": True,
                "batch_size_actual": 1, "fallback_used": False}

    def score(self, data):
        with self.pil.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width * height > CONFIG["max_pixels"]:
                raise ValueError("input exceeds frozen pixel budget")
            array = self.np.asarray(image.convert("RGB"), dtype=self.np.float32) / 255.0
        tensor = self.torch.from_numpy(array.copy()).permute(2, 0, 1).unsqueeze(0)
        if (tuple(tensor.shape) != (1, 3, height, width) or str(tensor.device) != "cpu"
                or tensor.dtype != self.torch.float32 or not self.torch.isfinite(tensor).all()
                or tensor.min().item() < 0 or tensor.max().item() > 1):
            raise ValueError("invalid actual native RGB float32 NCHW input")
        with self.torch.inference_mode():
            result = self.metric(tensor)
        if result.numel() != 1 or str(result.device) != "cpu":
            raise ValueError("single native CPU MUSIQ score required")
        score = float(result.item())
        if not math.isfinite(score):
            raise ValueError("MUSIQ returned nonfinite raw score")
        return {"status": "ok", "score": score, **self.validate(),
                "input_shape": list(tensor.shape), "input_dtype": "float32",
                "input_range": [0, 1], "input_color": "RGB"}


def record_hash(record):
    # Reuse the immutable semantic recipe, removing observational RSS as well as timing.
    return nima.record_hash({k: v for k, v in record.items() if k != "peak_rss_bytes"})


def reusable(record, identity, item, state):
    try:
        score = record["score"]
        shape = record["input_shape"]
        return (record["identity"] == identity and record["id"] == item["id"]
                and record["input_sha256"] == state["inputs"][item["id"]]
                and record["record_sha256"] == record_hash(record)
                and record["model_sha256"] == state["model_sha256"]
                and record["protocol_sha256"] == state["protocol_sha256"]
                and record["model_revision"] == MODEL_REVISION and record["status"] == "ok"
                and record["execution_status"] == "success" and record["execution_devices"] == ["CPU"]
                and record["lower_better"] is False and record["fallback_used"] is False
                and record["preprocess"] == PREPROCESS and record["seed"] == CONFIG["seed"]
                and record["deterministic_algorithms"] is True
                and record["torch_threads"] == CONFIG["threads"]
                and record["torch_interop_threads"] == CONFIG["threads"]
                and record["batch_size_actual"] == 1 and record["input_dtype"] == "float32"
                and record["input_range"] == [0, 1] and record["input_color"] == "RGB"
                and isinstance(shape, list) and len(shape) == 4 and shape[:2] == [1, 3]
                and all(type(v) is int and v > 0 for v in shape)
                and shape[2] * shape[3] <= CONFIG["max_pixels"]
                and not isinstance(score, bool) and isinstance(score, (int, float))
                and math.isfinite(score))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def resampling_units(cohort, track):
    if track == "koniq":
        return [[i] for i in range(len(cohort))]
    groups = {}
    for index, item in enumerate(cohort):
        groups.setdefault(item["group"], []).append(index)
    return [groups[key] for key in sorted(groups)]


def draw_indices(units, rng):
    # Repeated reference draws duplicate every family member with its multiplicity intact.
    return [index for unit in rng.integers(0, len(units), size=len(units)) for index in units[unit]]


def paired_bootstrap(cohort, baseline_scores, records, track, statistics=STATISTICS):
    import numpy as np
    from scipy.stats import rankdata

    def corr(a, b):
        if len(a) < 2 or not np.isfinite(a).all() or not np.isfinite(b).all():
            return None
        left, right = a - a.mean(), b - b.mean()
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        return float(np.dot(left, right) / denominator) if denominator else None

    units = resampling_units(cohort, track)
    estimate = {name: [] for name in ("plcc", "srocc")}
    targets = np.asarray([i["target"] for i in cohort], dtype=np.float64)
    native = np.asarray([records[i["id"]]["score"] for i in cohort], dtype=np.float64)
    heuristic = np.asarray([baseline_scores[i["id"]] for i in cohort], dtype=np.float64)
    rng = np.random.default_rng(statistics["seed"])
    for _ in range(statistics["replicates"]):
        indices = draw_indices(units, rng) if units else []
        target, musiq, fixed = targets[indices], native[indices], heuristic[indices]
        for name in estimate:
            a, b, y = (musiq, fixed, target) if name == "plcc" else (
                rankdata(musiq), rankdata(fixed), rankdata(target))
            model_corr, baseline_corr = corr(a, y), corr(b, y)
            if model_corr is not None and baseline_corr is not None:
                estimate[name].append(model_corr - baseline_corr)
    tail = (1 - statistics["confidence_level"]) / 2
    return {"method": statistics["method"], "replicates": statistics["replicates"],
            "seed": statistics["seed"], "confidence_level": statistics["confidence_level"],
            "unit": statistics["resampling_units"][track], "units": len(units),
            "scope": statistics["scope"],
            "delta": {name: {"valid_replicates": len(values),
                             "invalid_replicates": statistics["replicates"] - len(values),
                             "interval": [float(v) for v in np.quantile(values, [tail, 1 - tail])]
                             if values else None} for name, values in estimate.items()}}


def metrics(items, baseline_scores, records, complete):
    padded = {item["id"]: records.get(item["id"], {"status": "not_processed"}) for item in items}
    tracks = nima.metrics(items, baseline_scores, padded)
    for track, splits in tracks.items():
        for split, result in splits.items():
            result["musiq_paired"] = result.pop("nima_paired")
            result["training_exposure"] = EXPOSURE[track]
            cohort = [i for i in items if i["track"] == track
                      and (split == "all" or i["split"] == split)]
            if complete and result["status"] == "complete":
                result["bootstrap"] = paired_bootstrap(cohort, baseline_scores, records, track)
            else:
                result.update(status="incomplete", delta={"plcc": None, "srocc": None},
                              bootstrap=None)
    return tracks


class BudgetExceeded(BaseException):
    pass


def peak_rss_bytes():
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(raw if sys.platform == "darwin" else raw * 1024)


@contextmanager
def process_budget(started):
    """Interrupt long native inference too; poll peak RSS while preserving completed records."""
    if threading.current_thread() is not threading.main_thread():
        raise ValueError("bounded runner must execute in the main thread")
    stop = threading.Event()
    reason = {"value": "process_budget_seconds"}

    def expired(signum, frame):
        raise BudgetExceeded(reason["value"])

    def monitor():
        while not stop.wait(0.05):
            if peak_rss_bytes() > LIMITS["max_peak_rss_bytes"]:
                reason["value"] = "max_peak_rss_bytes"
                os.kill(os.getpid(), signal.SIGUSR1)
                return

    old_alarm, old_rss = signal.getsignal(signal.SIGALRM), signal.getsignal(signal.SIGUSR1)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    if previous_timer != (0.0, 0.0):
        raise ValueError("runner requires exclusive process timer")
    signal.signal(signal.SIGALRM, expired)
    signal.signal(signal.SIGUSR1, expired)
    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    remaining = LIMITS["process_budget_seconds"] - (time.perf_counter() - started)
    try:
        if remaining <= 0:
            raise BudgetExceeded("process_budget_seconds")
        if peak_rss_bytes() > LIMITS["max_peak_rss_bytes"]:
            raise BudgetExceeded("max_peak_rss_bytes")
        signal.setitimer(signal.ITIMER_REAL, remaining)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        stop.set()
        watcher.join(timeout=1)
        signal.signal(signal.SIGALRM, old_alarm)
        signal.signal(signal.SIGUSR1, old_rss)


def assert_stable(state, code, root):
    for filename, expected in {**state["frozen_files"], **code}.items():
        if hash_file(Path(filename)) != expected:
            raise ValueError("frozen asset or source changed during run")
    for item in state["items"]:
        if hash_file(root / item["path"]) != state["inputs"][item["id"]]:
            raise ValueError("input changed during run")


def run(root, manifest, baseline, protocol, model_path, reference_protocol, reference_model, output):
    started = time.perf_counter()
    state = preflight(root, manifest, baseline, protocol, model_path, reference_protocol,
                      reference_model, output)
    records, reused, failed, stop_reason, error_detail = {}, 0, 0, None, None
    provenance, identity, code, tracks = {}, None, source_hashes(), None

    def checkpoint(status):
        base.atomic_json(output / "checkpoint.json", {"identity": identity, "state": status,
                         "complete": status == "complete", "completed": len(records),
                         "successful": sum(r["status"] == "ok" for r in records.values()),
                         "failed": failed, "reused": reused, "total": len(state["items"]),
                         "stop_reason": stop_reason})

    try:
        with process_budget(started), isolated_homes(output), offline_guard() as stack:
            checkpoint("initializing")
            runtime = CpuMusiq(model_path, stack)
            code = source_hashes()
            provenance = {"protocol_sha256": state["protocol_sha256"],
                          "model_sha256": MODEL_SHA, "model_revision": MODEL_REVISION,
                          "config": CONFIG, "statistics": STATISTICS, "inputs": state["inputs"],
                          "code": code, "runtime_versions": {v: importlib.metadata.version(v)
                                                             for v in VERSIONS},
                          "python": platform.python_version(), "platform": platform.platform(),
                          "cpu": {"machine": platform.machine(), "processor": platform.processor()},
                          "model_execution": runtime.evidence}
            identity = base.digest(json.dumps(provenance, sort_keys=True, allow_nan=False).encode())
            for item in state["items"]:
                key = item["id"]
                data = (root / item["path"]).read_bytes()
                if base.digest(data) != state["inputs"][key]:
                    raise ValueError("input changed after preflight")
                path = output / "predictions" / (base.digest(key.encode()) + ".json")
                base.reject_symlinks(path)
                try:
                    cached = read_json(path) if path.exists() else {}
                except (ValueError, OSError):
                    cached = {}
                if reusable(cached, identity, item, state):
                    record = cached
                    reused += 1
                else:
                    image_started = time.perf_counter()
                    try:
                        record = runtime.score(data)
                        record.update(id=key, identity=identity, input_sha256=state["inputs"][key],
                                      model_sha256=MODEL_SHA, model_revision=MODEL_REVISION,
                                      protocol_sha256=state["protocol_sha256"])
                        record["record_sha256"] = record_hash(record)
                        if not reusable(record, identity, item, state):
                            raise ValueError("invalid native CPU execution evidence")
                    except Exception as error:
                        record = {"status": "error", "error_type": type(error).__name__, "id": key,
                                  "identity": identity, "input_sha256": state["inputs"][key],
                                  "model_sha256": MODEL_SHA, "model_revision": MODEL_REVISION,
                                  "protocol_sha256": state["protocol_sha256"]}
                        record["record_sha256"] = record_hash(record)
                    record["elapsed_ms"] = (time.perf_counter() - image_started) * 1000
                    record["peak_rss_bytes"] = peak_rss_bytes()
                    base.atomic_json(path, record)
                records[key] = record
                failed += record["status"] != "ok"
                checkpoint("extracting")
                if failed >= LIMITS["max_failure_count"]:
                    raise BudgetExceeded("max_failure_count")
            assert_stable(state, code, root)
            complete = len(records) == len(state["items"]) and failed == 0
            tracks = metrics(state["items"], state["baseline_scores"], records, complete)
            assert_stable(state, code, root)
    except (Exception, BudgetExceeded, KeyboardInterrupt) as error:
        stop_reason = str(error) if isinstance(error, BudgetExceeded) else type(error).__name__
        error_detail = {"type": type(error).__name__, "message": str(error)[:1000]}
    complete = stop_reason is None and len(records) == len(state["items"]) and failed == 0
    if not complete:
        tracks = metrics(state["items"], state["baseline_scores"], records, False)
    report = {"schema_version": "material-agent.public-musiq-report.v1", "identity": identity,
              "complete": complete, "stop_reason": stop_reason, "error": error_detail,
              "provenance": provenance,
              "cache_reused": reused, "successful": sum(r["status"] == "ok" for r in records.values()),
              "failed": failed, "processed": len(records), "total": len(state["items"]),
              "tracks": tracks, "training_exposure": EXPOSURE,
              "inherited_tracks": {k: v for k, v in state["parent"]["tracks"].items()
                                   if k not in {"koniq", "kadid"}},
              "semantic_records_sha256": base.digest(json.dumps(
                  {key: record["record_sha256"] for key, record in records.items()},
                  sort_keys=True).encode()),
              "timing": {"elapsed_seconds": time.perf_counter() - started,
                         "peak_rss_bytes": peak_rss_bytes(),
                         "description": "observational startup-inclusive pass; resume may reuse predictions"},
              "limitations": "Fixed-corpus diagnostic only; native raw scores, no fitting/fusion or "
                              "promotion; training overlap unaudited, no independent generalization "
                              "or full-pipeline G1/G2 claim. Signal budgets interrupt Python execution; "
                              "a native call may defer delivery until returning."}
    base.atomic_json(output / "report.json", report)
    checkpoint("complete" if complete else "incomplete")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("root", "manifest", "baseline", "protocol", "model-path", "reference-protocol",
                "reference-model", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    report = run(args.root, args.manifest, args.baseline, args.protocol, args.model_path,
                 args.reference_protocol, args.reference_model, args.output)
    print(json.dumps({k: report[k] for k in ("identity", "complete", "successful", "failed",
                                           "cache_reused", "stop_reason")}, indent=2))
    if not report["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
