#!/usr/bin/env python3
"""Bounded exact-native-shape MUSIQ diagnostic; no production policy admission."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import io
import json
import math
from pathlib import Path
import resource
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
HELPER_SOURCE = Path(__file__).with_name("benchmark_musiq_openvino.py")
SPEC = importlib.util.spec_from_file_location("native_shape_helpers", HELPER_SOURCE)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
sha, digest, clean, read, atomic = (
    helper.sha,
    helper.digest,
    helper.clean,
    helper.read,
    helper.atomic,
)
relative, owned_cache, offline = helper.relative, helper.owned_cache, helper.offline
SHAPES = {
    "control": [1, 3, 384, 512],
    "landscape": [1, 3, 682, 1024],
    "portrait": [1, 3, 1024, 682],
}
MODEL_SHA, CONFIG = helper.MODEL_SHA, helper.CONFIG
MODEL_SIZE = 108610983


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def integer(value, minimum=1):
    return type(value) is int and value >= minimum


def hash_string(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def exact(value, expected):
    try:
        return digest(value) == digest(expected)
    except TypeError, ValueError:
        return False


def peak_rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
        1 if sys.platform == "darwin" else 1024
    )


def check_resources(started, limits):
    if time.monotonic() - started > limits["max_seconds"]:
        raise ValueError("elapsed resource bound exceeded")
    if peak_rss() > limits["max_rss_bytes"]:
        raise ValueError("RSS resource bound exceeded")


def bounded_asset(root, name, expected, maximum):
    if (
        not isinstance(expected, dict)
        or set(expected) != {"size", "sha256"}
        or not integer(expected["size"])
        or expected["size"] > maximum
        or not hash_string(expected["sha256"])
    ):
        raise ValueError("invalid bounded asset metadata")
    path = relative(root, name)
    if not path.is_file() or path.stat().st_size != expected["size"]:
        raise ValueError("asset size identity mismatch")
    if sha(path) != expected["sha256"]:
        raise ValueError("asset hash identity mismatch")
    return path


def image_array(path, shape, *, max_pixels):
    import numpy as np
    from PIL import Image

    with Image.open(io.BytesIO(clean(path).read_bytes())) as image:
        width, height = image.size
        if width * height > max_pixels or not exact([1, 3, height, width], shape):
            raise ValueError("decoded input shape/budget mismatch")
        if image.format not in {"JPEG", "PNG"} or image.mode != "RGB":
            raise ValueError("native RGB JPEG/PNG input required")
        array = np.asarray(image, dtype=np.float32) / 255.0
    out = np.ascontiguousarray(array.transpose(2, 0, 1)[None])
    if out.dtype != np.float32 or not np.isfinite(out).all() or out.min() < 0 or out.max() > 1:
        raise ValueError("finite native RGB float32 input required")
    return out


def resize_dimensions(height, width):
    """Installed native MUSIQ util's Python round recipe for both default scales."""
    if not integer(height) or not integer(width):
        raise ValueError("positive integer native dimensions required")
    return {
        str(scale): [
            round(height * (scale / max(height, width))),
            round(width * (scale / max(height, width))),
        ]
        for scale in (224, 384)
    }


def token_metadata(tokens):
    mask = tokens[:, :, -1]
    if not bool(((mask == 0) | (mask == 1)).all().item()):
        raise ValueError("native token validity mask must be binary")
    valid = int(mask.sum().item())
    total = int(mask.numel())
    return {"shape": list(tokens.shape), "count": total, "valid": valid, "padding": total - valid}


def output_dir(root, protocol, output, protected=()):
    root, output = clean(root).resolve(), clean(output).resolve()
    paths = (
        root,
        clean(protocol).resolve(),
        clean(__file__).resolve(),
        clean(HELPER_SOURCE).resolve(),
        *(clean(p).resolve() for p in protected),
    )
    if any(output.is_relative_to(path) or path.is_relative_to(output) for path in paths):
        raise ValueError("output must be separate from all protected inputs/sources")
    output.mkdir(parents=True, exist_ok=True)
    return output


def runtime_versions(ov):
    return {
        "python": sys.version,
        "platform": sys.platform,
        "openvino": ov.__version__,
        **{name: importlib.metadata.version(name) for name in ("numpy", "Pillow")},
    }


