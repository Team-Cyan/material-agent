from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "musiq_shared_core", Path(__file__).parents[1] / "scripts/benchmark_musiq_shared_core.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def tokens(variant):
    array = np.zeros(runner.TOKEN_METADATA[variant]["shape"], dtype=np.float32)
    array[0, : runner.TOKEN_METADATA[variant]["valid"], -1] = 1
    return array


class Graph:
    def __init__(self, value):
        self.value, self.calls = value, []
        self.properties = {
            "EXECUTION_DEVICES": ["CPU"],
            "INFERENCE_PRECISION_HINT": "<Type: 'float32'>",
            "INFERENCE_NUM_THREADS": 4,
            "NUM_STREAMS": 1,
        }

    def __call__(self, inputs):
        self.calls.append(inputs[0])
        return {0: self.value(inputs[0]) if callable(self.value) else self.value}

    def output(self):
        return 0

    def get_property(self, key):
        return self.properties[key]


@pytest.mark.parametrize(
    "key,value",
    [
        ("EXECUTION_DEVICES", ["GPU"]),
        ("INFERENCE_PRECISION_HINT", "<Type: 'float16'>"),
        ("INFERENCE_NUM_THREADS", True),
        ("INFERENCE_NUM_THREADS", 8),
        ("NUM_STREAMS", True),
        ("NUM_STREAMS", 2),
    ],
)
def test_actual_cpu_readback_fails_closed(key, value):
    graph = Graph(np.array([1.0]))
    graph.properties[key] = value
    with pytest.raises(ValueError, match="readback"):
        runner.execution_readback(graph)


def test_tokens_metadata_exact_and_pixels_absolute_only():
    expected = tokens("control")
    actual = expected.copy()
    actual[0, 0, 0] = np.float32(0.0000005)
    assert runner.compare_tokens(actual, expected, "control")["rtol"] == 0
    actual[0, 0, -3] += 1
    with pytest.raises(ValueError, match="metadata"):
        runner.compare_tokens(actual, expected, "control")
    actual = expected.copy()
    actual[0, 0, 0] = np.float32(0.000002)
    with pytest.raises(ValueError, match="pixel parity"):
        runner.compare_tokens(actual, expected, "control")
    expected[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        runner.compare_tokens(expected, expected, "control")


def test_token_loader_rejects_corrupt_identity_and_pickle(tmp_path):
    path = tmp_path / "tokens/control.npy"
    path.parent.mkdir()
    np.save(path, tokens("control"), allow_pickle=False)
    asset = {
        "path": "tokens/control.npy",
        "sha256": runner.sha(path),
        "size": path.stat().st_size,
        "shape": [1, 385, 3075],
        "dtype": "float32",
    }
    assert runner.load_tokens(tmp_path, "control", asset).shape == (1, 385, 3075)
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="size"):
        runner.load_tokens(tmp_path, "control", asset)
    np.save(path, np.asarray([{"arbitrary": True}], dtype=object))
    asset.update(size=path.stat().st_size, sha256=runner.sha(path))
    with pytest.raises(ValueError, match="allow_pickle"):
        runner.load_tokens(tmp_path, "control", asset)
    asset["path"] = "../control.npy"
    with pytest.raises(ValueError, match="path"):
        runner.load_tokens(tmp_path, "control", asset)


def test_output_must_be_fresh_and_disjoint(tmp_path):
    root, old = tmp_path / "root", tmp_path / "old"
    root.mkdir()
    old.mkdir()
    protocol = root / "protocol.json"
    protocol.write_text("{}")
    for output in (root / "report", old / "report", tmp_path):
        with pytest.raises(ValueError, match="separate"):
            runner.fresh_output(root, old, protocol, output)
    output = tmp_path / "report"
    output.mkdir()
    (output / "corrupt-report.json").write_bytes(b"\xff")
    with pytest.raises(ValueError, match="cannot resume"):
        runner.fresh_output(root, old, protocol, output)
    linked = tmp_path / "linked"
    linked.symlink_to(root)
    with pytest.raises(ValueError, match="symlink"):
        runner.fresh_output(root, old, protocol, linked / "report")


