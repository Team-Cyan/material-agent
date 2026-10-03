from __future__ import annotations

from contextlib import nullcontext
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
import tempfile
from types import SimpleNamespace
import urllib.request

import numpy as np
from PIL import Image
import pytest

SPEC = importlib.util.spec_from_file_location(
    "public_musiq", Path(__file__).parents[1] / "scripts/benchmark_public_musiq.py")
musiq = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(musiq)


def fixture(tmp_path, monkeypatch):
    root = tmp_path / "inputs"
    root.mkdir()
    items = []
    for track in ("koniq", "kadid"):
        for index in range(6):
            name = f"{track}-{index}.png"
            Image.new("RGB", (16, 12), (index * 30, 20, 20)).save(root / name)
            item = {"id": f"{track}:{index}", "path": name, "track": track,
                    "target": index + 1, "sha256": musiq.hash_file(root / name)}
            if track == "kadid":
                item["group"] = f"I{index // 2:02d}.png"
            items.append(item)
    payload = {"schema_version": musiq.base.SCHEMA, "items": items}
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps(payload))
    baseline = tmp_path / "baseline/report.json"
    parent = musiq.base.run(manifest, root, baseline.parent)
    reference_model = tmp_path / "nima.tflite"
    reference_model.write_bytes(b"\x18\x00\x00\x00TFL3mock weights")
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps(musiq.nima.freeze_protocol(
        payload, parent, musiq.hash_file(reference_model), "test-v1")))
    model = tmp_path / "musiq.pth"
    model.write_bytes(b"existing frozen weights")
    monkeypatch.setattr(musiq, "MODEL_SHA", musiq.hash_file(model))
    monkeypatch.setattr(musiq, "MODEL_SIZE", model.stat().st_size)
    plan = {"schema_version": musiq.SCHEMA, "metric": "musiq", "config": musiq.CONFIG,
            "limits": musiq.LIMITS, "statistics": musiq.STATISTICS,
            "training_exposure": musiq.EXPOSURE, "model_revision": musiq.MODEL_REVISION,
            "model_sha256": musiq.MODEL_SHA, "model_size_bytes": musiq.MODEL_SIZE,
            "parent_baseline_identity": parent["identity"],
            "parent_manifest_sha256": parent["manifest_sha256"],
            "reference_protocol_sha256": musiq.hash_file(reference),
            "items": musiq.read_json(reference)["items"]}
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps(plan))
    monkeypatch.setattr(musiq, "FROZEN_PROTOCOL_SHA", musiq.hash_file(protocol))
    return root, manifest, baseline, protocol, model, reference, reference_model, tmp_path / "out"


def evidence():
    return {"execution_devices": ["CPU"], "lower_better": False, "execution_status": "success",
            "preprocess": musiq.PREPROCESS, "torch_threads": 4, "torch_interop_threads": 4,
            "seed": 0, "deterministic_algorithms": True, "batch_size_actual": 1, "fallback_used": False}


def prediction(data):
    with Image.open(__import__("io").BytesIO(data)) as image:
        score = float(np.asarray(image)[0, 0, 0])
    return {"status": "ok", "score": score, **evidence(), "input_shape": [1, 3, 12, 16],
            "input_dtype": "float32", "input_range": [0, 1], "input_color": "RGB"}


def fake_runtime(monkeypatch, calls, mutate=None):
    class Fake:
        def __init__(self, model, stack):
            assert model.is_file()
            assert os.environ["HF_HUB_OFFLINE"] == "1"
            assert Path(os.environ["TORCH_HOME"]).is_relative_to(Path(os.environ["XDG_CACHE_HOME"]).parent)
            self.evidence = evidence()

        def score(self, data):
            calls.append(data)
            result = prediction(data)
            if mutate:
                mutate(result)
            return result
    monkeypatch.setattr(musiq, "CpuMusiq", Fake)
    monkeypatch.setattr(musiq.importlib.metadata, "version", lambda name: "fake-" + name)


