from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "musiq_native_shapes", Path(__file__).parents[1] / "scripts/benchmark_musiq_native_shapes.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.mark.parametrize(
    "height,width,expected",
    [
        (384, 512, {"224": [168, 224], "384": [288, 384]}),
        (682, 1024, {"224": [149, 224], "384": [256, 384]}),
        (1024, 682, {"224": [224, 149], "384": [384, 256]}),
        (680, 1024, {"224": [149, 224], "384": [255, 384]}),
        (684, 1024, {"224": [150, 224], "384": [256, 384]}),
    ],
)
def test_native_resize_round_recipe(height, width, expected):
    assert runner.resize_dimensions(height, width) == expected
    for scale in (224, 384):
        ratio = scale / max(height, width)
        assert expected[str(scale)] == [round(height * ratio), round(width * ratio)]


@pytest.mark.parametrize("height,width", [(True, 512), (512, False), (0, 512), (1.0, 512)])
def test_resize_dimensions_reject_noninteger_metadata(height, width):
    with pytest.raises(ValueError, match="integer"):
        runner.resize_dimensions(height, width)


@pytest.mark.parametrize("value", [True, 1, float("nan"), float("inf"), [1.0, 2.0]])
def test_output_requires_one_finite_float(value):
    import numpy as np

    with pytest.raises(ValueError, match="single float"):
        runner.scalar_result(np.asarray(value))


