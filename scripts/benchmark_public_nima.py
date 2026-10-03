#!/usr/bin/env python3
"""Frozen diagnostic comparison of raw CPU NIMA aesthetics and prior heuristics."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from material_agent.adapters.models.inference_contract import runtime_version  # noqa: E402
from material_agent.adapters.models.openvino_nima_aesthetic import (  # noqa: E402
    OpenVinoNimaAestheticAdapter,
)

SPEC = importlib.util.spec_from_file_location(
    "public_composite_helpers", REPO / "scripts/benchmark_public_composite.py"
)
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
SCHEMA = "material-agent.public-nima-protocol.v1"
CONFIG = {"device": "CPU", "batch_size": 1, "infer_requests": 1, "max_in_flight": 1,
          "fallback_device": "", "performance_hint": "THROUGHPUT",
          "preprocessing": "existing adapter default", "calibration": "none"}


def read_json(path: Path) -> dict:
    if path.stat().st_size > 50_000_000:
        raise ValueError("JSON exceeds 50 MB")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("JSON must be a mapping")
    return value


def hash_file(path: Path) -> str:
    return base.digest(path.read_bytes())


def freeze_protocol(manifest_payload: dict, baseline_payload: dict,
                    model_sha: str, model_revision: str) -> dict:
    """Pure partition recipe; consumes the parent's already selected quality IDs."""
    by_id = {i["id"]: i for i in manifest_payload["items"]}
    selected = baseline_payload["selected_ids"]
    if len(selected) != len(set(selected)) or any(i not in by_id for i in selected):
        raise ValueError("invalid parent membership")
    quality_ids = [i for i in selected if by_id[i]["track"] in {"koniq", "kadid"}]
    groups = {by_id[i]["group"] for i in quality_ids if by_id[i]["track"] == "kadid"}
    ordered_groups = sorted(groups, key=lambda g: (base.digest(
        ("public-quality-partition-v1:" + g).encode()), g))
    development_groups = set(ordered_groups[:len(ordered_groups) // 2])
    koniq = sorted((i for i in quality_ids if by_id[i]["track"] == "koniq"),
                   key=lambda i: (base.digest(("public-quality-partition-v1:" + i).encode()), i))
    development_koniq = set(koniq[:len(koniq) // 2])
    items = [{"id": i, "split": "development" if (
        i in development_koniq or (by_id[i]["track"] == "kadid"
                                  and by_id[i]["group"] in development_groups))
        else "comparison"} for i in sorted(quality_ids)]
    return {
        "schema_version": SCHEMA,
        "parent_manifest_sha256": baseline_payload["manifest_sha256"],
        "parent_baseline_identity": baseline_payload["identity"],
        "model_sha256": model_sha, "model_revision": model_revision,
        "partition_algorithm": "public-quality-partition-v1: SHA256(prefix + group/id) order, "
                               "floor half development; KADID reference families, KonIQ individual image IDs",
        "interpretation": "Untrained frozen diagnostic partitions; parent aggregate and labels already "
                          "available, not a blinded independent holdout. NIMA aesthetic versus native "
                          "MOS/DMOS technical quality; training-image overlap unknown. No tuning or policy promotion.",
        "items": items,
    }


def preflight(root: Path, manifest: Path, baseline: Path, protocol: Path,
              model_path: Path, output: Path) -> dict:
    base.reject_symlinks(output.absolute(), descendants=True)
    root, output = root.resolve(), output.resolve()
    source = base.load_manifest(manifest, root)
    parent = read_json(baseline)
    plan = read_json(protocol)
    if plan.get("schema_version") != SCHEMA:
        raise ValueError("invalid protocol schema")
    manifest_sha = hash_file(manifest)
    if (plan.get("parent_manifest_sha256") != manifest_sha
            or parent.get("manifest_sha256") != manifest_sha
            or plan.get("parent_baseline_identity") != parent.get("identity")):
        raise ValueError("stale manifest or baseline protocol identity")
    if parent.get("identity") != base.digest(json.dumps(
        {"config_identity": parent.get("config_identity"),
         "inputs": parent.get("input_fingerprints")}, sort_keys=True).encode()):
        raise ValueError("invalid baseline identity")
    if (parent.get("schema_version") != base.SCHEMA
            or not isinstance(parent.get("selected_ids"), list)
            or not isinstance(parent.get("input_fingerprints"), dict)
            or set(parent["selected_ids"]) != set(parent["input_fingerprints"])):
        raise ValueError("invalid baseline cohort")
    if parent.get("selected_membership_sha256") != base.digest(
            json.dumps(parent["selected_ids"]).encode()):
        raise ValueError("invalid baseline membership hash")
    if model_path.suffix.lower() != ".tflite":
        raise ValueError("comparison requires a single-file TFLite model")
    if not model_path.is_file() or not 1 <= model_path.stat().st_size <= 50_000_000:
        raise ValueError("TFLite model must contain 1 to 50000000 bytes")
    with model_path.open("rb") as handle:
        if handle.read(8)[4:8] != b"TFL3":
            raise ValueError("model must contain a TFLite TFL3 header")
    model_sha = hash_file(model_path)
    if plan.get("model_sha256") != model_sha:
        raise ValueError("stale model SHA256")
    if not isinstance(plan.get("model_revision"), str) or not plan["model_revision"]:
        raise ValueError("model revision is required")
    by_id = {i["id"]: i for i in source["items"]}
    if any(i not in by_id for i in parent["selected_ids"]):
        raise ValueError("baseline IDs are absent from manifest")
    expected = {i for i in parent["selected_ids"] if by_id[i]["track"] in {"koniq", "kadid"}}
    raw = plan.get("items")
    if not isinstance(raw, list) or not raw or len(raw) > 8192:
        raise ValueError("protocol items must be a bounded non-empty list")
    partitions = {}
    groups = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("protocol items must be mappings")
        key = item.get("id")
        split = item.get("split")
        if not isinstance(key, str) or key in partitions or key not in expected:
            raise ValueError("invalid or duplicate protocol item ID")
        if split not in {"development", "comparison"}:
            raise ValueError("invalid diagnostic split")
        partitions[key] = split
        if by_id[key]["track"] == "kadid":
            group = by_id[key].get("group")
            if not isinstance(group, str) or not group:
                raise ValueError("KADID requires native reference group")
            if group in groups and groups[group] != split:
                raise ValueError("KADID reference group crosses diagnostic splits")
            groups[group] = split
    if set(partitions) != expected:
        raise ValueError("protocol must preserve the exact baseline quality cohort")
    expected_protocol = freeze_protocol(source, parent, model_sha, plan["model_revision"])
    if plan != expected_protocol:
        raise ValueError("protocol differs from the frozen partition recipe")
    protected = [manifest, baseline, protocol, model_path, *baseline.parent.joinpath("features").rglob("*")]
    protected += [root / i["path"] for i in source["items"]]
    if (any(p.resolve().is_relative_to(output) for p in protected)
            or output.is_relative_to(baseline.parent.resolve())):
        raise ValueError("output overlaps protected input or baseline cache")
    scores, inputs = {}, {}
    for key in sorted(expected):
        item = by_id[key]
        actual = hash_file(root / item["path"])
        if actual != item.get("sha256") or actual != parent["input_fingerprints"].get(key):
            raise ValueError("frozen input SHA256 mismatch")
        cache_path = baseline.parent / "features" / (base.digest(key.encode()) + ".json")
        base.reject_symlinks(cache_path)
        cached = read_json(cache_path)
        fingerprint = base.digest((parent["config_identity"] + actual).encode())
        if (not base.valid_cached(cached, fingerprint) or cached.get("id") != key
                or cached.get("input_sha256") != actual or cached.get("scoring_mode") != "heuristic"):
            raise ValueError("stale or corrupt baseline feature")
        scores[key] = cached["score"]
        inputs[key] = actual
    return {"items": [dict(by_id[key], split=partitions[key]) for key in sorted(expected)],
            "baseline_scores": scores, "inputs": inputs, "parent": parent, "plan": plan,
            "model_sha256": model_sha, "protocol_sha256": hash_file(protocol),
            "manifest_sha256": manifest_sha, "baseline_sha256": hash_file(baseline)}


def normalize_prediction(result: dict, model_sha: str, revision: str) -> dict:
    execution = result.get("execution", {})
    declaration = execution.get("model") or {}
    if (result.get("model_digest") != model_sha or result.get("model_version") != revision
            or declaration.get("revision") != revision
            or execution.get("status") != "success"
            or execution.get("lifecycle") != "shared_openvino"
            or result.get("runtime") != "openvino"
            or result.get("fallback_used") is not False
            or (execution.get("fallback") or {}).get("kind") != "none"
            or result.get("execution_device_readback") != "actual"
            or execution.get("execution_device_readback") != "actual"
            or result.get("execution_devices") != ["CPU"]
            or execution.get("execution_devices") != ["CPU"]
            or result.get("batch_size_actual") != 1
            or result.get("compiled_device") != "CPU"
            or execution.get("requested_device") != "CPU"
            or execution.get("compiled_device") != "CPU"
            or (execution.get("batch") or {}).get("actual") != 1
            or (execution.get("batch") or {}).get("fallback") is not False):
        raise ValueError("successful CPU model execution evidence required")
    score = result.get("score")
    distribution = result.get("distribution")
    if (isinstance(score, bool) or not isinstance(score, (int, float))
            or not math.isfinite(score) or not 1 <= score <= 10
            or not isinstance(distribution, list) or len(distribution) != 10
            or any(isinstance(v, bool) or not isinstance(v, (int, float))
                   or not math.isfinite(v) or v < 0 for v in distribution)
            or abs(sum(distribution) - 1) > 1e-5
            or abs(sum((i + 1) * v for i, v in enumerate(distribution)) - score) > 1e-5):
        raise ValueError("invalid NIMA score/distribution")
    return {"status": "ok", "score": score, "distribution": distribution,
            "execution_devices": ["CPU"], "model_sha256": model_sha,
            "model_revision": revision, "execution_status": "success"}


def associations(predicted: list, targets: list) -> dict:
    return {"n": len(predicted), "plcc": base.correlation(predicted, targets),
            "srocc": base.correlation(base.ranks(predicted), base.ranks(targets))}


def metrics(items: list, baseline_scores: dict, records: dict) -> dict:
    result = {}
    for track in ("koniq", "kadid"):
        result[track] = {}
        for split in ("all", "development", "comparison"):
            cohort = [i for i in items if i["track"] == track
                      and (split == "all" or i["split"] == split)]
            paired = [i for i in cohort if records[i["id"]]["status"] == "ok"]
            targets = [i["target"] for i in paired]
            heuristic = associations([baseline_scores[i["id"]] for i in paired], targets)
            nima = associations([records[i["id"]]["score"] for i in paired], targets)
            complete = len(paired) == len(cohort) and bool(cohort)
            result[track][split] = {
                "status": "complete" if complete else "incomplete", "total": len(cohort),
                "failed": len(cohort) - len(paired),
                "baseline_full": associations([baseline_scores[i["id"]] for i in cohort],
                                              [i["target"] for i in cohort]),
                "baseline_paired": heuristic, "nima_paired": nima,
                "delta": {key: nima[key] - heuristic[key]
                          if complete and nima[key] is not None and heuristic[key] is not None
                          else None for key in ("plcc", "srocc")},
            }
    return result


def record_hash(record: dict) -> str:
    return base.digest(json.dumps({k: v for k, v in record.items()
                                   if k not in {"record_sha256", "elapsed_ms"}},
                                  sort_keys=True, allow_nan=False).encode())


def reusable(record: dict, identity: str, item: dict, state: dict) -> bool:
    try:
        if (record.get("identity") != identity or record.get("id") != item["id"]
                or record.get("input_sha256") != state["inputs"][item["id"]]
                or record.get("record_sha256") != record_hash(record)):
            return False
        return (record.get("status") == "ok" and record.get("model_sha256") == state["model_sha256"]
                and record.get("model_revision") == state["plan"]["model_revision"]
                and record.get("execution_devices") == ["CPU"]
                and record.get("execution_status") == "success"
                and not isinstance(record.get("score"), bool)
                and isinstance(record.get("score"), (int, float))
                and math.isfinite(record["score"]) and 1 <= record["score"] <= 10
                and isinstance(record.get("distribution"), list)
                and len(record["distribution"]) == 10
                and all(not isinstance(v, bool) and isinstance(v, (int, float))
                        and math.isfinite(v) and v >= 0
                        for v in record["distribution"])
                and abs(sum(record["distribution"]) - 1) <= 1e-5
                and abs(sum((i + 1) * v for i, v in enumerate(record["distribution"]))
                        - record["score"]) <= 1e-5)
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def run(root: Path, manifest: Path, baseline: Path, protocol: Path,
        model_path: Path, output: Path) -> dict:
    started = time.perf_counter()
    state = preflight(root, manifest, baseline, protocol, model_path, output)
    code = [Path(__file__), REPO / "scripts/benchmark_public_composite.py"]
    code += [REPO / "src/material_agent" / p for p in (
        "clients/local.py", "utils/constants.py", "adapters/models/openvino_nima_aesthetic.py",
        "adapters/models/openvino_session.py", "adapters/models/inference_contract.py",
        "adapters/models/openvino_embedding.py")]
    provenance = {"protocol_sha256": state["protocol_sha256"], "model_sha256": state["model_sha256"],
                  "model_revision": state["plan"]["model_revision"], "config": CONFIG,
                  "inputs": state["inputs"], "code": {p.name: hash_file(p) for p in code},
                  "runtime_versions": {name: runtime_version(name)
                                       for name in ("numpy", "scipy", "pillow", "openvino", "imagehash")},
                  "python": platform.python_version()}
    identity = base.digest(json.dumps(provenance, sort_keys=True).encode())
    adapter = OpenVinoNimaAestheticAdapter({
        **{k: v for k, v in CONFIG.items() if k not in {"preprocessing", "calibration"}},
        "model_path": str(model_path), "model_version": state["plan"]["model_revision"],
        "compiled_cache_dir": str(output / "cache")})
    records = {}
    reused = 0
    for item in state["items"]:
        key = item["id"]
        data = (root / item["path"]).read_bytes()
        if base.digest(data) != state["inputs"][key]:
            raise ValueError("input changed after preflight")
        path = output / "predictions" / (base.digest(key.encode()) + ".json")
        base.reject_symlinks(path)
        try:
            cached = read_json(path) if path.exists() else {}
        except (ValueError, OSError):
            cached = {}
        if reusable(cached, identity, item, state):
            record = cached
            reused += 1
        else:
            image_started = time.perf_counter()
            try:
                prediction = asyncio.run(adapter.score_image(data))
                record = normalize_prediction(prediction, state["model_sha256"],
                                              state["plan"]["model_revision"])
            except Exception as error:
                record = {"status": "error", "error_type": type(error).__name__}
            record.update(id=key, identity=identity, input_sha256=state["inputs"][key])
            record["record_sha256"] = record_hash(record)
            record["elapsed_ms"] = (time.perf_counter() - image_started) * 1000
            base.atomic_json(path, record)
        records[key] = record
        base.atomic_json(output / "checkpoint.json", {"identity": identity, "state": "extracting",
                         "completed": len(records), "total": len(state["items"])})
    if (hash_file(protocol) != state["protocol_sha256"]
            or hash_file(model_path) != state["model_sha256"]
            or hash_file(manifest) != state["manifest_sha256"]
            or hash_file(baseline) != state["baseline_sha256"]):
        raise ValueError("frozen protocol, model, manifest, or baseline changed during run")
    report = {"schema_version": "material-agent.public-nima-report.v1", "identity": identity,
              "provenance": provenance, "cache_reused": reused,
              "tracks": metrics(state["items"], state["baseline_scores"], records),
              "inherited_tracks": {k: v for k, v in state["parent"]["tracks"].items()
                                   if k not in {"koniq", "kadid"}},
              "semantic_records_sha256": base.digest(json.dumps(
                  {key: record["record_sha256"] for key, record in records.items()},
                  sort_keys=True).encode()),
              "timing": {"elapsed_seconds": time.perf_counter() - started,
                         "description": "observational startup-inclusive one pass; resume may reuse predictions"},
              "limitations": "Diagnostic partitions; labels previously observed. Raw aesthetics only; "
                              "no calibration, tuning, full-pipeline or G1/G2 claim."}
    base.atomic_json(output / "report.json", report)
    base.atomic_json(output / "checkpoint.json", {"identity": identity, "state": "complete",
                     "completed": len(records), "total": len(state["items"])})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("root", "manifest", "baseline", "protocol", "model-path", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    report = run(args.root, args.manifest, args.baseline, args.protocol, args.model_path, args.output)
    print(json.dumps({"identity": report["identity"], "tracks": report["tracks"]}, indent=2))


if __name__ == "__main__":
    main()
