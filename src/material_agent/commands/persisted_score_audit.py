"""Read-only, job-pinned diagnostics of persisted facts; never reconstruct policy."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import hashlib
import math
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

from ..adapters.state.sqlite_runtime import redact_secrets

MAX_JSON_BYTES = 16 * 1024 * 1024
SUPPORTED_FACT_VERSION = 1  # domain.layered_decision stores both facts at version 1.
TERMINAL_JOB_STATUSES = {"finished", "finished_with_errors"}


def safe_values(value: Any, path: str = "", invalid: list[str] | None = None) -> Any:
    """Retain invalid-number identity explicitly instead of emitting NaN or a zero."""
    if isinstance(value, bytes):
        return {
            "invalid_type": "bytes",
            "byte_count": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > sys.float_info.max:
        if invalid is not None:
            invalid.append(path or "/")
        return {"invalid_number": "unrepresentable_integer", "decimal": str(value)}
    if isinstance(value, float) and not math.isfinite(value):
        if invalid is not None:
            invalid.append(path or "/")
        return {"invalid_number": "NaN" if math.isnan(value) else "+Inf" if value > 0 else "-Inf"}
    if isinstance(value, dict):
        return {key: safe_values(child, f"{path}/{key}", invalid) for key, child in value.items()}
    if isinstance(value, list):
        return [safe_values(child, f"{path}/{index}", invalid) for index, child in enumerate(value)]
    return value


class _DuplicateKeys(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeys("duplicate JSON object keys")
        result[key] = value
    return result


def object_diagnostic(text: str | None) -> tuple[dict, dict]:
    if text is None or text == "":
        return {}, {"status": "missing", "invalid_numbers": []}
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_JSON_BYTES:
        return {}, {"status": "oversized_or_invalid_type", "invalid_numbers": []}
    try:
        raw = json.loads(text, object_pairs_hook=_unique_object)
        if not isinstance(raw, dict):
            return {}, {"status": "malformed", "invalid_numbers": []}
        invalid: list[str] = []
        value = safe_values(redact_secrets(raw), invalid=invalid)
    except _DuplicateKeys:
        return {}, {"status": "ambiguous_duplicate_keys", "invalid_numbers": []}
    except ValueError, TypeError, RecursionError:
        return {}, {"status": "malformed", "invalid_numbers": []}
    return value, {"status": "invalid_numbers" if invalid else "valid", "invalid_numbers": invalid}


def number_diagnostic(value: Any) -> dict:
    if value is None:
        return {"status": "missing", "value": None}
    if isinstance(value, dict) and value.get("invalid_number") == "unrepresentable_integer":
        return {"status": "unrepresentable", "value": None, "raw": value}
    if isinstance(value, dict) and set(value) == {"invalid_number"}:
        return {"status": "nonfinite", "value": None, "raw": value}
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {"status": "invalid_type", "value": None, "raw": safe_values(value)}
    try:
        finite = math.isfinite(value)
    except OverflowError:
        return {"status": "unrepresentable", "value": None, "raw": safe_values(value)}
    if not finite:
        return {"status": "nonfinite", "value": None, "raw": safe_values(value)}
    return {"status": "finite", "value": value}


def versioned_fact(meta: dict, key: str) -> dict:
    if key not in meta:
        return {"status": "missing", "version": None, "raw": None}
    value = meta[key]
    result = {"status": "malformed", "version": None, "raw": value}
    if not isinstance(value, dict) or "invalid_number" in value:
        return result
    version = value.get("version")
    result["version"] = version
    if "version" not in value:
        result["status"] = "missing_version"
    elif type(version) is not int:
        result["status"] = "malformed"
    elif version != SUPPORTED_FACT_VERSION:
        result["status"] = "unsupported_version"
    elif (
        isinstance(value.get("decision"), str)
        and value.get("decision") in {"keep", "review", "reject"}
        and isinstance(value.get("reasons"), list)
        and all(isinstance(reason, str) for reason in value["reasons"])
        and (
            key != "selection"
            or (
                isinstance(value.get("role"), str)
                and value.get("role") in {"quality_policy", "group_coverage"}
            )
        )
    ):
        result["status"] = "valid"
    return result


def application_revision(config: dict) -> dict:
    recorded = {
        key: config[key]
        for key in ("app_revision", "application_revision", "git_revision")
        if key in config
    }
    if not recorded:
        return {"status": "unknown", "value": None, "source": None}
    if not all(isinstance(value, str) and value.strip() for value in recorded.values()):
        return {"status": "invalid", "value": None, "recorded": recorded}
    if len(set(recorded.values())) != 1:
        return {"status": "conflicting", "value": None, "recorded": recorded}
    return {
        "status": "recorded",
        "value": next(iter(recorded.values())),
        "source": "session.config_snapshot",
        "recorded": recorded,
    }


def output_isolation(output: Path, source_roots: list[str | Path], database: Path) -> None:
    output_forms = (Path(os.path.abspath(output)), output.resolve(strict=False))
    for root in source_roots:
        if not isinstance(root, (str, Path)) or not str(root):
            continue
        forms = (Path(os.path.abspath(root)), Path(root).resolve(strict=False))
        for destination in output_forms:
            for source in forms:
                if destination.is_relative_to(source) or source.is_relative_to(destination):
                    raise ValueError(
                        "review output must be outside and separate from every photo input root"
                    )
    resolved_database = database.resolve(strict=True)
    if any(resolved_database.is_relative_to(destination) for destination in output_forms):
        raise ValueError("review output must not contain the runtime database")


def _job(connection: sqlite3.Connection, job_id: str) -> dict:
    row = connection.execute(
        "SELECT j.*,s.input_root,s.config_snapshot,s.kind AS session_kind,"
        "s.status AS session_status,s.created_at AS session_created_at,"
        "s.finished_at AS session_finished_at FROM jobs j JOIN sessions s ON s.id=j.session_id "
        "WHERE j.id=?",
        (job_id,),
    ).fetchone()
    if row is None:
        raise ValueError("requested review job or its session was not found")
    if row["type"] != "review_photos" or row["status"] not in TERMINAL_JOB_STATUSES:
        raise ValueError("requested job must be a terminal review_photos job")
    config, config_status = object_diagnostic(row["config_snapshot"])
    summary, summary_status = object_diagnostic(row["summary_json"])
    return {
        "job": {
            "id": row["id"],
            "session_id": row["session_id"],
            "type": row["type"],
            "stage": row["stage"],
            "status": safe_values(row["status"]),
            "input_root": row["input_root"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "summary": summary,
            "summary_diagnostic": summary_status,
        },
        "session": {
            "id": row["session_id"],
            "kind": row["session_kind"],
            "status": row["session_status"],
            "input_root": row["input_root"],
            "created_at": row["session_created_at"],
            "finished_at": row["session_finished_at"],
        },
        "config": config,
        "config_diagnostic": config_status,
        "historical_application_revision": application_revision(config),
    }


def _percentiles(values: list[float]) -> dict:
    ordered = sorted(values)
    result = {}
    for name, fraction in (
        ("minimum", 0),
        ("p05", 0.05),
        ("p25", 0.25),
        ("median", 0.5),
        ("p75", 0.75),
        ("p95", 0.95),
        ("maximum", 1),
    ):
        if not ordered:
            result[name] = None
            continue
        position = fraction * (len(ordered) - 1)
        lower, upper = math.floor(position), math.ceil(position)
        weight = position - lower
        value = ordered[lower] * (1 - weight) + ordered[upper] * weight
        result[name] = round(value, 4)
    return result


def _model_values(value: Any) -> Any:
    # Runtime artifacts can predate the processed repository's vector sanitizer.
    if isinstance(value, dict):
        return {
            key: _model_values(child)
            for key, child in value.items()
            if key.lower() not in {"vector", "embedding_vector", "_embedding_vector"}
        }
    if isinstance(value, list):
        return [_model_values(child) for child in value]
    return value


def _quality_numbers(quality: Any) -> dict:
    if not isinstance(quality, dict) or "invalid_number" in quality:
        return {"status": "malformed", "numbers": {}}
    numbers = {"aggregate_score": number_diagnostic(quality.get("aggregate_score"))}
    aggregates = quality.get("aggregates")
    if isinstance(aggregates, dict):
        for role, value in aggregates.items():
            numbers[f"aggregates/{role}"] = number_diagnostic(value)
    signals = quality.get("signals")
    if not isinstance(signals, dict):
        return {"status": "missing_signals" if signals is None else "malformed", "numbers": numbers}
    for name, signal in signals.items():
        if not isinstance(signal, dict):
            numbers[f"signals/{name}"] = {"status": "invalid_type", "value": None}
            continue
        for key in ("raw_score", "normalized_score", "raw_min", "raw_max", "weight"):
            if key in ("raw_score", "normalized_score") or key in signal:
                numbers[f"signals/{name}/{key}"] = number_diagnostic(signal.get(key))
    return {
        "status": "finite"
        if all(value["status"] == "finite" for value in numbers.values())
        else "invalid_or_missing",
        "numbers": numbers,
    }


def quality_metric_diagnostics(meta: dict) -> dict:
    sources = [key for key in ("quality", "_quality") if key in meta]
    if not sources:
        return {"status": "missing", "source_key": None, "numbers": {}}
    if len(sources) == 2:
        encoded = [
            json.dumps(meta[key], sort_keys=True, separators=(",", ":"), allow_nan=False)
            for key in sources
        ]
        if encoded[0] != encoded[1]:
            return {
                "status": "ambiguous_aliases",
                "source_key": None,
                "numbers": {},
                "alias_diagnostics": {key: _quality_numbers(meta[key]) for key in sources},
            }
    source = sources[0]  # Persisted stripped key first; legacy fallback only when absent.
    return {
        **_quality_numbers(meta[source]),
        "source_key": source,
        "alias_status": "matching"
        if len(sources) == 2
        else "legacy_fallback"
        if source == "_quality"
        else "actual_only",
    }


def _row_facts(row: sqlite3.Row) -> dict:
    count = row["artifact_count"] or 0
    if count > 1:
        payload, diagnostic = {}, {"status": "duplicate_artifacts", "invalid_numbers": []}
    elif row["payload_bytes"] is not None and row["payload_bytes"] > MAX_JSON_BYTES:
        payload, diagnostic = {}, {"status": "oversized_or_invalid_type", "invalid_numbers": []}
    else:
        payload, diagnostic = object_diagnostic(row["metadata_json"])
    meta = payload.get("meta")
    meta_status = (
        "valid" if isinstance(meta, dict) else "missing" if "meta" not in payload else "malformed"
    )
    if "/meta" in diagnostic["invalid_numbers"]:
        meta_status = "malformed"
    meta = meta if isinstance(meta, dict) and meta_status == "valid" else {}
    readable = diagnostic["status"] in {"valid", "invalid_numbers"}
    facts_readable = readable and meta_status != "malformed"
    unresolved = {
        "status": "unresolved",
        "version": None,
        "raw": None,
        "reason": "malformed_meta" if readable else diagnostic["status"],
    }
    legacy = {"status": "unresolved", "present": None, "value": None, "reasons": None}
    if readable:
        decision = payload.get("decision")
        legacy = {
            "status": "missing"
            if "decision" not in payload
            else "valid"
            if isinstance(decision, str) and decision in {"keep", "review", "reject"}
            else "malformed",
            "present": "decision" in payload,
            "value": decision,
            "reasons": payload.get("decision_reasons"),
        }
    fact = {
        "job_file_id": row["id"],
        "file_path": safe_values(row["file_path"]),
        "group_id": safe_values(row["group_id"]),
        "group_status": "recorded"
        if isinstance(row["group_id"], str) and row["group_id"]
        else "missing"
        if row["group_id"] is None or row["group_id"] == ""
        else "invalid_type",
        "rank": safe_values(row["rank"]),
        "status": row["status"],
        "error_code": safe_values(row["error_code"]),
        "error_message": safe_values(row["error_message"]),
        "score": number_diagnostic(row["score_total"]),
        "score_total": row["score_total"]
        if number_diagnostic(row["score_total"])["status"] == "finite"
        else None,
        "scene": safe_values(row["scene"]),
        "scene_raw": safe_values(row["scene_raw"]),
        "artifact_count": count,
        "payload_diagnostic": diagnostic,
        "meta_status": meta_status,
        "quality_assessment": versioned_fact(meta, "quality_assessment")
        if facts_readable
        else dict(unresolved),
        "selection": versioned_fact(meta, "selection") if facts_readable else dict(unresolved),
        "legacy_decision": legacy,
        "payload_score": number_diagnostic(payload.get("score_total", payload.get("total_score")))
        if readable
        else {"status": "unresolved", "value": None},
        "quality_metric_diagnostics": quality_metric_diagnostics(meta)
        if facts_readable
        else {"status": "unresolved", "numbers": {}},
        "model_evidence": {
            key: _model_values(meta[key])
            for key in (
                "quality",
                "runtime",
                "runtime_components",
                "configured_runtime",
                "model_stack",
                "detection",
                "scoring_mode",
                "semantic",
                "face",
                "aesthetic",
                "embedding",
                "subject_context",
                "timing",
                "_quality",
                "_runtime",
                "_runtime_components",
                "_configured_runtime",
                "_model_stack",
                "_detection",
                "_scoring_mode",
                "_semantic",
                "_face",
                "_aesthetic",
                "_embedding",
                "_subject_context",
                "_timing",
            )
            if key in meta
        },
        "policy_version": payload.get("policy_version"),
    }
    return fact


def _cohort(connection: sqlite3.Connection, cohort: dict) -> dict:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(job_files)")}
    error_columns = ",".join(
        f"jf.{name}" if name in columns else f"NULL AS {name}"
        for name in ("error_code", "error_message")
    )
    cursor = connection.execute(
        "SELECT jf.id,jf.file_path,jf.group_id,jf.rank,jf.status,jf.score_total,jf.scene,jf.scene_raw,"
        + error_columns
        + ",ac.artifact_count,length(CAST(a.metadata_json AS BLOB)) AS payload_bytes,"
        "CASE WHEN length(CAST(a.metadata_json AS BLOB))<=? THEN a.metadata_json END AS metadata_json "
        "FROM job_files jf LEFT JOIN (SELECT job_file_id,count(*) AS artifact_count,min(id) AS artifact_id "
        "FROM artifacts WHERE job_id=? AND kind='score_payload' GROUP BY job_file_id) ac ON ac.job_file_id=jf.id "
        "LEFT JOIN artifacts a ON a.id=ac.artifact_id AND ac.artifact_count=1 "
        "WHERE jf.job_id=? ORDER BY jf.file_path,jf.id",
        (MAX_JSON_BYTES, cohort["job"]["id"], cohort["job"]["id"]),
    )
    facts = []
    groups = defaultdict(list)
    for row in cursor:
        fact = _row_facts(row)
        facts.append(fact)
        key = (
            ("group", fact["group_id"])
            if fact["group_status"] == "recorded"
            else ("ungrouped", fact["job_file_id"])
        )
        groups[key].append(fact)
    scores = [fact["score"]["value"] for fact in facts if fact["score"]["status"] == "finite"]
    ranks = Counter(
        str(fact["rank"]) for fact in facts if type(fact["rank"]) is int and fact["rank"] > 0
    )
    group_facts = []
    for (kind, group_id), members in groups.items():
        group_scores = [
            fact["score"]["value"] for fact in members if fact["score"]["status"] == "finite"
        ]
        group_ranks = Counter(
            str(fact["rank"]) for fact in members if type(fact["rank"]) is int and fact["rank"] > 0
        )
        group_facts.append(
            {
                "group_id": group_id if kind == "group" else None,
                "ungrouped_job_file_id": group_id if kind == "ungrouped" else None,
                "member_count": len(members),
                "finite_score_count": len(group_scores),
                "status_counts": dict(
                    Counter(
                        str(fact["status"]) if fact["status"] is not None else "<missing>"
                        for fact in members
                    )
                ),
                "rank_counts": dict(sorted(group_ranks.items())),
                "rank_missing_count": sum(fact["rank"] is None for fact in members),
                "rank_invalid_count": sum(
                    fact["rank"] is not None
                    and (type(fact["rank"]) is not int or fact["rank"] <= 0)
                    for fact in members
                ),
                "rank_above_member_count_count": sum(
                    type(fact["rank"]) is int and fact["rank"] > len(members) for fact in members
                ),
                "duplicate_ranks": {
                    rank: count for rank, count in group_ranks.items() if count > 1
                },
                "score_distribution": _percentiles(group_scores),
            }
        )
    evidence = {
        key: dict(sorted(Counter(fact[key]["status"] for fact in facts).items()))
        for key in (
            "quality_assessment",
            "selection",
            "payload_diagnostic",
            "quality_metric_diagnostics",
        )
    }
    score_states = Counter(fact["score"]["status"] for fact in facts)
    cohort.update(
        rows=facts,
        evidence=evidence,
        distribution={
            "row_count": len(facts),
            "finite_score_count": len(scores),
            "score_states": dict(sorted(score_states.items())),
            "scores": _percentiles(scores),
            "statuses": dict(
                sorted(
                    Counter(
                        str(fact["status"]) if fact["status"] is not None else "<missing>"
                        for fact in facts
                    ).items()
                )
            ),
            "scenes": dict(
                sorted(Counter(str(fact["scene"] or "unknown") for fact in facts).items())
            ),
            "error_count": sum(
                isinstance(fact["status"], str)
                and fact["status"] in {"error", "failed"}
                or fact["error_code"] is not None
                or fact["error_message"] is not None
                for fact in facts
            ),
            "unscored_count": sum(fact["score"]["status"] == "missing" for fact in facts),
            "ranks": {
                "counts": dict(sorted(ranks.items())),
                "above_group_size_count": sum(
                    group["rank_above_member_count_count"] for group in group_facts
                ),
                "missing_count": sum(fact["rank"] is None for fact in facts),
                "invalid_count": sum(
                    fact["rank"] is not None
                    and (type(fact["rank"]) is not int or fact["rank"] <= 0)
                    for fact in facts
                ),
            },
            "groups": {
                "count": len(groups),
                "singleton_count": sum(len(members) == 1 for members in groups.values()),
                "multi_photo_count": sum(len(members) > 1 for members in groups.values()),
                "maximum_size": max((len(members) for members in groups.values()), default=0),
                "size_histogram": dict(
                    sorted(Counter(str(len(members)) for members in groups.values()).items())
                ),
                "group_id_states": dict(
                    sorted(Counter(fact["group_status"] for fact in facts).items())
                ),
                "members_include_unscored": True,
                "items": group_facts,
            },
        },
    )
    return cohort


def config_differences(a: Any, b: Any, path: str = "") -> list[dict]:
    if isinstance(a, dict) and isinstance(b, dict):
        result = []
        for key in sorted(a.keys() | b.keys()):
            if key not in a or key not in b:
                result.append(
                    {
                        "path": f"{path}/{key}",
                        "a_present": key in a,
                        "b_present": key in b,
                        "a": a.get(key),
                        "b": b.get(key),
                    }
                )
            else:
                result.extend(config_differences(a[key], b[key], f"{path}/{key}"))
        return result
    if type(a) is type(b) and a == b:
        return []
    return [{"path": path or "/", "a_present": True, "b_present": True, "a": a, "b": b}]


def compare_cohorts(a: dict, b: dict) -> dict:
    paths = []
    for cohort in (a, b):
        mapping = defaultdict(list)
        for fact in cohort["rows"]:
            if isinstance(fact["file_path"], str):
                mapping[fact["file_path"]].append(fact)
        paths.append(mapping)
    left, right = paths
    intersection = sorted(left.keys() & right.keys())
    pairs, ambiguous, not_finite = [], [], []
    for path in intersection:
        if len(left[path]) != 1 or len(right[path]) != 1:
            ambiguous.append(path)
            continue
        x, y = left[path][0], right[path][0]
        if x["score"]["status"] != "finite" or y["score"]["status"] != "finite":
            not_finite.append(
                {
                    "file_path": path,
                    "a_score_status": x["score"]["status"],
                    "b_score_status": y["score"]["status"],
                }
            )
            continue
        delta = y["score"]["value"] - x["score"]["value"]
        pairs.append(
            {
                "file_path": path,
                "a_score": x["score"]["value"],
                "b_score": y["score"]["value"],
                "a_status": x["status"],
                "b_status": y["status"],
                "delta": delta if math.isfinite(delta) else None,
                "delta_status": "finite" if math.isfinite(delta) else "nonfinite",
            }
        )
    return {
        "job_id": a["job"]["id"],
        "compare_job_id": b["job"]["id"],
        "exact_paths": {
            "intersection": intersection,
            "a_only": sorted(left.keys() - right.keys()),
            "b_only": sorted(right.keys() - left.keys()),
        },
        "delta_direction": "compare_job_minus_job",
        "finite_pairs": pairs,
        "finite_pair_count": len(pairs),
        "nonfinite_or_missing_pairs": not_finite,
        "ambiguous_pair_paths": ambiguous,
        "invalid_path_rows": [
            [
                fact["job_file_id"]
                for fact in cohort["rows"]
                if not isinstance(fact["file_path"], str)
            ]
            for cohort in (a, b)
        ],
        "duplicate_paths": [
            {path: len(rows) for path, rows in mapping.items() if len(rows) > 1}
            for mapping in paths
        ],
        "root_differences": {
            "different": a["job"]["input_root"] != b["job"]["input_root"],
            "a": a["job"]["input_root"],
            "b": b["job"]["input_root"],
        },
        "config_comparison_status": "valid"
        if a["config_diagnostic"]["status"] == b["config_diagnostic"]["status"] == "valid"
        else "unresolved",
        "config_diagnostics": {"a": a["config_diagnostic"], "b": b["config_diagnostic"]},
        "config_differences": config_differences(a["config"], b["config"]),
        "coverage_differences": {
            "a_rows": a["distribution"]["row_count"],
            "b_rows": b["distribution"]["row_count"],
            "a_statuses": a["distribution"]["statuses"],
            "b_statuses": b["distribution"]["statuses"],
        },
        "interpretation": "Observed persisted values only; no score or policy improvement attribution.",
    }


def load_job_audit(
    *,
    database_path: Path,
    input_root: Path,
    output_root: Path,
    job_id: str,
    compare_job_id: str | None = None,
) -> dict:
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("job-pinned diagnostics require --job-id")
    if compare_job_id is not None and (not compare_job_id.strip() or compare_job_id == job_id):
        raise ValueError("comparison requires two distinct explicit job IDs")
    if not database_path.is_file():
        raise ValueError("runtime database is missing")
    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise RuntimeError("runtime database quick_check failed")
        selected = [
            _job(connection, value)
            for value in [job_id, *([compare_job_id] if compare_job_id else [])]
        ]
        output_isolation(
            output_root,
            [input_root, *(cohort["job"]["input_root"] for cohort in selected)],
            database_path,
        )
        cohorts = [_cohort(connection, cohort) for cohort in selected]
        result = {
            "schema": "material-agent-score-review-v3",
            "database": {
                "path": str(database_path),
                "quick_check": quick_check,
                "transaction": "single_read_only_snapshot",
            },
            "job": cohorts[0]["job"],
            "cohorts": cohorts,
            "comparison": compare_cohorts(*cohorts) if len(cohorts) == 2 else None,
            "requested_input_root": str(input_root),
            "sample_count_rendered": 0,
            "contact_sheet": None,
            "samples": [],
            "image_note": "No previews reconstructed; paths are exact stored identities, not file acceptance evidence.",
        }
        json.dumps(result, allow_nan=False)
        return result
    finally:
        connection.close()