def test_output_isolation_covers_protocol_and_code(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    protocol = tmp_path / "separate" / "protocol.json"
    protocol.parent.mkdir()
    protocol.write_text("{}")
    for output in (root / "reports", root.parent, protocol.parent):
        with pytest.raises(ValueError, match="separate"):
            runner.output_dir(root, protocol, output)
    link = tmp_path / "link"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        runner.output_dir(root, protocol, link / "report")


def test_runner_import_does_not_import_quality_or_production_modules():
    import ast

    tree = ast.parse(Path(runner.__file__).read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(name.startswith(("torch", "pyiqa", "material_agent")) for name in imported)


def test_asset_bounds_precede_full_hash(tmp_path, monkeypatch):
    path = tmp_path / "large.bin"
    path.write_bytes(b"12345")
    calls = []
    monkeypatch.setattr(runner, "sha", lambda p: calls.append(p) or "a" * 64)
    with pytest.raises(ValueError, match="metadata"):
        runner.bounded_asset(tmp_path, path.name, {"size": 5, "sha256": "a" * 64}, 4)
    with pytest.raises(ValueError, match="size"):
        runner.bounded_asset(tmp_path, path.name, {"size": 4, "sha256": "a" * 64}, 4)
    assert not calls


@pytest.mark.parametrize("size", [True, 0, -1, 5.0])
def test_asset_metadata_rejects_boolean_and_malformed_sizes(tmp_path, size):
    with pytest.raises(ValueError, match="metadata"):
        runner.bounded_asset(tmp_path, "model.bin", {"size": size, "sha256": "a" * 64}, 10)


def native_reference(item):
    return {
        "id": "kadid:original-control" if item["variant"] == "control" else item["id"],
        "input_sha256": item["input_sha256"],
        "status": "ok",
        "score": item["reference_score"],
        "execution_status": "success",
        "execution_devices": ["CPU"],
        "fallback_used": False,
        "model_sha256": runner.MODEL_SHA,
        "model_revision": "pyiqa-musiq-koniq-e95806b9",
        "lower_better": False,
        "input_shape": item["input_shape"],
        "input_color": "RGB",
        "input_dtype": "float32",
        "input_range": [0, 1],
        "preprocess": runner.PREPROCESS,
        "seed": 0,
        "deterministic_algorithms": True,
        "torch_threads": 4,
        "torch_interop_threads": 4,
        "batch_size_actual": 1,
        "identity": runner.CONTROL_REFERENCE_IDENTITY,
        "protocol_sha256": runner.CONTROL_REFERENCE_PROTOCOL,
        "elapsed_ms": 1.0,
        "peak_rss_bytes": 100,
    }


def fixture(tmp_path, monkeypatch, *, phase="evaluation"):
    from PIL import Image

    root = tmp_path / "inputs"
    (root / "images").mkdir(parents=True)
    items, preparations, references, graphs = [], [], {}, {}
    shapes = [
        *runner.SHAPES.values(),
        [1, 3, 680, 1024],
        [1, 3, 684, 1024],
        [1, 3, 768, 1024],
        [1, 3, 1024, 1024],
        [1, 3, 552, 976],
        [1, 3, 1364, 2048],
    ]
    for index, shape in enumerate(shapes):
        variant = list(runner.SHAPES)[index] if index < 3 else None
        color = index * 13
        scratch = root / "scratch.png"
        Image.new("RGB", (shape[3], shape[2]), (color, 50, 80)).save(scratch)
        input_sha = runner.sha(scratch)
        path = f"images/{input_sha}.png"
        scratch.rename(root / path)
        kind = (
            "standard_corpus_control"
            if index == 0
            else "derived_portrait_png"
            if index == 2
            else "derived_oversized_png"
            if index == 8
            else "public_raw_embedded_preview"
        )
        item = {
            "id": f"native:{index}",
            "path": path,
            "input_sha256": input_sha,
            "input_shape": shape,
            "expected_status": "supported" if variant else "unsupported_shape",
            "variant": variant,
            "reference_score": color / 255 * 100 if variant else None,
            "source_kind": kind,
            "source_sha256": runner.digest(f"source-{index}"),
        }
        metadata = {
            "id": item["id"],
            "input_sha256": input_sha,
            "shape": shape,
            "source_kind": kind,
            "source_sha256": item["source_sha256"],
            "pixel_rgb_uint8_sha256": runner.digest(f"pixels-{index}"),
        }
        if variant:
            reference = native_reference(item)
            reference["record_sha256"] = runner.native_record_hash(reference)
            if index == 0:
                metadata.update(
                    original_id=reference["id"], reference_record_sha256=reference["record_sha256"]
                )
            reference_path = f"references/{variant}.json"
            runner.atomic(root / reference_path, reference)
            references[variant] = {
                "path": reference_path,
                "sha256": runner.sha(root / reference_path),
                "size": (root / reference_path).stat().st_size,
            }
            graphs[variant] = {}
            for suffix in ("xml", "bin"):
                graph_path = f"models/{variant}/musiq.{suffix}"
                dest = root / graph_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(f"test graph {variant} {suffix}".encode())
                graphs[variant][graph_path] = {
                    "size": dest.stat().st_size,
                    "sha256": runner.sha(dest),
                }
            if phase == "preexport" and index > 0:
                references[variant] = graphs[variant] = None
                item["reference_score"] = None
        items.append(item)
        preparations.append(metadata)
    monkeypatch.setattr(runner, "CONTROL_GRAPH", graphs["control"])
    inventory = runner.digest("inventory")
    prep = root / "preparation.json"
    runner.atomic(prep, {"source_inventory_sha256": inventory, "items": preparations})
    plan = {
        "schema_version": runner.SCHEMA,
        "phase": phase,
        "checkpoint_sha256": runner.MODEL_SHA,
        "checkpoint_size_bytes": runner.MODEL_SIZE,
        "config": runner.CONFIG,
        "limits": runner.LIMITS,
        "export_gate": runner.EXPORT_GATE,
        "shapes": runner.SHAPES,
        "input_contract": runner.INPUT_CONTRACT,
        "source_inventory_sha256": inventory,
        "preparation": {"path": prep.name, "sha256": runner.sha(prep), "size": prep.stat().st_size},
        "graphs": graphs,
        "references": references,
        "items": items,
    }
    protocol = root / "protocol.json"
    runner.atomic(protocol, plan)
    return root, protocol, runner.sha(protocol), tmp_path / "output"


def fake_runtime(
    monkeypatch,
    calls,
    compiles,
    *,
    devices=None,
    precision="<Type: 'float32'>",
    delta=0,
    output=None,
    input_shape=None,
    threads=4,
    streams=1,
    repeat_delta=0,
    on_call=None,
):
    import numpy as np
    import sys
    from types import SimpleNamespace

    class Compiled:
        def __init__(self, variant):
            self.variant, self.count = variant, 0

        def get_property(self, key):
            return {
                "EXECUTION_DEVICES": devices if devices is not None else ["CPU"],
                "INFERENCE_PRECISION_HINT": precision,
                "INFERENCE_NUM_THREADS": threads,
                "NUM_STREAMS": streams,
            }[key]

        def output(self):
            return "score"

        def __call__(self, inputs):
            array = inputs[0]
            assert list(array.shape) == runner.SHAPES[self.variant]
            assert array.dtype == np.float32
            calls.append((self.variant, list(array.shape)))
            self.count += 1
            if on_call:
                on_call(len(calls))
            score = float(array[0, 0, 0, 0]) * 100 + delta
            if self.count % 2 == 0:
                score += repeat_delta
            return {"score": np.asarray([[score]]) if output is None else output}

    class Core:
        def read_model(self, path):
            variant = Path(path).parent.name
            model = SimpleNamespace(inputs=[1], outputs=[1], variant=variant)
            model.input = lambda: SimpleNamespace(
                shape=input_shape or runner.SHAPES[variant],
                get_element_type=lambda: "<Type: 'float32'>",
            )
            model.output = lambda: SimpleNamespace(
                shape=[1, 1], get_element_type=lambda: "<Type: 'float32'>"
            )
            return model

        def compile_model(self, model, device, config):
            assert device == "CPU"
            assert config == {
                "INFERENCE_NUM_THREADS": 4,
                "NUM_STREAMS": 1,
                "PERFORMANCE_HINT": "LATENCY",
                "INFERENCE_PRECISION_HINT": "f32",
            }
            compiles.append(model.variant)
            return Compiled(model.variant)

    runtime = SimpleNamespace(Core=Core, __version__="frozen-test-ov")
    monkeypatch.setitem(sys.modules, "openvino", runtime)
    return runtime


def mutate_protocol(args, mutate):
    plan = runner.read(args[1])
    mutate(plan)
    runner.atomic(args[1], plan)
    return args[0], args[1], runner.sha(args[1]), args[3]


def test_nine_exact_dispatch_first_and_resume(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls, compiles = [], []
    fake_runtime(monkeypatch, calls, compiles)
    first = runner.evaluate(*args)
    assert first["status"] == "passed" and first["complete"]
    assert (first["successful"], first["unsupported"], first["failures"]) == (3, 6, 0)
    assert first["new_native_inferences"] == 6 and first["cache_reused"] == 0
    assert len(first["records"]) == 9 and compiles == list(runner.SHAPES)
    assert len(calls) == 6 and {tuple(shape) for _, shape in calls} == {
        tuple(shape) for shape in runner.SHAPES.values()
    }
    unsupported = [r for r in first["records"] if r["status"] == "unsupported_shape"]
    assert len(unsupported) == 6
    assert any(r["input_shape"][2:] == [680, 1024] for r in unsupported)
    assert any(r["input_shape"][2:] == [684, 1024] for r in unsupported)
    assert any(r["input_shape"][2:] == [1364, 2048] for r in unsupported)
    assert all(not r["graph_selected"] and not r["score_produced"] for r in unsupported)
    assert all(
        not set(r) & {"score", "scores", "reference_score", "fallback_used"} for r in unsupported
    )
    second = runner.evaluate(*args)
    assert second["status"] == "passed" and second["cache_reused"] == 9
    assert second["new_native_inferences"] == 0 and second["records"] == first["records"]
    assert len(calls) == 6 and compiles == list(runner.SHAPES) * 2


@pytest.mark.parametrize("corruption", [b"bad json", b"\xff\xfe\xff"])
def test_corrupt_prediction_recomputes_only_one_supported_item(tmp_path, monkeypatch, corruption):
    args = fixture(tmp_path, monkeypatch)
    calls, compiles = [], []
    fake_runtime(monkeypatch, calls, compiles)
    first = runner.evaluate(*args)
    record = first["records"][1]
    path = args[-1] / "predictions" / (runner.digest(record["id"]) + ".json")
    path.write_bytes(corruption)
    report = runner.evaluate(*args)
    assert report["status"] == "passed" and report["cache_reused"] == 8
    assert report["new_native_inferences"] == 2 and len(calls) == 8


def test_unsupported_cache_score_injection_recomputed_without_model_call(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls, compiles = [], []
    fake_runtime(monkeypatch, calls, compiles)
    record = runner.evaluate(*args)["records"][-1]
    record["score"] = 1.0
    record["record_sha256"] = runner.digest(
        {k: v for k, v in record.items() if k != "record_sha256"}
    )
    runner.atomic(args[-1] / "predictions" / (runner.digest(record["id"]) + ".json"), record)
    report = runner.evaluate(*args)
    assert report["status"] == "passed" and report["cache_reused"] == 8
    assert report["new_native_inferences"] == 0 and len(calls) == 6
    assert "score" not in report["records"][-1]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"devices": ["GPU"]},
        {"devices": []},
        {"precision": "bf16"},
        {"threads": True},
        {"threads": 2},
        {"streams": True},
        {"streams": 2},
        {"input_shape": [1, 3, 384, 511]},
    ],
)
def test_strict_execution_readback_before_inference(tmp_path, monkeypatch, kwargs):
    args = fixture(tmp_path, monkeypatch)
    calls, compiles = [], []
    fake_runtime(monkeypatch, calls, compiles, **kwargs)
    report = runner.evaluate(*args)
    assert report["status"] == "incomplete" and not report["complete"] and not calls


def test_resume_still_requires_cpu_f32_readback(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls, compiles = [], []
    fake_runtime(monkeypatch, calls, compiles)
    assert runner.evaluate(*args)["status"] == "passed"
    fake_runtime(monkeypatch, calls, compiles, precision="bf16")
    report = runner.evaluate(*args)
    assert report["status"] == "incomplete" and report["new_native_inferences"] == 0
    assert len(calls) == 6


@pytest.mark.parametrize("delta,repeat_delta", [(0.01, 0), (0, 0.0001)])
def test_complete_failed_parity_cannot_pass(tmp_path, monkeypatch, delta, repeat_delta):
    args = fixture(tmp_path, monkeypatch)
    fake_runtime(monkeypatch, [], [], delta=delta, repeat_delta=repeat_delta)
    report = runner.evaluate(*args)
    assert report["status"] == "parity_failed" and report["complete"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, 1, [1.0, 2.0]])
def test_invalid_native_output_has_no_success_record(tmp_path, monkeypatch, value):
    import numpy as np

    args = fixture(tmp_path, monkeypatch)
    fake_runtime(monkeypatch, [], [], output=np.asarray(value))
    report = runner.evaluate(*args)
    assert report["status"] == "incomplete" and report["successful"] == 0
    assert report["records"] == [] and report["new_native_inferences"] == 1


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["config"].update(streams=True),
        lambda p: p["config"].update(device="cpu"),
        lambda p: p["limits"].update(max_items=True),
        lambda p: p["shapes"].update(landscape=[1, 3, 680, 1024]),
        lambda p: p["items"][0].update(input_shape=[True, 3, 384, 512]),
        lambda p: p["items"][0].update(reference_score=True),
        lambda p: p["items"][-1].update(variant="landscape"),
        lambda p: p["items"][-1].update(reference_score=1.0),
        lambda p: p["items"][-1].update(expected_status="supported"),
        lambda p: p["items"][0].update(path="../escape.png"),
        lambda p: p["items"][0].update(source_kind="private_jpeg"),
        lambda p: p["items"][0].update(extra_key=True),
        lambda p: p["items"][-1].update(id=p["items"][0]["id"]),
        lambda p: p["preparation"].update(size=True),
        lambda p: p["graphs"]["landscape"]["models/landscape/musiq.bin"].update(size=True),
        lambda p: p["references"]["portrait"].update(path="references/landscape.json"),
        lambda p: p.update(unfrozen_config={}),
    ],
)
def test_malformed_or_aliased_protocol_rejected_before_any_model(tmp_path, monkeypatch, mutation):
    args = mutate_protocol(fixture(tmp_path, monkeypatch), mutation)
    calls = []
    fake_runtime(monkeypatch, calls, [])
    with pytest.raises((ValueError, TypeError)):
        runner.evaluate(*args)
    assert not calls and not args[-1].exists()


