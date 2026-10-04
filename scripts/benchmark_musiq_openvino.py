#!/usr/bin/env python3
"""Fixed-shape MUSIQ conversion/parity diagnostic; never promote production policy."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import resource
import socket
import sys
import tempfile
import time
import urllib.request
from unittest.mock import patch

sys.dont_write_bytecode = True
SCHEMA = "material-agent.musiq-openvino-parity.v1"
SHAPE = [1, 3, 384, 512]
MODEL_SHA = "e95806b9eae5f3814c410f574ba8e552362bd5bc63d758ed5b97860f5d6185aa"
CONFIG = {"device": "CPU", "threads": 4, "streams": 1, "precision": "f32"}
LIMITS = {
    "max_items": 32,
    "max_seconds": 900,
    "max_rss_bytes": 2500000000,
    "max_graph_bytes": 150000000,
    "max_abs_error": 0.001,
    "max_repeat_error": 0.000001,
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def clean(path):
    p = Path(path).absolute()
    if any(part.is_symlink() for part in (p, *p.parents)):
        raise ValueError("symlink in experiment path")
    return p


def read(path):
    p = clean(path)
    if not p.is_file() or p.stat().st_size > 16777216:
        raise ValueError("bounded regular JSON required")
    return json.loads(p.read_text())


def atomic(path, value):
    p = clean(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = clean(p.with_suffix(p.suffix + ".partial"))
    with tmp.open("w") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, p)


def relative(root, name):
    p = PurePosixPath(name)
    if (
        not name
        or p.is_absolute()
        or p.as_posix() != name
        or any(part in {".", ".."} or part.startswith(".") for part in name.split("/"))
    ):
        raise ValueError("unsafe protocol path")
    out = clean(root / name)
    if not out.is_relative_to(root):
        raise ValueError("path outside experiment root")
    return out


@contextmanager
def offline():
    def denied(*args, **kwargs):
        raise RuntimeError("network forbidden by MUSIQ parity protocol")

    with (
        patch.object(socket, "socket", denied),
        patch.object(socket, "create_connection", denied),
        patch.object(urllib.request, "urlopen", denied),
        patch.object(urllib.request, "urlretrieve", denied),
    ):
        yield


@contextmanager
def owned_cache(output):
    keys = {
        "XDG_CACHE_HOME": str(output / "runtime-cache"),
        "TORCH_HOME": str(output / "runtime-cache/torch"),
        "TMPDIR": str(output / "tmp"),
    }
    previous = {key: os.environ.get(key) for key in keys}
    previous_tempdir = tempfile.tempdir
    for value in keys.values():
        clean(value).mkdir(parents=True, exist_ok=True)
    os.environ.update(keys)
    tempfile.tempdir = keys["TMPDIR"]
    try:
        yield
    finally:
        tempfile.tempdir = previous_tempdir
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def image_array(path):
    import numpy as np
    from PIL import Image

    with Image.open(io.BytesIO(Path(path).read_bytes())) as image:
        if image.size != (512, 384):
            raise ValueError("only frozen 512x384 images supported")
        array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    return np.ascontiguousarray(array.transpose(2, 0, 1)[None])


def validate_protocol(root, protocol, expected_sha, *, graph=True):
    root = clean(root).resolve()
    if sha(protocol) != expected_sha:
        raise ValueError("protocol approval fingerprint mismatch")
    p = read(protocol)
    if (
        p["schema_version"] != SCHEMA
        or p["input_shape"] != SHAPE
        or p["config"] != CONFIG
        or p["limits"] != LIMITS
        or p["checkpoint_sha256"] != MODEL_SHA
    ):
        raise ValueError("protocol settings differ from frozen runtime contract")
    items = p["items"]
    if len(items) != LIMITS["max_items"] or len({item["id"] for item in items}) != len(items):
        raise ValueError("exactly 32 unique frozen inputs required")
    if any(sum(item["track"] == track for item in items) != 16 for track in ("koniq", "kadid")):
        raise ValueError("exactly sixteen inputs per track required")
    for item in items:
        path = relative(root, item["path"])
        if sha(path) != item["input_sha256"] or not math.isfinite(item["reference_score"]):
            raise ValueError("input/reference identity invalid")
        image_array(path)
    if graph:
        if set(p["graph"]) != {"models/musiq.xml", "models/musiq.bin"}:
            raise ValueError("exactly the reviewed XML/BIN graph required")
        total = 0
        for name, expected in p["graph"].items():
            path = relative(root, name)
            if sha(path) != expected["sha256"] or path.stat().st_size != expected["size"]:
                raise ValueError("graph identity mismatch")
            total += path.stat().st_size
        if total > LIMITS["max_graph_bytes"]:
            raise ValueError("graph exceeds frozen size bound")
    return p


def output_dir(root, output):
    root, output = clean(root).resolve(), clean(output).resolve()
    if output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("output must be separate from protected inputs")
    output.mkdir(parents=True, exist_ok=True)
    return output


def export(root, protocol, expected_sha, checkpoint, output, openvino_site):
    p = validate_protocol(root, protocol, expected_sha, graph=False)
    output = output_dir(root, output)
    if any(clean(path).resolve().is_relative_to(output) for path in (protocol, checkpoint)):
        raise ValueError("output contains protected protocol/checkpoint")
    if sha(checkpoint) != MODEL_SHA or Path(checkpoint).stat().st_size != 108610983:
        raise ValueError("checkpoint mismatch")
    if openvino_site:
        sys.path.append(str(clean(openvino_site).resolve()))
    source = Path(__file__).with_name("benchmark_public_musiq.py")
    spec = importlib.util.spec_from_file_location("frozen_musiq", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    started = time.monotonic()
    with owned_cache(output), module.offline_guard() as stack:
        runtime = module.CpuMusiq(checkpoint, stack)
        import openvino as ov
        import pyiqa.data.multiscale_trans_util as util

        torch = runtime.torch
        tensor = torch.from_numpy(
            image_array(relative(Path(root).resolve(), p["items"][0]["path"]))
        )

        # Preserve the installed bicubic operator and known aspect ratio. Python round
        # cannot consume trace-derived sizes; specialize only the frozen spatial shape.
        def fixed_resize(image, h, w, longer_side_length):
            sizes = {224: (168, 224), 384: (288, 384)}
            if longer_side_length not in sizes:
                raise ValueError("unexpected MUSIQ scale")
            height, width = sizes[longer_side_length]
            return (
                torch.nn.functional.interpolate(
                    image, (height, width), mode="bicubic", align_corners=False
                ),
                height,
                width,
            )

        eager_errors = []
        with torch.inference_mode():
            tokens = util.get_multiscale_patches(
                (tensor - 0.5) * 2, **runtime.metric.net.data_preprocess_opts
            )
            with patch.object(util, "resize_preserve_aspect_ratio", fixed_resize):
                fixed_tokens = util.get_multiscale_patches(
                    (tensor - 0.5) * 2, **runtime.metric.net.data_preprocess_opts
                )
            if not torch.equal(tokens, fixed_tokens):
                raise ValueError("specialized preprocessing differs from native tokens")
            for item in p["items"]:
                sample = torch.from_numpy(image_array(relative(Path(root).resolve(), item["path"])))
                native = float(runtime.metric(sample).item())
                with patch.object(util, "resize_preserve_aspect_ratio", fixed_resize):
                    specialized = float(runtime.metric.net(sample).item())
                error = max(abs(native - specialized), abs(native - item["reference_score"]))
                if not math.isfinite(error) or error > p["export_gate"]["eager_max_abs_error"]:
                    raise ValueError("native/specialized/parent eager parity failed")
                eager_errors.append(error)
        with (
            torch.inference_mode(),
            patch.object(util, "resize_preserve_aspect_ratio", fixed_resize),
        ):
            traced = torch.jit.trace(runtime.metric.net, tensor, strict=True, check_trace=True)
            converted = ov.convert_model(traced, input=[SHAPE], share_weights=False)
        ov.save_model(converted, output / "musiq.xml", compress_to_fp16=False)
        graph = {
            "models/" + path.name: {"size": path.stat().st_size, "sha256": sha(path)}
            for path in (output / "musiq.xml", output / "musiq.bin")
        }
        if sum(v["size"] for v in graph.values()) > LIMITS["max_graph_bytes"]:
            raise ValueError("export graph exceeds budget")
        receipt = {
            "status": "exported_not_yet_parity_verified",
            "graph": graph,
            "checkpoint_sha256": MODEL_SHA,
            "protocol_sha256": expected_sha,
            "shape": SHAPE,
            "fp16_compression": False,
            "resize_specialization": {"224": [168, 224], "384": [288, 384]},
            "eager_inputs": len(eager_errors),
            "eager_max_abs_error": max(eager_errors),
            "preprocess_tokens_equal": True,
            "preprocess_token_shape": list(tokens.shape),
            "source_hashes": {
                str(source.name): sha(source),
                Path(__file__).name: sha(__file__),
                "musiq_arch.py": sha(sys.modules[runtime.metric.net.__class__.__module__].__file__),
                "multiscale_trans_util.py": sha(util.__file__),
            },
            "openvino_version": ov.__version__,
            "torch_version": torch.__version__,
            "elapsed_seconds": time.monotonic() - started,
        }
        atomic(output / "export-receipt.json", receipt)
        return receipt


def valid_record(record, identity, item):
    if not isinstance(record, dict):
        return False
    saved = dict(record)
    checksum = saved.pop("record_sha256", None)
    try:
        actual_checksum = digest(saved)
    except TypeError, ValueError:
        return False
    return (
        checksum == actual_checksum
        and record.get("identity") == identity
        and record.get("id") == item["id"]
        and record.get("input_sha256") == item["input_sha256"]
        and record.get("execution_devices") == ["CPU"]
        and record.get("fallback_used") is False
        and isinstance(record.get("scores"), list)
        and len(record["scores"]) == 2
        and all(type(score) in (int, float) and math.isfinite(score) for score in record["scores"])
    )


def evaluate(root, protocol, expected_sha, output):
    import importlib.metadata
    import numpy as np
    import openvino as ov

    started = time.monotonic()
    root = clean(root).resolve()
    output = output_dir(root, output)
    p = validate_protocol(root, protocol, expected_sha)
    provenance = {
        "protocol_sha256": expected_sha,
        "runner_sha256": sha(__file__),
        "graph": p["graph"],
        "python": sys.version,
        "platform": sys.platform,
        "openvino": ov.__version__,
        "numpy": importlib.metadata.version("numpy"),
        "pillow": importlib.metadata.version("Pillow"),
        "config": CONFIG,
    }
    identity = digest(provenance)
    records, reused, status = [], 0, "incomplete"

    def checkpoint():
        atomic(
            output / "checkpoint.json",
            {"identity": identity, "status": status, "processed": len(records), "total": 32},
        )

    checkpoint()
    try:
        with owned_cache(output), offline():
            core = ov.Core()
            model = core.read_model(root / "models/musiq.xml")
            if (
                len(model.inputs) != 1
                or list(model.input().shape) != SHAPE
                or len(model.outputs) != 1
            ):
                raise ValueError("exported graph shape/output contract mismatch")
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
            devices = list(compiled.get_property("EXECUTION_DEVICES"))
            if (
                devices != ["CPU"]
                or str(compiled.get_property("INFERENCE_PRECISION_HINT")) != "<Type: 'float32'>"
            ):
                raise ValueError("actual CPU/FP32 execution readback required")
            for item in p["items"]:
                path = output / "predictions" / (digest(item["id"]) + ".json")
                try:
                    record = read(path) if path.exists() else None
                except json.JSONDecodeError, UnicodeDecodeError:
                    record = None
                if record and valid_record(record, identity, item):
                    reused += 1
                else:
                    array = image_array(relative(root, item["path"]))
                    scores = []
                    timer = time.monotonic()
                    for _ in range(2):
                        result = np.asarray(compiled([array])[compiled.output()])
                        if result.size != 1 or not np.isfinite(result).all():
                            raise ValueError("finite single raw MUSIQ output required")
                        scores.append(float(result.item()))
                    record = {
                        "identity": identity,
                        "id": item["id"],
                        "input_sha256": item["input_sha256"],
                        "scores": scores,
                        "execution_devices": devices,
                        "fallback_used": False,
                        "elapsed_seconds": time.monotonic() - timer,
                    }
                    record["record_sha256"] = digest(record)
                    atomic(path, record)
                records.append(record)
                checkpoint()
                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
                    1 if sys.platform == "darwin" else 1024
                )
                if (
                    time.monotonic() - started > LIMITS["max_seconds"]
                    or rss > LIMITS["max_rss_bytes"]
                ):
                    raise ValueError("resource bound exceeded")
        validate_protocol(root, protocol, expected_sha)
        errors = [
            abs(r["scores"][0] - item["reference_score"])
            for r, item in zip(records, p["items"], strict=True)
        ]
        repeat_errors = [abs(r["scores"][0] - r["scores"][1]) for r in records]
        passed = (
            max(errors) <= LIMITS["max_abs_error"]
            and max(repeat_errors) <= LIMITS["max_repeat_error"]
        )
        status = "passed" if passed else "parity_failed"
        report = {
            "schema_version": SCHEMA,
            "status": status,
            "complete": True,
            "identity": identity,
            "provenance": provenance,
            "successful": 32,
            "failures": 0,
            "cache_reused": reused,
            "max_abs_error": max(errors),
            "mean_abs_error": sum(errors) / len(errors),
            "max_repeat_error": max(repeat_errors),
            "execution_devices": devices,
            "fallback_used": False,
            "elapsed_seconds": time.monotonic() - started,
            "peak_rss_bytes": rss,
            "records": records,
            "limitations": "Fixed shape/corpus parity only; no production policy admission or controlled speedup.",
        }
    except Exception as exc:
        report = {
            "schema_version": SCHEMA,
            "status": "incomplete",
            "complete": False,
            "identity": identity,
            "successful": len(records),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "provenance": provenance,
            "records": records,
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
    args = parser.parse_args()
    if args.action == "export":
        result = export(
            args.root,
            args.protocol,
            args.protocol_sha256,
            args.checkpoint,
            args.output,
            args.openvino_site,
        )
    else:
        result = evaluate(args.root, args.protocol, args.protocol_sha256, args.output)
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"records", "provenance", "source_hashes"}
            }
        )
    )
    return 0 if result["status"] in {"exported_not_yet_parity_verified", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