@pytest.mark.parametrize("variant", ["whole", "shared"])
def test_measurement_makes_48_real_calls_and_40_timings(variant, monkeypatch):
    refs = {key: {"reference_score": float(i + 1)} for i, key in enumerate(runner.SHAPES)}
    arrays = {key: np.array([i + 1], dtype=np.float32) for i, key in enumerate(runner.SHAPES)}
    compiled = {key: Graph(lambda array: array.copy()) for key in runner.SHAPES}
    if variant == "shared":
        compiled["core"] = Graph(lambda array: array.copy())
    checkpoints = []
    monkeypatch.setattr(runner.native, "check_resources", lambda *args: None)
    result = runner.measurement(
        compiled,
        arrays,
        refs,
        variant,
        0,
        lambda calls, cycle: checkpoints.append((calls.copy(), cycle)),
    )
    assert result["calls"]["logical"] == 48
    assert len(result["measured_latency_ms"]) == 40
    assert [len(result["scores"][k]) for k in runner.SHAPES] == [24, 12, 12]
    assert len(checkpoints) == 108
    assert len(result["cycles"]) == 12
    assert [len(compiled[k].calls) for k in runner.SHAPES] == [24, 12, 12]
    if variant == "shared":
        assert len(compiled["core"].calls) == 48
        assert all(array is not arrays[k] for k in arrays for array in compiled["core"].calls)
    assert all(cycle["growth_bytes"] >= 0 for cycle in result["cycles"])


@pytest.mark.parametrize("bad", [np.array([np.nan]), np.array([99.0])])
def test_bad_raw_outputs_never_complete_measurement(bad, monkeypatch):
    monkeypatch.setattr(runner.native, "check_resources", lambda *args: None)
    graphs = {key: Graph(bad) for key in runner.SHAPES}
    refs = {key: {"reference_score": 1.0} for key in runner.SHAPES}
    with pytest.raises(ValueError, match="finite|parity"):
        runner.measurement(graphs, refs, refs, "whole", 0, lambda *args: None)


def test_resource_and_source_guards(monkeypatch):
    monkeypatch.setattr(runner.native.time, "monotonic", lambda: 901)
    with pytest.raises(ValueError, match="elapsed"):
        runner.native.check_resources(0, runner.LIMITS)
    monkeypatch.setattr(runner.native.time, "monotonic", lambda: 1)
    monkeypatch.setattr(runner.native, "peak_rss", lambda: 2500000001)
    with pytest.raises(ValueError, match="RSS"):
        runner.native.check_resources(0, runner.LIMITS)
    expected = runner.frozen_sources()
    expected[Path(runner.__file__).name] = "0" * 64
    with pytest.raises(ValueError, match="source changed"):
        runner.verify_sources(expected)


class Tensor(np.ndarray):
    def bool(self):
        return self.astype(bool)

    def permute(self, *axes):
        return self.transpose(*axes)

    def mean(self, *, dim):
        return np.asarray(self).mean(axis=dim).view(Tensor)


class Module:
    def eval(self):
        return self

    def __call__(self, *args):
        return self.forward(*args)


def test_core_reuses_eval_submodules_in_original_order_without_net_forward():
    calls = []

    def layer(name):
        def execute(value, *args):
            calls.append(name)
            if name == "transformer_encoder":
                assert len(args) == 3 and args[-1].dtype == np.bool_
            if name == "head":
                return np.ones((value.shape[0], 1), dtype=np.float32).view(Tensor)
            return value

        return execute

    net = SimpleNamespace(
        training=False,
        patch_size=32,
        data_preprocess_opts={},
        forward=lambda *_: pytest.fail("net.forward must never receive tokens"),
    )
    for name in (
        "conv_root",
        "gn_root",
        "root_pool",
        "block1",
        "embedding",
        "transformer_encoder",
        "head",
    ):
        setattr(net, name, layer(name))
    net.head.out_features = 1
    torch = SimpleNamespace(nn=SimpleNamespace(Module=Module))
    util = SimpleNamespace(get_multiscale_patches=lambda image, **opts: image)
    prep, core = runner.make_modules(torch, net, util, lambda q: q)
    assert core.conv_root is net.conv_root
    assert np.array_equal(prep(np.array([0.0, 0.5, 1.0])), [-1, 0, 1])
    for variant in runner.SHAPES:
        output = core(tokens(variant).view(Tensor))
        assert output.shape == (1, 1)
    assert (
        calls
        == [
            "conv_root",
            "gn_root",
            "root_pool",
            "block1",
            "embedding",
            "transformer_encoder",
            "head",
        ]
        * 3
    )
    net.training = True
    with pytest.raises(ValueError, match="eval"):
        runner.make_modules(torch, net, util, lambda q: q)


