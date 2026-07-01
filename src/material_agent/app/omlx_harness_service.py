from __future__ import annotations

import copy
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from ..adapters.models.omlx.instance import (
    collect_omlx_runtime_models,
    is_configured_shared_omlx_runtime,
)
from ..app.omlx_instance_service import OMLXInstanceService
from ..io.scanner import scan_arw_files
from ..utils.config_validator import sync_omlx_model_selection

_DEFAULT_LIMIT = 12
_RAW_DUMP_PREFIXES = ("【组内问题】", "Group issues:")
_POST_PREFIXES = ("【后期指导】", "Post advice:")
_POST_INVALID_MARKERS = (
    "【组内问题】",
    "【拍摄建议】",
    "拍摄时",
    "快门",
    "机位",
    "三脚架",
    "对焦",
    "补光",
    "浅景深",
    "Group issues:",
    "Shooting advice:",
    "while shooting",
    "press the shutter",
    "tripod",
    "camera position",
)
_FAVORITE_VALUES = {4.0, 5.5, 6.5, 7.5, 8.5}
_VISION_SCORE_COLUMNS = (
    "score_subject",
    "score_composition",
    "score_lighting",
    "score_color",
    "score_clarity",
    "score_depth",
    "score_mood",
)
_REDACTED_KEYS = {"api_key"}
_HIGH_REPEAT_THRESHOLD = 3


def _default_run_command(args, config) -> None:
    from ..commands.scoring import cmd_run

    cmd_run(args, config)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())
    return slug.strip("-._") or "model"


def _strip_prefix(text: str, prefixes: tuple[str, ...]) -> str:
    body = (text or "").strip()
    for prefix in prefixes:
        if body.startswith(prefix):
            return body[len(prefix) :].strip()
    return body


