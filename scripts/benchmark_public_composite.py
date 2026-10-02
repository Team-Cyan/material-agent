#!/usr/bin/env python3
"""Report-only, model-free native metrics for a frozen public composite corpus.

Manifest paths are relative to --root. No score implies safe discard. AlbumBench
labels are retained but unevaluated because the heuristic has no query predictor.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import platform
import sys
import tempfile

import imagehash
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from material_agent.clients.local import AsyncLocalClient  # noqa: E402
from material_agent.utils.constants import VISION_DIMS  # noqa: E402

SCHEMA = "material-agent.public-composite.v1"
MAX_ITEMS = 100_000
MAX_IMAGE_BYTES = 50_000_000
MAX_PIXELS = 40_000_000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reject_symlinks(path: Path, *, descendants: bool = False) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("output paths must not contain symlinks")
    if descendants and path.exists() and any(p.is_symlink() for p in path.rglob("*")):
        raise ValueError("output tree must not contain symlinks")


def atomic_json(path: Path, payload: dict) -> None:
    reject_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".composite-", suffix=".part", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        reject_symlinks(path)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def valid_cached(cached: object, fingerprint: str) -> bool:
    if not isinstance(cached, dict):
        return False
    try:
        expected = digest(json.dumps(
            {k: v for k, v in cached.items() if k != "record_sha256"},
            sort_keys=True, allow_nan=False).encode())
    except (TypeError, ValueError):
        return False
    phash = cached.get("phash")
    score = cached.get("score")
    return (cached.get("fingerprint") == fingerprint and cached.get("record_sha256") == expected
            and cached.get("status") == "ok" and not isinstance(score, bool)
            and isinstance(score, (int, float)) and math.isfinite(score)
            and isinstance(phash, str) and len(phash) == 16
            and all(c in "0123456789abcdef" for c in phash))


def load_manifest(manifest: Path, root: Path) -> dict:
    if manifest.stat().st_size > 50_000_000:
        raise ValueError("manifest exceeds 50 MB")
    payload = json.loads(manifest.read_text())
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA:
        raise ValueError(f"schema_version must be {SCHEMA}")
    items = payload.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise ValueError("items must contain 1 to 100000 records")
    seen = set()
    galleries = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each item must be a mapping")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in seen:
            raise ValueError("item IDs must be unique non-empty strings")
        seen.add(item_id)
        relative = item.get("path")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise ValueError("item paths must be non-empty relative paths")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"item path escapes root or is missing: {item_id}")
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError(f"image exceeds byte bound: {item_id}")
        expected_hash = item.get("sha256")
        if expected_hash is not None and (not isinstance(expected_hash, str)
                or len(expected_hash) != 64
                or any(c not in "0123456789abcdef" for c in expected_hash)):
            raise ValueError("item sha256 must be a lowercase SHA256 hex digest")
        track = item.get("track")
        if track in {"koniq", "kadid"}:
            target = item.get("target")
            if isinstance(target, bool) or not isinstance(target, (int, float)):
                raise ValueError("quality target must be numeric MOS/DMOS")
            if not math.isfinite(target):
                raise ValueError("quality MOS/DMOS must be finite")
        elif track == "copydays":
            source = item.get("source_id")
            if not isinstance(source, str) or not source:
                raise ValueError("Copydays requires a non-empty source_id")
            if item.get("role") not in {"gallery", "query"}:
                raise ValueError("Copydays role must be gallery or query")
            if item["role"] == "gallery":
                if source in galleries:
                    raise ValueError("Copydays requires one gallery original per source_id")
                galleries.add(source)
        else:
            raise ValueError("unknown track")
    if len(galleries) > 10_000:
        raise ValueError("Copydays gallery exceeds 10000 originals")
    for item in items:
        if item["track"] == "copydays" and item["source_id"] not in galleries:
            raise ValueError("Copydays query has no matching gallery source_id")
    tasks = payload.get("album_tasks", [])
    if not isinstance(tasks, list) or len(tasks) > MAX_ITEMS:
        raise ValueError("album_tasks must be a bounded list")
    task_ids = set()
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not task["id"]:
            raise ValueError("AlbumBench tasks require a non-empty id")
        if task["id"] in task_ids:
            raise ValueError("duplicate AlbumBench task ID")
        task_ids.add(task["id"])
        if not all(key in task for key in ("task_type", "album_id", "image_ids", "target")):
            raise ValueError("AlbumBench task fields are missing")
        if (not isinstance(task["image_ids"], list)
                or not all(isinstance(i, str) and i for i in task["image_ids"])
                or not isinstance(task["album_id"], str) or not task["album_id"]
                or not isinstance(task["task_type"], str) or not task["task_type"]):
            raise ValueError("AlbumBench requires string image IDs, album_id, and task_type")
    return payload


def select_items(items: list[dict], limit: int) -> list[dict]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 4096:
        raise ValueError("limit_per_track must be an integer from 1 to 4096")
    selected = [i for i in items if i["track"] == "copydays" and i["role"] == "gallery"]
    for track in ("koniq", "kadid", "copydays"):
        candidates = [i for i in items if i["track"] == track
                      and not (track == "copydays" and i["role"] == "gallery")]
        candidates.sort(key=lambda i: (digest(i["id"].encode()), i["id"]))
        selected.extend(candidates[:limit])
    return sorted(selected, key=lambda i: i["id"])


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        for index in order[start:end]:
            result[index] = (start + end - 1) / 2
        start = end
    return result


def correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    if np.std(left) == 0 or np.std(right) == 0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def native_metrics(items: list[dict], records: dict[str, dict], album_tasks: list) -> dict:
    quality = {}
    for track in ("koniq", "kadid"):
        members = [i for i in items if i["track"] == track]
        usable = [i for i in members if records[i["id"]]["status"] == "ok"]
        predictions = [records[i["id"]]["score"] for i in usable]
        targets = [i["target"] for i in usable]
        quality[track] = {
            "selected": len(members), "evaluated": len(usable),
            "failed": len(members) - len(usable), "plcc": correlation(predictions, targets),
            "srocc": correlation(ranks(predictions), ranks(targets)),
            "target_direction": "higher is better",
            "predictor": "existing local heuristic mean of VISION_DIMS; no target calibration",
        }
        if track == "kadid":
            quality[track]["per_distortion"] = {}
            for distortion in sorted({str(i["distortion"]) for i in usable if "distortion" in i}):
                subset = [i for i in usable if str(i.get("distortion")) == distortion]
                predicted = [records[i["id"]]["score"] for i in subset]
                target = [i["target"] for i in subset]
                quality[track]["per_distortion"][distortion] = {
                    "evaluated": len(subset), "plcc": correlation(predicted, target),
                    "srocc": correlation(ranks(predicted), ranks(target)),
                }
    galleries = [i for i in items if i["track"] == "copydays" and i["role"] == "gallery"]
    queries = [i for i in items if i["track"] == "copydays" and i["role"] == "query"]
    gallery_ok = [i for i in galleries if records[i["id"]]["status"] == "ok"]
    reciprocal = []
    top1 = []
    tied_first = 0
    for query in queries if len(gallery_ok) == len(galleries) else []:
        record = records[query["id"]]
        if record["status"] != "ok":
            continue
        matches = sorted(
            ((int(record["phash"], 16) ^ int(records[g["id"]]["phash"], 16)).bit_count(),
             g["id"], g["source_id"])
            for g in gallery_ok
        )
        if not any(source == query["source_id"] for _, _, source in matches):
            continue
        rank = next(index + 1 for index, (_, _, source) in enumerate(matches)
                    if source == query["source_id"])
        reciprocal.append(1 / rank)
        top1.append(rank == 1)
        tied_first += sum(distance == matches[0][0] for distance, _, _ in matches) > 1
    return {
        **quality,
        "copydays": {"status": "complete" if len(gallery_ok) == len(galleries) else "incomplete",
                     "gallery_failed_count": len(galleries) - len(gallery_ok),
                     "selected_queries": len(queries), "evaluated_queries": len(top1),
                     "failed_or_missing_gallery": len(queries) - len(top1),
                     "gallery_count": len(galleries), "usable_gallery_count": len(gallery_ok),
                     "top1": sum(top1) / len(top1) if top1 else None,
                     "mrr": sum(reciprocal) / len(reciprocal) if reciprocal else None,
                     "tied_first_queries": tied_first, "tie_break": "lexicographic gallery id",
                     "predictor": "64-bit pHash Hamming distance; copy correspondence only"},
        "albumbench": {"status": "unsupported", "retained_tasks": len(album_tasks),
                       "reason": "existing heuristic has no query-conditioned selection predictor"},
    }


async def extract(data: bytes, client: AsyncLocalClient) -> dict:
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > MAX_PIXELS or min(image.size) < 2:
            raise ValueError("image dimensions exceed bounds or are too small")
        image.load()
        phash = str(imagehash.phash(image))
    result = await client.score_image(data)
    return {"status": "ok", "score": float(np.mean([result[d] for d in VISION_DIMS])),
            "phash": phash, "scoring_mode": result["_scoring_mode"]}


def run(manifest: Path, root: Path, output: Path, limit_per_track: int = 256) -> dict:
    reject_symlinks(output.absolute(), descendants=True)
    root, manifest, output = root.resolve(), manifest.resolve(), output.resolve()
    payload = load_manifest(manifest, root)
    selected = select_items(payload["items"], limit_per_track)
    if manifest.is_relative_to(output) or any(
        (root / i["path"]).resolve().is_relative_to(output) for i in payload["items"]
    ):
        raise ValueError("output must not contain the manifest or any source image")
    input_hashes = {}
    for item in selected:
        data = (root / item["path"]).read_bytes()
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("image changed to exceed byte bound")
        input_hashes[item["id"]] = digest(data)
        if item.get("sha256") is not None and item["sha256"] != input_hashes[item["id"]]:
            raise ValueError(f"frozen input SHA256 mismatch: {item['id']}")
    config = {"limit_per_track": limit_per_track, "selection": "sha256-id ascending",
              "quality": "local heuristic default; all learned models disabled", "copy": "phash64"}
    code_paths = [Path(__file__), REPO / "src/material_agent/clients/local.py",
                  REPO / "src/material_agent/utils/constants.py"]
    identity = digest(json.dumps({"manifest": digest(manifest.read_bytes()), "config": config,
                                 "code": [digest(p.read_bytes()) for p in code_paths],
                                 "python": platform.python_version(), "numpy": np.__version__,
                                 "pillow": Image.__version__, "imagehash": imagehash.__version__},
                                sort_keys=True).encode())
    client = AsyncLocalClient({"output_language": "en", "inference": {"runtime": "cpu"}})
    records = {}
    reused = 0
    for item in selected:
        data = (root / item["path"]).read_bytes()
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("image changed to exceed byte bound")
        if digest(data) != input_hashes[item["id"]]:
            raise ValueError(f"input changed after preflight: {item['id']}")
        fingerprint = digest((identity + digest(data)).encode())
        cache = output / "features" / (digest(item["id"].encode()) + ".json")
        cached = None
        reject_symlinks(cache)
        if cache.exists():
            try:
                cached = json.loads(cache.read_text())
            except (ValueError, OSError):
                pass
        if valid_cached(cached, fingerprint):
            record = cached
            reused += 1
        else:
            try:
                record = asyncio.run(extract(data, client))
            except Exception as error:
                record = {"status": "error", "error_type": type(error).__name__}
            record.update({"id": item["id"], "fingerprint": fingerprint,
                           "input_sha256": digest(data)})
            record["record_sha256"] = digest(json.dumps(record, sort_keys=True,
                                                       allow_nan=False).encode())
            atomic_json(cache, record)
        records[item["id"]] = record
        atomic_json(output / "checkpoint.json", {"identity": identity,
                    "completed": len(records), "selected": len(selected), "state": "extracting"})
    report = {"schema_version": SCHEMA, "config_identity": identity, "config": config,
              "manifest_sha256": digest(manifest.read_bytes()),
              "selected_membership_sha256": digest(json.dumps([i["id"] for i in selected]).encode()),
              "selected_ids": [i["id"] for i in selected], "corpus_items": len(payload["items"]),
              "corpus_by_track": {track: sum(i["track"] == track for i in payload["items"])
                                  for track in ("koniq", "kadid", "copydays")},
              "cache_reused": reused, "tracks": native_metrics(selected, records,
                                                             payload.get("album_tasks", [])),
              "input_fingerprints": {key: value["input_sha256"] for key, value in records.items()},
              "limits": "Diagnostic subset; no training, no mixed score, no G1/G2 coverage claim."}
    report["identity"] = digest(json.dumps({"config_identity": identity,
                                            "inputs": report["input_fingerprints"]},
                                           sort_keys=True).encode())
    atomic_json(output / "report.json", report)
    atomic_json(output / "checkpoint.json", {"identity": report["identity"],
                                            "completed": len(records),
                                            "selected": len(selected), "state": "complete"})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit-per-track", type=int, default=256)
    args = parser.parse_args()
    report = run(args.manifest, args.root, args.output, args.limit_per_track)
    print(json.dumps({"identity": report["identity"], "tracks": report["tracks"]}, indent=2))


if __name__ == "__main__":
    main()