@pytest.mark.parametrize("variant", ["whole", "shared"])
def test_evaluate_fresh_fake_native_calls_and_unsupported_no_dispatch(
    tmp_path, monkeypatch, variant
):
    root, old = tmp_path / "root", tmp_path / "old"
    root.mkdir()
    old.mkdir()
    items = [
        {
            "id": key,
            "variant": key,
            "path": f"images/{key}.png",
            "input_sha256": "a" * 64,
            "input_shape": shape,
            "expected_status": "supported",
            "reference_score": 1.0,
        }
        for key, shape in runner.SHAPES.items()
    ]
    items += [
        {
            "id": f"unsupported-{i}",
            "variant": None,
            "path": f"images/u{i}.png",
            "input_sha256": "b" * 64,
            "input_shape": [1, 3, 10, 10],
            "expected_status": "unsupported_shape",
            "reference_score": None,
        }
        for i in range(6)
    ]
    p = {
        "items": items,
        "graphs": {},
        "token_references": {k: {} for k in runner.SHAPES},
        "references": {},
        "preparation": {},
        "structural_references": {},
    }
    monkeypatch.setattr(runner, "validate_protocol", lambda *a, **kw: (p, {"graphs": {}}))
    monkeypatch.setattr(
        runner.native, "image_array", lambda *a, **kw: np.array([1.0], dtype=np.float32)
    )
    monkeypatch.setattr(runner.native, "runtime_versions", lambda ov: {"openvino": "fake"})
    monkeypatch.setattr(runner.native, "check_resources", lambda *args: None)
    monkeypatch.setattr(runner, "load_tokens", lambda root, k, asset: tokens(k))

    def structural(compiled, root, asset, checks, state, checkpoint, started, limits):
        for bucket in runner.SHAPES:
            for probe in runner.PROBES:
                state["attempted"] += 1
                checks[bucket + "__" + probe] = {"variant": bucket, "probe": probe}
                actual = runner.run_graph(compiled[bucket], np.array([1.0]))
                runner.compare_tokens(actual, tokens(bucket), bucket, checks[bucket + "__" + probe])
                state["succeeded"] += 1
                checkpoint()

    monkeypatch.setattr(runner, "structural_check", structural)

    compile_calls, graphs = [], {}

    class Core:
        def set_property(self, settings):
            assert settings == {"CACHE_DIR": ""}

        def get_property(self, key):
            return ""

    def compile_model(core, root, kind):
        compile_calls.append(kind)
        bucket = kind.split("/")[-1]
        graph = Graph(
            tokens(bucket)
            if kind.startswith("preprocess/")
            else np.array([[1.0]], dtype=np.float32)
        )
        graphs[kind] = graph
        return graph

    monkeypatch.setitem(sys.modules, "openvino", SimpleNamespace(Core=Core))
    monkeypatch.setattr(runner, "compile_graph", compile_model)
    monkeypatch.setattr(runner.native, "compiled_graph", compile_model)
    output = tmp_path / "report"
    checkpoint_history = []
    original_atomic = runner.atomic

    def atomic_capture(path, value):
        if path.name == "checkpoint.json":
            checkpoint_history.append(json.loads(json.dumps(value)))
        original_atomic(path, value)

    monkeypatch.setattr(runner, "atomic", atomic_capture)
    report = runner.evaluate(variant, 1, root, old, root / "protocol.json", "a" * 64, output)
    assert report["status"] == "raw_parity_pass"
    expected_validation = {
        "attempted": 18 if variant == "shared" else 0,
        "succeeded": 18 if variant == "shared" else 0,
    }
    measuring = [entry for entry in checkpoint_history if entry["status"] == "measuring"]
    assert measuring
    for entry in [*measuring, checkpoint_history[-1]]:
        assert entry["structural_validation"] == expected_validation
        assert entry["structural_checks"] == report["structural_checks"]
        assert entry["token_parity"] == report["token_parity"]
        assert entry["token_validation"] == {
            "attempted": 3 if variant == "shared" else 0,
            "succeeded": 3 if variant == "shared" else 0,
        }
    assert report["total_native_calls"]["preprocess"] == (69 if variant == "shared" else 0)
    assert report["scheduled_native_calls"]["preprocess"] == (51 if variant == "shared" else 0)
    assert report["graph_calls"] == {
        "whole": 48 if variant == "whole" else 0,
        "preprocess": 51 if variant == "shared" else 0,
        "core": 48 if variant == "shared" else 0,
    }
    assert report["structural_validation_calls"] == (18 if variant == "shared" else 0)
    assert report["total_actual_graph_calls"]["preprocess"] == (69 if variant == "shared" else 0)
    assert len(compile_calls) == (3 if variant == "whole" else 4)
    assert all("unsupported" not in name for name in compile_calls)
    unsupported = [r for r in report["records"] if r["status"] == "unsupported_shape"]
    assert len(unsupported) == 6
    assert all(
        not r["graph_selected"] and "scores" not in r and r["native_calls"] == 0
        for r in unsupported
    )
    assert len(list((output / "predictions").glob("*.json"))) == 9
    assert len(report["measured_latency_ms"]) == 40
    saved = json.loads((output / "report.json").read_text())
    assert saved["complete"] is True and saved["prediction_cache_reused"] == 0
    with pytest.raises(ValueError, match="cannot resume"):
        runner.evaluate(variant, 1, root, old, root / "protocol.json", "a" * 64, output)
    assert len(compile_calls) == (3 if variant == "whole" else 4)