def test_preexport_phase_and_original_control_join(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch, phase="preexport")
    assert len(runner.validate_protocol(*args[:3], phase="preexport")["items"]) == 9
    with pytest.raises(ValueError, match="contract"):
        runner.validate_protocol(*args[:3], phase="evaluation")
    prep_path = args[0] / "preparation.json"
    prep = runner.read(prep_path)
    prep["items"][0]["original_id"] = "rewritten-control-id"
    runner.atomic(prep_path, prep)
    args = mutate_protocol(
        args,
        lambda p: p["preparation"].update(
            sha256=runner.sha(prep_path), size=prep_path.stat().st_size
        ),
    )
    with pytest.raises(ValueError, match="original reference join"):
        runner.validate_protocol(*args[:3], phase="preexport")


@pytest.mark.parametrize(
    "field,value",
    [
        ("score", True),
        ("torch_threads", True),
        ("fallback_used", True),
        ("input_shape", [1, 3, 1024, 682]),
        ("protocol_sha256", "f" * 64),
        ("identity", "f" * 64),
    ],
)
def test_native_reference_semantic_metadata_checked_even_with_recomputed_hash(
    tmp_path, monkeypatch, field, value
):
    args = fixture(tmp_path, monkeypatch)
    plan = runner.read(args[1])
    reference_path = args[0] / "references/control.json"
    reference = runner.read(reference_path)
    reference[field] = value
    reference["record_sha256"] = runner.native_record_hash(reference)
    runner.atomic(reference_path, reference)
    plan["references"]["control"].update(
        sha256=runner.sha(reference_path), size=reference_path.stat().st_size
    )
    runner.atomic(args[1], plan)
    with pytest.raises(ValueError, match="reference"):
        runner.validate_protocol(args[0], args[1], runner.sha(args[1]), phase="evaluation")