def compiled_graph(core, root, variant):
    model = core.read_model(relative(root, f"models/{variant}/musiq.xml"))
    if (
        len(model.inputs) != 1
        or len(model.outputs) != 1
        or list(model.input().shape) != SHAPES[variant]
        or str(model.input().get_element_type()) != "<Type: 'float32'>"
        or str(model.output().get_element_type()) != "<Type: 'float32'>"
        or math.prod(list(model.output().shape)) != 1
    ):
        raise ValueError("static exact shape/single float output graph required")
    compiled = core.compile_model(
        model,
        "CPU",
        {
            "INFERENCE_NUM_THREADS": 4,
            "NUM_STREAMS": 1,
            "PERFORMANCE_HINT": "LATENCY",
            "INFERENCE_PRECISION_HINT": "f32",
        },
    )
    if (
        list(compiled.get_property("EXECUTION_DEVICES")) != ["CPU"]
        or str(compiled.get_property("INFERENCE_PRECISION_HINT")) != "<Type: 'float32'>"
        or type(compiled.get_property("INFERENCE_NUM_THREADS")) is not int
        or compiled.get_property("INFERENCE_NUM_THREADS") != 4
        or type(compiled.get_property("NUM_STREAMS")) is bool
        or str(compiled.get_property("NUM_STREAMS")) != "1"
    ):
        raise ValueError("actual CPU/F32/threads/streams execution readback required")
    return compiled


def scalar_result(result):
    import numpy as np

    array = np.asarray(result)
    if array.size != 1 or array.dtype.kind != "f" or not np.isfinite(array).all():
        raise ValueError("finite single float raw MUSIQ output required")
    return float(array.item())


EXPORT_LIMITS = {"max_seconds": 300, "max_rss_bytes": 2500000000, "max_graph_bytes": 150000000}
TOKEN_METADATA = {
    "control": {"shape": [1, 385, 3075], "count": 385, "valid": 342, "padding": 43},
    **{
        variant: {"shape": [1, 897, 3075], "count": 897, "valid": 835, "padding": 62}
        for variant in ("landscape", "portrait")
    },
}