def test_success_resume_semantic_hash_and_corrupt_cache_retry(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls)
    first = musiq.run(*args)
    assert first["complete"] and len(calls) == 12
    assert first["tracks"]["kadid"]["all"]["bootstrap"]["units"] == 3
    assert first["tracks"]["koniq"]["all"]["musiq_paired"]["n"] == 6
    calls.clear()
    second = musiq.run(*args)
    assert not calls and second["cache_reused"] == 12
    assert first["identity"] == second["identity"]
    assert first["semantic_records_sha256"] == second["semantic_records_sha256"]
    path = next((args[-1] / "predictions").glob("*.json"))
    record = musiq.read_json(path)
    record["score"] += 1
    path.write_text(json.dumps(record))
    assert musiq.run(*args)["cache_reused"] == 11
    assert len(calls) == 1
    calls.clear()
    path.write_text("broken JSON")
    assert musiq.run(*args)["cache_reused"] == 11
    assert len(calls) == 1
    checkpoint = musiq.read_json(args[-1] / "checkpoint.json")
    assert checkpoint["complete"] and checkpoint["successful"] == 12
    assert checkpoint["failed"] == 0 and checkpoint["reused"] == 11


@pytest.mark.parametrize("change", ["missing_model", "model", "protocol", "config", "item",
                                    "reference", "input", "baseline", "feature"])
def test_asset_drift_fails_before_runtime_or_outputs(tmp_path, monkeypatch, change):
    args = fixture(tmp_path, monkeypatch)
    root, manifest, baseline, protocol, model, reference, _, output = args
    if change == "missing_model":
        model.unlink()
    elif change == "model":
        model.write_bytes(b"wrong")
    elif change == "protocol":
        protocol.write_text(protocol.read_text() + " ")
    elif change in {"config", "item"}:
        plan = musiq.read_json(protocol)
        if change == "config":
            plan["config"]["device"] = "mps"
        else:
            plan["items"].pop()
        protocol.write_text(json.dumps(plan))
        # Even a newly approved digest cannot weaken exact fixed settings/cohort validation.
        monkeypatch.setattr(musiq, "FROZEN_PROTOCOL_SHA", musiq.hash_file(protocol))
    elif change == "reference":
        reference.write_text(reference.read_text() + " ")
    elif change == "input":
        next(root.glob("*.png")).write_bytes(b"wrong")
    elif change == "baseline":
        parent = musiq.read_json(baseline)
        parent["identity"] = "wrong"
        baseline.write_text(json.dumps(parent))
    else:
        cache = next((baseline.parent / "features").glob("*.json"))
        cache.write_text("{}")
    calls = []
    fake_runtime(monkeypatch, calls)
    with pytest.raises(ValueError):
        musiq.run(*args)
    assert not calls and not output.exists()
    assert manifest.exists()


@pytest.mark.parametrize("unsafe", ["model_ancestor", "baseline_child", "output_symlink",
                                    "descendant_symlink", "reference_ancestor"])
def test_output_isolation(tmp_path, monkeypatch, unsafe):
    args = fixture(tmp_path, monkeypatch)
    output = args[-1]
    if unsafe == "model_ancestor" or unsafe == "reference_ancestor":
        output = tmp_path
    elif unsafe == "baseline_child":
        output = args[2].parent / "other"
    elif unsafe == "output_symlink":
        output.symlink_to(args[0], target_is_directory=True)
    else:
        output.mkdir()
        (output / "runtime-home").symlink_to(args[0], target_is_directory=True)
    with pytest.raises(ValueError, match="overlap|symlink"):
        musiq.preflight(*args[:-1], output)


def test_guard_blocks_sockets_urls_nested_download_aliases_and_restores(monkeypatch):
    module = SimpleNamespace(load_file_from_url=lambda *a: None,
                             download_url_to_file=lambda *a: None)
    monkeypatch.setitem(sys.modules, "pyiqa.fake_download_alias", module)
    original = module.load_file_from_url
    original_connect = socket.socket.connect
    with musiq.offline_guard() as stack:
        musiq.block_download_helpers(stack)
        for call in (lambda: socket.create_connection(("127.0.0.1", 1)),
                     lambda: socket.socket().connect(("127.0.0.1", 1)),
                     lambda: socket.socket().connect_ex(("127.0.0.1", 1)),
                     lambda: urllib.request.urlopen("https://example.invalid"),
                     lambda: module.load_file_from_url("https://example.invalid"),
                     lambda: module.download_url_to_file("https://example.invalid", "output")):
            with pytest.raises(RuntimeError, match="forbidden"):
                call()
    assert socket.socket.connect is original_connect
    assert module.load_file_from_url is original


