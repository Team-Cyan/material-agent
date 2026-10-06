#!/usr/bin/env python3
"""Fresh-process, bounded MUSIQ shared-token-core experiment; no policy admission."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
import statistics
import zipfile
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
NATIVE_SOURCE = Path(__file__).with_name("benchmark_musiq_native_shapes.py")
HELPER_SOURCE = Path(__file__).with_name("benchmark_musiq_openvino.py")
HELPER_SHA = "31da83e4700be28e6a6baa127cc50004530a813731dc770215e3d40067c248d7"
NATIVE_SHA = "11c959d0f3b150bd747bcdf2904330d71eb9fe8cdab3cb2451332787e3f5cc34"
BASELINE_SHA = "dffa681fb4612f4a343ba50bbc94e062641fd145c14821dc2be9d99533a373da"


def file_sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            result.update(block)
    return result.hexdigest()


if file_sha(NATIVE_SOURCE) != NATIVE_SHA or file_sha(HELPER_SOURCE) != HELPER_SHA:
    raise ValueError("immutable native helper source mismatch")
SPEC = importlib.util.spec_from_file_location("shared_core_native_helpers", NATIVE_SOURCE)
native = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(native)
sha, digest, clean, read, atomic = (
    native.sha,
    native.digest,
    native.clean,
    native.read,
    native.atomic,
)
relative, bounded_asset = native.relative, native.bounded_asset
SHAPES, CONFIG = native.SHAPES, native.CONFIG
MODEL_SHA, MODEL_SIZE = native.MODEL_SHA, native.MODEL_SIZE
TOKEN_METADATA = native.TOKEN_METADATA
SCHEMA = "material-agent.musiq-shared-core.v2"
PREPROCESSING_LOWERING = {"method": "native-f32-basis-sparse-cubic-v1"}
PROBES = ("constant", "impulse", "ramp", "alternating-sign", "edge", "corner")
STRUCTURAL_COMPRESSED_MAX = 4000000
STRUCTURAL_EXPANDED_MAX = 200000000
LIMITS = {
    "max_abs_error": 0.001,
    "max_decode_pixels": 4194304,
    "max_graph_bytes": 150000000,
    "max_input_bytes": 16777216,
    "max_items": 9,
    "max_package_bytes": 160000000,
    "max_repeat_error": 0.000001,
    "max_rss_bytes": 2500000000,
    "max_seconds": 900,
    "max_tokens": 897,
    "max_total_graph_bytes": 150000000,
}
EXPORT_GATE = {
    "eager_max_abs_error": 0.00001,
    "fp16_compression": False,
    "max_rss_bytes": 2500000000,
    "max_seconds": 300,
    "token_pixel_max_abs_error": 0.000001,
    "token_pixel_rtol": 0,
}
SCHEDULE = {
    "additional_shared_token_validation_calls": 3,
    "core_token_lengths": [385, 897],
    "logical_calls": 48,
    "measure_cycles": 10,
    "order": [
        ["whole", 1],
        ["shared", 1],
        ["shared", 2],
        ["whole", 2],
        ["whole", 3],
        ["shared", 3],
    ],
    "prediction_cache": False,
    "rounds": 3,
    "sequence": ["control", "landscape", "portrait", "control"],
    "timed_calls": 40,
    "timing_scope": "prepared arrays; whole graph versus preprocess+token bridge+shared core",
    "warm_cycles": 2,
}
ADMISSION = {
    "complete_paired_rounds": 3,
    "max_package_bytes": 160000000,
    "max_total_graph_bytes": 150000000,
    "median_peak_rss_max_ratio": 0.85,
    "median_warm_latency_max_ratio": 1.10,
}


def frozen_sources():
    sources = [Path(__file__), NATIVE_SOURCE, HELPER_SOURCE]
    if sha(NATIVE_SOURCE) != NATIVE_SHA or sha(HELPER_SOURCE) != HELPER_SHA:
        raise ValueError("immutable native helper source mismatch")
    return {source.name: sha(clean(source)) for source in sources}


def verify_sources(expected):
    if not native.exact(frozen_sources(), expected):
        raise ValueError("runner/helper source changed during experiment")


def fresh_output(root, baseline_root, protocol, output, protected=()):
    output = native.output_dir(root, protocol, output, [baseline_root, NATIVE_SOURCE, *protected])
    if any(output.iterdir()):
        raise ValueError("fresh process requires empty output; predictions/reports cannot resume")
    return output


def make_modules(torch, net, util, dist_to_mos):
    """Reuse native eval submodules; never feed tokens through MUSIQ.forward."""
    if net.training or net.patch_size != 32 or net.head.out_features != 1:
        raise ValueError("native eval single-output MUSIQ required")

    class Preprocess(torch.nn.Module):
        def forward(self, image):
            return util.get_multiscale_patches((image - 0.5) * 2, **net.data_preprocess_opts)

    class TokenCore(torch.nn.Module):
        def __init__(self):
            super().__init__()
            for name in (
                "conv_root",
                "gn_root",
                "root_pool",
                "block1",
                "embedding",
                "transformer_encoder",
                "head",
            ):
                setattr(self, name, getattr(net, name))

        def forward(self, tokens):
            b, seq_len, dim = tokens.shape
            inputs_spatial_positions = tokens[:, :, -3]
            inputs_scale_positions = tokens[:, :, -2]
            inputs_masks = tokens[:, :, -1].bool()
            x = tokens[:, :, :-3]
            x = x.reshape(-1, 3, 32, 32)
            x = self.conv_root(x)
            x = self.gn_root(x)
            x = self.root_pool(x)
            x = self.block1(x)
            x = x.permute(0, 2, 3, 1)
            x = x.reshape(b, seq_len, -1)
            x = self.embedding(x)
            x = self.transformer_encoder(
                x, inputs_spatial_positions, inputs_scale_positions, inputs_masks
            )
            q = self.head(x[:, 0])
            q = q.reshape(b, 1, -1)
            q = q.mean(dim=1)
            return dist_to_mos(q)

    return Preprocess().eval(), TokenCore().eval()


def fixed_resize(torch, variant):
    dimensions = native.resize_dimensions(*SHAPES[variant][2:])

    def resize(image, h, w, longer_side_length):
        if longer_side_length not in (224, 384):
            raise ValueError("unexpected native MUSIQ scale")
        height, width = dimensions[str(longer_side_length)]
        return (
            torch.nn.functional.interpolate(
                image, (height, width), mode="bicubic", align_corners=False
            ),
            height,
            width,
        )

    return resize


def structural_image(variant, probe):
    """Frozen, photo-independent RGB [0,1] probes; normalization remains native."""
    import numpy as np

    height, width = SHAPES[variant][2:]
    plane = np.full((height, width), np.float32(0.5), dtype=np.float32)
    if probe == "constant":
        plane.fill(np.float32(0.75))
    elif probe == "impulse":
        plane[height // 2, width // 2] = 1
    elif probe == "ramp":
        x = np.arange(width, dtype=np.float32) / np.float32(width - 1)
        y = np.arange(height, dtype=np.float32) / np.float32(height - 1)
        plane = (x[None, :] + y[:, None]) * np.float32(0.5)
    elif probe == "alternating-sign":
        plane = ((np.arange(height)[:, None] + np.arange(width)[None, :]) % 2).astype(np.float32)
    elif probe == "edge":
        plane[:, : width // 2] = 0
        plane[:, width // 2 :] = 1
    elif probe == "corner":
        plane[[0, 0, height - 1, height - 1], [0, width - 1, 0, width - 1]] = 1
    else:
        raise ValueError("unknown frozen structural probe")
    return np.ascontiguousarray(np.broadcast_to(plane, SHAPES[variant]).copy())


def sparse_basis(torch, source, destination, *, axis=3):
    """Extract exact native f32 unit-basis coefficients; no image-dependent tuning."""
    import numpy as np

    if (
        not native.integer(source)
        or not native.integer(destination)
        or max(source, destination) > 1024
    ):
        raise ValueError("bounded static native basis dimensions required")
    if axis not in (2, 3):
        raise ValueError("native spatial basis axis must be 2 or 3")
    shape = (source, 1, 1, source) if axis == 3 else (source, 1, source, 1)
    size = (1, destination) if axis == 3 else (destination, 1)
    basis = torch.eye(source, dtype=torch.float32, device="cpu").reshape(*shape)
    with torch.inference_mode():
        resized = torch.nn.functional.interpolate(
            basis, size, mode="bicubic", align_corners=False, antialias=False
        )
    if str(resized.device) != "cpu" or resized.dtype != torch.float32:
        raise ValueError("native float32 CPU basis required")
    array = resized.numpy()
    matrix = (array[:, 0, 0, :] if axis == 3 else array[:, 0, :, 0]).T
    if matrix.shape != (destination, source) or not np.isfinite(matrix).all():
        raise ValueError("invalid native basis output")
    indices = np.zeros((4, destination), dtype=np.int64)
    weights = np.zeros((4, destination), dtype=np.float32)
    counts = []
    for row, coefficients in enumerate(matrix):
        nonzero = np.flatnonzero(coefficients != 0)
        if len(nonzero) > 4 or len(nonzero) == 0:
            raise ValueError("native cubic basis must have one to four exact nonzero coefficients")
        indices[: len(nonzero), row] = nonzero
        weights[: len(nonzero), row] = coefficients[nonzero]
        counts.append(len(nonzero))
    evidence = {
        "source": source,
        "destination": destination,
        "axis": axis,
        "dtype": "float32",
        "index_dtype": "int64",
        "indices_sha256": hashlib.sha256(indices.tobytes()).hexdigest(),
        "weights_sha256": hashlib.sha256(weights.tobytes()).hexdigest(),
        "basis_sha256": hashlib.sha256(matrix.tobytes()).hexdigest(),
        "min_support": min(counts),
        "max_support": max(counts),
        "support_order": "ascending",
        "coefficient_pruning": False,
        "renormalization": False,
        "clipping": False,
    }
    return indices, weights, evidence


def sparse_resize_graph(op, value, horizontal, vertical):
    """Eight sparse Gather/Mul branches with sequential f32 sums, no MatMul."""
    import numpy as np

    def axis_pass(data, axis, table):
        indices, weights, _ = table
        output = None
        weight_shape = [1, 1, 1, 1]
        weight_shape[axis] = weights.shape[1]
        for tap in range(4):
            gathered = op.gather(
                data, op.constant(indices[tap], dtype=np.int64), op.constant(axis, dtype=np.int64)
            )
            term = op.multiply(
                gathered, op.constant(weights[tap].reshape(weight_shape), dtype=np.float32)
            )
            output = term if output is None else op.add(output, term)
        return output

    return axis_pass(axis_pass(value, 3, horizontal), 2, vertical)


def interpolate_signature(node):
    return {
        "name": node.get_friendly_name(),
        "attributes": node.get_attributes(),
        "inputs": [
            port.get_source_output().get_node().get_friendly_name() for port in node.inputs()
        ],
        "shape": list(node.get_output_shape(0)),
        "type": str(node.get_output_element_type(0)),
    }


def lower_preprocess(model, torch, variant):
    """Replace exactly the two frozen cubic ops, retaining every existing consumer."""
    import numpy as np
    from openvino import opset13 as op
    from openvino.utils import replace_node

    all_interpolates = [
        node for node in model.get_ordered_ops() if node.get_type_name() == "Interpolate"
    ]
    cubic = [node for node in all_interpolates if node.get_attributes().get("mode") == "cubic"]
    nearest = [node for node in all_interpolates if node not in cubic]
    if len(cubic) != 2 or any(node.get_attributes().get("mode") != "nearest" for node in nearest):
        raise ValueError("exactly two native cubic nodes and only nearest HSE required")
    nearest_before = sorted(
        [interpolate_signature(node) for node in nearest], key=lambda row: row["name"]
    )
    attributes = {
        "mode": "cubic",
        "shape_calculation_mode": "sizes",
        "coordinate_transformation_mode": "pytorch_half_pixel",
        "nearest_mode": "floor",
        "antialias": False,
        "pads_begin": [0, 0, 0, 0],
        "pads_end": [0, 0, 0, 0],
        "cube_coeff": -0.75,
    }
    dimensions = native.resize_dimensions(*SHAPES[variant][2:])
    remaining = {tuple(value) for value in dimensions.values()}
    replacements = []
    for node in cubic:
        sizes_node, axes_node = node.input_value(1).get_node(), node.input_value(2).get_node()
        if (
            node.get_type_info().version_id != "opset11"
            or len(node.inputs()) != 3
            or node.get_output_size() != 1
            or not native.exact(node.get_attributes(), attributes)
            or list(node.get_input_shape(0)) != SHAPES[variant]
            or str(node.get_input_element_type(0)) != "<Type: 'float32'>"
            or str(node.get_output_element_type(0)) != "<Type: 'float32'>"
            or sizes_node.get_type_name() != "Constant"
            or axes_node.get_type_name() != "Constant"
            or not np.array_equal(axes_node.get_data(), np.array([2, 3]))
        ):
            raise ValueError("native cubic node attributes/inputs/type mismatch")
        sizes = tuple(int(value) for value in sizes_node.get_data())
        if sizes not in remaining or list(node.get_output_shape(0)) != [1, 3, *sizes]:
            raise ValueError("native cubic static resize dimensions mismatch")
        remaining.remove(sizes)
        horizontal = sparse_basis(torch, SHAPES[variant][3], sizes[1], axis=3)
        vertical = sparse_basis(torch, SHAPES[variant][2], sizes[0], axis=2)
        replacement = sparse_resize_graph(op, node.input_value(0), horizontal, vertical)
        replacement.set_friendly_name(node.get_friendly_name())
        names = node.output(0).get_names()
        consumers = list(node.output(0).get_target_inputs())
        consumer_names = sorted(
            (value.get_node().get_friendly_name(), value.get_index()) for value in consumers
        )
        replacement.output(0).get_tensor().set_names(names)
        replace_node(node, replacement)
        if (
            list(replacement.get_output_shape(0)) != [1, 3, *sizes]
            or str(replacement.get_output_element_type(0)) != "<Type: 'float32'>"
            or replacement.output(0).get_names() != names
            or sorted(
                (value.get_node().get_friendly_name(), value.get_index())
                for value in replacement.output(0).get_target_inputs()
            )
            != consumer_names
            or any(value.get_source_output().get_node() != replacement for value in consumers)
        ):
            raise ValueError("lowered cubic output shape/type/names/consumers differ")
        replacements.append(
            {
                "name": replacement.get_friendly_name(),
                "sizes": list(sizes),
                "horizontal": horizontal[2],
                "vertical": vertical[2],
                "consumers": [list(value) for value in consumer_names],
                "output_names": sorted(names),
                "consumers_preserved": True,
            }
        )
    model.validate_nodes_and_infer_types()
    nearest_after = sorted(
        [
            interpolate_signature(node)
            for node in model.get_ordered_ops()
            if node.get_type_name() == "Interpolate"
        ],
        key=lambda row: row["name"],
    )
    if remaining or not native.exact(nearest_before, nearest_after):
        raise ValueError("native nearest HSE nodes changed during lowering")
    return {
        "method": PREPROCESSING_LOWERING["method"],
        "replaced_cubic_nodes": 2,
        "nearest_unchanged": True,
        "nearest_nodes": len(nearest_after),
        "nearest_sha256": digest(nearest_before),
        "replacements": replacements,
    }


def structural_keys():
    return {f"{variant}__{probe}" for variant in SHAPES for probe in PROBES}


def validate_structural_asset(root, asset):
    import numpy as np

    if (
        not isinstance(asset, dict)
        or set(asset) != {"path", "size", "sha256"}
        or asset["path"] != "structural-references.npz"
    ):
        raise ValueError("structural reference metadata invalid")
    path = bounded_asset(
        root, asset["path"], {k: asset[k] for k in ("size", "sha256")}, STRUCTURAL_COMPRESSED_MAX
    )
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if (
            len(infos) != 18
            or {info.filename for info in infos} != {key + ".npy" for key in structural_keys()}
            or any(
                info.compress_type != zipfile.ZIP_LZMA
                or info.flag_bits & 1
                or not 0 < info.file_size <= LIMITS["max_input_bytes"]
                for info in infos
            )
            or sum(info.file_size for info in infos) > STRUCTURAL_EXPANDED_MAX
        ):
            raise ValueError("bounded exact structural archive entries required")
        for info in infos:
            variant = info.filename.split("__")[0]
            with archive.open(info) as stream:
                version = np.lib.format.read_magic(stream)
                if version != (1, 0):
                    raise ValueError("structural NPY v1 header required")
                shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
                if (
                    not native.exact(list(shape), TOKEN_METADATA[variant]["shape"])
                    or fortran
                    or dtype != np.float32
                    or info.file_size != stream.tell() + int(np.prod(shape)) * 4
                ):
                    raise ValueError("structural NPY shape/dtype/size header mismatch")
    return path


def save_structural_references(torch, util, options, output, started):
    import numpy as np
    import os

    path = relative(output, "structural-references.npz")
    temporary = clean(path.with_suffix(".npz.partial"))
    with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_LZMA) as archive:
        for variant in SHAPES:
            for probe in PROBES:
                image = torch.from_numpy(structural_image(variant, probe))
                with torch.inference_mode():
                    expected = util.get_multiscale_patches((image - 0.5) * 2, **options).numpy()
                expected = np.ascontiguousarray(check_token_array(expected, variant))
                with archive.open(f"{variant}__{probe}.npy", "w") as stream:
                    np.lib.format.write_array(stream, expected, allow_pickle=False)
                atomic(
                    output / "checkpoint.json",
                    {"status": "structural_native_saved", "variant": variant, "probe": probe},
                )
                native.check_resources(started, native.EXPORT_LIMITS)
    os.replace(temporary, path)
    asset = {"path": "structural-references.npz", "size": path.stat().st_size, "sha256": sha(path)}
    validate_structural_asset(output, asset)
    return asset


def structural_check(compiled, root, asset, checks, state, checkpoint, started, limits):
    import numpy as np

    path = validate_structural_asset(root, asset)
    with zipfile.ZipFile(path) as archive:
        for variant in SHAPES:
            for probe in PROBES:
                key = f"{variant}__{probe}"
                with archive.open(key + ".npy") as stream:
                    expected = np.lib.format.read_array(stream, allow_pickle=False)
                state["attempted"] += 1
                checks[key] = {"variant": variant, "probe": probe, "passed": False}
                checkpoint()
                actual = np.array(
                    run_graph(compiled[variant], structural_image(variant, probe)),
                    dtype=np.float32,
                    order="C",
                    copy=True,
                )
                try:
                    compare_tokens(actual, expected, variant, checks[key])
                finally:
                    checkpoint()
                state["succeeded"] += 1
                checkpoint()
                native.check_resources(started, limits)
    return checks


def check_token_array(array, variant):
    import numpy as np

    if (
        not isinstance(array, np.ndarray)
        or array.dtype != np.float32
        or list(array.shape) != TOKEN_METADATA[variant]["shape"]
        or not np.isfinite(array).all()
    ):
        raise ValueError("finite float32 exact native token shape required")
    mask = array[:, :, -1]
    if not np.isin(mask, [0, 1]).all() or int(mask.sum()) != TOKEN_METADATA[variant]["valid"]:
        raise ValueError("native token mask metadata mismatch")
    return array


def compare_tokens(actual, expected, variant, evidence=None):
    import numpy as np

    check_token_array(actual, variant)
    check_token_array(expected, variant)
    difference = np.abs(actual[:, :, :-3] - expected[:, :, :-3])
    result = {
        "metadata_equal": bool(np.array_equal(actual[:, :, -3:], expected[:, :, -3:])),
        "pixel_max_abs_error": float(difference.max()),
        "pixel_mean_abs_error": float(difference.mean(dtype=np.float64)),
        "pixel_count_above_gate": int(
            np.count_nonzero(difference > EXPORT_GATE["token_pixel_max_abs_error"])
        ),
        "pixel_count": int(difference.size),
        "rtol": 0,
    }
    result["passed"] = result["metadata_equal"] and result["pixel_count_above_gate"] == 0
    if evidence is not None:
        evidence.update(result)
    if not result["metadata_equal"]:
        raise ValueError("token HSE/scale/mask metadata must match exactly")
    if not result["passed"]:
        raise ValueError("preprocess token pixel parity failed: " + str(result))
    return result


def load_tokens(root, variant, asset):
    import numpy as np

    if not isinstance(asset, dict) or set(asset) != {"path", "size", "sha256", "shape", "dtype"}:
        raise ValueError("token asset metadata invalid")
    if (
        asset["path"] != f"tokens/{variant}.npy"
        or asset["dtype"] != "float32"
        or not native.exact(asset["shape"], TOKEN_METADATA[variant]["shape"])
    ):
        raise ValueError("token reference path invalid")
    path = bounded_asset(
        root, asset["path"], {k: asset[k] for k in ("size", "sha256")}, LIMITS["max_input_bytes"]
    )
    return check_token_array(np.load(path, allow_pickle=False), variant)


def graph_names(kind):
    return {f"models/{kind}/musiq.xml", f"models/{kind}/musiq.bin"}


def graph_assets(root, kind, assets):
    if not isinstance(assets, dict) or set(assets) != graph_names(kind):
        raise ValueError("exact shared graph XML/BIN paths required")
    for name, metadata in assets.items():
        bounded_asset(root, name, metadata, LIMITS["max_graph_bytes"])
    return sum(value["size"] for value in assets.values())


def package_size(root):
    total = 0
    for path in root.rglob("*"):
        clean(path)
        if path.is_file():
            total += path.stat().st_size
    return total


def execution_readback(compiled):
    evidence = {
        key: compiled.get_property(key)
        for key in (
            "EXECUTION_DEVICES",
            "INFERENCE_PRECISION_HINT",
            "INFERENCE_NUM_THREADS",
            "NUM_STREAMS",
        )
    }
    if (
        list(evidence["EXECUTION_DEVICES"]) != ["CPU"]
        or str(evidence["INFERENCE_PRECISION_HINT"]) != "<Type: 'float32'>"
        or type(evidence["INFERENCE_NUM_THREADS"]) is not int
        or evidence["INFERENCE_NUM_THREADS"] != 4
        or type(evidence["NUM_STREAMS"]) is bool
        or str(evidence["NUM_STREAMS"]) != "1"
    ):
        raise ValueError("actual CPU/F32/threads/streams execution readback required")
    return {
        "execution_devices": ["CPU"],
        "inference_precision": "f32",
        "threads": 4,
        "streams": 1,
        "fallback_used": False,
    }


def compile_graph(core, root, kind):
    model = core.read_model(relative(root, f"models/{kind}/musiq.xml"))
    if (
        len(model.inputs) != 1
        or len(model.outputs) != 1
        or str(model.input().get_element_type()) != "<Type: 'float32'>"
        or str(model.output().get_element_type()) != "<Type: 'float32'>"
    ):
        raise ValueError("single float32 graph input/output required")
    for op in model.get_ops():
        if op.get_type_name() == "Constant" and str(op.get_output_element_type(0)) in {
            "<Type: 'float16'>",
            "<Type: 'bfloat16'>",
            "<Type: 'float64'>",
        }:
            raise ValueError("native FP32 storage required")
    if kind == "core":
        shape = model.input().partial_shape
        if (
            shape.rank.get_length() != 3
            or shape[0].get_length() != 1
            or shape[1].get_min_length() != 385
            or shape[1].get_max_length() != 897
            or shape[2].get_length() != 3075
            or list(model.output().shape) != [1, 1]
        ):
            raise ValueError("bounded shared token core shape required")
    else:
        variant = kind.split("/")[-1]
        if (
            list(model.input().shape) != SHAPES[variant]
            or list(model.output().shape) != TOKEN_METADATA[variant]["shape"]
        ):
            raise ValueError("static native preprocess shape required")
    compiled = core.compile_model(
        model,
        "CPU",
        {
            "INFERENCE_NUM_THREADS": 4,
            "NUM_STREAMS": 1,
            "PERFORMANCE_HINT": "LATENCY",
            "INFERENCE_PRECISION_HINT": "f32",
            "CACHE_DIR": "",
        },
    )
    execution_readback(compiled)
    return compiled


def run_graph(graph, array):
    return graph([array])[graph.output()]


def measurement(
    compiled, arrays, supported, variant, started, checkpoint, calls=None, progress=None
):
    """Only inference/materialization occurs inside each measured timing interval."""
    import numpy as np

    scores = {key: [] for key in SHAPES}
    latencies, cycles = [], []
    if calls is None:
        calls = {"logical": 0, "preprocess": 0, "core": 0, "whole": 0}
    calls["logical_attempted"] = 0
    if progress is not None:
        progress.update(scores=scores, measured_latency_ms=latencies, cycles=cycles)
    rss_before = native.peak_rss()
    for cycle in range(SCHEDULE["warm_cycles"] + SCHEDULE["measure_cycles"]):
        cycle_start_rss = native.peak_rss()
        for bucket in SCHEDULE["sequence"]:
            calls["logical_attempted"] += 1
            checkpoint(calls, cycle)
            timer = time.perf_counter()
            if variant == "shared":
                calls["preprocess"] += 1
                tokens = np.array(
                    run_graph(compiled[bucket], arrays[bucket]),
                    dtype=np.float32,
                    order="C",
                    copy=True,
                )
                calls["core"] += 1
                result = run_graph(compiled["core"], tokens)
            else:
                calls["whole"] += 1
                result = run_graph(compiled[bucket], arrays[bucket])
            elapsed = (time.perf_counter() - timer) * 1000
            score = native.scalar_result(result)
            if abs(score - supported[bucket]["reference_score"]) > LIMITS["max_abs_error"]:
                raise ValueError("raw score parity failed")
            scores[bucket].append(score)
            calls["logical"] += 1
            if cycle >= SCHEDULE["warm_cycles"]:
                latencies.append(elapsed)
            checkpoint(calls, cycle)
            native.check_resources(started, LIMITS)
        rss_after = native.peak_rss()
        cycles.append(
            {
                "cycle": cycle + 1,
                "phase": "warm" if cycle < 2 else "measured",
                "peak_rss_bytes": rss_after,
                "growth_bytes": rss_after - cycle_start_rss,
            }
        )
        checkpoint(calls, cycle + 1)
    if (
        calls["logical"] != 48
        or len(latencies) != 40
        or any(max(values) - min(values) > LIMITS["max_repeat_error"] for values in scores.values())
    ):
        raise ValueError("logical count/repeat parity failed")
    return {
        "scores": scores,
        "measured_latency_ms": latencies,
        "warm_median_latency_ms": statistics.median(latencies),
        "calls": calls,
        "cycles": cycles,
        "inference_start_peak_rss_bytes": rss_before,
        "inference_end_peak_rss_bytes": native.peak_rss(),
    }


def validate_protocol(root, baseline_root, protocol, expected_sha, *, phase):
    root, baseline_root, protocol = (clean(p).resolve() for p in (root, baseline_root, protocol))
    if (
        not native.hash_string(expected_sha)
        or not protocol.is_file()
        or protocol.stat().st_size > 16777216
        or sha(protocol) != expected_sha
    ):
        raise ValueError("protocol approval fingerprint mismatch")
    baseline = native.validate_protocol(
        baseline_root, baseline_root / "protocol.json", BASELINE_SHA, phase="evaluation"
    )
    p = read(protocol)
    fixed = {
        "schema_version": SCHEMA,
        "phase": phase,
        "checkpoint_sha256": MODEL_SHA,
        "checkpoint_size_bytes": MODEL_SIZE,
        "config": CONFIG,
        "limits": LIMITS,
        "export_gate": EXPORT_GATE,
        "measurement": SCHEDULE,
        "admission": ADMISSION,
        "baseline": {"path": "baseline-protocol.json", "size": 8167, "sha256": BASELINE_SHA},
    }
    fixed["preprocessing_lowering"] = PREPROCESSING_LOWERING
    dynamic = {"graphs", "token_references", "structural_references"}
    if (
        phase not in {"preexport", "evaluation"}
        or not isinstance(p, dict)
        or set(p) != set(fixed) | dynamic
        or any(not native.exact(p.get(k), value) for k, value in fixed.items())
    ):
        raise ValueError("protocol differs from frozen shared core contract")
    bounded_asset(root, "baseline-protocol.json", {"size": 8167, "sha256": BASELINE_SHA}, 16777216)
    copied = read(root / "baseline-protocol.json")
    if not native.exact(copied, baseline):
        raise ValueError("copied baseline metadata identity mismatch")
    # The frozen baseline supplies all nine inputs, original CPU references and preparation.
    p = {
        **p,
        "items": baseline["items"],
        "references": baseline["references"],
        "preparation": baseline["preparation"],
    }
    prep = p["preparation"]
    bounded_asset(root, prep["path"], {k: prep[k] for k in ("size", "sha256")}, 16777216)
    for item in p["items"]:
        path = relative(root, item["path"])
        if (
            not path.is_file()
            or not 0 < path.stat().st_size <= 16777216
            or sha(path) != item["input_sha256"]
        ):
            raise ValueError("frozen input size/hash identity invalid")
        native.image_array(path, item["input_shape"], max_pixels=4194304)
        if item["variant"] is not None:
            native.validate_reference(
                read(
                    native.reference_asset(root, item["variant"], p["references"][item["variant"]])
                ),
                item,
            )
    if (
        not isinstance(p["graphs"], dict)
        or set(p["graphs"]) != {"preprocess", "core"}
        or not isinstance(p["graphs"]["preprocess"], dict)
        or set(p["graphs"]["preprocess"]) != set(SHAPES)
        or not isinstance(p["token_references"], dict)
        or set(p["token_references"]) != set(SHAPES)
    ):
        raise ValueError("exact three preprocess graphs/one core/three token references required")
    if phase == "preexport":
        if p["structural_references"] is not None:
            raise ValueError("preexport structural references must be null")
        if (
            p["graphs"]["core"] is not None
            or any(v is not None for v in p["graphs"]["preprocess"].values())
            or any(v is not None for v in p["token_references"].values())
        ):
            raise ValueError("preexport graph/token assets must be null")
    else:
        validate_structural_asset(root, p["structural_references"])
        total = graph_assets(root, "core", p["graphs"]["core"])
        for variant in SHAPES:
            total += graph_assets(root, f"preprocess/{variant}", p["graphs"]["preprocess"][variant])
            load_tokens(root, variant, p["token_references"][variant])
        if total > LIMITS["max_graph_bytes"]:
            raise ValueError("four shared graphs exceed size bound")
    if package_size(root) > LIMITS["max_package_bytes"]:
        raise ValueError("shared package exceeds size bound")
    return p, baseline


def save_graph(ov, model, output, kind, started):
    path = relative(output, f"models/{kind}/musiq.xml")
    path.parent.mkdir(parents=True, exist_ok=True)
    ov.save_model(model, path, compress_to_fp16=False)
    assets = {}
    for name in sorted(graph_names(kind)):
        graph = relative(output, name)
        size = graph.stat().st_size
        if not 0 < size <= LIMITS["max_graph_bytes"]:
            raise ValueError("export graph storage size bound exceeded")
        assets[name] = {"size": size, "sha256": sha(graph)}
        native.check_resources(started, native.EXPORT_LIMITS)
    if graph_assets(output, kind, assets) > LIMITS["max_graph_bytes"]:
        raise ValueError("export graph pair storage size bound exceeded")
    return assets


def export(root, baseline_root, protocol, expected_sha, checkpoint, output, openvino_site):
    started = time.monotonic()
    p, baseline = validate_protocol(root, baseline_root, protocol, expected_sha, phase="preexport")
    root = clean(root).resolve()
    checkpoint = clean(checkpoint).resolve()
    if (
        not checkpoint.is_file()
        or checkpoint.stat().st_size != MODEL_SIZE
        or sha(checkpoint) != MODEL_SHA
    ):
        raise ValueError("checkpoint identity mismatch")
    source = Path(__file__).with_name("benchmark_public_musiq.py")
    protected = [checkpoint, source]
    if openvino_site is not None:
        protected.append(openvino_site)
    output = fresh_output(root, baseline_root, protocol, output, protected)
    sources = frozen_sources()
    atomic(
        output / "checkpoint.json",
        {"status": "native_initializing", "protocol_sha256": expected_sha},
    )
    lowering, structural_checks = {}, {}
    native_hashes, versions, identity = {}, {}, None
    structural_state = {"attempted": 0, "succeeded": 0}
    try:
        if openvino_site:
            sys.path.append(str(clean(openvino_site).resolve()))
        spec = importlib.util.spec_from_file_location("shared_core_cpu_parent", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with (
            native.owned_cache(output),
            module.isolated_homes(output),
            module.offline_guard() as stack,
        ):
            runtime = module.CpuMusiq(checkpoint, stack)
            torch = runtime.torch
            ov = __import__("openvino")
            util = __import__(
                "pyiqa.data.multiscale_trans_util", fromlist=["get_multiscale_patches"]
            )
            arch = sys.modules[runtime.metric.net.__class__.__module__]
            preprocess, token_core = make_modules(torch, runtime.metric.net, util, arch.dist_to_mos)
            native_sources = [
                source,
                Path(module.nima.__file__),
                Path(module.base.__file__),
                Path(arch.__file__),
                Path(util.__file__),
            ]
            native_hashes = {path.name: sha(clean(path)) for path in native_sources}
            versions = {
                **native.runtime_versions(ov),
                "torch": torch.__version__,
                "pyiqa": __import__("importlib.metadata").metadata.version("pyiqa"),
            }
            identity = digest(
                {
                    "protocol_sha256": expected_sha,
                    "source_hashes": sources,
                    "native_source_hashes": native_hashes,
                    "runtime_versions": versions,
                    "checkpoint_sha256": MODEL_SHA,
                    "references": baseline["references"],
                }
            )
            tokens, tensors, token_assets, derivations = {}, {}, {}, {}
            lowering = {}
            structural_checks = {}
            structural_state = {"attempted": 0, "succeeded": 0}
            local_compiled = {}
            local_core = ov.Core()
            local_cpu = "CPU" in list(local_core.available_devices)
            structural_asset = save_structural_references(
                torch, util, runtime.metric.net.data_preprocess_opts, output, started
            )
            with torch.inference_mode():
                for variant in SHAPES:
                    item = next(item for item in p["items"] if item["variant"] == variant)
                    tensors[variant] = torch.from_numpy(
                        native.image_array(
                            relative(root, item["path"]), SHAPES[variant], max_pixels=1048576
                        )
                    )
                    tokens[variant] = util.get_multiscale_patches(
                        (tensors[variant] - 0.5) * 2, **runtime.metric.net.data_preprocess_opts
                    )
                    check_token_array(tokens[variant].numpy(), variant)
                    with patch.object(
                        util, "resize_preserve_aspect_ratio", fixed_resize(torch, variant)
                    ):
                        specialized = preprocess(tensors[variant])
                    if not torch.equal(tokens[variant], specialized):
                        raise ValueError("specialized/native eager tokens must match exactly")
                    split_score = native.scalar_result(token_core(tokens[variant]).numpy())
                    error = abs(split_score - item["reference_score"])
                    if error > 0.00001:
                        raise ValueError("split core eager raw parity failed")
                    path = relative(output, f"tokens/{variant}.npy")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("xb") as stream:
                        runtime.np.save(stream, tokens[variant].numpy(), allow_pickle=False)
                        stream.flush()
                        __import__("os").fsync(stream.fileno())
                    token_assets[variant] = {
                        "path": f"tokens/{variant}.npy",
                        "size": path.stat().st_size,
                        "sha256": sha(path),
                        "shape": TOKEN_METADATA[variant]["shape"],
                        "dtype": "float32",
                    }
                    derivations[variant] = {
                        "input_sha256": item["input_sha256"],
                        "reference": p["references"][variant],
                        "reference_score": item["reference_score"],
                        "split_score": split_score,
                        "eager_max_abs_error": error,
                        "tokens": token_assets[variant],
                        "tokens_equal": True,
                        "native_metadata": TOKEN_METADATA[variant],
                    }
                    atomic(
                        output / "reference-derivation.json",
                        {
                            "identity": identity,
                            "source_hashes": sources,
                            "native_source_hashes": native_hashes,
                            "runtime_versions": versions,
                            "derivations": derivations,
                        },
                    )
                    atomic(
                        output / "checkpoint.json",
                        {
                            "status": "native_tokens_saved",
                            "identity": identity,
                            "variants": list(derivations),
                        },
                    )
                    native.check_resources(started, native.EXPORT_LIMITS)
                runtime.validate()
                graphs = {"preprocess": {}, "core": None}
                atomic(
                    output / "checkpoint.json",
                    {"status": "core_trace_pending", "identity": identity},
                )
                traced = torch.jit.trace(
                    token_core,
                    tokens["control"],
                    strict=True,
                    check_trace=True,
                    check_inputs=[(tokens["landscape"],), (tokens["portrait"],)],
                )
                converted = ov.convert_model(
                    traced,
                    input=[ov.PartialShape([1, ov.Dimension(385, 897), 3075])],
                    share_weights=False,
                )
                graphs["core"] = save_graph(ov, converted, output, "core", started)
                del converted, traced
                for variant in SHAPES:
                    atomic(
                        output / "checkpoint.json",
                        {
                            "status": "preprocess_trace_pending",
                            "identity": identity,
                            "variant": variant,
                        },
                    )
                    with patch.object(
                        util, "resize_preserve_aspect_ratio", fixed_resize(torch, variant)
                    ):
                        traced = torch.jit.trace(
                            preprocess, tensors[variant], strict=True, check_trace=True
                        )
                        converted = ov.convert_model(
                            traced, input=[SHAPES[variant]], share_weights=False
                        )
                    lowering[variant] = lower_preprocess(converted, torch, variant)
                    if local_cpu:
                        compiled_local = local_core.compile_model(
                            converted,
                            "CPU",
                            {
                                "INFERENCE_NUM_THREADS": 4,
                                "NUM_STREAMS": 1,
                                "PERFORMANCE_HINT": "LATENCY",
                                "INFERENCE_PRECISION_HINT": "f32",
                                "CACHE_DIR": "",
                            },
                        )
                        execution_readback(compiled_local)
                        local_compiled[variant] = compiled_local
                    graphs["preprocess"][variant] = save_graph(
                        ov, converted, output, f"preprocess/{variant}", started
                    )
                    del converted, traced
            if local_cpu:

                def structural_checkpoint():
                    atomic(
                        output / "checkpoint.json",
                        {
                            "status": "local_structural_validation",
                            "identity": identity,
                            "structural_validation": structural_state,
                            "structural_checks": structural_checks,
                        },
                    )

                structural_check(
                    local_compiled,
                    output,
                    structural_asset,
                    structural_checks,
                    structural_state,
                    structural_checkpoint,
                    started,
                    native.EXPORT_LIMITS,
                )
            runtime.validate()
            total = sum(
                v["size"]
                for g in [graphs["core"], *graphs["preprocess"].values()]
                for v in g.values()
            )
            if (
                total > LIMITS["max_graph_bytes"]
                or package_size(output) > LIMITS["max_package_bytes"]
            ):
                raise ValueError("shared export graph/package budget exceeded")
            verify_sources(sources)
            if any(sha(path) != native_hashes[path.name] for path in native_sources):
                raise ValueError("native source changed during export")
            if checkpoint.stat().st_size != MODEL_SIZE or sha(checkpoint) != MODEL_SHA:
                raise ValueError("checkpoint changed during export")
            validate_protocol(root, baseline_root, protocol, expected_sha, phase="preexport")
            validate_structural_asset(output, structural_asset)
            graph_assets(output, "core", graphs["core"])
            for variant in SHAPES:
                graph_assets(output, f"preprocess/{variant}", graphs["preprocess"][variant])
                load_tokens(output, variant, token_assets[variant])
            native.check_resources(started, native.EXPORT_LIMITS)
            receipt = {
                "schema_version": SCHEMA,
                "status": "exported_not_yet_parity_verified",
                "identity": identity,
                "protocol_sha256": expected_sha,
                "graphs": graphs,
                "tokens": token_assets,
                "preprocessing_lowering": PREPROCESSING_LOWERING,
                "lowering_evidence": lowering,
                "structural_references": structural_asset,
                "local_structural_checks": structural_checks,
                "local_structural_validation": {
                    **structural_state,
                    "status": "passed" if local_cpu else "cpu_plugin_unavailable",
                    "does_not_replace_target_acceptance": True,
                },
                "derivations": derivations,
                "source_hashes": sources,
                "native_source_hashes": native_hashes,
                "runtime_versions": versions,
                "native_execution": runtime.evidence,
                "checkpoint_sha256": MODEL_SHA,
                "checkpoint_size_bytes": MODEL_SIZE,
                "storage_precision": "FP32",
                "fp16_compression": False,
                "graph_bytes": total,
                "elapsed_seconds": time.monotonic() - started,
                "peak_rss_bytes": native.peak_rss(),
                "trace_check_variants": list(SHAPES),
                "limitations": "Raw diagnostic only; no policy or MOS admission.",
            }
            atomic(output / "export-receipt.json", receipt)
            atomic(output / "checkpoint.json", {"status": receipt["status"], "identity": identity})
            return receipt
    except Exception as exc:
        atomic(
            output / "export-receipt.json",
            {
                "status": "incomplete",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "protocol_sha256": expected_sha,
                "lowering_evidence": lowering,
                "local_structural_checks": structural_checks,
                "local_structural_validation": {**structural_state, "status": "incomplete"},
                "source_hashes": sources,
                "native_source_hashes": native_hashes,
                "runtime_versions": versions,
                "identity": identity,
            },
        )
        raise


def evaluate(variant, round_number, root, baseline_root, protocol, expected_sha, output):
    started = time.monotonic()
    if (
        variant not in {"whole", "shared"}
        or type(round_number) is not int
        or round_number not in (1, 2, 3)
    ):
        raise ValueError("whole/shared variant and round 1/2/3 required")
    p, baseline = validate_protocol(root, baseline_root, protocol, expected_sha, phase="evaluation")
    native.check_resources(started, LIMITS)
    root, baseline_root = clean(root).resolve(), clean(baseline_root).resolve()
    output = fresh_output(root, baseline_root, protocol, output)
    sources = frozen_sources()
    progress = {}
    validation = {}
    validation_state = {"attempted": 0, "succeeded": 0}
    structural_checks = {}
    structural_state = {"attempted": 0, "succeeded": 0}
    identity, calls = None, {"logical": 0, "preprocess": 0, "core": 0, "whole": 0}
    atomic(
        output / "checkpoint.json",
        {
            "status": "initializing",
            "variant": variant,
            "round": round_number,
            "protocol_sha256": expected_sha,
        },
    )
    try:
        with native.owned_cache(output), native.offline():
            ov = __import__("openvino")
            provenance = {
                "protocol_sha256": expected_sha,
                "baseline_protocol_sha256": BASELINE_SHA,
                "source_hashes": sources,
                "graphs": p["graphs"],
                "whole_graphs": baseline["graphs"],
                "token_references": p["token_references"],
                "structural_references": p["structural_references"],
                "preprocessing_lowering": PREPROCESSING_LOWERING,
                "references": p["references"],
                "preparation": p["preparation"],
                "runtime_versions": native.runtime_versions(ov),
                "config": CONFIG,
                "measurement": SCHEDULE,
                "variant": variant,
                "round": round_number,
            }
            identity = digest(provenance)
            supported = {
                item["variant"]: item for item in p["items"] if item["variant"] is not None
            }
            arrays = {
                bucket: native.image_array(
                    relative(root, item["path"]), SHAPES[bucket], max_pixels=1048576
                )
                for bucket, item in supported.items()
            }
            token_refs = (
                {
                    bucket: load_tokens(root, bucket, p["token_references"][bucket])
                    for bucket in SHAPES
                }
                if variant == "shared"
                else {}
            )
            core, compiled = ov.Core(), {}
            core.set_property({"CACHE_DIR": ""})
            if core.get_property("CACHE_DIR") != "":
                raise ValueError("compiled cache must be disabled")
            compile_start = time.monotonic()
            compile_peak_start = native.peak_rss()
            if variant == "whole":
                for bucket in SHAPES:
                    compiled[bucket] = native.compiled_graph(core, baseline_root, bucket)
                    native.check_resources(started, LIMITS)
            else:
                for bucket in SHAPES:
                    compiled[bucket] = compile_graph(core, root, f"preprocess/{bucket}")
                    native.check_resources(started, LIMITS)
                compiled["core"] = compile_graph(core, root, "core")
            compile_seconds = time.monotonic() - compile_start
            compile_peak_end = native.peak_rss()

            def validation_checkpoint():
                atomic(
                    output / "checkpoint.json",
                    {
                        "status": "preprocess_validation",
                        "identity": identity,
                        "variant": variant,
                        "round": round_number,
                        "token_validation": validation_state,
                        "token_parity": validation,
                        "structural_validation": structural_state,
                        "structural_checks": structural_checks,
                    },
                )

            if variant == "shared":
                import numpy as np

                structural_check(
                    compiled,
                    root,
                    p["structural_references"],
                    structural_checks,
                    structural_state,
                    validation_checkpoint,
                    started,
                    LIMITS,
                )
                for bucket in SHAPES:
                    validation_state["attempted"] += 1
                    validation[bucket] = {"passed": False}
                    validation_checkpoint()
                    actual = np.array(
                        run_graph(compiled[bucket], arrays[bucket]),
                        dtype=np.float32,
                        order="C",
                        copy=True,
                    )
                    try:
                        compare_tokens(actual, token_refs[bucket], bucket, validation[bucket])
                    finally:
                        validation_checkpoint()
                    validation_state["succeeded"] += 1
                    validation_checkpoint()
                    native.check_resources(started, LIMITS)
            validation_calls = validation_state["succeeded"]

            def checkpoint(current_calls, cycle):
                atomic(
                    output / "checkpoint.json",
                    {
                        "status": "measuring",
                        "identity": identity,
                        "variant": variant,
                        "round": round_number,
                        "calls": current_calls,
                        "completed_cycles": cycle,
                        "token_validation_preprocess_calls": validation_calls,
                        "partial_measurement": progress,
                        "structural_validation": structural_state,
                        "structural_checks": structural_checks,
                        "token_validation": validation_state,
                        "token_parity": validation,
                    },
                )
                for graph in compiled.values():
                    execution_readback(graph)

            checkpoint(calls, 0)
            measured = measurement(
                compiled, arrays, supported, variant, started, checkpoint, calls, progress
            )
            calls = measured["calls"]
            records = []
            for item in p["items"]:
                record = native.record_base(identity, item)
                if item["variant"] is None:
                    record.update(
                        status="unsupported_shape",
                        graph_selected=False,
                        score_produced=False,
                        native_calls=0,
                        fallback_used=False,
                    )
                else:
                    bucket = item["variant"]
                    record.update(
                        status="ok",
                        graph_selected=True,
                        score_produced=True,
                        variant=bucket,
                        scores=measured["scores"][bucket],
                        reference_score=item["reference_score"],
                        **execution_readback(compiled[bucket]),
                    )
                record["record_sha256"] = digest(record)
                atomic(output / "predictions" / (digest(item["id"]) + ".json"), record)
                records.append(record)
            validate_protocol(root, baseline_root, protocol, expected_sha, phase="evaluation")
            verify_sources(sources)
            for graph in compiled.values():
                execution_readback(graph)
            native.check_resources(started, LIMITS)
            report = {
                "schema_version": SCHEMA,
                "status": "raw_parity_pass",
                "complete": True,
                "identity": identity,
                "provenance": provenance,
                "variant": variant,
                "round": round_number,
                "records": records,
                "successful": 3,
                "unsupported": 6,
                "failures": 0,
                "execution_devices": ["CPU"],
                "precision": "F32",
                "fallback_used": False,
                "logical_calls": 48,
                "timed_calls": 40,
                "graph_calls": {
                    key: calls[key] + (validation_calls if key == "preprocess" else 0)
                    for key in ("whole", "preprocess", "core")
                },
                "compile_count": len(compiled),
                "compile_seconds": compile_seconds,
                "compile_start_peak_rss_bytes": compile_peak_start,
                "compile_end_peak_rss_bytes": compile_peak_end,
                "token_parity": validation,
                "token_validation_preprocess_calls": validation_calls,
                "token_validation_attempted_calls": validation_state["attempted"],
                "structural_validation_calls": structural_state["succeeded"],
                "structural_validation_attempted_calls": structural_state["attempted"],
                "structural_checks": structural_checks,
                "total_actual_graph_calls": {
                    key: calls[key]
                    + (
                        validation_calls + structural_state["succeeded"]
                        if key == "preprocess"
                        else 0
                    )
                    for key in ("whole", "preprocess", "core")
                },
                "scheduled_native_calls": {
                    **calls,
                    "preprocess": calls["preprocess"] + validation_calls,
                },
                "total_native_calls": {
                    **calls,
                    "preprocess": calls["preprocess"]
                    + validation_calls
                    + structural_state["succeeded"],
                },
                "prediction_cache_reused": 0,
                "start_elapsed_seconds": compile_start - started,
                "elapsed_seconds": time.monotonic() - started,
                "peak_rss_bytes": native.peak_rss(),
                **measured,
                "max_abs_error": max(
                    abs(value - supported[bucket]["reference_score"])
                    for bucket, values in measured["scores"].items()
                    for value in values
                ),
                "max_repeat_error": max(
                    max(values) - min(values) for values in measured["scores"].values()
                ),
                "admission_status": "controller_cross_round_comparison_required",
                "limitations": "Raw diagnostic only; no policy or MOS admission.",
            }
            report["report_sha256"] = digest(report)
            atomic(output / "report.json", report)
            atomic(
                output / "checkpoint.json",
                {
                    "status": report["status"],
                    "identity": identity,
                    "variant": variant,
                    "round": round_number,
                    "calls": calls,
                    "token_validation_preprocess_calls": validation_calls,
                    "records": len(records),
                    "structural_validation": structural_state,
                    "structural_checks": structural_checks,
                    "token_validation": validation_state,
                    "token_parity": validation,
                },
            )
            return report
    except Exception as exc:
        atomic(
            output / "report.json",
            {
                "schema_version": SCHEMA,
                "status": "incomplete",
                "complete": False,
                "identity": identity,
                "variant": variant,
                "round": round_number,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "protocol_sha256": expected_sha,
                "calls": calls,
                "partial_measurement": progress,
                "token_validation": validation_state,
                "token_parity": validation,
                "structural_validation": structural_state,
                "structural_checks": structural_checks,
                "elapsed_seconds": time.monotonic() - started,
                "peak_rss_bytes": native.peak_rss(),
                "admission_status": "incomplete",
            },
        )
        atomic(
            output / "checkpoint.json",
            {
                "status": "incomplete",
                "identity": identity,
                "variant": variant,
                "round": round_number,
                "calls": calls,
                "partial_measurement": progress,
                "token_validation": validation_state,
                "token_parity": validation,
                "structural_validation": structural_state,
                "structural_checks": structural_checks,
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "evaluate"):
        sub = commands.add_parser(name)
        for flag in ("root", "baseline-root", "protocol", "output"):
            sub.add_argument(f"--{flag}", type=Path, required=True)
        sub.add_argument("--protocol-sha256", required=True)
        if name == "export":
            sub.add_argument("--checkpoint", type=Path, required=True)
            sub.add_argument("--openvino-site", type=Path)
        else:
            sub.add_argument("--variant", choices=("whole", "shared"), required=True)
            sub.add_argument("--round", type=int, choices=(1, 2, 3), required=True)
    args = parser.parse_args()
    if args.command == "export":
        export(
            args.root,
            args.baseline_root,
            args.protocol,
            args.protocol_sha256,
            args.checkpoint,
            args.output,
            args.openvino_site,
        )
    else:
        evaluate(
            args.variant,
            args.round,
            args.root,
            args.baseline_root,
            args.protocol,
            args.protocol_sha256,
            args.output,
        )


if __name__ == "__main__":
    main()
