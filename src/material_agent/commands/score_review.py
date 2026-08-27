from __future__ import annotations

import io
import json
import math
import os
import sqlite3
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageOps

from ..domain.scoring_engine import decode_raw


_CONFIG_KEYS = (
    "backend",
    "output_language",
    "commentary_enabled",
    "raw_extensions",
    "local",
    "inference",
    "grouping",
    "preview",
    "focus_integrity",
    "portrait_face_eye",
    "scorers",
    "scoring",
    "screening",
    "review_pipeline",
    "decision_policy",
    "screening_policy",
    "scene_profiles",
    "xmp",
)


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _percentile(sorted_values: list[float], fraction: float) -> float | None:
    if not sorted_values:
        return None
    position = fraction * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(sorted_values[lower], 4)
    weight = position - lower
    return round(
        sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight,
        4,
    )


def _score_value(row: sqlite3.Row) -> float:
    score = float(row["score_total"] or 0.0)
    if not math.isfinite(score):
        raise ValueError(f"non-finite score_total for job file {row['id']}: {score}")
    return score


def score_distribution(rows: Iterable[sqlite3.Row]) -> dict[str, Any]:
    materialized = list(rows)
    scores = sorted(_score_value(row) for row in materialized)
    buckets: Counter[str] = Counter()
    group_sizes = Counter(
        str(row["group_id"] or f"ungrouped:{row['id']}") for row in materialized
    )
    for score in scores:
        lower = min(9, max(0, int(score)))
        buckets[f"{lower}-{lower + 1}"] += 1
    return {
        "count": len(scores),
        "minimum": _percentile(scores, 0.0),
        "p05": _percentile(scores, 0.05),
        "p25": _percentile(scores, 0.25),
        "median": _percentile(scores, 0.5),
        "p75": _percentile(scores, 0.75),
        "p95": _percentile(scores, 0.95),
        "maximum": _percentile(scores, 1.0),
        "buckets": dict(sorted(buckets.items())),
        "scenes": dict(
            sorted(Counter(str(row["scene"] or "unknown") for row in materialized).items())
        ),
        "statuses": dict(
            sorted(Counter(str(row["status"] or "unknown") for row in materialized).items())
        ),
        "groups": {
            "count": len(group_sizes),
            "singleton_count": sum(size == 1 for size in group_sizes.values()),
            "multi_photo_count": sum(size > 1 for size in group_sizes.values()),
            "maximum_size": max(group_sizes.values(), default=0),
        },
    }


def select_score_samples(rows: Iterable[sqlite3.Row], limit: int) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (_score_value(row), str(row["file_path"])),
    )
    selected: dict[str, dict[str, Any]] = {}

    def add(row: sqlite3.Row, reason: str) -> None:
        entry = selected.setdefault(str(row["id"]), {"row": row, "reasons": []})
        if reason not in entry["reasons"]:
            entry["reasons"].append(reason)

    quantile_count = min(limit, 10, len(ordered))
    for index in range(quantile_count):
        position = round(index * (len(ordered) - 1) / max(1, quantile_count - 1))
        add(ordered[position], f"score_quantile_{index + 1}_of_{quantile_count}")

    by_scene: defaultdict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in ordered:
        by_scene[str(row["scene"] or "unknown")].append(row)
    for scene, scene_rows in sorted(by_scene.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(selected) >= limit:
            break
        add(scene_rows[0], f"scene_{scene}_low")
        if len(selected) < limit:
            add(scene_rows[-1], f"scene_{scene}_high")

    by_group: defaultdict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in ordered:
        if row["group_id"]:
            by_group[str(row["group_id"])].append(row)
    spreads = sorted(
        (
            _score_value(group_rows[-1]) - _score_value(group_rows[0]),
            group_id,
            group_rows,
        )
        for group_id, group_rows in by_group.items()
        if len(group_rows) > 1
    )
    for _, group_id, group_rows in reversed(spreads):
        if len(selected) >= limit:
            break
        add(group_rows[0], f"group_{group_id}_low")
        if len(selected) < limit:
            add(group_rows[-1], f"group_{group_id}_high")

    for row in ordered:
        if len(selected) >= limit:
            break
        add(row, "distribution_fill")
    return list(selected.values())[:limit]


def _safe_photo_path(raw_path: str, input_root: Path) -> Path:
    root = input_root.resolve(strict=True)
    path = Path(raw_path)
    if not path.is_absolute():
        raise ValueError(f"database photo path is not absolute: {path}")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"database photo path escapes input root: {resolved}") from error
    if not resolved.is_file():
        raise ValueError(f"photo is not a file: {resolved}")
    return resolved