def test_environment_cache_homes_stay_in_output_and_restore(tmp_path):
    before = dict(os.environ)
    with musiq.isolated_homes(tmp_path / "experiment"):
        assert os.environ["HOME"] == before["HOME"]
        assert Path(tempfile.gettempdir()).is_relative_to(tmp_path / "experiment")
        for key in ("TORCH_HOME", "HF_HOME", "TMPDIR", "XDG_CACHE_HOME"):
            assert Path(os.environ[key]).is_relative_to(tmp_path / "experiment")
            assert Path(os.environ[key]).is_dir()
    assert dict(os.environ) == before


@pytest.mark.parametrize("mutation", [lambda r: r.update(score=float("nan")),
                                       lambda r: r.update(execution_devices=["GPU"]),
                                       lambda r: r.update(lower_better=True),
                                       lambda r: r.update(fallback_used=True),
                                       lambda r: r.update(input_dtype="float64"),
                                       lambda r: r.update(seed=1)])
def test_invalid_runtime_evidence_is_failure_never_fallback(tmp_path, monkeypatch, mutation):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls, mutation)
    report = musiq.run(*args)
    assert not report["complete"] and report["failed"] == 8 and len(calls) == 8
    assert report["stop_reason"] == "max_failure_count"
    for splits in report["tracks"].values():
        for result in splits.values():
            assert result["delta"] == {"plcc": None, "srocc": None}
            assert result["bootstrap"] is None
    calls.clear()
    fake_runtime(monkeypatch, calls)
    complete = musiq.run(*args)
    assert complete["complete"] and complete["cache_reused"] == 0 and len(calls) == 12


def test_interruption_preserves_atomic_records_and_resume(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls)
    original = musiq.CpuMusiq

    class Interrupt(original):
        def score(self, data):
            if len(calls) == 3:
                raise KeyboardInterrupt
            return super().score(data)
    monkeypatch.setattr(musiq, "CpuMusiq", Interrupt)
    partial = musiq.run(*args)
    assert not partial["complete"] and partial["processed"] == 3
    assert partial["stop_reason"] == "KeyboardInterrupt"
    assert len(list((args[-1] / "predictions").glob("*.json"))) == 3
    calls.clear()
    fake_runtime(monkeypatch, calls)
    resumed = musiq.run(*args)
    assert resumed["complete"] and resumed["cache_reused"] == 3 and len(calls) == 9


@pytest.mark.parametrize("field", ["runtime", "code"])
def test_runtime_or_source_identity_drift_invalidates_cache(tmp_path, monkeypatch, field):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls)
    first = musiq.run(*args)
    calls.clear()
    if field == "runtime":
        monkeypatch.setattr(musiq.importlib.metadata, "version", lambda name: "new-" + name)
    else:
        path = tmp_path / "extra-source.py"
        path.write_text("pass\n")
        original = musiq.source_hashes
        monkeypatch.setattr(musiq, "source_hashes", lambda: {
            **original(), str(path): musiq.hash_file(path)})
    second = musiq.run(*args)
    assert second["complete"] and second["cache_reused"] == 0 and len(calls) == 12
    assert first["identity"] != second["identity"]


@pytest.mark.parametrize("drift", ["input", "model", "source", "feature"])
def test_midrun_drift_never_proves_success(tmp_path, monkeypatch, drift):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls)
    original = musiq.CpuMusiq
    extra = tmp_path / "extra-source.py"
    extra.write_text("before\n")
    original_hashes = musiq.source_hashes
    monkeypatch.setattr(musiq, "source_hashes", lambda: {
        **original_hashes(), str(extra): musiq.hash_file(extra)})

    class Drift(original):
        def score(self, data):
            result = super().score(data)
            if len(calls) == 12:
                path = {"model": args[4], "input": next(args[0].glob("*.png")), "source": extra,
                        "feature": next((args[2].parent / "features").glob("*.json"))}[drift]
                path.write_bytes(b"changed after final inference")
            return result
    monkeypatch.setattr(musiq, "CpuMusiq", Drift)
    report = musiq.run(*args)
    assert not report["complete"] and report["stop_reason"] == "ValueError"
    assert report["tracks"]["koniq"]["all"]["bootstrap"] is None


