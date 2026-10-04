from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

SPEC = importlib.util.spec_from_file_location(
    "musiq_full", Path(__file__).parents[1] / "scripts/benchmark_musiq_openvino_full.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def fixture(tmp_path, monkeypatch):
    root = tmp_path / "inputs"
    root.mkdir()
    counts = {"koniq": {"development": 3, "comparison": 3},
              "kadid": {"development": 4, "comparison": 4}}
    monkeypatch.setattr(runner, "SPLIT_COUNTS", counts)
    monkeypatch.setattr(runner, "FAMILY_COUNTS", {"development": 2, "comparison": 2})
    monkeypatch.setattr(runner, "LIMITS", {**runner.LIMITS, "max_items": 14})
    monkeypatch.setattr(runner, "STATISTICS", {**runner.STATISTICS, "replicates": 20})
    # The bootstrap default is frozen, so avoid 2000 draws in integration tests only.
    bootstrap = runner.paired_bootstrap
    monkeypatch.setattr(runner, "paired_bootstrap", lambda a, b, c: bootstrap(a, b, c, runner.STATISTICS))
    items = []
    for track, splits in counts.items():
        for split, count in splits.items():
            for i in range(count):
                name = f"{track}-{split}-{i}.png"
                Image.new("RGB", (512, 384), (i * 20, 40, 50)).save(root / name)
                item = {"id": name, "path": name, "track": track, "split": split,
                        "input_sha256": runner.sha(root / name), "target": float(i),
                        "baseline_score": float(count-i), "reference_score": i * 20 / 255 * 100,
                        "reference_record_sha256": "a" * 64, "baseline_record_sha256": "b" * 64}
                if track == "kadid":
                    item["group"] = f"{split}-{i // 2}"
                items.append(item)
    (root / "models").mkdir()
    graph = {}
    for name in ("models/musiq.xml", "models/musiq.bin"):
        (root / name).write_bytes(b"graph")
        graph[name] = {"size": 5, "sha256": runner.sha(root / name)}
    monkeypatch.setattr(runner, "GRAPH", graph)
    plan = {"schema_version": runner.SCHEMA, "input_shape": runner.SHAPE, "config": runner.CONFIG,
            "limits": runner.LIMITS, "checkpoint_sha256": runner.MODEL_SHA, "graph": graph,
            "statistics": runner.STATISTICS, "training_exposure": runner.EXPOSURE,
            **runner.PARENTS, "items": items}
    protocol = root / "protocol.json"
    runner.atomic(protocol, plan)
    return root, protocol, runner.sha(protocol), tmp_path / "output"


def fake_runtime(monkeypatch, calls, *, devices=("CPU",), precision="<Type: 'float32'>",
                 fail_at=None, delta=0):
    class Compiled:
        def get_property(self, key):
            return list(devices) if key == "EXECUTION_DEVICES" else precision

        def output(self):
            return "score"

        def __call__(self, data):
            calls.append(data[0].shape)
            if fail_at == len(calls):
                raise RuntimeError("inference failed")
            return {"score": np.array(float(data[0][0, 0, 0, 0]) * 100 + delta)}

    class Core:
        def read_model(self, path):
            return SimpleNamespace(inputs=[1], outputs=[1], input=lambda: SimpleNamespace(shape=runner.SHAPE))

        def compile_model(self, model, device, config):
            assert device == "CPU"
            assert config == {"INFERENCE_NUM_THREADS": 4, "NUM_STREAMS": 1,
                              "PERFORMANCE_HINT": "LATENCY", "INFERENCE_PRECISION_HINT": "f32"}
            return Compiled()

    monkeypatch.setitem(sys.modules, "openvino", SimpleNamespace(Core=Core, __version__="test"))


@pytest.mark.parametrize("corrupt", [b"broken json", b"\xff\xfe"])
def test_single_inference_resume_and_corrupt_recompute(tmp_path, monkeypatch, corrupt):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls)
    first = runner.evaluate(*args)
    assert first["status"] == "passed" and len(calls) == 14 and first["failures"] == 0
    second = runner.evaluate(*args)
    assert second["cache_reused"] == 14 and len(calls) == 14
    assert first["records"] == second["records"]
    assert first["tracks"] == second["tracks"]
    next((args[-1] / "predictions").glob("*.json")).write_bytes(corrupt)
    third = runner.evaluate(*args)
    assert third["cache_reused"] == 13 and len(calls) == 15 and third["status"] == "passed"