def test_native_hash_recipe_ignores_only_parent_observation_fields():
    record = {"score": 42.0, "record_sha256": "old", "elapsed_ms": 1.0, "peak_rss_bytes": 500}
    expected = runner.digest({"score": 42.0})
    assert runner.native_record_hash(record) == expected
    record.update(elapsed_ms=99.0, peak_rss_bytes=999, record_sha256="new")
    assert runner.native_record_hash(record) == expected
    record["score"] = 43.0
    assert runner.native_record_hash(record) != expected


def test_protocol_graph_input_and_preparation_drift_before_native(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls, [])
    with pytest.raises(ValueError, match="fingerprint"):
        runner.evaluate(args[0], args[1], "0" * 64, args[-1])
    graph = args[0] / "models/landscape/musiq.bin"
    graph.write_bytes(b"modified graph")
    with pytest.raises(ValueError, match="identity"):
        runner.evaluate(*args)
    assert not calls


def test_post_inference_asset_hash_drift_invalidates_complete_report(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []

    def corrupt_graph(count):
        if count == 6:
            (args[0] / "models/landscape/musiq.bin").write_bytes(b"drift")

    fake_runtime(monkeypatch, calls, [], on_call=corrupt_graph)
    report = runner.evaluate(*args)
    assert report["status"] == "incomplete" and not report["complete"]
    assert len(calls) == 6 and len(report["records"]) == 9
    assert "max_abs_error" not in report


def test_runtime_version_change_invalidates_all_cached_records(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    runtime = fake_runtime(monkeypatch, calls, [])
    first = runner.evaluate(*args)
    runtime.__version__ = "different-ov"
    second = runner.evaluate(*args)
    assert second["identity"] != first["identity"] and second["cache_reused"] == 0
    assert second["new_native_inferences"] == 6 and len(calls) == 12


def test_cached_symlink_is_unsafe_and_never_resumed(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls, [])
    first = runner.evaluate(*args)
    record = first["records"][0]
    cache = args[-1] / "predictions" / (runner.digest(record["id"]) + ".json")
    cache.unlink()
    cache.symlink_to(args[1])
    report = runner.evaluate(*args)
    assert report["status"] == "incomplete" and "symlink" in report["error"]
    assert report["new_native_inferences"] == 0


def test_resources_checked_after_final_asset_hashes(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    calls = []
    fake_runtime(monkeypatch, calls, [])
    original_sha = runner.sha
    final_hash_seen = []

    def observed_sha(path):
        value = original_sha(path)
        if len(calls) == 6 and Path(path) == args[0] / "models/portrait/musiq.bin":
            final_hash_seen.append(path)
        return value

    monkeypatch.setattr(runner, "sha", observed_sha)
    monkeypatch.setattr(
        runner, "peak_rss", lambda: runner.LIMITS["max_rss_bytes"] + 1 if final_hash_seen else 1
    )
    report = runner.evaluate(*args)
    assert final_hash_seen and report["status"] == "incomplete"
    assert "RSS resource bound" in report["error"] and len(calls) == 6


def test_input_size_and_decode_shape_preflight_includes_unsupported(tmp_path, monkeypatch):
    from PIL import Image

    args = fixture(tmp_path, monkeypatch)
    plan = runner.read(args[1])
    unsupported = plan["items"][-1]
    Image.new("RGB", (32, 32)).save(args[0] / unsupported["path"])
    unsupported["input_sha256"] = runner.sha(args[0] / unsupported["path"])
    prep_path = args[0] / "preparation.json"
    prep = runner.read(prep_path)
    prep["items"][-1]["input_sha256"] = unsupported["input_sha256"]
    runner.atomic(prep_path, prep)
    plan["preparation"].update(size=prep_path.stat().st_size, sha256=runner.sha(prep_path))
    runner.atomic(args[1], plan)
    with pytest.raises(ValueError, match="decoded input shape"):
        runner.validate_protocol(args[0], args[1], runner.sha(args[1]), phase="evaluation")


@pytest.mark.parametrize("scores", [[True, False], [float("nan"), 0], [0, float("inf")], [0]])
def test_invalid_success_cache_cannot_resume(scores):
    item = {
        "id": "x",
        "input_sha256": "a" * 64,
        "input_shape": runner.SHAPES["control"],
        "expected_status": "supported",
        "variant": "control",
        "reference_score": 0.0,
    }
    record = {
        **runner.record_base("i", item),
        "status": "ok",
        "variant": "control",
        "reference_score": 0.0,
        "execution_devices": ["CPU"],
        "fallback_used": False,
        "inference_precision": "f32",
        "threads": 4,
        "streams": 1,
        "scores": scores,
        "elapsed_seconds": 0.1,
    }
    try:
        record["record_sha256"] = runner.digest(record)
    except ValueError:
        record["record_sha256"] = "invalid"
    assert not runner.valid_record(record, "i", item)


def test_native_token_metadata_counts_padding_and_binary_validity():
    import numpy as np

    class Scalar:
        def __init__(self, value):
            self.value = value

        def item(self):
            return self.value

    class Mask:
        def __init__(self, array):
            self.array = array

        def __eq__(self, value):
            return Mask(self.array == value)

        def __or__(self, other):
            return Mask(self.array | other.array)

        def all(self):
            return Scalar(bool(self.array.all()))

        def sum(self):
            return Scalar(self.array.sum())

        def numel(self):
            return self.array.size

    class Tokens:
        shape = [1, 897, 3075]

        def __init__(self, mask):
            self.mask = mask

        def __getitem__(self, item):
            assert item == (slice(None), slice(None), -1)
            return Mask(self.mask)

    mask = np.concatenate([np.ones(835), np.zeros(62)])[None]
    assert runner.token_metadata(Tokens(mask)) == runner.TOKEN_METADATA["landscape"]
    mask[0, 0] = 0.5
    with pytest.raises(ValueError, match="binary"):
        runner.token_metadata(Tokens(mask))


def test_owned_cache_offline_restore_home_and_tmp(tmp_path, monkeypatch):
    import os
    import socket
    import tempfile

    home, sock = os.environ.get("HOME"), socket.socket
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "original-tmp"))
    prior = tempfile.tempdir
    with runner.owned_cache(tmp_path), runner.offline():
        assert os.environ.get("HOME") == home
        assert tempfile.gettempdir() == str(tmp_path / "tmp")
        with pytest.raises(RuntimeError, match="network forbidden"):
            socket.socket()
    assert os.environ.get("HOME") == home and socket.socket is sock and tempfile.tempdir == prior