def test_failure_after_first_call_retains_attempts_completed_scores_and_timings(monkeypatch):
    monkeypatch.setattr(runner.native, "check_resources", lambda *args: None)
    graphs = {key: Graph(np.array([1.0], dtype=np.float32)) for key in runner.SHAPES}
    graphs["landscape"] = Graph(np.array([99.0], dtype=np.float32))
    refs = {key: {"reference_score": 1.0} for key in runner.SHAPES}
    calls = {"logical": 0, "preprocess": 0, "core": 0, "whole": 0}
    progress, saved = {}, []
    with pytest.raises(ValueError, match="parity"):
        runner.measurement(
            graphs,
            refs,
            refs,
            "whole",
            0,
            lambda c, cycle: saved.append((c.copy(), cycle)),
            calls,
            progress,
        )
    assert calls["logical_attempted"] == 2
    assert calls["logical"] == 1 and calls["whole"] == 2
    assert progress["scores"]["control"] == [1.0]
    assert progress["scores"]["landscape"] == []
    assert saved[-1][0]["logical_attempted"] == 2
    assert saved[-1][0]["logical"] == 1


class Dimension:
    def __init__(self, minimum, maximum=None):
        self.minimum, self.maximum = minimum, minimum if maximum is None else maximum

    def get_length(self):
        assert self.minimum == self.maximum
        return self.minimum

    def get_min_length(self):
        return self.minimum

    def get_max_length(self):
        return self.maximum


class Partial(list):
    @property
    def rank(self):
        return Dimension(len(self))


@pytest.mark.parametrize(
    "kind", ["preprocess/control", "preprocess/landscape", "preprocess/portrait", "core"]
)
def test_fake_openvino_shape_and_config_validation(kind, tmp_path):
    bucket = kind.split("/")[-1]
    input_port = SimpleNamespace(get_element_type=lambda: "<Type: 'float32'>")
    output_port = SimpleNamespace(get_element_type=lambda: "<Type: 'float32'>")
    if kind == "core":
        input_port.partial_shape = Partial([Dimension(1), Dimension(385, 897), Dimension(3075)])
        output_port.shape = [1, 1]
    else:
        input_port.shape = runner.SHAPES[bucket].copy()
        output_port.shape = runner.TOKEN_METADATA[bucket]["shape"].copy()
    ops = []
    model = SimpleNamespace(
        inputs=[input_port],
        outputs=[output_port],
        input=lambda: input_port,
        output=lambda: output_port,
        get_ops=lambda: ops,
    )
    calls = []

    class Core:
        def read_model(self, path):
            assert path == tmp_path / f"models/{kind}/musiq.xml"
            return model

        def compile_model(self, model, device, config):
            calls.append((device, config))
            return Graph(np.array([1.0]))

    runner.compile_graph(Core(), tmp_path, kind)
    assert calls == [
        (
            "CPU",
            {
                "INFERENCE_NUM_THREADS": 4,
                "NUM_STREAMS": 1,
                "PERFORMANCE_HINT": "LATENCY",
                "INFERENCE_PRECISION_HINT": "f32",
                "CACHE_DIR": "",
            },
        )
    ]
    if kind == "core":
        input_port.partial_shape[1] = Dimension(384, 898)
    else:
        output_port.shape[1] += 1
    with pytest.raises(ValueError, match="shape"):
        runner.compile_graph(Core(), tmp_path, kind)
    assert len(calls) == 1
    ops.append(
        SimpleNamespace(
            get_type_name=lambda: "Constant", get_output_element_type=lambda _: "<Type: 'float16'>"
        )
    )
    with pytest.raises(ValueError, match="FP32 storage"):
        runner.compile_graph(Core(), tmp_path, kind)
    assert len(calls) == 1