def test_failure_invalidates_all_intervals_and_resumes(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls, fail_at=4)
    result = runner.evaluate(*args)
    assert result["status"] == "incomplete" and result["successful"] == 3
    assert runner.read(args[-1] / "checkpoint.json")["processed"] == 3
    for splits in result["tracks"].values():
        for stats in splits.values():
            assert stats["bootstrap"] is None and stats["delta"] == {"plcc": None, "srocc": None}
    calls.clear()
    fake_runtime(monkeypatch, calls)
    resumed = runner.evaluate(*args)
    assert resumed["status"] == "passed" and resumed["cache_reused"] == 3 and len(calls) == 11


@pytest.mark.parametrize("devices,precision", [([], "<Type: 'float32'>"),
    (["GPU"], "<Type: 'float32'>"), (["CPU"], "bf16")])
def test_cpu_f32_readback_required(tmp_path, monkeypatch, devices, precision):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls, devices=devices, precision=precision)
    assert runner.evaluate(*args)["status"] == "incomplete" and not calls


def test_parity_fail_has_no_trustworthy_statistics(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls, delta=0.1)
    report = runner.evaluate(*args)
    assert report["complete"] and report["status"] == "parity_failed"
    assert all(s["bootstrap"] is None for v in report["tracks"].values() for s in v.values())


def test_budget_after_statistics_invalidates_results(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls)
    metrics = runner.metrics
    def exceeded(*a):
        result = metrics(*a)
        if a[-1]:
            monkeypatch.setattr(runner, "peak_rss_bytes", lambda: runner.LIMITS["max_rss_bytes"] + 1)
        return result
    monkeypatch.setattr(runner, "metrics", exceeded)
    report = runner.evaluate(*args)
    assert report["status"] == "incomplete" and report["error"] == "resource bound exceeded"
    assert all(s["delta"]["plcc"] is None for v in report["tracks"].values() for s in v.values())


@pytest.mark.parametrize("mutate", [
    lambda p: p["items"][0].update(target=True),
    lambda p: p["items"][0].update(reference_score=float("inf")),
    lambda p: p["items"][0].update(baseline_record_sha256="bad"),
    lambda p: p["items"][0].update(track="other"),
    lambda p: p["items"][0].update(split="test"),
    lambda p: p["items"][0].update(path="../escape"),
    lambda p: p["items"][0].update(id=p["items"][1]["id"]),
    lambda p: p["items"][0].update(path=p["items"][1]["path"]),
    lambda p: p["items"][-1].update(group="development-0"),
    lambda p: p.update(parent_protocol_sha256="c" * 64),
    lambda p: p.update(extra="unknown"),
])
def test_invalid_protocols(tmp_path, monkeypatch, mutate):
    args = fixture(tmp_path, monkeypatch)
    plan = runner.read(args[1])
    mutate(plan)
    # Write invalid nonfinite JSON deliberately; the validator must reject it.
    import json
    args[1].write_text(json.dumps(plan))
    with pytest.raises(ValueError):
        runner.validate_protocol(args[0], args[1], runner.sha(args[1]))


def test_identity_shape_drift_and_unsafe_cache(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="approval"):
        runner.validate_protocol(args[0], args[1], "0" * 64)
    plan = runner.read(args[1])
    image = args[0] / plan["items"][0]["path"]
    Image.new("RGB", (128, 128)).save(image)
    with pytest.raises(ValueError, match="input identity"):
        runner.validate_protocol(args[0], args[1], args[2])
    plan["items"][0]["input_sha256"] = runner.sha(image)
    runner.atomic(args[1], plan)
    with pytest.raises(ValueError, match="512x384"):
        runner.validate_protocol(args[0], args[1], runner.sha(args[1]))