def export_native(sample_path, item, variant, checkpoint, output, openvino_site, expected_sha):
    """Export only after the caller has validated protocol and output isolation."""
    started = time.monotonic()
    checkpoint = clean(checkpoint).resolve()
    if (
        not checkpoint.is_file()
        or checkpoint.stat().st_size != MODEL_SIZE
        or sha(checkpoint) != MODEL_SHA
    ):
        raise ValueError("checkpoint identity mismatch")
    check_resources(started, EXPORT_LIMITS)
    if openvino_site:
        sys.path.append(str(clean(openvino_site).resolve()))
    source = clean(Path(__file__).with_name("benchmark_public_musiq.py"))
    spec = importlib.util.spec_from_file_location("native_shapes_cpu_parent", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    atomic(
        output / "checkpoint.json",
        {"status": "initializing_native_cpu", "variant": variant, "protocol_sha256": expected_sha},
    )
    with owned_cache(output), module.isolated_homes(output), module.offline_guard() as stack:
        runtime = module.CpuMusiq(checkpoint, stack)
        ov = __import__("openvino")
        util = __import__("pyiqa.data.multiscale_trans_util", fromlist=["get_multiscale_patches"])
        torch = runtime.torch
        shape = SHAPES[variant]
        tensor = torch.from_numpy(image_array(sample_path, shape, max_pixels=1048576))
        dimensions = resize_dimensions(shape[2], shape[3])
        arch = sys.modules[runtime.metric.net.__class__.__module__].__file__
        sources = [
            source,
            Path(__file__),
            HELPER_SOURCE,
            Path(module.nima.__file__),
            Path(module.base.__file__),
            Path(arch),
            Path(util.__file__),
        ]
        source_hashes = {p.name: sha(p) for p in sources}
        versions = {
            **runtime_versions(ov),
            "torch": torch.__version__,
            "pyiqa": importlib.metadata.version("pyiqa"),
        }
        reference_identity = digest(
            {
                "source_hashes": source_hashes,
                "runtime_versions": versions,
                "protocol_sha256": expected_sha,
                "input": item,
                "checkpoint_sha256": MODEL_SHA,
            }
        )
        atomic(
            output / "checkpoint.json",
            {
                "status": "native_reference_pending",
                "variant": variant,
                "identity": reference_identity,
                "protocol_sha256": expected_sha,
            },
        )
        reference = runtime.score(sample_path.read_bytes())
        reference.update(
            id=item["id"],
            input_sha256=item["input_sha256"],
            model_sha256=MODEL_SHA,
            model_revision="pyiqa-musiq-koniq-e95806b9",
            protocol_sha256=expected_sha,
            identity=reference_identity,
        )
        reference["record_sha256"] = module.record_hash(reference)
        if native_record_hash(reference) != reference["record_sha256"]:
            raise ValueError("independent native reference hash recipe mismatch")
        validate_reference(reference, {**item, "reference_score": reference["score"]})
        atomic(output / "reference.json", reference)
        atomic(
            output / "checkpoint.json",
            {
                "status": "native_reference_saved",
                "variant": variant,
                "identity": reference_identity,
            },
        )
        check_resources(started, EXPORT_LIMITS)

        def fixed_resize(image, h, w, longer_side_length):
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

        with torch.inference_mode():
            native_tokens = util.get_multiscale_patches(
                (tensor - 0.5) * 2, **runtime.metric.net.data_preprocess_opts
            )
            with patch.object(util, "resize_preserve_aspect_ratio", fixed_resize):
                specialized_tokens = util.get_multiscale_patches(
                    (tensor - 0.5) * 2, **runtime.metric.net.data_preprocess_opts
                )
            metadata = token_metadata(native_tokens)
            if not torch.equal(native_tokens, specialized_tokens) or not exact(
                metadata, TOKEN_METADATA[variant]
            ):
                raise ValueError("native/specialized full tokens or metadata differ")
            native_score = reference["score"]
            with patch.object(util, "resize_preserve_aspect_ratio", fixed_resize):
                specialized_score = scalar_result(runtime.metric.net(tensor).numpy())
            eager_error = abs(native_score - specialized_score)
            if eager_error > 0.00001:
                raise ValueError("native/specialized eager raw parity failed")
        runtime.validate()
        check_resources(started, EXPORT_LIMITS)
        atomic(
            output / "checkpoint.json",
            {"status": "trace_pending", "variant": variant, "identity": reference_identity},
        )
        with (
            torch.inference_mode(),
            patch.object(util, "resize_preserve_aspect_ratio", fixed_resize),
        ):
            traced = torch.jit.trace(runtime.metric.net, tensor, strict=True, check_trace=True)
            converted = ov.convert_model(traced, input=[shape], share_weights=False)
        ov.save_model(converted, output / "musiq.xml", compress_to_fp16=False)
        graph = {}
        for suffix in ("xml", "bin"):
            path = clean(output / f"musiq.{suffix}")
            size = path.stat().st_size
            if size <= 0 or size > EXPORT_LIMITS["max_graph_bytes"]:
                raise ValueError("export graph size budget exceeded")
            graph[f"models/{variant}/musiq.{suffix}"] = {"size": size, "sha256": sha(path)}
            check_resources(started, EXPORT_LIMITS)
        if sum(asset["size"] for asset in graph.values()) > EXPORT_LIMITS["max_graph_bytes"]:
            raise ValueError("export graph pair size budget exceeded")
        if checkpoint.stat().st_size != MODEL_SIZE or sha(checkpoint) != MODEL_SHA:
            raise ValueError("checkpoint changed during export")
        check_resources(started, EXPORT_LIMITS)
        if any(sha(path) != source_hashes[path.name] for path in sources):
            raise ValueError("export source changed during conversion")
        receipt = {
            "status": "exported_not_yet_parity_verified",
            "variant": variant,
            "protocol_sha256": expected_sha,
            "graph": graph,
            "checkpoint_sha256": MODEL_SHA,
            "checkpoint_size": MODEL_SIZE,
            "input_sha256": sha(sample_path),
            "input_shape": shape,
            "reference_score": native_score,
            "specialized_score": specialized_score,
            "eager_max_abs_error": eager_error,
            "preprocess_tokens_equal": True,
            "tokens": metadata,
            "resize_specialization": dimensions,
            "fp16_compression": False,
            "storage_precision": "FP32",
            "runtime_versions": versions,
            "source_hashes": source_hashes,
            "native_execution": runtime.evidence,
            "elapsed_seconds": time.monotonic() - started,
            "peak_rss_bytes": peak_rss(),
            "limitations": "Exact native-shape diagnostic only; no policy admission.",
        }
        atomic(output / "export-receipt.json", receipt)
        atomic(
            output / "checkpoint.json",
            {
                "status": "exported_not_yet_parity_verified",
                "variant": variant,
                "identity": reference_identity,
            },
        )
        return receipt


SCHEMA = "material-agent.musiq-native-shapes.v1"
LIMITS = {
    "max_items": 9,
    "max_supported": 3,
    "max_graph_bytes": 150000000,
    "max_total_graph_bytes": 450000000,
    "max_input_bytes": 16777216,
    "max_decode_pixels": 4194304,
    "max_supported_side": 1024,
    "max_seconds": 900,
    "max_rss_bytes": 2500000000,
    "max_abs_error": 0.001,
    "max_repeat_error": 0.000001,
}
EXPORT_GATE = {**EXPORT_LIMITS, "eager_max_abs_error": 0.00001, "fp16_compression": False}
INPUT_CONTRACT = {
    "color": "RGB",
    "dtype": "float32",
    "range": [0, 1],
    "preprocessing": "native PyIQA original/224/384; no external resize",
    "scope": "bounded exact shape buckets; derived portrait is not actual RAW "
    "orientation acceptance",
}
PREPROCESS = {
    "patch_size": 32,
    "patch_stride": 32,
    "hse_grid_size": 10,
    "longer_side_lengths": [224, 384],
    "max_seq_len_from_original_res": -1,
}
SOURCE_KINDS = {
    "public_raw_embedded_preview",
    "public_raw_postprocess",
    "standard_corpus_control",
    "derived_portrait_png",
    "derived_oversized_png",
}
CONTROL_GRAPH = {
    "models/control/musiq.xml": {
        "size": 651979,
        "sha256": "0dd4bb0b77223a7d446a19e1d0a8b898a44257c420821c1033b7b8f8bfe3dfd8",
    },
    "models/control/musiq.bin": {
        "size": 108504308,
        "sha256": "09c37d5322ff14e0008f191899eac80f780b97eeea3c5bf27f440964791ba999",
    },
}
CONTROL_REFERENCE_PROTOCOL = "a73c197c2216c99a8038c320309c8837d0f7a9417a21c6f20bb6459ca735861a"
CONTROL_REFERENCE_IDENTITY = "156b2c70250a102d31cd30023f0527ba314d40aa995ff1f639e52b4e8db485b4"


def native_record_hash(record):
    return digest(
        {
            key: value
            for key, value in record.items()
            if key not in {"record_sha256", "elapsed_ms", "peak_rss_bytes"}
        }
    )


def validate_reference(record, item):
    fixed = {
        "id": item["id"],
        "input_sha256": item["input_sha256"],
        "status": "ok",
        "execution_status": "success",
        "execution_devices": ["CPU"],
        "fallback_used": False,
        "model_sha256": MODEL_SHA,
        "model_revision": "pyiqa-musiq-koniq-e95806b9",
        "lower_better": False,
        "input_shape": item["input_shape"],
        "input_color": "RGB",
        "input_dtype": "float32",
        "input_range": [0, 1],
        "preprocess": PREPROCESS,
        "seed": 0,
        "deterministic_algorithms": True,
        "torch_threads": 4,
        "torch_interop_threads": 4,
        "batch_size_actual": 1,
    }
    if item["variant"] == "control":
        fixed.pop("id")  # The unmodified original corpus record retains its original ID.
    if (
        not isinstance(record, dict)
        or any(not exact(record.get(k), v) for k, v in fixed.items())
        or not isinstance(record.get("id"), str)
        or not record["id"]
        or not finite(record.get("score"))
        or not hash_string(record.get("identity"))
        or not hash_string(record.get("protocol_sha256"))
        or record.get("record_sha256") != native_record_hash(record)
        or (
            item["variant"] == "control"
            and (
                record["protocol_sha256"] != CONTROL_REFERENCE_PROTOCOL
                or record["identity"] != CONTROL_REFERENCE_IDENTITY
            )
        )
    ):
        raise ValueError("frozen original native CPU reference evidence invalid")
    if not exact(record["score"], item["reference_score"]):
        raise ValueError("reference score differs from frozen native record")


def reference_asset(root, variant, expected):
    if (
        not isinstance(expected, dict)
        or set(expected) != {"path", "sha256", "size"}
        or expected["path"] != f"references/{variant}.json"
    ):
        raise ValueError("reference asset metadata invalid")
    return bounded_asset(
        root,
        expected["path"],
        {k: expected[k] for k in ("size", "sha256")},
        LIMITS["max_input_bytes"],
    )


def validate_protocol(root, protocol, expected_sha, *, phase):
    root, protocol = clean(root).resolve(), clean(protocol).resolve()
    if (
        not hash_string(expected_sha)
        or not protocol.is_file()
        or protocol.stat().st_size > LIMITS["max_input_bytes"]
        or sha(protocol) != expected_sha
    ):
        raise ValueError("protocol approval fingerprint mismatch")
    p = read(protocol)
    fixed = {
        "schema_version": SCHEMA,
        "phase": phase,
        "checkpoint_sha256": MODEL_SHA,
        "checkpoint_size_bytes": MODEL_SIZE,
        "config": CONFIG,
        "limits": LIMITS,
        "export_gate": EXPORT_GATE,
        "shapes": SHAPES,
        "input_contract": INPUT_CONTRACT,
    }
    dynamic = {"source_inventory_sha256", "preparation", "graphs", "references", "items"}
    if (
        phase not in {"preexport", "evaluation"}
        or not isinstance(p, dict)
        or set(p) != set(fixed) | dynamic
        or any(not exact(p.get(k), v) for k, v in fixed.items())
        or not hash_string(p["source_inventory_sha256"])
    ):
        raise ValueError("protocol differs from frozen native-shape contract")
    preparation = p["preparation"]
    if (
        not isinstance(preparation, dict)
        or set(preparation) != {"path", "sha256", "size"}
        or preparation["path"] != "preparation.json"
    ):
        raise ValueError("preparation asset metadata invalid")
    prep_path = bounded_asset(
        root,
        preparation["path"],
        {k: preparation[k] for k in ("size", "sha256")},
        LIMITS["max_input_bytes"],
    )
    prep = read(prep_path)
    if (
        not isinstance(prep, dict)
        or prep.get("source_inventory_sha256") != p["source_inventory_sha256"]
        or not isinstance(prep.get("items"), list)
        or len(prep["items"]) != 9
    ):
        raise ValueError("preparation must contain structured source metadata")
    prepared = {}
    for metadata in prep["items"]:
        if (
            not isinstance(metadata, dict)
            or not isinstance(metadata.get("id"), str)
            or metadata["id"] in prepared
            or not hash_string(metadata.get("pixel_rgb_uint8_sha256"))
        ):
            raise ValueError("preparation item identity invalid")
        prepared[metadata["id"]] = metadata
    graphs, references = p["graphs"], p["references"]
    if (
        not isinstance(graphs, dict)
        or set(graphs) != set(SHAPES)
        or not isinstance(references, dict)
        or set(references) != set(SHAPES)
        or not exact(graphs["control"], CONTROL_GRAPH)
    ):
        raise ValueError("exact graph/reference variants and reviewed control graph required")
    total_graph_bytes = 0
    for variant in SHAPES:
        graph, ref = graphs[variant], references[variant]
        if phase == "preexport" and variant != "control":
            if graph is not None or ref is not None:
                raise ValueError("preexport new graph/reference must be null")
            continue
        names = {f"models/{variant}/musiq.xml", f"models/{variant}/musiq.bin"}
        if not isinstance(graph, dict) or set(graph) != names:
            raise ValueError("exact variant graph XML/BIN required")
        for name, metadata in graph.items():
            bounded_asset(root, name, metadata, LIMITS["max_graph_bytes"])
        graph_bytes = sum(v["size"] for v in graph.values())
        if graph_bytes > LIMITS["max_graph_bytes"]:
            raise ValueError("variant graph pair exceeds budget")
        total_graph_bytes += graph_bytes
        reference_asset(root, variant, ref)
    if total_graph_bytes > LIMITS["max_total_graph_bytes"]:
        raise ValueError("total graph size budget exceeded")
    items = p["items"]
    if not isinstance(items, list) or len(items) != 9:
        raise ValueError("exactly nine frozen inputs required")
    required = {
        "id",
        "path",
        "input_sha256",
        "input_shape",
        "expected_status",
        "variant",
        "reference_score",
        "source_kind",
        "source_sha256",
    }
    ids, paths, hashes, variants = set(), set(), set(), []
    for item in items:
        if (
            not isinstance(item, dict)
            or set(item) != required
            or not isinstance(item["id"], str)
            or not 0 < len(item["id"]) <= 256
            or item["id"] in ids
            or not hash_string(item["input_sha256"])
            or item["input_sha256"] in hashes
            or not hash_string(item["source_sha256"])
            or item["source_kind"] not in SOURCE_KINDS
        ):
            raise ValueError("input metadata invalid or duplicate")
        name = item["path"]
        if (
            not isinstance(name, str)
            or len(name.split("/")) != 2
            or name.split("/")[0] != "images"
            or Path(name).suffix not in {".jpg", ".png"}
            or not hash_string(Path(name).stem)
            or name in paths
        ):
            raise ValueError("unsafe or duplicate image path")
        shape = item["input_shape"]
        if (
            not isinstance(shape, list)
            or len(shape) != 4
            or not all(integer(n) for n in shape)
            or shape[:2] != [1, 3]
            or shape[2] * shape[3] > LIMITS["max_decode_pixels"]
        ):
            raise ValueError("input shape metadata invalid")
        metadata = prepared.get(item["id"], {})
        expected_metadata = {
            "input_sha256": item["input_sha256"],
            "shape": shape,
            "source_kind": item["source_kind"],
            "source_sha256": item["source_sha256"],
        }
        if any(not exact(metadata.get(k), v) for k, v in expected_metadata.items()):
            raise ValueError("input differs from frozen preparation metadata")
        actual_variant = next((k for k, v in SHAPES.items() if exact(shape, v)), None)
        variant = item["variant"]
        if actual_variant is None:
            if (
                item["expected_status"] != "unsupported_shape"
                or variant is not None
                or item["reference_score"] is not None
            ):
                raise ValueError("unsupported shape cannot have graph or reference score")
        else:
            if (
                variant != actual_variant
                or item["expected_status"] != "supported"
                or max(shape[2:]) > LIMITS["max_supported_side"]
            ):
                raise ValueError("only exact supported variant dispatch allowed")
            variants.append(variant)
            if phase == "preexport" and variant != "control":
                if item["reference_score"] is not None:
                    raise ValueError("preexport new reference score must be null")
            else:
                reference = read(reference_asset(root, variant, references[variant]))
                validate_reference(reference, item)
                if variant == "control" and (
                    metadata.get("original_id") != reference["id"]
                    or metadata.get("reference_record_sha256") != reference["record_sha256"]
                ):
                    raise ValueError("control original reference join differs from preparation")
        path = relative(root, name)
        if (
            not path.is_file()
            or not 0 < path.stat().st_size <= LIMITS["max_input_bytes"]
            or sha(path) != item["input_sha256"]
        ):
            raise ValueError("input size/hash identity invalid")
        image_array(path, shape, max_pixels=LIMITS["max_decode_pixels"])
        ids.add(item["id"])
        paths.add(name)
        hashes.add(item["input_sha256"])
    if sorted(variants) != sorted(SHAPES):
        raise ValueError("exactly three supported variants and six unsupported inputs required")
    return p


def export(root, protocol, expected_sha, checkpoint, output, openvino_site, variant):
    if variant not in {"landscape", "portrait"}:
        raise ValueError("only new landscape/portrait graphs may be exported")
    if checkpoint is None:
        raise ValueError("explicit existing checkpoint required")
    started = time.monotonic()
    root = clean(root).resolve()
    p = validate_protocol(root, protocol, expected_sha, phase="preexport")
    check_resources(started, EXPORT_LIMITS)
    protected = [checkpoint, Path(__file__).with_name("benchmark_public_musiq.py")]
    if openvino_site is not None:
        protected.append(openvino_site)
    output = output_dir(root, protocol, output, protected)
    item = next(item for item in p["items"] if item["variant"] == variant)
    try:
        receipt = export_native(
            relative(root, item["path"]),
            item,
            variant,
            checkpoint,
            output,
            openvino_site,
            expected_sha,
        )
        validate_protocol(root, protocol, expected_sha, phase="preexport")
        check_resources(started, EXPORT_LIMITS)
        receipt["elapsed_seconds"] = time.monotonic() - started
        receipt["peak_rss_bytes"] = peak_rss()
        atomic(output / "export-receipt.json", receipt)
        return receipt
    except Exception as exc:
        atomic(
            output / "export-receipt.json",
            {
                "status": "incomplete",
                "variant": variant,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "protocol_sha256": expected_sha,
            },
        )
        raise


def record_base(identity, item):
    return {
        "identity": identity,
        "id": item["id"],
        "input_sha256": item["input_sha256"],
        "input_shape": item["input_shape"],
    }


def valid_record(record, identity, item):
    if not isinstance(record, dict):
        return False
    saved = {k: v for k, v in record.items() if k != "record_sha256"}
    try:
        if record.get("record_sha256") != digest(saved):
            return False
    except TypeError, ValueError:
        return False
    base = record_base(identity, item)
    if any(not exact(record.get(k), v) for k, v in base.items()):
        return False
    if item["expected_status"] == "unsupported_shape":
        fixed = {
            **base,
            "status": "unsupported_shape",
            "graph_selected": False,
            "score_produced": False,
        }
        return set(saved) == set(fixed) and all(exact(saved[k], v) for k, v in fixed.items())
    fixed = {
        **base,
        "status": "ok",
        "variant": item["variant"],
        "reference_score": item["reference_score"],
        "execution_devices": ["CPU"],
        "fallback_used": False,
        "inference_precision": "f32",
        "threads": 4,
        "streams": 1,
    }
    return (
        set(saved) == set(fixed) | {"scores", "elapsed_seconds"}
        and all(exact(saved.get(k), v) for k, v in fixed.items())
        and isinstance(saved["scores"], list)
        and len(saved["scores"]) == 2
        and all(finite(score) for score in saved["scores"])
        and finite(saved["elapsed_seconds"])
        and saved["elapsed_seconds"] >= 0
    )


def evaluate(root, protocol, expected_sha, output):
    started = time.monotonic()
    root = clean(root).resolve()
    p = validate_protocol(root, protocol, expected_sha, phase="evaluation")
    check_resources(started, LIMITS)
    output = output_dir(root, protocol, output)
    records, reused, native_inferences, status = [], 0, 0, "incomplete"
    runner_hashes = {Path(__file__).name: sha(__file__), HELPER_SOURCE.name: sha(HELPER_SOURCE)}
    with owned_cache(output), offline():
        ov = __import__("openvino")
        provenance = {
            "protocol_sha256": expected_sha,
            "source_hashes": runner_hashes,
            "graphs": p["graphs"],
            "references": p["references"],
            "preparation": p["preparation"],
            "source_inventory_sha256": p["source_inventory_sha256"],
            "runtime_versions": runtime_versions(ov),
            "config": CONFIG,
        }
        identity = digest(provenance)

        def checkpoint():
            atomic(
                output / "checkpoint.json",
                {
                    "identity": identity,
                    "status": status,
                    "processed": len(records),
                    "total": 9,
                    "new_native_inferences": native_inferences,
                },
            )

        checkpoint()
        try:
            core, compiled = None, {}
            for item in p["items"]:
                variant = item["variant"]
                if variant is not None and variant not in compiled:
                    if core is None:
                        core = ov.Core()
                    compiled[variant] = compiled_graph(core, root, variant)
                    check_resources(started, LIMITS)
                path = clean(output / "predictions" / (digest(item["id"]) + ".json"))
                try:
                    record = read(path) if path.exists() else None
                except json.JSONDecodeError, UnicodeDecodeError:
                    record = None
                if valid_record(record, identity, item):
                    reused += 1
                elif item["expected_status"] == "unsupported_shape":
                    record = {
                        **record_base(identity, item),
                        "status": "unsupported_shape",
                        "graph_selected": False,
                        "score_produced": False,
                    }
                    record["record_sha256"] = digest(record)
                    atomic(path, record)
                else:
                    graph = compiled[variant]
                    array = image_array(
                        relative(root, item["path"]),
                        item["input_shape"],
                        max_pixels=LIMITS["max_decode_pixels"],
                    )
                    scores, timer = [], time.monotonic()
                    for _ in range(2):
                        native_inferences += 1
                        checkpoint()
                        scores.append(scalar_result(graph([array])[graph.output()]))
                        check_resources(started, LIMITS)
                    if (
                        list(graph.get_property("EXECUTION_DEVICES")) != ["CPU"]
                        or str(graph.get_property("INFERENCE_PRECISION_HINT"))
                        != "<Type: 'float32'>"
                    ):
                        raise ValueError("actual CPU/F32 execution changed during inference")
                    record = {
                        **record_base(identity, item),
                        "status": "ok",
                        "variant": variant,
                        "scores": scores,
                        "reference_score": item["reference_score"],
                        "execution_devices": ["CPU"],
                        "fallback_used": False,
                        "inference_precision": "f32",
                        "threads": 4,
                        "streams": 1,
                        "elapsed_seconds": time.monotonic() - timer,
                    }
                    record["record_sha256"] = digest(record)
                    atomic(path, record)
                records.append(record)
                checkpoint()
                check_resources(started, LIMITS)
            validate_protocol(root, protocol, expected_sha, phase="evaluation")
            if any(
                sha(source) != runner_hashes[source.name]
                for source in (Path(__file__), HELPER_SOURCE)
            ):
                raise ValueError("runner/helper source identity changed during run")
            check_resources(started, LIMITS)
            successes = [record for record in records if record["status"] == "ok"]
            errors = [
                max(abs(score - record["reference_score"]) for score in record["scores"])
                for record in successes
            ]
            repeat_errors = [abs(record["scores"][0] - record["scores"][1]) for record in successes]
            passed = (
                len(successes) == 3
                and len(records) == 9
                and max(errors) <= LIMITS["max_abs_error"]
                and max(repeat_errors) <= LIMITS["max_repeat_error"]
            )
            status = "passed" if passed else "parity_failed"
            report = {
                "schema_version": SCHEMA,
                "status": status,
                "complete": True,
                "identity": identity,
                "provenance": provenance,
                "successful": 3,
                "unsupported": 6,
                "failures": 0,
                "cache_reused": reused,
                "new_native_inferences": native_inferences,
                "records": records,
                "max_abs_error": max(errors),
                "mean_abs_error": sum(errors) / 3,
                "max_repeat_error": max(repeat_errors),
                "execution_devices": ["CPU"],
                "fallback_used": False,
                "elapsed_seconds": time.monotonic() - started,
                "peak_rss_bytes": peak_rss(),
                "limitations": "Three exact supported shapes; no quality bootstrap, MOS labels, "
                "policy admission or actual RAW portrait acceptance.",
            }
        except Exception as exc:
            status = "incomplete"
            report = {
                "schema_version": SCHEMA,
                "status": status,
                "complete": False,
                "identity": identity,
                "provenance": provenance,
                "records": records,
                "successful": sum(r["status"] == "ok" for r in records),
                "unsupported": sum(r["status"] == "unsupported_shape" for r in records),
                "failures": 1,
                "cache_reused": reused,
                "new_native_inferences": native_inferences,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "elapsed_seconds": time.monotonic() - started,
                "peak_rss_bytes": peak_rss(),
            }
        checkpoint()
        atomic(output / "report.json", report)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "evaluate"))
    for name in ("root", "protocol", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--openvino-site", type=Path)
    parser.add_argument("--variant", choices=("landscape", "portrait"))
    args = parser.parse_args()
    if args.action == "export":
        result = export(
            args.root,
            args.protocol,
            args.protocol_sha256,
            args.checkpoint,
            args.output,
            args.openvino_site,
            args.variant,
        )
    else:
        if args.checkpoint or args.openvino_site or args.variant:
            parser.error("evaluate does not accept export-only options")
        result = evaluate(args.root, args.protocol, args.protocol_sha256, args.output)
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"records", "provenance", "source_hashes"}
            },
            allow_nan=False,
        )
    )
    return 0 if result["status"] in {"passed", "exported_not_yet_parity_verified"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
