from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

SPEC = importlib.util.spec_from_file_location(
    "musiq_ov", Path(__file__).parents[1] / "scripts/benchmark_musiq_openvino.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def fixture(tmp_path):
    root = tmp_path / "inputs"
    root.mkdir()
    items = []
    for track in ("koniq", "kadid"):
        for index in range(16):
            path = root / f"{track}-{index}.png"
            Image.new("RGB", (512, 384), (index * 10, 50, 80)).save(path)
            items.append(
                {
                    "id": f"{track}:{index}",
                    "track": track,
                    "path": path.name,
                    "input_sha256": runner.sha(path),
                    "reference_score": index * 10 / 255 * 100,
                }
            )
    model = root / "models"
    model.mkdir()
    graph = {}
    for name in ("musiq.xml", "musiq.bin"):
        path = model / name
        path.write_bytes(b"fixed graph")
        graph["models/" + name] = {"sha256": runner.sha(path), "size": path.stat().st_size}
    plan = {
        "schema_version": runner.SCHEMA,
        "input_shape": runner.SHAPE,
        "config": runner.CONFIG,
        "limits": runner.LIMITS,
        "checkpoint_sha256": runner.MODEL_SHA,
        "items": items,
        "graph": graph,
    }
    protocol = root / "protocol.json"
    runner.atomic(protocol, plan)
    return root, protocol, runner.sha(protocol), tmp_path / "output"


def fake_runtime(monkeypatch, calls, *, device=None, precision="<Type: 'float32'>", delta=0.0):
    class Compiled:
        def get_property(self, key):
            return (
                device
                if key == "EXECUTION_DEVICES" and device is not None
                else (["CPU"] if key == "EXECUTION_DEVICES" else precision)
            )

        def output(self):
            return "score"

        def __call__(self, inputs):
            calls.append(inputs[0].shape)
            return {"score": np.array([[float(inputs[0][0, 0, 0, 0]) * 100 + delta]])}

    class Core:
        def read_model(self, path):
            assert Path(path).name == "musiq.xml"
            return SimpleNamespace(
                inputs=[1], outputs=[1], input=lambda: SimpleNamespace(shape=runner.SHAPE)
            )

        def compile_model(self, model, device, config):
            assert device == "CPU" and config["INFERENCE_PRECISION_HINT"] == "f32"
            assert config["INFERENCE_NUM_THREADS"] == 4 and config["NUM_STREAMS"] == 1
            return Compiled()

    monkeypatch.setitem(
        sys.modules, "openvino", SimpleNamespace(Core=Core, __version__="fixed-test")
    )


@pytest.mark.parametrize("corruption", [b"corrupt json", b"\xff\xfe\xff"])
def test_success_resume_and_corrupt_cache_recovery(tmp_path, monkeypatch, corruption):
    args = fixture(tmp_path)
    calls = []
    fake_runtime(monkeypatch, calls)
    first = runner.evaluate(*args)
    assert first["status"] == "passed" and first["cache_reused"] == 0
    assert len(calls) == 64 and first["max_repeat_error"] == 0
    second = runner.evaluate(*args)
    assert second["identity"] == first["identity"] and second["cache_reused"] == 32
    assert second["records"] == first["records"] and len(calls) == 64
    next((args[-1] / "predictions").glob("*.json")).write_bytes(corruption)
    third = runner.evaluate(*args)
    assert third["status"] == "passed" and third["cache_reused"] == 31 and len(calls) == 66


@pytest.mark.parametrize(
    "device,precision",
    [(["GPU"], "<Type: 'float32'>"), ([], "<Type: 'float32'>"), (["CPU"], "bf16")],
)
def test_unknown_or_wrong_device_precision_cannot_pass(tmp_path, monkeypatch, device, precision):
    args = fixture(tmp_path)
    calls = []
    fake_runtime(monkeypatch, calls, device=device, precision=precision)
    report = runner.evaluate(*args)
    assert report["status"] == "incomplete" and not report["complete"] and not calls


def test_parity_gate_does_not_relax_for_complete_run(tmp_path, monkeypatch):
    args = fixture(tmp_path)
    calls = []
    fake_runtime(monkeypatch, calls, delta=0.01)
    report = runner.evaluate(*args)
    assert report["complete"] and report["status"] == "parity_failed"
    assert report["max_abs_error"] > runner.LIMITS["max_abs_error"]


def test_source_or_graph_drift_rejected_before_inference(tmp_path, monkeypatch):
    args = fixture(tmp_path)
    calls = []
    fake_runtime(monkeypatch, calls)
    (args[0] / "models/musiq.bin").write_bytes(b"changed")
    with pytest.raises(ValueError, match="graph identity"):
        runner.evaluate(*args)
    assert not calls


def test_shape_and_approval_fingerprint_are_mandatory(tmp_path):
    args = fixture(tmp_path)
    with pytest.raises(ValueError, match="approval fingerprint"):
        runner.validate_protocol(*args[:2], "0" * 64)
    plan = runner.read(args[1])
    Image.new("RGB", (224, 224)).save(args[0] / plan["items"][0]["path"])
    plan["items"][0]["input_sha256"] = runner.sha(args[0] / plan["items"][0]["path"])
    runner.atomic(args[1], plan)
    with pytest.raises(ValueError, match="512x384"):
        runner.validate_protocol(args[0], args[1], runner.sha(args[1]))


def test_output_symlinks_and_parent_overlap_rejected(tmp_path):
    args = fixture(tmp_path)
    with pytest.raises(ValueError, match="separate"):
        runner.output_dir(args[0], args[0] / "reports")
    link = tmp_path / "link"
    link.symlink_to(args[0], target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        runner.clean(link / "missing")
    with pytest.raises(ValueError, match="unsafe"):
        runner.relative(args[0], "../escape")


def test_offline_and_cache_restore_preserve_home(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "previous-cached-tempdir"))
    home, original_socket = os.environ.get("HOME"), socket.socket
    old_cache = os.environ.get("XDG_CACHE_HOME")
    old_tempdir = tempfile.tempdir
    with runner.owned_cache(tmp_path), runner.offline():
        assert os.environ.get("HOME") == home
        assert tempfile.gettempdir() == str(tmp_path / "tmp")
        with pytest.raises(RuntimeError, match="network forbidden"):
            socket.socket()
    assert socket.socket is original_socket and os.environ.get("HOME") == home
    assert os.environ.get("XDG_CACHE_HOME") == old_cache
    assert tempfile.tempdir == old_tempdir


@pytest.mark.parametrize("scores", [[True, False], [float("nan"), 1], [1], [1, float("inf")]])
def test_invalid_prediction_never_reused(scores):
    item = {"id": "x", "input_sha256": "a"}
    record = {
        "identity": "i",
        **item,
        "scores": scores,
        "execution_devices": ["CPU"],
        "fallback_used": False,
    }
    try:
        record["record_sha256"] = runner.digest(record)
    except ValueError:
        record["record_sha256"] = "invalid"
    assert not runner.valid_record(record, "i", item)