@pytest.mark.parametrize("axis", [2, 3])
def test_sparse_basis_is_native_f32_exact_support_without_epsilon_or_renormalization(axis):
    matrix = np.array([[-0.125, 0, 1.125, 0], [0, 1e-12, 0.75, 0.25]], dtype=np.float32)
    seen = []

    class Basis:
        def reshape(self, *shape):
            seen.append(shape)
            return self

    class Result:
        device, dtype = "cpu", "f32"

        def numpy(self):
            return matrix.T[:, None, None, :] if axis == 3 else matrix.T[:, None, :, None]

    def interpolate(basis, size, **kwargs):
        assert size == ((1, 2) if axis == 3 else (2, 1))
        assert kwargs == {"mode": "bicubic", "align_corners": False, "antialias": False}
        return Result()

    from contextlib import nullcontext

    fake = SimpleNamespace(
        eye=lambda source, **kwargs: Basis(),
        float32="f32",
        inference_mode=nullcontext,
        nn=SimpleNamespace(functional=SimpleNamespace(interpolate=interpolate)),
    )
    indices, weights, evidence = runner.sparse_basis(fake, 4, 2, axis=axis)
    assert seen == [(4, 1, 1, 4) if axis == 3 else (4, 1, 4, 1)]
    assert indices[:, 0].tolist() == [0, 2, 0, 0]
    assert weights[0, 1] == np.float32(1e-12)
    assert evidence["max_support"] == 3
    assert not evidence["coefficient_pruning"] and not evidence["renormalization"]
    matrix = np.ones((2, 5), dtype=np.float32)
    with pytest.raises(ValueError, match="invalid native basis"):
        runner.sparse_basis(fake, 4, 2, axis=axis)


def test_structural_probes_are_bounded_deterministic_and_photo_independent():
    for probe in runner.PROBES:
        left = runner.structural_image("control", probe)
        right = runner.structural_image("control", probe)
        assert np.array_equal(left, right)
        assert left.shape == (1, 3, 384, 512) and left.dtype == np.float32
        assert left.min() >= 0 and left.max() <= 1
    with pytest.raises(ValueError, match="unknown"):
        runner.structural_image("control", "photo-tuned")


def structural_archive(tmp_path, monkeypatch, *, bad_dtype=False, extra=False, codec=None):
    import zipfile
    import io

    monkeypatch.setattr(
        runner,
        "TOKEN_METADATA",
        {variant: {"shape": [1, 2, 3075], "valid": 1} for variant in runner.SHAPES},
    )
    path = tmp_path / "structural-references.npz"
    with zipfile.ZipFile(
        path, "w", compression=zipfile.ZIP_LZMA if codec is None else codec
    ) as archive:
        for key in sorted(runner.structural_keys()):
            array = np.zeros((1, 2, 3075), dtype=np.float64 if bad_dtype else np.float32)
            array[0, 0, -1] = 1
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, array, allow_pickle=False)
            archive.writestr(key + ".npy", buffer.getvalue())
        if extra:
            archive.writestr("../evil.npy", b"not a numpy array")
    return {"path": path.name, "size": path.stat().st_size, "sha256": runner.sha(path)}


def test_structural_archive_headers_validated_before_expansion(tmp_path, monkeypatch):
    asset = structural_archive(tmp_path, monkeypatch)
    assert runner.validate_structural_asset(tmp_path, asset).name == "structural-references.npz"
    asset = structural_archive(tmp_path, monkeypatch, bad_dtype=True)
    with pytest.raises(ValueError, match="header"):
        runner.validate_structural_asset(tmp_path, asset)
    asset = structural_archive(tmp_path, monkeypatch, extra=True)
    with pytest.raises(ValueError, match="entries"):
        runner.validate_structural_asset(tmp_path, asset)


