import json

from ..adapters.state.processed_sqlite import SQLiteProcessedRepository
from ..domain.layered_decision import (
    apply_group_best_candidate_review,
    group_best_candidate_review_enabled,
    summarize_signals,
)
from ..domain.aesthetic_calibration import calibrate_signals_for_rescore


class RescoreService:
    def __init__(self, repository: SQLiteProcessedRepository):
        self.repository = repository

    def run(
        self,
        *,
        scene_filters: list[str] | None,
        scene_profiles: dict,
        decision_policy: dict,
        screening_policy: dict,
        aesthetic_calibration: dict | None = None,
        grouping_config: dict | None = None,
    ) -> int:
        config = {
            "scene_profiles": scene_profiles or {},
            "decision_policy": decision_policy or {},
            "screening_policy": screening_policy or {},
        }
        best_candidate_review_enabled = group_best_candidate_review_enabled(
            {"grouping": grouping_config or {}}
        )
        filtered_mode = bool(scene_filters)

        rows = self.repository.fetch_rescore_rows(scene_filters=scene_filters)
        signal_rows = self.repository.fetch_signal_rows()
        signals_by_file: dict[str, list[dict]] = {}
        for row in signal_rows:
            signals_by_file.setdefault(row["file_path"], []).append(
                {
                    "stage": row["stage"],
                    "signal_key": row["signal_key"],
                    "value": row["value"],
                    "confidence": row["confidence"],
                    "source": row["source"],
                    "model_name": row["model_name"],
                    "model_version": row["model_version"],
                }
            )

        summaries_by_group: dict[str, list[dict]] = {}
        for row in rows:
            scene = row["scene"] or "other"
            file_signals = signals_by_file.get(
                row["file_path"]
            ) or self.repository.legacy_scores_to_signals(row)
            if not file_signals:
                continue

            file_signals = calibrate_signals_for_rescore(
                file_signals, scene=scene, config=aesthetic_calibration
            )

            summary = summarize_signals(file_signals, scene=scene, config=config)
            summaries_by_group.setdefault(row["group_id"] or row["file_path"], []).append(
                {
                    "file_path": row["file_path"],
                    "group_id": row["group_id"],
                    "group_rank": row["group_rank"],
                    "total_score": summary.total_score,
                    "star_rating": summary.star_rating,
                    "decision": summary.decision,
                    "decision_reasons": summary.decision_reasons,
                    "screening_prior": summary.screening_prior,
                    "visible_breakdown": summary.visible_breakdown,
                    "policy_version": summary.policy_version,
                }
            )

        updates: list[dict] = []
        if filtered_mode:
            for items in summaries_by_group.values():
                for item in items:
                    updates.append(
                        {
                            **item,
                            "decision_reasons": json.dumps(
                                item["decision_reasons"], ensure_ascii=False
                            ),
                            "visible_breakdown_json": json.dumps(
                                item["visible_breakdown"], ensure_ascii=False
                            ),
                        }
                    )
            if updates:
                self.repository.update_rejudge_batch(updates)
            return len(updates)

        for group_id, items in summaries_by_group.items():
            ranked = sorted(items, key=lambda item: float(item["total_score"]), reverse=True)
            ranked_pairs = [(item["file_path"], item) for item in ranked]
            ranked_pairs = apply_group_best_candidate_review(
                ranked_pairs, enabled=best_candidate_review_enabled
            )
            ranked_pairs = sorted(
                ranked_pairs, key=lambda item: float(item[1]["total_score"]), reverse=True
            )
            for rank, (_, item) in enumerate(ranked_pairs, start=1):
                updates.append(
                    {
                        **item,
                        "group_rank": rank,
                        "decision_reasons": json.dumps(
                            item["decision_reasons"], ensure_ascii=False
                        ),
                        "visible_breakdown_json": json.dumps(
                            item["visible_breakdown"], ensure_ascii=False
                        ),
                    }
                )

        if updates:
            self.repository.update_rejudge_batch(updates)
        return len(updates)
