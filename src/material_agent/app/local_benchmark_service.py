from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ..clients.local import AsyncLocalClient
from ..domain.scoring_engine import decode_raw
from ..utils.constants import VISION_DIMS


SCHEMA_VERSION = "material-agent.local-benchmark.v1"


@dataclass(frozen=True)
class BenchmarkItem:
    item_id: str
    path: Path
    manifest_path: str
    group: str
    expected_scene: str | None
    face_present: bool | None
    non_photo: bool
    reject: bool | None


def load_benchmark_manifest(path: str | Path) -> tuple[dict[str, Any], list[BenchmarkItem]]:
    manifest_path = Path(path).resolve()
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark manifest must be a mapping")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION!r}")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("benchmark manifest items must be a non-empty list")

    items: list[BenchmarkItem] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise ValueError(f"items[{index}] must be a mapping")
        item_id = str(raw.get("id", "")).strip()
        relative_path = str(raw.get("path", "")).strip()
        group = str(raw.get("group", "")).strip()
        if not item_id or not relative_path or not group:
            raise ValueError(f"items[{index}] requires non-empty id, path, and group")
        if item_id in seen_ids:
            raise ValueError(f"duplicate benchmark item id: {item_id!r}")
        seen_ids.add(item_id)
        image_path = (manifest_path.parent / relative_path).resolve()
        if not image_path.is_file():
            raise ValueError(f"benchmark image does not exist: {image_path}")
        labels = raw.get("labels") or {}
        if not isinstance(labels, dict):
            raise ValueError(f"items[{index}].labels must be a mapping")
        items.append(
            BenchmarkItem(
                item_id=item_id,
                path=image_path,
                manifest_path=relative_path,
                group=group,
                expected_scene=_optional_string(labels.get("scene")),
                face_present=_optional_bool(
                    labels.get("face_present"), f"items[{index}].labels.face_present"
                ),
                non_photo=bool(labels.get("non_photo", False)),
                reject=_optional_bool(labels.get("reject"), f"items[{index}].labels.reject"),
            )
        )

    preferences = payload.get("pairwise_preferences", [])
    if not isinstance(preferences, list):
        raise ValueError("pairwise_preferences must be a list")
    for index, preference in enumerate(preferences):
        if not isinstance(preference, dict):
            raise ValueError(f"pairwise_preferences[{index}] must be a mapping")
        preferred = str(preference.get("preferred", ""))
        other = str(preference.get("other", ""))
        if preferred not in seen_ids or other not in seen_ids or preferred == other:
            raise ValueError(f"pairwise_preferences[{index}] references invalid item ids")

    preferred_by_group = payload.get("preferred_by_group", {})
    if not isinstance(preferred_by_group, dict):
        raise ValueError("preferred_by_group must be a mapping")
    group_by_id = {item.item_id: item.group for item in items}
    for group, item_id in preferred_by_group.items():
        if str(item_id) not in group_by_id or group_by_id[str(item_id)] != str(group):
            raise ValueError(f"preferred_by_group[{group!r}] must reference an item in that group")
    return payload, items


def run_local_benchmark(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    repeat_count: int = 2,
    reject_threshold: float = 4.0,
    quality_reject_threshold: float = 5.0,
    client_config: dict[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    if repeat_count < 1:
        raise ValueError("repeat_count must be at least 1")
    manifest, items = load_benchmark_manifest(manifest_path)
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    effective_client_config = {
        "output_language": "en",
        "inference": {"runtime": "cpu"},
        "preview": {"prefer_embedded": True, "max_size": 1024, "jpeg_quality": 85},
        **(client_config or {}),
    }
    client = AsyncLocalClient(effective_client_config)

    started = time.perf_counter()
    repetitions: list[list[dict[str, Any]]] = []
    durations: list[float] = []
    for _ in range(repeat_count):
        client.clear_embedding_result_cache()
        repetition_started = time.perf_counter()
        repetitions.append(
            asyncio.run(_score_items(client, items, effective_client_config["preview"]))
        )
        durations.append(time.perf_counter() - repetition_started)
    elapsed = time.perf_counter() - started

    deterministic = _stable_scores(repetitions)
    results = repetitions[0]
    metrics = _calculate_metrics(
        manifest,
        items,
        results,
        reject_threshold=reject_threshold,
        quality_reject_threshold=quality_reject_threshold,
    )
    manifest_digest = hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()
    report_items = [
        {key: value for key, value in row.items() if key != "embedding_vector"} for row in results
    ]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest": {
            "path": str(Path(manifest_path)),
            "sha256": manifest_digest,
            "name": manifest.get("name", Path(manifest_path).stem),
            "version": manifest.get("version", 1),
        },
        "runtime": {
            "backend": "local",
            "scoring_mode": _common_or_mixed(results, "scoring_mode"),
            "runtime": _common_or_mixed(results, "runtime"),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "repeat_count": repeat_count,
            "reject_threshold": reject_threshold,
            "quality_reject_threshold": quality_reject_threshold,
        },
        "metrics": {
            **metrics,
            "timings": _benchmark_timing_metrics(results),
            "deterministic_scores": deterministic,
            "elapsed_seconds": round(elapsed, 6),
            "cold_run_seconds": round(durations[0], 6),
            "warm_p50_run_seconds": (
                round(statistics.median(durations[1:]), 6) if len(durations) > 1 else None
            ),
            "p50_run_seconds": round(statistics.median(durations), 6),
            "images_per_second": round((len(items) * repeat_count) / elapsed, 4)
            if elapsed
            else None,
        },
        "items": report_items,
    }
    json_path = output_path / "benchmark-report.json"
    markdown_path = output_path / "benchmark-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, markdown_path, report