def test_family_bootstrap_paired_ties_and_multiplicity():
    cohort = [{"id": str(i), "group": str(i // 2), "target": v, "baseline_score": v}
              for i, v in enumerate([1, 1, 2, 3, 4, 4])]
    records = {i["id"]: {"score": i["baseline_score"]} for i in cohort}
    config = {**runner.STATISTICS, "replicates": 50}
    boot = runner.paired_bootstrap(cohort, records, "kadid", config)
    assert boot["units"] == 3
    assert all(v["interval"] == [0., 0.] for v in boot["delta"].values())
    assert runner.associations([1, 1, 2, 3], [1, 1, 2, 3])["srocc"] == pytest.approx(1)
    class RNG:
        def integers(self, *a, **k):
            return [1, 1, 0]
    assert runner.draw_indices([[0, 1], [2, 3], [4, 5]], RNG()) == [2, 3, 2, 3, 0, 1]


@pytest.mark.parametrize("score", [True, float("nan"), float("inf"), "3"])
def test_malformed_scores_not_reused(score):
    item = {"id": "x", "input_sha256": "a" * 64}
    record = {**item, "identity": "i", "status": "ok", "execution_devices": ["CPU"],
              "fallback_used": False, "score": score, "native_call_seconds": 0.0}
    try:
        record["record_sha256"] = runner.digest(record)
    except ValueError:
        record["record_sha256"] = "invalid"
    assert not runner.valid_record(record, "i", item)


def test_unsafe_cache_symlink_fails_closed(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls)
    runner.evaluate(*args)
    cached = next((args[-1] / "predictions").glob("*.json"))
    cached.unlink()
    cached.symlink_to(args[1])
    report = runner.evaluate(*args)
    assert report["status"] == "incomplete" and "symlink" in report["error"]
    assert len(calls) == 14


def test_graph_size_and_time_bounds_fail_before_inference(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls)
    monkeypatch.setattr(runner, "check_budget", lambda started: (_ for _ in ()).throw(
        ValueError("resource bound exceeded")))
    report = runner.evaluate(*args)
    assert report["status"] == "incomplete" and not calls
    # Independently exercise the real clock gate, without sleeping.
    monkeypatch.undo()
    with pytest.raises(ValueError, match="resource bound"):
        runner.check_budget(runner.time.monotonic() - runner.LIMITS["max_seconds"] - 1)


def test_posthash_drift_invalidates_completed_statistics(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls)
    original = runner.metrics
    def drift(*a):
        result = original(*a)
        if a[-1]:
            (args[0] / "models/musiq.bin").write_bytes(b"drift")
        return result
    monkeypatch.setattr(runner, "metrics", drift)
    report = runner.evaluate(*args)
    assert report["successful"] == 14 and report["status"] == "incomplete"
    assert report["error"] == "graph identity mismatch"
    assert all(s["bootstrap"] is None for v in report["tracks"].values() for s in v.values())


def test_frozen_settings_reject_boolean_alias(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    plan = runner.read(args[1])
    plan["config"]["streams"] = True
    runner.atomic(args[1], plan)
    with pytest.raises(ValueError, match="frozen full"):
        runner.validate_protocol(args[0], args[1], runner.sha(args[1]))


def test_graph_size_bound(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    plan = runner.read(args[1])
    monkeypatch.setattr(runner, "LIMITS", {**runner.LIMITS, "max_graph_bytes": 9})
    plan["limits"] = runner.LIMITS
    runner.atomic(args[1], plan)
    with pytest.raises(ValueError, match="graph exceeds"):
        runner.validate_protocol(args[0], args[1], runner.sha(args[1]))


@pytest.mark.parametrize("delta", [float("nan"), float("inf")])
def test_nonfinite_native_inference_cannot_succeed(tmp_path, monkeypatch, delta):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls, delta=delta)
    report = runner.evaluate(*args)
    assert report["status"] == "incomplete" and report["successful"] == 0
    assert not list((args[-1] / "predictions").glob("*.json"))