def test_structural_archive_rejects_unapproved_lossless_codec(tmp_path, monkeypatch):
    import zipfile

    asset = structural_archive(tmp_path, monkeypatch, codec=zipfile.ZIP_DEFLATED)
    with pytest.raises(ValueError, match="entries"):
        runner.validate_structural_asset(tmp_path, asset)


def test_structural_failure_persists_attempt_and_detailed_pixel_error(tmp_path, monkeypatch):
    asset = structural_archive(tmp_path, monkeypatch)
    actual = np.zeros((1, 2, 3075), dtype=np.float32)
    actual[0, 0, -1] = 1
    actual[0, 0, 0] = np.float32(0.01)
    graphs = {key: Graph(actual) for key in runner.SHAPES}
    checks, state, saved = {}, {"attempted": 0, "succeeded": 0}, []
    monkeypatch.setattr(runner.native, "check_resources", lambda *args: None)
    with pytest.raises(ValueError, match="pixel parity"):
        runner.structural_check(
            graphs,
            tmp_path,
            asset,
            checks,
            state,
            lambda: saved.append(json.loads(json.dumps([state, checks]))),
            0,
            {},
        )
    assert state == {"attempted": 1, "succeeded": 0}
    evidence = checks["control__constant"]
    assert evidence["passed"] is False and evidence["pixel_count_above_gate"] == 1
    assert evidence["pixel_max_abs_error"] > 1e-6 and evidence["pixel_mean_abs_error"] > 0
    assert saved[-1][1]["control__constant"]["pixel_count_above_gate"] == 1


def test_lowering_replaces_only_two_cubic_nodes_and_preserves_consumers(monkeypatch):
    ov = pytest.importorskip("openvino")
    from openvino import opset11 as op

    value = op.parameter([1, 3, 384, 512], np.float32)
    cubic, results = [], []
    for sizes in ([168, 224], [288, 384]):
        node = op.interpolate(
            value,
            np.array(sizes, dtype=np.int32),
            "cubic",
            "sizes",
            pads_begin=[0, 0, 0, 0],
            pads_end=[0, 0, 0, 0],
            coordinate_transformation_mode="pytorch_half_pixel",
            nearest_mode="floor",
            antialias=False,
            cube_coeff=-0.75,
            axes=np.array([2, 3], dtype=np.int32),
        )
        cubic.append(node)
        results.append(op.result(node))
    nearest = op.interpolate(
        value,
        np.array([2, 3], dtype=np.int32),
        "nearest",
        "sizes",
        axes=np.array([2, 3], dtype=np.int32),
    )
    results.append(op.result(nearest))
    model = ov.Model(results, [value])

    def basis(torch, source, destination, *, axis):
        indices = np.zeros((4, destination), dtype=np.int64)
        weights = np.zeros((4, destination), dtype=np.float32)
        weights[0] = 1
        return indices, weights, {"source": source, "destination": destination}

    monkeypatch.setattr(runner, "sparse_basis", basis)
    evidence = runner.lower_preprocess(model, None, "control")
    assert evidence["replaced_cubic_nodes"] == 2 and evidence["nearest_unchanged"]
    assert [n for n in model.get_ordered_ops() if n.get_type_name() == "Interpolate"] == [nearest]
    assert not any(n.get_type_name() == "MatMul" for n in model.get_ordered_ops())
    assert len([n for n in model.get_ordered_ops() if n.get_type_name() == "Gather"]) == 16
    for result, old in zip(results, cubic, strict=False):
        assert result.input_value(0).get_node().get_friendly_name() == old.get_friendly_name()


def test_protocol_v2_and_lowering_are_frozen():
    assert runner.SCHEMA == "material-agent.musiq-shared-core.v2"
    assert runner.PREPROCESSING_LOWERING == {"method": "native-f32-basis-sparse-cubic-v1"}
    assert runner.EXPORT_GATE["token_pixel_max_abs_error"] == 1e-6
    assert runner.SCHEDULE["logical_calls"] == 48 and runner.SCHEDULE["timed_calls"] == 40