def _extract_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    model = meta.get("aesthetic") or meta.get("embedding") or {}
    if not isinstance(model, dict):
        model = {}
    return {
        "scores": payload.get("scores", {}),
        "visible_breakdown": payload.get("visible_breakdown", {}),
        "decision": payload.get("decision"),
        "decision_reasons": payload.get("decision_reasons", []),
        "screening_prior": payload.get("screening_prior"),
        "policy_version": payload.get("policy_version"),
        "output_preview": payload.get("output_preview", {}),
        "model": {
            key: model.get(key)
            for key in (
                "status",
                "runtime",
                "device",
                "execution_devices",
                "execution_device_readback",
                "performance_hint",
                "model_name",
                "model_version",
                "model_digest",
                "batch_size_actual",
                "batch_strategy",
            )
            if key in model
        },
        "aesthetic_calibration": meta.get("aesthetic_calibration"),
    }


def _execution_summary(connection: sqlite3.Connection, job_id: str) -> dict[str, Any]:
    counters: dict[str, Any] = {
        "payloads": 0,
        "model_statuses": Counter(),
        "runtimes": Counter(),
        "execution_devices": Counter(),
        "model_digests": Counter(),
        "calibration_reasons": Counter(),
        "calibration_applied": 0,
        "decisions": Counter(),
        "decision_reasons": Counter(),
    }
    cursor = connection.execute(
        "SELECT metadata_json FROM artifacts WHERE job_id=? AND kind='score_payload'",
        (job_id,),
    )
    for row in cursor:
        payload = _json_object(row[0])
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        model = meta.get("aesthetic") or meta.get("embedding") or {}
        if not isinstance(model, dict):
            model = {}
        counters["payloads"] += 1
        counters["decisions"][str(payload.get("decision", "missing"))] += 1
        for reason in _as_values(payload.get("decision_reasons")):
            counters["decision_reasons"][str(reason)] += 1
        counters["model_statuses"][str(model.get("status", "missing"))] += 1
        counters["runtimes"][str(model.get("runtime", "missing"))] += 1
        devices = _as_values(model.get("execution_devices"))
        if not devices:
            devices = [model.get("device", "missing")]
        for device in devices:
            counters["execution_devices"][str(device)] += 1
        if model.get("model_digest"):
            counters["model_digests"][str(model["model_digest"])] += 1
        calibration = meta.get("aesthetic_calibration")
        if isinstance(calibration, dict):
            counters["calibration_reasons"][str(calibration.get("reason", "missing"))] += 1
            counters["calibration_applied"] += int(bool(calibration.get("applied")))
    return {
        key: dict(sorted(value.items())) if isinstance(value, Counter) else value
        for key, value in counters.items()
    }


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.contain(image.convert("RGB"), size, Image.Resampling.LANCZOS)