def _benchmark_timing_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    raw_decode = sum(float(row.get("input_decode_seconds", 0.0)) for row in results)
    heuristic = sum(
        float((row.get("timing") or {}).get("local_heuristic_seconds", 0.0)) for row in results
    )
    embedding_totals = {
        "preprocess_seconds": 0.0,
        "inference_seconds": 0.0,
        "postprocess_seconds": 0.0,
        "compile_seconds": 0.0,
    }
    seen_runs: set[object] = set()
    for row in results:
        embedding = row.get("embedding")
        if not isinstance(embedding, dict):
            continue
        run_id = embedding.get("inference_run_id")
        if run_id is None or run_id in seen_runs:
            continue
        seen_runs.add(run_id)
        timing = embedding.get("timing")
        if not isinstance(timing, dict):
            continue
        for key in ("preprocess_seconds", "inference_seconds", "postprocess_seconds"):
            embedding_totals[key] += float(timing.get(key, 0.0))
        embedding_totals["compile_seconds"] = max(
            embedding_totals["compile_seconds"],
            float(timing.get("compile_seconds", 0.0)),
        )
    return {
        "raw_decode_seconds": round(raw_decode, 6),
        "local_heuristic_seconds": round(heuristic, 6),
        "embedding_runs": len(seen_runs),
        **{f"embedding_{key}": round(value, 6) for key, value in embedding_totals.items()},
    }


async def _score_items(
    client: AsyncLocalClient,
    items: list[BenchmarkItem],
    preview_config: dict[str, Any],
) -> list[dict[str, Any]]:
    loaded: list[tuple[BenchmarkItem, bytes, dict[str, Any], float]] = []
    for item in items:
        decode_started = time.perf_counter()
        image_bytes, input_decode = _load_benchmark_image(item.path, preview_config)
        decode_seconds = time.perf_counter() - decode_started
        loaded.append((item, image_bytes, input_decode, decode_seconds))
    if client.embedding_config.get("enabled", False):
        await client.embed_images([image_bytes for _, image_bytes, _, _ in loaded])

    scored: list[dict[str, Any]] = []
    for item, image_bytes, input_decode, decode_seconds in loaded:
        payload = await client.score_image(image_bytes)
        dimensions = {dim: float(payload.get(dim, 5.0)) for dim in VISION_DIMS}
        total = statistics.fmean(dimensions.values())
        scored.append(
            {
                "id": item.item_id,
                "path": item.manifest_path,
                "group": item.group,
                "input_decode": input_decode,
                "input_decode_seconds": round(decode_seconds, 6),
                "score": round(total, 6),
                "scene": payload.get("scene", "other"),
                "scoring_mode": payload.get("_scoring_mode", "unknown"),
                "runtime": payload.get("_runtime", "unknown"),
                "runtime_components": payload.get("_runtime_components", []),
                "model_stack": payload.get("_model_stack", []),
                "semantic": payload.get("_semantic"),
                "quality": payload.get("_quality"),
                "embedding": payload.get("_embedding"),
                "timing": payload.get("_timing"),
                "embedding_vector": payload.get("_embedding_vector"),
                "face": payload.get("_face"),
                "dimensions": dimensions,
            }
        )
    return scored