class OMLXHarnessService:
    """Run real end-to-end review jobs against a small sample set and audit the outputs.

    This service intentionally reuses the normal `material-agent run` path instead of a
    benchmark-only stub so the resulting report matches real user behavior:
    shared-runtime sync, grouping, scoring, commentary generation, XMP writing, and
    processed-state persistence all happen exactly as they would in production.
    """

    def __init__(
        self,
        *,
        run_command=_default_run_command,
        runtime_status_provider=None,
        capture_runtime_status: bool = True,
        restore_runtime_command=None,
        restore_runtime_after_run: bool = True,
    ):
        self.run_command = run_command
        self.runtime_status_provider = runtime_status_provider or self._default_runtime_status_provider
        self.capture_runtime_status = capture_runtime_status
        self.restore_runtime_command = restore_runtime_command or self._default_restore_runtime_command
        self.restore_runtime_after_run = restore_runtime_after_run

    def run(
        self,
        config: dict,
        *,
        models: list[str],
        sample_set: list[str],
        result_path: str | None = None,
        limit: int = _DEFAULT_LIMIT,
        profile_mode: str = "auto",
        no_visual_merge: bool = False,
    ) -> dict[str, Any]:
        if config.get("backend") != "omlx":
            raise ValueError("OMLX harness requires backend: omlx")
        if not models:
            raise ValueError("OMLX harness requires at least one model")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        sample_paths = self._resolve_sample_paths(sample_set, config, limit=limit)
        run_root = self._resolve_result_root(result_path)
        run_dir = run_root / datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        request_snapshot = {
            "requested_models": models,
            "sample_set": sample_set,
            "resolved_sample_paths": [str(path) for path in sample_paths],
            "limit": limit,
            "profile_mode": profile_mode,
            "no_visual_merge": no_visual_merge,
        }
        (run_dir / "sample_manifest.json").write_text(
            json.dumps([str(path) for path in sample_paths], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "run_request.json").write_text(
            json.dumps(request_snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "config_snapshot.json").write_text(
            json.dumps(self._redact_config(config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        results: list[dict[str, Any]] = []
        for model in models:
            candidate_config = self._build_candidate_config(
                config,
                model=model,
                profile_mode=profile_mode,
            )
            model_dir = run_dir / _slugify(model)
            input_dir = model_dir / "input"
            input_dir.mkdir(parents=True, exist_ok=True)
            self._materialize_sample_dir(sample_paths, input_dir)
            candidate_snapshot_path = model_dir / "config_snapshot.json"
            candidate_snapshot_path.write_text(
                json.dumps(self._redact_config(candidate_config), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            runtime_status_before = self._capture_runtime_status(candidate_config)
            runtime_status_before_path = model_dir / "runtime_status.before.json"
            if runtime_status_before is not None:
                runtime_status_before_path.write_text(
                    json.dumps(runtime_status_before, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            started = perf_counter()
            error = ""
            success = True
            try:
                self._run_candidate(input_dir, candidate_config, no_visual_merge=no_visual_merge)
            except Exception as exc:  # pragma: no cover - exercised via caller behavior
                success = False
                error = str(exc)
            elapsed_seconds = round(perf_counter() - started, 2)
            runtime_status_after = self._capture_runtime_status(candidate_config)
            runtime_status_after_path = model_dir / "runtime_status.after.json"
            if runtime_status_after is not None:
                runtime_status_after_path.write_text(
                    json.dumps(runtime_status_after, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            db_path = input_dir / ".material-agent" / "state.db"
            result = self._collect_result(
                db_path=db_path,
                model=model,
                elapsed_seconds=elapsed_seconds,
                sample_count=len(sample_paths),
                success=success,
                error=error,
                profile_mode=profile_mode,
                expected_models=collect_omlx_runtime_models(candidate_config),
                runtime_status_before=runtime_status_before,
                runtime_status_after=runtime_status_after,
                shared_runtime=is_configured_shared_omlx_runtime(candidate_config),
            )
            result["input_dir"] = str(input_dir)
            result["db_path"] = str(db_path)
            result["report_path"] = str(model_dir / "report.md")
            result["config_snapshot_path"] = str(candidate_snapshot_path)
            result["sample_manifest_path"] = str(run_dir / "sample_manifest.json")
            result["runtime_status_before_path"] = (
                str(runtime_status_before_path) if runtime_status_before is not None else None
            )
            result["runtime_status_after_path"] = (
                str(runtime_status_after_path) if runtime_status_after is not None else None
            )
            (model_dir / "summary.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (model_dir / "report.md").write_text(
                self._build_model_report(result),
                encoding="utf-8",
            )
            results.append(result)

        restore_summary = self._restore_original_runtime(config, models=models)

        comparison = {
            "run_dir": str(run_dir),
            "result_root": str(run_root),
            "sample_count": len(sample_paths),
            "sample_paths": [str(path) for path in sample_paths],
            "models": models,
            "profile_mode": profile_mode,
            "limit": limit,
            "no_visual_merge": no_visual_merge,
            "results": results,
            "recommended_order": self._recommended_order(results),
            "report_path": str(run_dir / "report.md"),
            "request_path": str(run_dir / "run_request.json"),
            "config_snapshot_path": str(run_dir / "config_snapshot.json"),
            "restore_summary": restore_summary,
        }
        comparison["best_model"] = comparison["recommended_order"][0] if comparison["recommended_order"] else None
        comparison["best_model_reason"] = self._build_best_model_reason(comparison)
        (run_dir / "summary.json").write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "report.md").write_text(
            self._build_comparison_report(comparison),
            encoding="utf-8",
        )
        return comparison

    def _resolve_sample_paths(self, sample_set: list[str], config: dict, *, limit: int) -> list[Path]:
        if not sample_set:
            raise ValueError("sample_set is required for OMLX harness")
        raw_extensions = config.get("raw_extensions") or ["ARW", "DNG", "CR2", "NEF"]
        resolved: list[Path] = []
        seen: set[str] = set()
        for entry in sample_set:
            path = Path(entry).expanduser().resolve()
            if not path.exists():
                raise FileNotFoundError(f"Sample path does not exist: {path}")
            if path.is_dir():
                candidates = [Path(p) for p in scan_arw_files(str(path), raw_extensions)]
            else:
                candidates = [path]
            for candidate in candidates:
                key = str(candidate)
                if key in seen:
                    continue
                seen.add(key)
                resolved.append(candidate)
                if len(resolved) >= limit:
                    return resolved
        if not resolved:
            raise ValueError("No RAW samples resolved for OMLX harness")
        return resolved

    def _resolve_result_root(self, result_path: str | None) -> Path:
        if result_path:
            root = Path(result_path).expanduser().resolve()
        else:
            root = Path("artifacts/harnesses/omlx").resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _build_candidate_config(self, config: dict, *, model: str, profile_mode: str) -> dict:
        candidate = copy.deepcopy(config)
        sync_omlx_model_selection(
            candidate,
            full_vision_model=model,
            commentary_model=model,
            fast_vision_model=model,
        )
        omlx = candidate.setdefault("omlx", {})
        requests = omlx.setdefault("requests", {})
        # Force a same-model path across fast/full/commentary so the harness compares one
        # model at a time under the exact review pipeline that users actually run.
        requests["model_profile_mode"] = profile_mode
        return candidate

    def _materialize_sample_dir(self, sample_paths: list[Path], input_dir: Path) -> None:
        used_names: set[str] = set()
        for index, source in enumerate(sample_paths, start=1):
            name = source.name
            if name in used_names:
                name = f"{index:02d}-{name}"
            used_names.add(name)
            target = input_dir / name
            # Symlinks keep the harness cheap and reproducible: the live run sees a normal
            # input directory, but we do not duplicate the user's RAW files for each model.
            target.symlink_to(source)

    def _run_candidate(self, input_dir: Path, config: dict, *, no_visual_merge: bool) -> None:
        args = SimpleNamespace(
            input_dir=str(input_dir),
            config="config.yaml",
            reprocess=False,
            dry_run=False,
            scorers=None,
            no_visual_merge=no_visual_merge,
        )
        self.run_command(args, copy.deepcopy(config))

    def _default_runtime_status_provider(self, config: dict) -> dict[str, Any]:
        return OMLXInstanceService().status(config)

    def _default_restore_runtime_command(self, config: dict) -> dict[str, Any]:
        service = OMLXInstanceService()
        expected_models = collect_omlx_runtime_models(config)
        sync_summary = service.sync_shared(config)
        status = service.status(config)
        drift_detected = self._shared_runtime_drift(expected_models, status)
        restarted = False
        if sync_summary.get("changed") or not status.get("reachable", False) or drift_detected:
            service.restart_shared(config)
            restarted = True
            status = service.status(config)
        return {
            "restored": True,
            "restarted": restarted,
            "active_models": expected_models,
            "linked_models": self._status_list(status, "linked_models"),
            "served_models": self._status_list(status, "served_models"),
            "drift_detected": self._shared_runtime_drift(expected_models, status),
        }

    def _restore_original_runtime(self, config: dict, *, models: list[str]) -> dict[str, Any] | None:
        if not self.restore_runtime_after_run:
            return None
        if not is_configured_shared_omlx_runtime(config):
            return {
                "restored": False,
                "reason": "not_shared_runtime",
            }
        if not models or self._normalized_model_names(models) == self._normalized_model_names(
            collect_omlx_runtime_models(config)
        ):
            # Even a one-model harness may have disturbed the shared runtime, so still restore.
            pass
        try:
            return self.restore_runtime_command(copy.deepcopy(config))
        except Exception as exc:
            return {
                "restored": False,
                "reason": "restore_failed",
                "error": str(exc),
            }

    def _capture_runtime_status(self, config: dict) -> dict[str, Any] | None:
        if not self.capture_runtime_status:
            return None
        try:
            return self.runtime_status_provider(copy.deepcopy(config))
        except Exception as exc:
            return {"capture_error": str(exc)}

    def _collect_result(
        self,
        *,
        db_path: Path,
        model: str,
        elapsed_seconds: float,
        sample_count: int,
        success: bool,
        error: str,
        profile_mode: str,
        expected_models: list[str],
        runtime_status_before: dict[str, Any] | None,
        runtime_status_after: dict[str, Any] | None,
        shared_runtime: bool,
    ) -> dict[str, Any]:
        if not db_path.exists():
            return {
                "model": model,
                "success": False,
                "error": error or f"Expected processed DB was not created: {db_path}",
                "elapsed_seconds": elapsed_seconds,
                "sample_count": sample_count,
                "done_count": 0,
                "error_count": sample_count,
                "profile_mode": profile_mode,
                "expected_runtime_models": expected_models,
                "runtime_linked_models_before": [],
                "runtime_linked_models_after": [],
                "runtime_served_models_after": [],
                "runtime_mode_before": None,
                "runtime_mode_after": None,
                "runtime_shared_desktop_running_before": None,
                "runtime_shared_desktop_running_after": None,
                "runtime_instance_matches_after": None,
                "runtime_effective_model_set_matches_after": None,
                "runtime_served_models_catalog_superset_after": None,
                "scoring_metrics": {},
                "warnings": ["processed_db_missing"],
            }

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            done_rows = conn.execute(
                """
                SELECT file_path, total_score, group_id, decision, scene, scene_raw,
                       score_subject, score_composition, score_lighting, score_color,
                       score_clarity, score_depth, score_mood,
                       commentary_group_issues, commentary_shooting, commentary_post
                FROM processed
                WHERE status='done'
                ORDER BY total_score DESC, file_path ASC
                """
            ).fetchall()
            error_rows = conn.execute(
                "SELECT file_path, error_message FROM processed WHERE status='error' ORDER BY file_path ASC"
            ).fetchall()
        finally:
            conn.close()

        post_counter = Counter(
            row["commentary_post"].strip()
            for row in done_rows
            if isinstance(row["commentary_post"], str) and row["commentary_post"].strip()
        )
        group_counter = Counter(
            row["commentary_group_issues"].strip()
            for row in done_rows
            if isinstance(row["commentary_group_issues"], str) and row["commentary_group_issues"].strip()
        )
        invalid_post_count = sum(
            1 for row in done_rows if self._is_invalid_post_commentary(row["commentary_post"])
        )
        invalid_group_count = sum(
            1 for row in done_rows if self._is_invalid_group_issue(row["commentary_group_issues"])
        )
        scores = [
            float(row["total_score"])
            for row in done_rows
            if isinstance(row["total_score"], (int, float))
        ]

        result = {
            "model": model,
            "success": success and not error_rows,
            "error": error,
            "elapsed_seconds": elapsed_seconds,
            "seconds_per_file": round(elapsed_seconds / sample_count, 2) if sample_count else 0.0,
            "sample_count": sample_count,
            "done_count": len(done_rows),
            "error_count": len(error_rows),
            "profile_mode": profile_mode,
            "expected_runtime_models": expected_models,
            "score_stats": {
                "min": round(min(scores), 2) if scores else None,
                "avg": round(sum(scores) / len(scores), 2) if scores else None,
                "max": round(max(scores), 2) if scores else None,
            },
            "decision_distribution": dict(
                sorted(Counter(row["decision"] or "unknown" for row in done_rows).items())
            ),
            "scene_distribution": dict(
                sorted(Counter(row["scene"] or "other" for row in done_rows).items())
            ),
            "max_post_repeat": max(post_counter.values(), default=0),
            "max_group_repeat": max(group_counter.values(), default=0),
            "invalid_post_count": invalid_post_count,
            "invalid_group_issue_count": invalid_group_count,
            "top_repeated_post": [
                {"text": text, "count": count} for text, count in post_counter.most_common(5)
            ],
            "top_repeated_group_issues": [
                {"text": text, "count": count} for text, count in group_counter.most_common(5)
            ],
            "examples": [
                {
                    "file_name": Path(str(row["file_path"])).name,
                    "scene": row["scene"],
                    "decision": row["decision"],
                    "total_score": round(float(row["total_score"]), 2),
                    "scene_raw": row["scene_raw"],
                    "group_issues": row["commentary_group_issues"],
                    "post": row["commentary_post"],
                }
                for row in done_rows[:5]
            ],
            "error_rows": [
                {
                    "file_name": Path(str(row["file_path"])).name,
                    "error": row["error_message"],
                }
                for row in error_rows[:10]
            ],
            "runtime_mode_before": self._status_value(runtime_status_before, "runtime_mode"),
            "runtime_mode_after": self._status_value(runtime_status_after, "runtime_mode"),
            "runtime_shared_desktop_running_before": self._status_value(
                runtime_status_before, "shared_desktop_running"
            ),
            "runtime_shared_desktop_running_after": self._status_value(
                runtime_status_after, "shared_desktop_running"
            ),
            "runtime_linked_models_before": self._status_list(runtime_status_before, "linked_models"),
            "runtime_linked_models_after": self._status_list(runtime_status_after, "linked_models"),
            "runtime_served_models_after": self._status_list(runtime_status_after, "served_models"),
            "runtime_instance_matches_after": self._status_value(
                runtime_status_after, "instance_matches"
            ),
            "runtime_effective_model_set_matches_after": self._status_value(
                runtime_status_after, "effective_model_set_matches"
            ),
            "runtime_served_models_catalog_superset_after": self._status_value(
                runtime_status_after, "served_models_catalog_superset"
            ),
            "scoring_metrics": self._build_scoring_metrics(done_rows),
            "runtime_status_capture_error": self._runtime_capture_error(
                runtime_status_before, runtime_status_after
            ),
            "shared_runtime_drift_detected": (
                shared_runtime and self._shared_runtime_drift(expected_models, runtime_status_after)
            ),
        }
        result["warnings"] = self._build_warnings(result)
        result["verdict"] = self._build_verdict(result)
        result["primary_risks"] = self._build_primary_risks(result)
        result["action_hint"] = self._build_action_hint(result)
        return result

    def _build_scoring_metrics(self, done_rows) -> dict[str, float | int]:
        total_scores = [
            round(float(row["total_score"]), 2)
            for row in done_rows
            if isinstance(row["total_score"], (int, float))
        ]
        vectors: list[tuple[float, ...]] = []
        favorite_hits = 0
        total_values = 0
        group_totals: dict[str, list[float]] = {}

        for row in done_rows:
            values: list[float] = []
            for column in _VISION_SCORE_COLUMNS:
                value = row[column]
                if not isinstance(value, (int, float)):
                    values = []
                    break
                rounded_value = round(float(value), 1)
                values.append(rounded_value)
                total_values += 1
                if rounded_value in _FAVORITE_VALUES:
                    favorite_hits += 1
            if values:
                vectors.append(tuple(values))

            group_id = row["group_id"]
            if isinstance(group_id, str) and group_id.strip() and isinstance(
                row["total_score"], (int, float)
            ):
                group_totals.setdefault(group_id, []).append(round(float(row["total_score"]), 2))

        vector_counts = Counter(vectors)
        repeated_rows = sum(count for count in vector_counts.values() if count > 1)
        multi_frame_ranges = [
            round(max(scores) - min(scores), 2)
            for scores in group_totals.values()
            if len(scores) > 1
        ]

        return {
            "score_range": round(max(total_scores) - min(total_scores), 2) if total_scores else 0.0,
            "favorite_value_ratio": round(favorite_hits / total_values, 3) if total_values else 0.0,
            "repeated_score_vector_ratio": (
                round(repeated_rows / len(vectors), 3) if vectors else 0.0
            ),
            "unique_score_vector_count": len(vector_counts),
            "multi_frame_group_count": len(multi_frame_ranges),
            "avg_group_score_range": (
                round(sum(multi_frame_ranges) / len(multi_frame_ranges), 2)
                if multi_frame_ranges
                else 0.0
            ),
        }

    def _build_warnings(self, result: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        if result.get("done_count", 0) != result.get("sample_count", 0):
            warnings.append("sample_count_mismatch")
        if result.get("invalid_post_count", 0):
            warnings.append("post_commentary_contains_shooting_or_group_text")
        if result.get("invalid_group_issue_count", 0):
            warnings.append("group_issue_looks_like_raw_score_dump")
        if result.get("max_post_repeat", 0) >= _HIGH_REPEAT_THRESHOLD:
            warnings.append("post_commentary_repetition_high")
        if result.get("max_group_repeat", 0) >= _HIGH_REPEAT_THRESHOLD:
            warnings.append("group_commentary_repetition_high")
        if result.get("error_count", 0):
            warnings.append("run_contains_errors")
        if result.get("shared_runtime_drift_detected", False):
            warnings.append("shared_runtime_linked_models_drift")
        if result.get("runtime_effective_model_set_matches_after") is False:
            warnings.append("runtime_effective_model_set_mismatch")
        if result.get("runtime_status_capture_error"):
            warnings.append("runtime_status_capture_failed")
        return warnings

    def _build_verdict(self, result: dict[str, Any]) -> str:
        if result.get("error_count", 0) or result.get("done_count", 0) != result.get("sample_count", 0):
            return "runtime_unstable"
        if result.get("invalid_post_count", 0) or result.get("invalid_group_issue_count", 0):
            return "needs_structural_fix"
        if (
            result.get("max_post_repeat", 0) >= _HIGH_REPEAT_THRESHOLD
            or result.get("max_group_repeat", 0) >= _HIGH_REPEAT_THRESHOLD
        ):
            return "needs_prompt_refine"
        return "ready_for_default_path"

    def _build_primary_risks(self, result: dict[str, Any]) -> list[str]:
        risks: list[str] = []
        if result.get("error_count", 0):
            risks.append("runtime errors occurred during the live run")
        if result.get("done_count", 0) != result.get("sample_count", 0):
            risks.append("not every sample finished successfully")
        if result.get("shared_runtime_drift_detected", False):
            risks.append("shared runtime linked models drifted away from the candidate model set")
        if result.get("runtime_effective_model_set_matches_after") is False:
            risks.append("runtime did not effectively expose the expected model set after the run")
        if result.get("invalid_post_count", 0):
            risks.append("post commentary leaked shooting/group content")
        if result.get("invalid_group_issue_count", 0):
            risks.append("group issues degraded into raw score dumps")
        if result.get("max_post_repeat", 0) >= _HIGH_REPEAT_THRESHOLD:
            risks.append("post commentary repetition is high")
        if result.get("max_group_repeat", 0) >= _HIGH_REPEAT_THRESHOLD:
            risks.append("group commentary repetition is high")
        if result.get("runtime_status_capture_error"):
            risks.append("runtime status snapshots could not be captured reliably")
        return risks

    def _build_action_hint(self, result: dict[str, Any]) -> str:
        verdict = result.get("verdict")
        if verdict == "runtime_unstable":
            return "Fix runtime/probe issues first before comparing prompt quality."
        if result.get("runtime_effective_model_set_matches_after") is False:
            return "Investigate runtime readiness before trusting this comparison."
        if result.get("shared_runtime_drift_detected", False):
            return "Investigate shared runtime model pinning before trusting speed or cache comparisons."
        if verdict == "needs_structural_fix":
            return "Tighten prompts or commentary guards before trusting this model."
        if verdict == "needs_prompt_refine":
            return "Keep the model, but refine model profile prompts to reduce repetition."
        return "This model is stable enough for the default path on the sampled set."

    def _shared_runtime_drift(
        self,
        expected_models: list[str],
        runtime_status: dict[str, Any] | None,
    ) -> bool:
        if not runtime_status or runtime_status.get("capture_error"):
            return False
        linked_models = self._status_list(runtime_status, "linked_models")
        if not linked_models:
            return False
        return self._normalized_model_names(linked_models) != self._normalized_model_names(
            expected_models
        )

    @staticmethod
    def _normalized_model_names(models: list[str]) -> list[str]:
        return sorted({Path(str(model)).name for model in models if str(model).strip()})

    @staticmethod
    def _status_list(runtime_status: dict[str, Any] | None, key: str) -> list[str]:
        if not runtime_status:
            return []
        value = runtime_status.get(key)
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    @staticmethod
    def _status_value(runtime_status: dict[str, Any] | None, key: str) -> Any:
        if not runtime_status:
            return None
        return runtime_status.get(key)

    @staticmethod
    def _runtime_capture_error(
        runtime_status_before: dict[str, Any] | None,
        runtime_status_after: dict[str, Any] | None,
    ) -> str | None:
        for candidate in (runtime_status_before, runtime_status_after):
            if isinstance(candidate, dict) and str(candidate.get("capture_error") or "").strip():
                return str(candidate["capture_error"])
        return None

    def _build_best_model_reason(self, summary: dict[str, Any]) -> str:
        best_model = summary.get("best_model")
        if not best_model:
            return "No successful model result was produced."
        best = next(
            (result for result in summary.get("results", []) if result.get("model") == best_model),
            None,
        )
        if not best:
            return "Best model could not be resolved from the result list."
        return (
            f"{best_model} ranked first because verdict={best.get('verdict')}, "
            f"shared_runtime_drift={best.get('shared_runtime_drift_detected')}, "
            f"invalid_post={best.get('invalid_post_count')}, "
            f"invalid_group={best.get('invalid_group_issue_count')}, "
            f"post_repeat={best.get('max_post_repeat')}, "
            f"group_repeat={best.get('max_group_repeat')}, "
            f"seconds_per_file={best.get('seconds_per_file')}."
        )

    def _recommended_order(self, results: list[dict[str, Any]]) -> list[str]:
        def _rank_key(result: dict[str, Any]) -> tuple[Any, ...]:
            # Prefer correctness over style, then style over speed.
            return (
                1 if result.get("runtime_effective_model_set_matches_after") is False else 0,
                1 if result.get("shared_runtime_drift_detected", False) else 0,
                result.get("invalid_post_count", 0),
                result.get("invalid_group_issue_count", 0),
                result.get("max_post_repeat", 0),
                result.get("max_group_repeat", 0),
                result.get("error_count", 0),
                result.get("seconds_per_file", 0.0),
                -result.get("done_count", 0),
            )

        return [result["model"] for result in sorted(results, key=_rank_key)]

    def _is_invalid_post_commentary(self, text: str | None) -> bool:
        body = _strip_prefix(text or "", _POST_PREFIXES)
        return bool(body) and any(marker in body for marker in _POST_INVALID_MARKERS)

    def _is_invalid_group_issue(self, text: str | None) -> bool:
        body = _strip_prefix(text or "", _RAW_DUMP_PREFIXES)
        if not body:
            return False
        return body.count("=") >= 3 and "这组" not in body and "set" not in body.lower()

    def _redact_config(self, value: Any) -> Any:
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                if key in _REDACTED_KEYS:
                    redacted[key] = "***"
                else:
                    redacted[key] = self._redact_config(item)
            return redacted
        if isinstance(value, list):
            return [self._redact_config(item) for item in value]
        return value

    def _build_model_report(self, result: dict[str, Any]) -> str:
        lines = [
            f"# OMLX Harness Report: {result['model']}",
            "",
            f"- Success: `{result.get('success')}`",
            f"- Verdict: `{result.get('verdict')}`",
            f"- Elapsed: `{result.get('elapsed_seconds')}s`",
            f"- Seconds per file: `{result.get('seconds_per_file')}s/file`",
            f"- Sample count: `{result.get('sample_count')}`",
            f"- Done count: `{result.get('done_count')}`",
            f"- Error count: `{result.get('error_count')}`",
            f"- Profile mode: `{result.get('profile_mode')}`",
            f"- Config snapshot: `{result.get('config_snapshot_path')}`",
            f"- Runtime status before: `{result.get('runtime_status_before_path')}`",
            f"- Runtime status after: `{result.get('runtime_status_after_path')}`",
            f"- DB path: `{result.get('db_path')}`",
            "",
            "## Quick Read",
            "",
            f"- Action hint: {result.get('action_hint')}",
            f"- Primary risks: `{json.dumps(result.get('primary_risks', []), ensure_ascii=False)}`",
            "",
            "## Runtime",
            "",
            f"- Runtime mode before: `{result.get('runtime_mode_before')}`",
            f"- Runtime mode after: `{result.get('runtime_mode_after')}`",
            f"- Shared desktop running before: `{result.get('runtime_shared_desktop_running_before')}`",
            f"- Shared desktop running after: `{result.get('runtime_shared_desktop_running_after')}`",
            f"- Expected runtime models: `{json.dumps(result.get('expected_runtime_models', []), ensure_ascii=False)}`",
            f"- Linked models before: `{json.dumps(result.get('runtime_linked_models_before', []), ensure_ascii=False)}`",
            f"- Linked models after: `{json.dumps(result.get('runtime_linked_models_after', []), ensure_ascii=False)}`",
            f"- Served models after: `{json.dumps(result.get('runtime_served_models_after', []), ensure_ascii=False)}`",
            f"- Instance matches after: `{result.get('runtime_instance_matches_after')}`",
            f"- Effective model-set matches after: `{result.get('runtime_effective_model_set_matches_after')}`",
            f"- Served-model catalog superset after: `{result.get('runtime_served_models_catalog_superset_after')}`",
            f"- Runtime interpretation: {self._build_runtime_interpretation(result)}",
            f"- Runtime status capture error: `{result.get('runtime_status_capture_error') or 'none'}`",
            "",
            "## Health",
            "",
            f"- Invalid post commentary rows: `{result.get('invalid_post_count')}`",
            f"- Invalid group-issue rows: `{result.get('invalid_group_issue_count')}`",
            f"- Max repeated post commentary: `{result.get('max_post_repeat')}`",
            f"- Max repeated group issue: `{result.get('max_group_repeat')}`",
            f"- Warnings: `{', '.join(result.get('warnings', [])) or 'none'}`",
            "",
            "## Scoring Metrics",
            "",
            f"- Score range: `{result.get('scoring_metrics', {}).get('score_range')}`",
            f"- Favorite-value ratio: `{result.get('scoring_metrics', {}).get('favorite_value_ratio')}`",
            f"- Repeated score-vector ratio: `{result.get('scoring_metrics', {}).get('repeated_score_vector_ratio')}`",
            f"- Multi-frame groups: `{result.get('scoring_metrics', {}).get('multi_frame_group_count')}`",
            f"- Avg group score range: `{result.get('scoring_metrics', {}).get('avg_group_score_range')}`",
            "",
            "## Distributions",
            "",
            f"- Decisions: `{json.dumps(result.get('decision_distribution', {}), ensure_ascii=False)}`",
            f"- Scenes: `{json.dumps(result.get('scene_distribution', {}), ensure_ascii=False)}`",
            f"- Score stats: `{json.dumps(result.get('score_stats', {}), ensure_ascii=False)}`",
            "",
            "## Repetition",
            "",
        ]
        for item in result.get("top_repeated_post", []):
            lines.append(f"- post x{item['count']}: {item['text']}")
        for item in result.get("top_repeated_group_issues", []):
            lines.append(f"- group x{item['count']}: {item['text']}")
        lines.extend(["", "## Examples", ""])
        for example in result.get("examples", []):
            lines.append(
                "- "
                f"{example['file_name']} | scene={example['scene']} | decision={example['decision']} | "
                f"score={example['total_score']}"
            )
            lines.append(f"  scene_raw: {example['scene_raw']}")
            lines.append(f"  group: {example['group_issues']}")
            lines.append(f"  post: {example['post']}")
        if result.get("error_rows"):
            lines.extend(["", "## Errors", ""])
            for item in result["error_rows"]:
                lines.append(f"- {item['file_name']}: {item['error']}")
        return "\n".join(lines).strip() + "\n"

    def _build_comparison_report(self, summary: dict[str, Any]) -> str:
        restore_summary = summary.get("restore_summary")
        lines = [
            "# OMLX Harness Comparison",
            "",
            f"- Sample count: `{summary['sample_count']}`",
            f"- Profile mode: `{summary['profile_mode']}`",
            f"- Limit: `{summary['limit']}`",
            f"- Visual merge disabled: `{summary['no_visual_merge']}`",
            f"- Best model: `{summary.get('best_model')}`",
            f"- Recommended order: `{', '.join(summary['recommended_order'])}`",
            f"- Request snapshot: `{summary['request_path']}`",
            f"- Config snapshot: `{summary['config_snapshot_path']}`",
            "",
            "## How To Read",
            "",
            "- `ready_for_default_path`: the sample set finished cleanly and the text quality guards stayed quiet.",
            "- `needs_prompt_refine`: structure is usable, but repetition is high enough to justify prompt/profile tuning.",
            "- `needs_structural_fix`: the model leaked the wrong kind of text, so prompt/guard work comes before taste debates.",
            "- `runtime_unstable`: fix runtime/probe or request stability before judging output quality.",
            "",
            "## Recommendation",
            "",
            f"- {summary.get('best_model_reason')}",
            "",
            "## Restore",
            "",
        ]
        lines.extend(self._build_restore_lines(restore_summary))
        lines.extend(["", "## Models", ""])
        for result in summary.get("results", []):
            lines.append(
                "- "
                f"{result['model']}: verdict={result.get('verdict')} "
                f"shared_runtime_drift={result.get('shared_runtime_drift_detected')} "
                f"effective_model_set_matches={result.get('runtime_effective_model_set_matches_after')} "
                f"invalid_post={result.get('invalid_post_count')} "
                f"invalid_group={result.get('invalid_group_issue_count')} "
                f"post_repeat={result.get('max_post_repeat')} "
                f"group_repeat={result.get('max_group_repeat')} "
                f"seconds_per_file={result.get('seconds_per_file')}"
            )
            lines.append(f"  runtime: {self._build_runtime_interpretation(result)}")
        return "\n".join(lines).strip() + "\n"

    def _build_restore_lines(self, restore_summary: dict[str, Any] | None) -> list[str]:
        if not restore_summary:
            return ["- Restore summary: `none`"]
        return [
            f"- Restored: `{restore_summary.get('restored')}`",
            f"- Restarted: `{restore_summary.get('restarted')}`",
            f"- Restore active models: `{json.dumps(restore_summary.get('active_models', []), ensure_ascii=False)}`",
            f"- Restore linked models: `{json.dumps(restore_summary.get('linked_models', []), ensure_ascii=False)}`",
            f"- Restore served models: `{json.dumps(restore_summary.get('served_models', []), ensure_ascii=False)}`",
            f"- Restore drift detected: `{restore_summary.get('drift_detected')}`",
            f"- Restore reason: `{restore_summary.get('reason') or 'none'}`",
            f"- Restore error: `{restore_summary.get('error') or 'none'}`",
            f"- Restore snapshot: `{json.dumps(restore_summary, ensure_ascii=False)}`",
        ]

    def _build_runtime_interpretation(self, result: dict[str, Any]) -> str:
        if result.get("runtime_status_capture_error"):
            return "runtime status snapshots failed, so runtime alignment could not be interpreted."
        runtime_mode = result.get("runtime_mode_after")
        if runtime_mode == "shared_desktop" and result.get("runtime_shared_desktop_running_after") is False:
            return "shared desktop runtime was not running after the harness run."
        if result.get("runtime_effective_model_set_matches_after") is False:
            return "runtime did not effectively expose the expected candidate model set."
        if result.get("shared_runtime_drift_detected"):
            return "shared desktop runtime drifted away from the candidate model set."
        if runtime_mode == "shared_desktop":
            if result.get("runtime_served_models_catalog_superset_after"):
                return (
                    "shared desktop runtime looks aligned; `/v1/models` appears to include "
                    "installed-model catalog extras."
                )
            return "shared desktop runtime looks aligned to the candidate model set."
        if runtime_mode == "dedicated":
            if result.get("runtime_instance_matches_after"):
                return "dedicated runtime looks aligned to the candidate model set."
            return "dedicated runtime did not report an exact model-set match."
        if result.get("runtime_instance_matches_after") is True:
            return "runtime looks aligned to the candidate model set."
        return "runtime state was not captured clearly enough to interpret."
