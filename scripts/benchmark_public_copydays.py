#!/usr/bin/env python3
"""Frozen offline Copydays correspondence experiment, never a culling/rejection claim."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager, ExitStack
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import resource
import socket
import sys
import tempfile
import time
import urllib.request
from unittest.mock import patch

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
# Resolve the installed package before the immutable helper adjusts sys.path.
embedding = importlib.import_module("material_agent.adapters.models.openvino_embedding")
SPEC = importlib.util.spec_from_file_location(
    "copydays_composite_helpers", REPO / "scripts/benchmark_public_composite.py"
)
base = importlib.util.module_from_spec(SPEC)
_saved_path = list(sys.path)
SPEC.loader.exec_module(base)
sys.path[:] = _saved_path
np = importlib.import_module("numpy")
SCHEMA = "material-agent.public-copydays-protocol.v1"
CONFIG = {
    "device": "CPU",
    "fallback_device": "",
    "allow_batch_fallback": False,
    "batch_size": 1,
    "infer_requests": 1,
    "max_in_flight": 1,
    "performance_hint": "THROUGHPUT",
    "offline": True,
    "preprocessing": "existing adapter 224 RGB ImageNet mean/std; normalized CLS",
    "similarity": "cosine descending then lexicographic gallery id",
    "baseline": "64-bit pHash Hamming ascending then lexicographic gallery id",
    "calibration": "none",
}
LIMITS = {
    "max_failure_count": 8,
    "max_images": 386,
    "process_budget_seconds": 1800,
    "max_peak_rss_bytes": 2000000000,
}
STATISTICS = {
    "replicates": 2000,
    "seed": 20261003,
    "confidence_level": 0.95,
    "method": "paired percentile bootstrap candidate-minus-baseline top1 and MRR",
    "resampling_units": "whole source_id query families; fixed complete gallery",
    "scope": "conditional fixed-corpus sampling uncertainty only",
}
EXPOSURE = (
    "Exact training overlap unknown; LVD public images may include exposure. "
    "Copydays correspondences are not semantic coverage or rejection evidence. "
    "No generalization, tuning, fusion or promotion claim."
)
MODEL_SHA = "7686e8c849202c4fdd67d1cd336449c29bdddbcca535d765d3014f50d04d516d"
EXTERNAL_SHA = "51572f7fc3c272eb574a70509ea1eeb7e674e5ca2cd96fec1632edb38983d529"
PROCESSOR_SHA = "960c41d1f3a7778b936365769a2d90550b318a6c0a53a0296957adacfe5e0dd7"
VERSIONS = ("openvino", "onnx", "numpy", "Pillow", "ImageHash")
PARENT_RUNTIME = {"python": "3.14.3", "numpy": "2.4.4", "pillow": "11.3.0", "imagehash": "4.3.2"}


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def hash_file(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for data in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(data)
    return result.hexdigest()


def read_json(path):
    if path.stat().st_size > 50000000:
        raise ValueError("JSON exceeds 50 MB")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("JSON must be a mapping")
    return value


def baseline_sources(root):
    paths = {"benchmark_public_composite.py": REPO / "scripts/benchmark_public_composite.py"}
    for name in ("clients/local.py", "utils/constants.py"):
        path = root / "src/material_agent" / name
        paths[name] = path if path.is_file() else REPO / "src/material_agent" / name
    return paths


def model_assets(model_path, processor_path):
    assets = embedding._model_bundle_assets(model_path, processor_path)
    result = {
        name: {"sha256": hash_file(path), "size_bytes": path.stat().st_size}
        for name, path in assets
    }
    models = [v for k, v in result.items() if k.startswith("model/")]
    external = [v for k, v in result.items() if k.startswith("external/")]
    processors = [v for k, v in result.items() if k.startswith("processor/")]
    if (
        models != [{"sha256": MODEL_SHA, "size_bytes": 183889}]
        or external != [{"sha256": EXTERNAL_SHA, "size_bytes": 21762048}]
        or processors != [{"sha256": PROCESSOR_SHA, "size_bytes": 585}]
    ):
        raise ValueError("model bundle differs from the single frozen DINOv3 candidate")
    return result, [p for _, p in assets]


def build_protocol(root, manifest, baseline, model_path, processor_path):
    """Controller freezes this exact object before any native inference."""
    root = root.resolve()
    payload = base.load_manifest(manifest, root)
    parent = read_json(baseline)
    items = sorted((i for i in payload["items"] if i["track"] == "copydays"), key=lambda i: i["id"])
    galleries = [i for i in items if i["role"] == "gallery"]
    queries = [i for i in items if i["role"] == "query"]
    if len(galleries) != 157 or len(queries) != 229 or len(items) != LIMITS["max_images"]:
        raise ValueError("protocol requires all 157 gallery originals and 229 strong queries")
    if any(not i["id"].startswith("copydays:query:strong:") for i in queries):
        # Native manifest currently uses a flat query ID; the path carries the release split.
        if any("copydays-strong" not in i["path"] for i in queries):
            raise ValueError("protocol requires native strong query split")
    assets, _ = model_assets(model_path, processor_path)
    frozen_items = []
    for item in items:
        feature = baseline.parent / "features" / (base.digest(item["id"].encode()) + ".json")
        frozen_items.append(
            {
                **{k: item[k] for k in ("id", "path", "role", "source_id", "sha256")},
                "baseline_feature_sha256": hash_file(feature),
            }
        )
    return {
        "schema_version": SCHEMA,
        "candidate": "dinov3-vits16-openvino-cls",
        "config": CONFIG,
        "limits": LIMITS,
        "statistics": STATISTICS,
        "training_exposure": EXPOSURE,
        "manifest_sha256": hash_file(manifest),
        "parent_baseline_sha256": hash_file(baseline),
        "parent_baseline_identity": parent["identity"],
        "parent_config_identity": parent["config_identity"],
        "parent_runtime": PARENT_RUNTIME,
        "model_assets": assets,
        "items": frozen_items,
        "source_code_sha256": {k: hash_file(p) for k, p in baseline_sources(root).items()},
        "counts": {
            "gallery": len(galleries),
            "query": len(queries),
            "source_families": len({i["source_id"] for i in galleries}),
        },
    }


def guard_output(output, protected, baseline):
    base.reject_symlinks(output.absolute(), descendants=True)
    output = output.resolve()
    if output.is_relative_to(baseline.parent.resolve()) or any(
        p.resolve().is_relative_to(output) for p in protected
    ):
        raise ValueError("output overlaps protected corpus, baseline, model or protocol")
    return output


def runtime_identity():
    modules = [
        embedding,
        importlib.import_module("material_agent.adapters.models.openvino_session"),
        importlib.import_module("material_agent.adapters.models.inference_contract"),
    ]
    paths = {Path(__file__).resolve(), REPO / "scripts/benchmark_public_composite.py"}
    paths.update(Path(m.__file__).resolve() for m in modules)
    versions = {name: importlib.metadata.version(name) for name in VERSIONS}
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": versions,
        "source_code_sha256": {str(p): hash_file(p) for p in sorted(paths)},
    }


def preflight(root, manifest, baseline, protocol, model_path, processor_path, output):
    plan = read_json(protocol)
    protocol_sha = hash_file(protocol)
    approved_sha = os.environ.get("COPYDAYS_PROTOCOL_SHA256", "")
    if len(approved_sha) != 64 or protocol_sha != approved_sha:
        raise ValueError("protocol SHA256 must match controller-reviewed COPYDAYS_PROTOCOL_SHA256")
    root = root.resolve()
    _, asset_paths = model_assets(model_path, processor_path)
    source = base.load_manifest(manifest, root)
    protected = [
        manifest,
        baseline,
        protocol,
        *asset_paths,
        *baseline.parent.joinpath("features").rglob("*"),
        *baseline_sources(root).values(),
        *(root / i["path"] for i in source["items"]),
    ]
    output = guard_output(output, protected, baseline)
    expected = build_protocol(root, manifest, baseline, model_path, processor_path)
    if plan != expected:
        raise ValueError("protocol differs from frozen full cohort or settings")
    parent = read_json(baseline)
    if (
        parent.get("schema_version") != base.SCHEMA
        or parent.get("manifest_sha256") != hash_file(manifest)
        or parent.get("identity")
        != digest_json(
            {
                "config_identity": parent.get("config_identity"),
                "inputs": parent.get("input_fingerprints"),
            }
        )
        or parent.get("selected_membership_sha256")
        != base.digest(json.dumps(parent.get("selected_ids")).encode())
        or parent.get("selected_ids") != sorted(set(parent.get("selected_ids", [])))
        or set(parent["selected_ids"]) != set(parent.get("input_fingerprints", {}))
    ):
        raise ValueError("invalid immutable baseline identity or membership")
    # Recompute the original recipe from the baseline's exact source snapshots/runtime pins.
    parent_config = parent["config"]
    if parent_config != {
        "limit_per_track": 1024,
        "selection": "sha256-id ascending",
        "quality": "local heuristic default; all learned models disabled",
        "copy": "phash64",
    }:
        raise ValueError("baseline is not the unchanged baseline-1024 pHash operator")
    original_identity = digest_json(
        {
            "manifest": hash_file(manifest),
            "config": parent_config,
            "code": [
                plan["source_code_sha256"][name]
                for name in (
                    "benchmark_public_composite.py",
                    "clients/local.py",
                    "utils/constants.py",
                )
            ],
            **plan["parent_runtime"],
        }
    )
    if original_identity != parent["config_identity"]:
        raise ValueError("baseline source/runtime config identity differs")
    if parent["selected_ids"] != [i["id"] for i in base.select_items(source["items"], 1024)]:
        raise ValueError("baseline cohort differs from immutable selection recipe")
    records = {}
    frozen_files = {
        str(p.resolve()): hash_file(p)
        for p in [manifest, baseline, protocol, *asset_paths, *baseline_sources(root).values()]
    }
    for item in plan["items"]:
        key = item["id"]
        path = root / item["path"]
        base.reject_symlinks(path)
        actual = hash_file(path)
        if actual != item["sha256"] or actual != parent["input_fingerprints"].get(key):
            raise ValueError("frozen source SHA256 mismatch")
        feature = baseline.parent / "features" / (base.digest(key.encode()) + ".json")
        base.reject_symlinks(feature)
        cached = read_json(feature)
        fingerprint = base.digest((parent["config_identity"] + actual).encode())
        if (
            not base.valid_cached(cached, fingerprint)
            or cached.get("id") != key
            or cached.get("input_sha256") != actual
            or cached.get("scoring_mode") != "heuristic"
        ):
            raise ValueError("stale or corrupt baseline feature")
        records[key] = cached
        frozen_files[str(path.resolve())] = actual
        frozen_files[str(feature.resolve())] = item["baseline_feature_sha256"]
    runtime = runtime_identity()
    frozen_files.update(runtime["source_code_sha256"])
    identity = digest_json({"protocol_sha256": protocol_sha, "runtime": runtime})
    return {
        "plan": plan,
        "parent": parent,
        "baseline_records": records,
        "identity": identity,
        "protocol_sha256": protocol_sha,
        "runtime": runtime,
        "frozen_files": frozen_files,
        "output": output,
        "items": plan["items"],
    }


def denied(*args, **kwargs):
    raise RuntimeError("network/download forbidden by frozen offline Copydays protocol")


@contextmanager
def offline_guard():
    with ExitStack() as stack:
        for obj, names in (
            (socket.socket, ("connect", "connect_ex", "sendto", "sendmsg")),
            (socket, ("create_connection", "getaddrinfo")),
            (urllib.request, ("urlopen", "urlretrieve")),
        ):
            for name in names:
                if hasattr(obj, name):
                    stack.enter_context(patch.object(obj, name, denied))
        yield stack


def block_download_helpers(stack):
    names = {
        "hf_hub_download",
        "snapshot_download",
        "cached_download",
        "download_url",
        "download_url_to_file",
        "load_state_dict_from_url",
        "load_file_from_url",
    }
    for module_name, module in list(sys.modules.items()):
        if module is not None and module_name.startswith(
            ("torch", "huggingface_hub", "transformers")
        ):
            for name in names & vars(module).keys():
                if callable(getattr(module, name)):
                    stack.enter_context(patch.object(module, name, denied))


@contextmanager
def isolated_homes(output):
    home = output / "runtime-home"
    paths = {
        "XDG_CACHE_HOME": home / "cache",
        "HF_HOME": home / "hf",
        "TMPDIR": home / "tmp",
        "TMP": home / "tmp",
        "TEMP": home / "tmp",
    }
    for path in paths.values():
        base.reject_symlinks(path)
        path.mkdir(parents=True, exist_ok=True)
    env = {k: str(v) for k, v in paths.items()}
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    with patch.dict(os.environ, env), patch.object(tempfile, "tempdir", str(home / "tmp")):
        yield


def validate_prediction(record, dimensions=None):
    expected = {
        "runtime": "openvino",
        "device": "CPU",
        "requested_device": "CPU",
        "compiled_device": "CPU",
        "fallback_device": "",
        "fallback_used": False,
        "fallback_reason": None,
        "execution_devices": ["CPU"],
        "execution_device_readback": "actual",
        "performance_hint": "THROUGHPUT",
        "batch_size_requested": 1,
        "batch_size_actual": 1,
        "batch_fallback_used": False,
        "infer_requests": 1,
    }
    if any(record.get(k) != v for k, v in expected.items()):
        raise ValueError("missing or invalid actual native CPU execution evidence")
    execution = record.get("execution", {})
    if (
        execution.get("status") != "success"
        or execution.get("execution_devices") != ["CPU"]
        or execution.get("execution_device_readback") != "actual"
        or execution.get("fallback", {}).get("kind") != "none"
        or execution.get("missing_evidence") != []
        or execution.get("batch", {}).get("actual") != 1
        or execution.get("batch", {}).get("fallback") is not False
        or execution.get("requests", {}).get("actual") != 1
    ):
        raise ValueError("native execution contract is incomplete or used fallback")
    vector = record.get("vector")
    if (
        not isinstance(vector, list)
        or not vector
        or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in vector
        )
        or record.get("dimensions") != len(vector)
        or (dimensions is not None and len(vector) != dimensions)
    ):
        raise ValueError("invalid finite embedding dimensions")
    norm = math.sqrt(sum(v * v for v in vector))
    if not math.isfinite(norm) or norm == 0 or not math.isclose(norm, 1, abs_tol=1e-5):
        raise ValueError("embedding must be nonzero and CLS L2 normalized")
    return len(vector)


def valid_cached(record, fingerprint, dimensions=None):
    if not isinstance(record, dict) or record.get("status") != "ok":
        return False
    try:
        validate_prediction(record, dimensions)
        return record.get("fingerprint") == fingerprint and record.get(
            "record_sha256"
        ) == digest_json({k: v for k, v in record.items() if k != "record_sha256"})
    except ValueError, TypeError, OverflowError:
        return False


def retrieval(items, records, *, cosine):
    galleries = sorted((i for i in items if i["role"] == "gallery"), key=lambda i: i["id"])
    queries = sorted((i for i in items if i["role"] == "query"), key=lambda i: i["id"])
    rows = []
    matrix = np.asarray([records[i["id"]]["vector"] for i in galleries]) if cosine else None
    if cosine:
        matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    for query in queries:
        record = records[query["id"]]
        if cosine:
            vector = np.asarray(record["vector"])
            scores = matrix @ (vector / np.linalg.norm(vector))
            matches = sorted(
                (
                    (-float(score), g["id"], g["source_id"])
                    for score, g in zip(scores, galleries, strict=True)
                )
            )
        else:
            matches = sorted(
                (
                    (int(record["phash"], 16) ^ int(records[g["id"]]["phash"], 16)).bit_count(),
                    g["id"],
                    g["source_id"],
                )
                for g in galleries
            )
        rank = next(
            n + 1 for n, (_, _, source) in enumerate(matches) if source == query["source_id"]
        )
        rows.append(
            {
                "id": query["id"],
                "source_id": query["source_id"],
                "rank": rank,
                "top1": int(rank == 1),
                "reciprocal_rank": 1 / rank,
                "predicted_gallery_id": matches[0][1],
                "top1_tie": sum(score == matches[0][0] for score, _, _ in matches) > 1,
            }
        )
    return {
        "top1": sum(r["top1"] for r in rows) / len(rows),
        "mrr": sum(r["reciprocal_rank"] for r in rows) / len(rows),
        "tied_first_queries": sum(r["top1_tie"] for r in rows),
        "gallery_count": len(galleries),
        "evaluated_queries": len(rows),
        "gallery_source_family_count": len({i["source_id"] for i in galleries}),
        "query_source_family_count": len({i["source_id"] for i in queries}),
        "queries_per_source_family": {
            s: sum(i["source_id"] == s for i in queries)
            for s in sorted({i["source_id"] for i in galleries})
        },
        "tie_break": "lexicographic gallery id",
    }, rows


def paired_bootstrap(candidate, baseline, families=None):
    if [(i["id"], i["source_id"]) for i in candidate] != [
        (i["id"], i["source_id"]) for i in baseline
    ]:
        raise ValueError("paired query identity or source family differs")
    families = sorted(families or {i["source_id"] for i in candidate})
    if not families or not candidate:
        raise ValueError("bootstrap requires nonempty native source families")
    sums = np.asarray(
        [
            [
                sum(
                    c[key] - b[key]
                    for c, b in zip(candidate, baseline, strict=True)
                    if c["source_id"] == family
                )
                for key in ("top1", "reciprocal_rank")
            ]
            for family in families
        ]
    )
    counts = np.asarray([sum(c["source_id"] == f for c in candidate) for f in families])
    rng = np.random.default_rng(STATISTICS["seed"])
    deltas = []
    for _ in range(STATISTICS["replicates"]):
        indexes = rng.integers(0, len(families), size=len(families))
        count = int(counts[indexes].sum())
        if not count:
            raise ValueError("bootstrap draw has no queries; intervals invalid")
        deltas.append(sums[indexes].sum(axis=0) / count)
    values = np.asarray(deltas)
    return {
        name: {
            "point_delta": sum(c[key] - b[key] for c, b in zip(candidate, baseline, strict=True))
            / len(candidate),
            "ci95": [float(v) for v in np.quantile(values[:, n], [0.025, 0.975])],
        }
        for n, (name, key) in enumerate((("top1", "top1"), ("mrr", "reciprocal_rank")))
    }


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def check_frozen(state):
    for filename, expected in state["frozen_files"].items():
        if hash_file(Path(filename)) != expected:
            raise ValueError("immutable source/model/parent/protocol/code changed during inference")


def run(root, manifest, baseline, protocol, model_path, processor_path, output):
    started = time.monotonic()
    with offline_guard() as stack:
        state = preflight(root, manifest, baseline, protocol, model_path, processor_path, output)
        output = state["output"]
        records, dimensions, reused, failures, stop_reason = {}, None, 0, 0, None
        with isolated_homes(output):
            block_download_helpers(stack)
            adapter = embedding.OpenVinoEmbeddingAdapter(
                {
                    **{
                        k: CONFIG[k]
                        for k in (
                            "device",
                            "fallback_device",
                            "allow_batch_fallback",
                            "batch_size",
                            "infer_requests",
                            "max_in_flight",
                            "performance_hint",
                        )
                    },
                    "model_path": str(model_path.resolve()),
                    "processor_path": str(processor_path.resolve()),
                    "compiled_cache_dir": str(output / "compiled-cache"),
                }
            )
            for item in state["items"]:
                if (
                    time.monotonic() - started > LIMITS["process_budget_seconds"]
                    or peak_rss_bytes() > LIMITS["max_peak_rss_bytes"]
                ):
                    stop_reason = "time_or_RSS_budget_exceeded"
                    break
                key = item["id"]
                data = (root / item["path"]).read_bytes()
                if base.digest(data) != item["sha256"]:
                    stop_reason = "frozen_source_changed"
                    break
                fingerprint = digest_json(
                    {"identity": state["identity"], "id": key, "input_sha256": item["sha256"]}
                )
                cache = output / "predictions" / (base.digest(key.encode()) + ".json")
                base.reject_symlinks(cache)
                cached = None
                if cache.exists():
                    try:
                        cached = read_json(cache)
                    except ValueError, OSError:
                        pass
                if (
                    valid_cached(cached, fingerprint, dimensions)
                    and cached.get("id") == key
                    and cached.get("input_sha256") == item["sha256"]
                ):
                    record = cached
                    reused += 1
                else:
                    try:
                        record = asyncio.run(adapter.embed_image(data))
                        dimensions = validate_prediction(record, dimensions)
                        record["status"] = "ok"
                    except Exception as error:
                        record = {
                            "status": "error",
                            "error_type": type(error).__name__,
                            "error": str(error),
                        }
                        failures += 1
                    record.update(id=key, input_sha256=item["sha256"], fingerprint=fingerprint)
                    record["record_sha256"] = digest_json(record)
                    base.atomic_json(cache, record)
                if record["status"] == "ok":
                    dimensions = validate_prediction(record, dimensions)
                records[key] = record
                base.atomic_json(
                    output / "checkpoint.json",
                    {
                        "identity": state["identity"],
                        "protocol_sha256": state["protocol_sha256"],
                        "completed": len(records),
                        "selected": len(state["items"]),
                        "failure_count": failures,
                        "state": "extracting",
                    },
                )
                if failures >= LIMITS["max_failure_count"]:
                    stop_reason = "failure_budget_exceeded"
                    break
        try:
            check_frozen(state)
        except (ValueError, OSError) as error:
            stop_reason = str(error)
        if (
            time.monotonic() - started > LIMITS["process_budget_seconds"]
            or peak_rss_bytes() > LIMITS["max_peak_rss_bytes"]
        ):
            stop_reason = "time_or_RSS_budget_exceeded"
        complete = (
            not stop_reason
            and len(records) == len(state["items"])
            and all(r["status"] == "ok" for r in records.values())
        )
        baseline_metrics, baseline_rows = retrieval(
            state["items"], state["baseline_records"], cosine=False
        )
        metrics, rows, comparison = None, [], None
        if complete:
            metrics, rows = retrieval(state["items"], records, cosine=True)
            comparison = paired_bootstrap(
                rows,
                baseline_rows,
                {i["source_id"] for i in state["items"] if i["role"] == "gallery"},
            )
        report = {
            "schema_version": "material-agent.public-copydays-report.v1",
            "status": "complete" if complete else "incomplete",
            "identity": state["identity"],
            "protocol_sha256": state["protocol_sha256"],
            "runtime": state["runtime"],
            "parent_baseline_identity": state["parent"]["identity"],
            "config": CONFIG,
            "limits": LIMITS,
            "statistics": STATISTICS,
            "training_exposure": EXPOSURE,
            "selected": len(state["items"]),
            "successful": sum(r["status"] == "ok" for r in records.values()),
            "failure_count": failures,
            "cache_reused": reused,
            "dimensions": dimensions,
            "stop_reason": stop_reason,
            "baseline": baseline_metrics,
            "candidate": metrics,
            "comparison": comparison,
            "valid_delta_and_ci": complete,
            "elapsed_seconds": time.monotonic() - started,
            "peak_rss_bytes": peak_rss_bytes(),
            "execution_devices": ["CPU"]
            if any(r["status"] == "ok" for r in records.values())
            else [],
            "source_family_counts": state["plan"]["counts"],
        }
        semantic = {
            "protocol_sha256": state["protocol_sha256"],
            "status": report["status"],
            "baseline": baseline_metrics,
            "candidate": metrics,
            "comparison": comparison,
            "rows": rows,
            "baseline_rows": baseline_rows,
            "vectors": {k: r["vector"] for k, r in records.items() if r["status"] == "ok"},
        }
        report["semantic_digest"] = digest_json(semantic)
        base.atomic_json(
            output / "query-ranks.json", {"candidate": rows, "baseline": baseline_rows}
        )
        base.atomic_json(output / "report.json", report)
        base.atomic_json(
            output / "checkpoint.json",
            {
                "identity": state["identity"],
                "completed": len(records),
                "selected": len(state["items"]),
                "state": report["status"],
                "protocol_sha256": state["protocol_sha256"],
                "semantic_digest": report["semantic_digest"],
            },
        )
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in (
        "root",
        "manifest",
        "baseline",
        "protocol",
        "model-path",
        "processor-path",
        "output",
    ):
        parser.add_argument("--" + option, type=Path, required=True)
    args = parser.parse_args()
    report = run(
        args.root,
        args.manifest,
        args.baseline,
        args.protocol,
        args.model_path,
        args.processor_path,
        args.output,
    )
    print(
        json.dumps(
            {k: report[k] for k in ("status", "semantic_digest", "candidate", "comparison")},
            sort_keys=True,
            allow_nan=False,
        )
    )
    if report["status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
