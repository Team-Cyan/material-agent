#!/usr/bin/env python3
"""Bounded, resumable full-corpus diagnostic of the already-reviewed MUSIQ graph."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode = True
HELPER_SOURCE = Path(__file__).with_name("benchmark_musiq_openvino.py")
SPEC = importlib.util.spec_from_file_location("frozen_musiq_parity_helpers", HELPER_SOURCE)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
sha, digest, clean, read, atomic = helper.sha, helper.digest, helper.clean, helper.read, helper.atomic
relative, image_array = helper.relative, helper.image_array
owned_cache, offline, output_dir = helper.owned_cache, helper.offline, helper.output_dir
SCHEMA = "material-agent.musiq-openvino-full.v1"
SHAPE, CONFIG, MODEL_SHA = helper.SHAPE, helper.CONFIG, helper.MODEL_SHA
LIMITS = {"max_items": 2048, "max_graph_bytes": 150000000, "max_rss_bytes": 2500000000,
          "max_seconds": 1800, "max_abs_error": 0.001}
GRAPH = {
    "models/musiq.xml": {"size": 651979, "sha256":
        "0dd4bb0b77223a7d446a19e1d0a8b898a44257c420821c1033b7b8f8bfe3dfd8"},
    "models/musiq.bin": {"size": 108504308, "sha256":
        "09c37d5322ff14e0008f191899eac80f780b97eeea3c5bf27f440964791ba999"}}
PARENTS = {
    "parent_protocol_sha256": "a73c197c2216c99a8038c320309c8837d0f7a9417a21c6f20bb6459ca735861a",
    "parent_prediction_identity": "156b2c70250a102d31cd30023f0527ba314d40aa995ff1f639e52b4e8db485b4",
    "parent_manifest_sha256": "33e9d754efd98956502097d14b75fa25952c109bdd98005f665c0d3b6d5e28c6",
    "parent_baseline_identity": "c497653307a97d9798f20c299e9a905feef5bddc9b717d0e252d96ea8e2bc0be"}
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
SPLIT_COUNTS = {"koniq": {"development": 512, "comparison": 512},
                "kadid": {"development": 530, "comparison": 494}}
FAMILY_COUNTS = {"development": 40, "comparison": 41}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def hash_string(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def validate_protocol(root, protocol, expected_sha):
    root = clean(root).resolve()
    if not hash_string(expected_sha) or sha(protocol) != expected_sha:
        raise ValueError("protocol approval fingerprint mismatch")
    p = read(protocol)
    fixed = {"schema_version": SCHEMA, "input_shape": SHAPE, "config": CONFIG, "limits": LIMITS,
             "checkpoint_sha256": MODEL_SHA, "graph": GRAPH, "statistics": STATISTICS,
             "training_exposure": EXPOSURE, **PARENTS}
    if not isinstance(p, dict) or set(p) != set(fixed) | {"items"} or any(
            digest(p.get(key)) != digest(value) for key, value in fixed.items()):
        raise ValueError("protocol settings differ from frozen full runtime contract")
    items = p["items"]
    if not isinstance(items, list) or len(items) != LIMITS["max_items"]:
        raise ValueError("exactly 2048 frozen inputs required")
    ids, paths, families = set(), set(), {split: set() for split in FAMILY_COUNTS}
    counts = {track: {split: 0 for split in splits} for track, splits in SPLIT_COUNTS.items()}
    required = {"id", "path", "input_sha256", "track", "split", "target", "baseline_score",
                "reference_score", "reference_record_sha256", "baseline_record_sha256"}
    for item in items:
        if not isinstance(item, dict) or item.get("track") not in counts:
            raise ValueError("unknown track or malformed item")
        track, split = item["track"], item.get("split")
        if split not in counts[track] or set(item) != required | ({"group"} if track == "kadid" else set()):
            raise ValueError("unknown split or item keys")
        if any(not isinstance(item[key], str) or not item[key] for key in ("id", "path")):
            raise ValueError("nonempty item ID/path required")
        if item["id"] in ids or item["path"] in paths:
            raise ValueError("duplicate ID/path")
        ids.add(item["id"])
        paths.add(item["path"])
        if any(not finite(item[key]) for key in ("target", "baseline_score", "reference_score")):
            raise ValueError("finite nonboolean labels and scores required")
        if any(not hash_string(item[key]) for key in
               ("input_sha256", "reference_record_sha256", "baseline_record_sha256")):
            raise ValueError("invalid record/input hash")
        if track == "kadid":
            if not isinstance(item["group"], str) or not item["group"]:
                raise ValueError("native family required")
            families[split].add(item["group"])
        counts[track][split] += 1
        path = relative(root, item["path"])
        if sha(path) != item["input_sha256"]:
            raise ValueError("input identity mismatch")
        image_array(path)
    if counts != SPLIT_COUNTS or any(len(families[s]) != n for s, n in FAMILY_COUNTS.items()) or (
            families["development"] & families["comparison"]):
        raise ValueError("frozen track/split/family partitions required")
    if sum(asset["size"] for asset in GRAPH.values()) > LIMITS["max_graph_bytes"]:
        raise ValueError("graph exceeds frozen size bound")
    for name, asset in GRAPH.items():
        path = relative(root, name)
        if path.stat().st_size != asset["size"] or sha(path) != asset["sha256"]:
            raise ValueError("graph identity mismatch")
    return p


def peak_rss_bytes():
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(raw if sys.platform == "darwin" else raw * 1024)


def check_budget(started):
    if time.monotonic() - started > LIMITS["max_seconds"] or peak_rss_bytes() > LIMITS["max_rss_bytes"]:
        raise ValueError("resource bound exceeded")


def valid_record(record, identity, item):
    if not isinstance(record, dict):
        return False
    saved = dict(record)
    checksum = saved.pop("record_sha256", None)
    try:
        return (checksum == digest(saved) and record.get("identity") == identity
                and record.get("id") == item["id"]
                and record.get("input_sha256") == item["input_sha256"]
                and record.get("execution_devices") == ["CPU"]
                and record.get("fallback_used") is False and record.get("status") == "ok"
                and finite(record.get("score")) and finite(record.get("native_call_seconds"))
                and record["native_call_seconds"] >= 0)
    except (TypeError, ValueError):
        return False


def correlation(a, b):
    import numpy as np
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if len(a) < 2 or not np.isfinite(a).all() or not np.isfinite(b).all():
        return None
    a, b = a - a.mean(), b - b.mean()
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denominator) if denominator else None


def associations(scores, targets):
    from scipy.stats import rankdata
    return {"n": len(scores), "plcc": correlation(scores, targets),
            "srocc": correlation(rankdata(scores), rankdata(targets))}


def resampling_units(cohort, track):
    if track == "koniq":
        return [[i] for i in range(len(cohort))]
    groups = {}
    for i, item in enumerate(cohort):
        groups.setdefault(item["group"], []).append(i)
    return [groups[group] for group in sorted(groups)]


def draw_indices(units, rng):
    return [i for u in rng.integers(0, len(units), size=len(units)) for i in units[u]]


def paired_bootstrap(cohort, records, track, statistics=STATISTICS):
    import numpy as np
    from scipy.stats import rankdata
    units = resampling_units(cohort, track)
    target = np.asarray([i["target"] for i in cohort], dtype=np.float64)
    native = np.asarray([records[i["id"]]["score"] for i in cohort], dtype=np.float64)
    fixed = np.asarray([i["baseline_score"] for i in cohort], dtype=np.float64)
    estimates = {key: [] for key in ("plcc", "srocc")}
    rng = np.random.default_rng(statistics["seed"])
    for _ in range(statistics["replicates"]):
        indices = draw_indices(units, rng) if units else []
        a, b, y = native[indices], fixed[indices], target[indices]
        for key in estimates:
            x, z, t = (a, b, y) if key == "plcc" else (rankdata(a), rankdata(b), rankdata(y))
            left, right = correlation(x, t), correlation(z, t)
            if left is not None and right is not None:
                estimates[key].append(left - right)
    tail = (1 - statistics["confidence_level"]) / 2
    return {"method": statistics["method"], "replicates": statistics["replicates"],
            "seed": statistics["seed"], "confidence_level": statistics["confidence_level"],
            "unit": statistics["resampling_units"][track], "units": len(units),
            "scope": statistics["scope"], "delta": {
                key: {"valid_replicates": len(values),
                      "invalid_replicates": statistics["replicates"] - len(values),
                      "interval": [float(v) for v in np.quantile(values, [tail, 1-tail])]
                      if values else None} for key, values in estimates.items()}}


def metrics(items, records, trustworthy):
    result = {}
    for track in SPLIT_COUNTS:
        result[track] = {}
        for split in ("all", "development", "comparison"):
            cohort = [i for i in items if i["track"] == track and
                      (split == "all" or i["split"] == split)]
            paired = [i for i in cohort if i["id"] in records]
            baseline = associations([i["baseline_score"] for i in paired], [i["target"] for i in paired])
            native = associations([records[i["id"]]["score"] for i in paired], [i["target"] for i in paired])
            valid = trustworthy and len(paired) == len(cohort) and bool(cohort)
            result[track][split] = {
                "status": "complete" if valid else "incomplete", "total": len(cohort),
                "failed": len(cohort) - len(paired), "baseline_full": associations(
                    [i["baseline_score"] for i in cohort], [i["target"] for i in cohort]),
                "baseline_paired": baseline, "musiq_paired": native,
                "reference": associations([i["reference_score"] for i in cohort],
                                          [i["target"] for i in cohort]),
                "delta": {key: native[key] - baseline[key] if valid and native[key] is not None
                          and baseline[key] is not None else None for key in ("plcc", "srocc")},
                "bootstrap": paired_bootstrap(cohort, records, track) if valid else None,
                "training_exposure": EXPOSURE[track]}
    return result


def evaluate(root, protocol, expected_sha, output):
    started = time.monotonic()
    import numpy as np
    import openvino as ov
    root = clean(root).resolve()
    output = output_dir(root, output)
    sources = {Path(__file__).name: sha(__file__), HELPER_SOURCE.name: sha(HELPER_SOURCE)}
    if any(clean(path).resolve().is_relative_to(output) for path in (protocol, __file__, HELPER_SOURCE)):
        raise ValueError("output contains protected protocol/source")
    p = validate_protocol(root, protocol, expected_sha)
    provenance = {"protocol_sha256": expected_sha, "source_hashes": sources, "graph": p["graph"],
                  "python": sys.version, "platform": sys.platform, "openvino": ov.__version__,
                  "runtime_versions": {name: importlib.metadata.version(name)
                                       for name in ("numpy", "Pillow", "scipy")}, "config": CONFIG}
    identity = digest(provenance)
    records, reused, status = [], 0, "incomplete"
    report = {}

    def checkpoint():
        atomic(output / "checkpoint.json", {"identity": identity, "status": status,
               "processed": len(records), "total": LIMITS["max_items"]})

    checkpoint()
    try:
        with owned_cache(output), offline():
            check_budget(started)
            core = ov.Core()
            model = core.read_model(root / "models/musiq.xml")
            if len(model.inputs) != 1 or list(model.input().shape) != SHAPE or len(model.outputs) != 1:
                raise ValueError("exported graph shape/output contract mismatch")
            compiled = core.compile_model(model, "CPU", {"INFERENCE_NUM_THREADS": 4,
                "NUM_STREAMS": 1, "PERFORMANCE_HINT": "LATENCY", "INFERENCE_PRECISION_HINT": "f32"})
            devices = list(compiled.get_property("EXECUTION_DEVICES"))
            if devices != ["CPU"] or str(compiled.get_property("INFERENCE_PRECISION_HINT")) != "<Type: 'float32'>":
                raise ValueError("actual CPU/FP32 execution readback required")
            for item in p["items"]:
                check_budget(started)
                source = relative(root, item["path"])
                data = source.read_bytes()
                if hashlib.sha256(data).hexdigest() != item["input_sha256"]:
                    raise ValueError("input changed after preflight")
                path = clean(output / "predictions" / (digest(item["id"]) + ".json"))
                try:
                    record = read(path) if path.exists() else None
                except (json.JSONDecodeError, UnicodeDecodeError):
                    record = None
                if valid_record(record, identity, item):
                    reused += 1
                else:
                    # Decode the same path and rehash immediately to detect intervening drift.
                    array = image_array(source)
                    if sha(source) != item["input_sha256"]:
                        raise ValueError("input changed during decode")
                    timer = time.monotonic()
                    value = np.asarray(compiled([array])[compiled.output()])
                    latency = time.monotonic() - timer
                    if value.size != 1 or value.dtype.kind not in "fiu" or not np.isfinite(value).all():
                        raise ValueError("finite single raw MUSIQ output required")
                    record = {"identity": identity, "id": item["id"], "status": "ok",
                              "input_sha256": item["input_sha256"], "score": float(value.item()),
                              "execution_devices": devices, "fallback_used": False,
                              "native_call_seconds": latency}
                    record["record_sha256"] = digest(record)
                    atomic(path, record)
                records.append(record)
                checkpoint()
            errors = [abs(r["score"] - i["reference_score"])
                      for r, i in zip(records, p["items"], strict=True)]
            status = "passed" if max(errors) <= LIMITS["max_abs_error"] else "parity_failed"
            tracks = metrics(p["items"], {r["id"]: r for r in records}, status == "passed")
            validate_protocol(root, protocol, expected_sha)
            if sources != {Path(__file__).name: sha(__file__), HELPER_SOURCE.name: sha(HELPER_SOURCE)}:
                raise ValueError("runner source changed")
            check_budget(started)
            report = {"complete": True, "max_abs_error": max(errors),
                      "mean_abs_error": sum(errors) / len(errors), "tracks": tracks,
                      "execution_devices": devices, "fallback_used": False}
    except Exception as exc:
        status = "incomplete"
        report = {"complete": False, "error_type": type(exc).__name__, "error": str(exc),
                  "tracks": metrics(p["items"], {r["id"]: r for r in records}, False)}
    report.update(schema_version=SCHEMA, status=status, identity=identity, provenance=provenance,
                  successful=len(records), failures=0 if status != "incomplete" else 1,
                  cache_reused=reused, records=records, training_exposure=EXPOSURE,
                  elapsed_seconds=time.monotonic()-started, peak_rss_bytes=peak_rss_bytes(),
                  timing_scope="Preflight, compilation, decode, inference, writes and statistics; "
                               "observational only, not controlled speedup.",
                  limitations="Native scores are uncalibrated; no production policy admission or "
                              "new improvement threshold. External process watchdog required.")
    checkpoint()
    atomic(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "protocol", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    report = evaluate(args.root, args.protocol, args.protocol_sha256, args.output)
    print(json.dumps({key: value for key, value in report.items()
                      if key not in {"records", "tracks", "provenance"}}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