def _load_benchmark_image(
    path: Path,
    preview_config: dict[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    if path.suffix.lower() not in {".arw", ".cr2", ".cr3", ".dng", ".nef", ".orf", ".raf", ".rw2"}:
        return path.read_bytes(), {"format": "raster", "source": "file"}
    frame = decode_raw(str(path), preview_config)
    return frame.jpeg_bytes, {
        "format": "raw_preview",
        "source": frame.preview_source,
        "original_size": list(frame.original_size) if frame.original_size else None,
        "preview_size": list(frame.preview_size) if frame.preview_size else None,
        "focus_assessment": frame.focus_assessment,
    }


def _calculate_metrics(
    manifest: dict[str, Any],
    items: list[BenchmarkItem],
    results: list[dict[str, Any]],
    *,
    reject_threshold: float,
    quality_reject_threshold: float,
) -> dict[str, Any]:
    score_by_id = {row["id"]: float(row["score"]) for row in results}
    scene_by_id = {row["id"]: str(row["scene"]) for row in results}
    preferred_by_group = {str(k): str(v) for k, v in manifest.get("preferred_by_group", {}).items()}
    group_hits = 0
    for group, preferred_id in preferred_by_group.items():
        candidates = [item.item_id for item in items if item.group == group]
        predicted = max(candidates, key=lambda item_id: (score_by_id[item_id], item_id))
        group_hits += int(predicted == preferred_id)

    preferences = manifest.get("pairwise_preferences", [])
    pairwise_hits = sum(
        score_by_id[str(row["preferred"])] > score_by_id[str(row["other"])] for row in preferences
    )
    reject_labeled = [item for item in items if item.reject is not None]
    false_negatives = sum(
        item.reject is True and score_by_id[item.item_id] >= reject_threshold
        for item in reject_labeled
    )
    true_rejects = sum(
        item.reject is True and score_by_id[item.item_id] < reject_threshold
        for item in reject_labeled
    )
    reject_positives = sum(item.reject is True for item in reject_labeled)
    scene_labeled = [item for item in items if item.expected_scene is not None]
    scene_hits = sum(scene_by_id[item.item_id] == item.expected_scene for item in scene_labeled)
    photos = [score_by_id[item.item_id] for item in items if not item.non_photo]
    non_photos = [score_by_id[item.item_id] for item in items if item.non_photo]
    screenshot_separation = None
    if photos and non_photos:
        screenshot_separation = round(min(photos) - max(non_photos), 6)
    role_scores: dict[str, dict[str, float]] = {}
    for row in results:
        quality = row.get("quality")
        if not isinstance(quality, dict) or quality.get("status") != "model":
            continue
        for role, value in quality.get("aggregates", {}).items():
            role_scores.setdefault(str(role), {})[row["id"]] = float(value)
    reject_prior_recall = None
    reject_prior_false_negatives = None
    reject_prior_scores = role_scores.get("reject_prior", {})
    if len(reject_prior_scores) == len(results):
        reject_prior_false_negatives = sum(
            item.reject is True and reject_prior_scores[item.item_id] >= quality_reject_threshold
            for item in reject_labeled
        )
        reject_prior_true_rejects = sum(
            item.reject is True and reject_prior_scores[item.item_id] < quality_reject_threshold
            for item in reject_labeled
        )
        reject_prior_recall = _ratio(reject_prior_true_rejects, reject_positives)
    embedding_metrics = _embedding_metrics(items, results)
    face_predictions = {
        row["id"]: bool(row["face"]["face_present"])
        for row in results
        if isinstance(row.get("face"), dict)
        and row["face"].get("status") == "model"
        and row["face"].get("face_present") is not None
    }
    face_labeled = [item for item in items if item.face_present is not None]
    face_positives = [item for item in face_labeled if item.face_present is True]
    face_recall = None
    face_accuracy = None
    if len(face_predictions) == len(results):
        face_recall = _ratio(
            sum(face_predictions[item.item_id] for item in face_positives),
            len(face_positives),
        )
        face_accuracy = _ratio(
            sum(face_predictions[item.item_id] == item.face_present for item in face_labeled),
            len(face_labeled),
        )

    return {
        "item_count": len(items),
        "group_top1": _ratio(group_hits, len(preferred_by_group)),
        "pairwise_preference": _ratio(pairwise_hits, len(preferences)),
        "reject_recall": _ratio(true_rejects, reject_positives),
        "reject_false_negative_count": false_negatives,
        "scene_accuracy": _ratio(scene_hits, len(scene_labeled)),
        "scene_other_rate": _ratio(sum(row["scene"] == "other" for row in results), len(results)),
        "face_positive_count": sum(item.face_present is True for item in items),
        "face_recall": face_recall,
        "face_accuracy": face_accuracy,
        "screenshot_photo_separation": screenshot_separation,
        "reject_prior_recall": reject_prior_recall,
        "reject_prior_false_negative_count": reject_prior_false_negatives,
        "quality_pairwise_preference": _role_pairwise(role_scores, "quality", preferences, results),
        "aesthetic_pairwise_preference": _role_pairwise(
            role_scores, "aesthetic", preferences, results
        ),
        **embedding_metrics,
    }


def _stable_scores(repetitions: list[list[dict[str, Any]]]) -> bool:
    baseline = [(row["id"], row["score"], row["scene"]) for row in repetitions[0]]
    return all(
        [(row["id"], row["score"], row["scene"]) for row in repetition] == baseline
        for repetition in repetitions[1:]
    )


def _common_or_mixed(rows: list[dict[str, Any]], key: str) -> str:
    values = {str(row.get(key, "unknown")) for row in rows}
    return values.pop() if len(values) == 1 else "mixed"


def _role_pairwise(
    role_scores: dict[str, dict[str, float]],
    role: str,
    preferences: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    scores = role_scores.get(role, {})
    if len(scores) != len(results):
        return None
    hits = sum(scores[str(row["preferred"])] > scores[str(row["other"])] for row in preferences)
    return _ratio(hits, len(preferences))


def _embedding_metrics(items: list[BenchmarkItem], results: list[dict[str, Any]]) -> dict[str, Any]:
    vectors = {
        row["id"]: row.get("embedding_vector")
        for row in results
        if isinstance(row.get("embedding_vector"), list) and row["embedding_vector"]
    }
    if len(vectors) != len(results) or len(results) < 2:
        return {
            "embedding_same_group_top1": None,
            "embedding_non_photo_photo_max_similarity": None,
        }
    eligible = [
        item for item in items if sum(candidate.group == item.group for candidate in items) > 1
    ]
    hits = 0
    for item in eligible:
        candidates = [candidate for candidate in items if candidate.item_id != item.item_id]
        nearest = max(
            candidates,
            key=lambda candidate: _cosine(vectors[item.item_id], vectors[candidate.item_id]),
        )
        hits += int(nearest.group == item.group)
    non_photo_ids = [item.item_id for item in items if item.non_photo]
    photo_ids = [item.item_id for item in items if not item.non_photo]
    separation = None
    if non_photo_ids and photo_ids:
        separation = round(
            max(
                _cosine(vectors[non_photo_id], vectors[photo_id])
                for non_photo_id in non_photo_ids
                for photo_id in photo_ids
            ),
            6,
        )
    return {
        "embedding_same_group_top1": _ratio(hits, len(eligible)),
        "embedding_non_photo_photo_max_similarity": separation,
    }


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _ratio(numerator: int, denominator: int) -> dict[str, Any] | None:
    if denominator == 0:
        return None
    return {"numerator": numerator, "total": denominator, "rate": round(numerator / denominator, 6)}


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: Any, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _render_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    mode = str(report["runtime"]["scoring_mode"])
    title = (
        "Local Heuristic Benchmark Report"
        if mode == "heuristic"
        else "Local Model Benchmark Report"
    )
    lines = [
        f"# {title}",
        "",
        f"- Manifest: `{report['manifest']['name']}` version `{report['manifest']['version']}`",
        f"- Manifest SHA-256: `{report['manifest']['sha256']}`",
        f"- Items: {metrics['item_count']}",
        f"- Repeat count: {report['runtime']['repeat_count']}",
        f"- Deterministic scores: {metrics['deterministic_scores']}",
        f"- Images per second: {metrics['images_per_second']}",
        "",
        "## Quality Metrics",
        "",
        "| Metric | Result |",
        "| --- | --- |",
    ]
    for key in (
        "group_top1",
        "pairwise_preference",
        "reject_recall",
        "scene_accuracy",
        "scene_other_rate",
        "screenshot_photo_separation",
        "quality_pairwise_preference",
        "aesthetic_pairwise_preference",
        "reject_prior_recall",
        "embedding_same_group_top1",
        "embedding_non_photo_photo_max_similarity",
        "face_recall",
        "face_accuracy",
    ):
        value = metrics[key]
        if isinstance(value, dict):
            rendered = f"{value['numerator']}/{value['total']} ({value['rate']:.3f})"
        else:
            rendered = "n/a" if value is None else str(value)
        lines.append(f"| `{key}` | {rendered} |")
    lines.extend(
        [
            "",
            "## Stage Timings",
            "",
            "| Stage | Seconds |",
            "| --- | ---: |",
            *[f"| `{key}` | {value} |" for key, value in metrics["timings"].items()],
            "",
            "## Item Scores",
            "",
            "| Item | Group | Score | Scene | Mode |",
            "| --- | --- | ---: | --- | --- |",
        ]
    )
    for row in report["items"]:
        lines.append(
            f"| `{row['id']}` | `{row['group']}` | {row['score']:.4f} | "
            f"`{row['scene']}` | `{row['scoring_mode']}` |"
        )
    return "\n".join(lines) + "\n"