def test_family_resampling_duplicates_whole_unequal_native_families():
    cohort = [{"group": "a"}, {"group": "a"}, {"group": "b"}]
    units = musiq.resampling_units(cohort, "kadid")
    assert units == [[0, 1], [2]]
    rng = SimpleNamespace(integers=lambda *a, **kw: [0, 0])
    assert musiq.draw_indices(units, rng) == [0, 1, 0, 1]
    assert musiq.resampling_units(cohort, "koniq") == [[0], [1], [2]]


def test_bootstrap_is_paired_deterministic_and_counts_constant_replicates():
    cohort = [{"id": str(i), "target": i, "group": str(i // 2)} for i in range(6)]
    baseline = {str(i): i for i in range(6)}
    records = {str(i): {"status": "ok", "score": i} for i in range(6)}
    statistics = {**musiq.STATISTICS, "replicates": 80}
    first = musiq.paired_bootstrap(cohort, baseline, records, "kadid", statistics)
    second = musiq.paired_bootstrap(cohort, baseline, records, "kadid", statistics)
    assert first == second
    for result in first["delta"].values():
        assert result["interval"] == [0, 0]
        assert result["valid_replicates"] + result["invalid_replicates"] == 80
    constant = {str(i): {"status": "ok", "score": 1} for i in range(6)}
    invalid = musiq.paired_bootstrap(cohort, baseline, constant, "koniq", statistics)
    for result in invalid["delta"].values():
        assert result == {"valid_replicates": 0, "invalid_replicates": 80, "interval": None}


def test_incomplete_whole_run_suppresses_even_complete_partition_deltas():
    items = [{"id": str(i), "track": "koniq", "split": "comparison", "target": i}
             for i in range(4)]
    baseline = {str(i): i for i in range(4)}
    records = {str(i): {"status": "ok", "score": i} for i in range(4)}
    result = musiq.metrics(items, baseline, records, False)["koniq"]["comparison"]
    assert result["musiq_paired"]["n"] == result["baseline_paired"]["n"] == 4
    assert result["delta"] == {"plcc": None, "srocc": None} and result["bootstrap"] is None


def test_semantic_record_hash_excludes_rss_and_time_only():
    record = {"status": "ok", "score": 999, "elapsed_ms": 1, "peak_rss_bytes": 2}
    before = musiq.record_hash(record)
    record.update(elapsed_ms=100, peak_rss_bytes=200)
    assert musiq.record_hash(record) == before
    record["score"] += 1
    assert musiq.record_hash(record) != before


def test_peak_rss_platform_units(monkeypatch):
    monkeypatch.setattr(musiq.resource, "getrusage", lambda *args: SimpleNamespace(ru_maxrss=5))
    monkeypatch.setattr(musiq.sys, "platform", "darwin")
    assert musiq.peak_rss_bytes() == 5
    monkeypatch.setattr(musiq.sys, "platform", "linux")
    assert musiq.peak_rss_bytes() == 5120


def test_native_call_process_budget_restores_signal_handlers(monkeypatch):
    monkeypatch.setattr(musiq, "LIMITS", {**musiq.LIMITS, "process_budget_seconds": 0.02})
    before = signal.getsignal(signal.SIGALRM)
    with pytest.raises(musiq.BudgetExceeded, match="process_budget_seconds"):
        with musiq.process_budget(time.perf_counter()):
            time.sleep(0.08)
    assert signal.getsignal(signal.SIGALRM) == before
    assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)


@pytest.mark.parametrize("limit", ["time", "rss"])
def test_limit_incomplete_checkpoint(tmp_path, monkeypatch, limit):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls)
    if limit == "time":
        monkeypatch.setitem(musiq.LIMITS, "process_budget_seconds", 0)
    else:
        monkeypatch.setattr(musiq, "peak_rss_bytes", lambda: 2500000001)
    # Updated JSON is only a synthetic test protocol; production digest stays hard pinned.
    plan = musiq.read_json(args[3])
    plan["limits"] = musiq.LIMITS
    args[3].write_text(json.dumps(plan))
    monkeypatch.setattr(musiq, "FROZEN_PROTOCOL_SHA", musiq.hash_file(args[3]))
    report = musiq.run(*args)
    assert not report["complete"] and not calls
    assert report["stop_reason"] == ("process_budget_seconds" if limit == "time"
                                     else "max_peak_rss_bytes")
    assert musiq.read_json(args[-1] / "checkpoint.json")["state"] == "incomplete"


def test_model_initialization_failure_is_reported_without_predictions(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)

    def fail(*a):
        raise ValueError("CPU model evidence missing")
    monkeypatch.setattr(musiq, "CpuMusiq", fail)
    report = musiq.run(*args)
    assert not report["complete"] and report["processed"] == 0
    assert report["stop_reason"] == "ValueError"
    assert not (args[-1] / "predictions").exists()


def fake_model(device="cpu"):
    net_class = type("MUSIQ", (), {})
    net = net_class()
    net.training = False
    net.head = SimpleNamespace(out_features=1)
    net.data_preprocess_opts = musiq.PREPROCESS.copy()
    return SimpleNamespace(parameters=lambda: [SimpleNamespace(device=device)], buffers=lambda: [],
                           device=device, lower_better=False, metric_name="musiq", metric_mode="NR",
                           as_loss=False, check_input_range=True, training=False, net=net, seed=0)


@pytest.mark.parametrize("device", ["cuda:0", "mps"])
def test_actual_model_device_readback_rejects_non_cpu(monkeypatch, device):
    runtime = musiq.CpuMusiq.__new__(musiq.CpuMusiq)
    runtime.metric = fake_model(device)
    runtime.torch = SimpleNamespace(get_num_threads=lambda: 4, get_num_interop_threads=lambda: 4,
                                   are_deterministic_algorithms_enabled=lambda: True)
    defaults = SimpleNamespace(DEFAULT_CONFIGS={"musiq": {
        "metric_opts": {"type": "MUSIQ", "pretrained": "koniq10k"}}})
    monkeypatch.setattr(musiq.importlib, "import_module", lambda name: defaults)
    with pytest.raises(ValueError, match="actual CPU"):
        runtime.validate()
    runtime.metric = fake_model("cpu")
    assert runtime.validate()["execution_devices"] == ["CPU"]


def test_native_rgb_input_keeps_original_resolution_float32_range():
    class Tensor:
        def __init__(self, array):
            self.array = array
            self.device = "cpu"
            self.dtype = array.dtype
            self.shape = array.shape

        def permute(self, *axes):
            return Tensor(self.array.transpose(axes))

        def unsqueeze(self, axis):
            return Tensor(np.expand_dims(self.array, axis))

        def min(self):
            return self.array.min()

        def max(self):
            return self.array.max()
    received = []

    def metric(tensor):
        received.append(tensor)
        return SimpleNamespace(numel=lambda: 1, device="cpu", item=lambda: 137.5)
    runtime = musiq.CpuMusiq.__new__(musiq.CpuMusiq)
    runtime.np, runtime.pil = np, Image
    runtime.torch = SimpleNamespace(from_numpy=Tensor, float32=np.dtype("float32"),
                                   isfinite=lambda t: np.isfinite(t.array), inference_mode=nullcontext)
    runtime.metric = metric
    runtime.validate = evidence
    import io
    buffer = io.BytesIO()
    Image.new("RGB", (19, 11), (255, 128, 0)).save(buffer, format="PNG")
    result = runtime.score(buffer.getvalue())
    assert result["score"] == 137.5  # Raw score is not clamped or normalized.
    assert result["input_shape"] == [1, 3, 11, 19]
    assert received[0].dtype == np.dtype("float32")
    assert received[0].array[0, 0, 0, 0] == 1
    assert received[0].array[0, 2, 0, 0] == 0