def _private_directory(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError(f"review output directory must not be a symbolic link: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError(f"review output path is not a directory: {path}")
    path.chmod(0o700)
    return path.resolve(strict=True)


def _write_private_bytes(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        temporary_path.replace(path)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def _render_contact_sheet(
    samples: list[dict[str, Any]],
    *,
    input_root: Path,
    output_root: Path,
    preview_config: dict[str, Any],
) -> str:
    missing_preview_keys = {"max_size", "jpeg_quality"} - preview_config.keys()
    if missing_preview_keys:
        missing = ", ".join(sorted(missing_preview_keys))
        raise ValueError(f"recorded job preview configuration is missing: {missing}")
    image_dir = _private_directory(output_root / "samples")
    tile_width, tile_height = 420, 310
    columns = 3
    row_count = max(1, math.ceil(len(samples) / columns))
    sheet = Image.new("RGB", (tile_width * columns, tile_height * row_count), "#17191d")
    draw = ImageDraw.Draw(sheet)
    for index, sample in enumerate(samples, start=1):
        try:
            path = _safe_photo_path(sample["file_path"], input_root)
            frame = decode_raw(str(path), preview_config)
            scored = Image.open(io.BytesIO(frame.jpeg_bytes)).convert("RGB")
            thumbnail = _fit(scored, (400, 220))
            sample_path = image_dir / f"{index:02d}.jpg"
            _write_private_bytes(sample_path, frame.jpeg_bytes)
            sample["image"] = {
                "file": str(sample_path.relative_to(output_root)),
                "source": "reconstructed_scoring_input",
                "preview_source": frame.preview_source,
                "original_size": frame.original_size,
                "preview_size": frame.preview_size,
            }
            x = ((index - 1) % columns) * tile_width
            y = ((index - 1) // columns) * tile_height
            sheet.paste(thumbnail, (x + (tile_width - thumbnail.width) // 2, y + 10))
            draw.text(
                (x + 10, y + 238),
                (
                    f"#{index:02d} score={sample['score_total']:.3f} "
                    f"scene={sample['scene']} decision={sample.get('decision') or '-'}"
                )[:68],
                fill="white",
            )
            draw.text((x + 10, y + 258), Path(sample["file_path"]).name[:68], fill="#c7cbd1")
            draw.text(
                (x + 10, y + 278),
                ", ".join(sample["selection_reasons"])[:68],
                fill="#8eb6ff",
            )
        except (OSError, RuntimeError, ValueError) as error:
            sample["image_error"] = f"{type(error).__name__}: {error}"
    sheet_path = output_root / "contact-sheet.jpg"
    encoded_sheet = io.BytesIO()
    sheet.save(encoded_sheet, "JPEG", quality=90, optimize=True)
    _write_private_bytes(sheet_path, encoded_sheet.getvalue())
    return str(sheet_path.relative_to(output_root))


def build_score_review(
    *,
    input_root: Path,
    database_path: Path,
    output_root: Path,
    sample_count: int,
) -> dict[str, Any]:
    if not 6 <= sample_count <= 24:
        raise ValueError("sample_count must be between 6 and 24")
    if not input_root.is_dir():
        raise ValueError(f"input root is not a directory: {input_root}")
    if not database_path.is_file():
        raise ValueError(f"runtime database is missing: {database_path}")
    resolved_input_root = input_root.resolve(strict=True)
    resolved_output_root = output_root.resolve(strict=False)
    try:
        resolved_output_root.relative_to(resolved_input_root)
    except ValueError:
        pass
    else:
        raise ValueError("review output directory must be outside the photo input root")
    try:
        resolved_input_root.relative_to(resolved_output_root)
    except ValueError:
        pass
    else:
        raise ValueError("review output directory must not contain the photo input root")
    output_root = _private_directory(output_root)

    database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise RuntimeError(f"SQLite quick_check failed: {quick_check}")
        job = connection.execute(
            "SELECT j.id,j.session_id,j.summary_json,j.started_at,j.finished_at,s.config_snapshot "
            "FROM jobs j JOIN sessions s ON s.id=j.session_id "
            "WHERE j.type='review_photos' AND j.status='finished' "
            "ORDER BY coalesce(j.finished_at,j.started_at) DESC,j.rowid DESC LIMIT 1"
        ).fetchone()
        if job is None:
            raise ValueError("no finished review_photos job exists")
        rows = connection.execute(
            "SELECT id,file_path,group_id,rank,status,score_total,scene,scene_raw "
            "FROM job_files WHERE job_id=? AND score_total IS NOT NULL",
            (job["id"],),
        ).fetchall()
        if not rows:
            raise ValueError("latest finished review job has no scored rows")
        selections = select_score_samples(rows, sample_count)
        ids = [entry["row"]["id"] for entry in selections]
        placeholders = ",".join("?" for _ in ids)
        artifacts = {
            row["job_file_id"]: _json_object(row["metadata_json"])
            for row in connection.execute(
                f"SELECT job_file_id,metadata_json FROM artifacts "
                f"WHERE kind='score_payload' AND job_file_id IN ({placeholders})",
                ids,
            )
        }
        samples = []
        for entry in selections:
            row = entry["row"]
            samples.append(
                {
                    "job_file_id": row["id"],
                    "file_path": row["file_path"],
                    "group_id": row["group_id"],
                    "rank": row["rank"],
                    "status": row["status"],
                    "score_total": round(float(row["score_total"]), 4),
                    "scene": row["scene"],
                    "scene_raw": row["scene_raw"],
                    "selection_reasons": entry["reasons"],
                    **_extract_metadata(artifacts.get(row["id"], {})),
                }
            )
        config = _json_object(job["config_snapshot"])
        raw_preview = config.get("preview")
        preview = dict(raw_preview) if isinstance(raw_preview, dict) else {}
        contact_sheet = _render_contact_sheet(
            samples,
            input_root=input_root,
            output_root=output_root,
            preview_config=preview,
        )
        result = {
            "schema": "material-agent-score-review-v2",
            "database": {"path": str(database_path), "quick_check": quick_check},
            "job": {
                "id": job["id"],
                "session_id": job["session_id"],
                "started_at": job["started_at"],
                "finished_at": job["finished_at"],
                "summary": _json_object(job["summary_json"]),
            },
            "distribution": score_distribution(rows),
            "execution": _execution_summary(connection, job["id"]),
            "config": {key: config[key] for key in _CONFIG_KEYS if key in config},
            "sample_count_requested": sample_count,
            "sample_count_rendered": sum("image" in sample for sample in samples),
            "contact_sheet": contact_sheet,
            "samples": samples,
            "image_note": (
                "samples are reconstructed with the recorded job preview configuration "
                "and the current decoder; historical JPEG byte identity cannot be proven"
            ),
        }
    finally:
        connection.close()
    _write_private_bytes(
        output_root / "review.json",
        (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    return result


def cmd_review_scores(args: Any) -> int:
    output_root = Path(args.output_dir).expanduser()
    result = build_score_review(
        input_root=Path(args.input_dir).expanduser(),
        database_path=Path(args.work_dir).expanduser() / "state.db",
        output_root=output_root,
        sample_count=args.sample_count,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "job_id": result["job"]["id"],
                "samples": result["sample_count_rendered"],
                "output_dir": str(output_root),
            },
            ensure_ascii=False,
        )
    )
    return 0
