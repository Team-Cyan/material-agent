import json
from collections import defaultdict
from contextlib import nullcontext

from ..adapters.state.processed_sqlite import SQLiteProcessedRepository
from ..domain.commentary import (
    regenerate_group_commentary,
    regenerate_post_commentary,
    split_group_commentary_sections,
)
from .rewrite_xmp_service import RewriteXmpService


class RewriteCommentaryService:
    def __init__(
        self,
        repository: SQLiteProcessedRepository | None = None,
        xmp_service: RewriteXmpService | None = None,
    ):
        self.repository = repository
        self.xmp_service = xmp_service

    def run(
        self,
        input_dir: str,
        *,
        dry_run: bool,
        rewrite_xmp: bool,
        output_language: str = "zh",
    ) -> dict[str, int]:
        with self._open_repository(input_dir) as repository:
            rows = repository.fetch_done_commentary_rows()
            grouped: dict[str, list] = defaultdict(list)
            for row in rows:
                grouped[row["group_id"] or row["file_path"]].append(row)

            updates: list[dict] = []
            changed = 0
            for group_rows in grouped.values():
                score_details = [self._score_detail(row) for row in group_rows]
                group_key = group_rows[0]["group_id"] or group_rows[0]["file_path"]
                group_commentary = regenerate_group_commentary(
                    score_details,
                    variant_key=group_key,
                    output_language=output_language,
                )
                group_issues, shooting = split_group_commentary_sections(group_commentary, output_language)
                for row in group_rows:
                    post = regenerate_post_commentary(
                        self._scores(row),
                        scene=row["scene"],
                        scene_raw=row["scene_raw"] or "",
                        decision=row["decision"],
                        rank=row["group_rank"],
                        group_size=row["group_size"],
                        variant_key=row["file_path"],
                        visible_breakdown=self._visible_breakdown(row),
                        output_language=output_language,
                    )
                    update = {
                        "file_path": row["file_path"],
                        "issues": group_issues,
                        "shooting": shooting,
                        "post": post,
                    }
                    updates.append(update)
                    if (
                        (row["commentary_group_issues"] or "") != group_issues
                        or (row["commentary_shooting"] or "") != shooting
                        or (row["commentary_post"] or "") != post
                    ):
                        changed += 1

            if not dry_run:
                repository.update_commentary_batch(updates)

        rewritten_xmp = 0
        xmp_errors = 0
        if rewrite_xmp:
            summary = (self.xmp_service or RewriteXmpService()).run(
                input_dir,
                dry_run=dry_run,
                output_language=output_language,
            )
            rewritten_xmp = int(summary.get("ok", 0))
            xmp_errors = int(summary.get("err", 0))

        return {
            "done_rows": len(rows),
            "updated": changed,
            "rewritten_xmp": rewritten_xmp,
            "xmp_errors": xmp_errors,
        }

    @staticmethod
    def _scores(row) -> dict[str, float]:
        scores = {}
        if row["score_exposure"] is not None:
            scores["exposure"] = float(row["score_exposure"])
        if row["score_sharpness"] is not None:
            scores["sharpness"] = float(row["score_sharpness"])
        for dim in ("subject", "composition", "lighting", "color", "clarity", "depth", "mood"):
            value = row[f"score_{dim}"]
            if value is not None:
                scores[dim] = float(value)
        return scores

    @classmethod
    def _score_detail(cls, row) -> dict[str, float]:
        detail = cls._scores(row)
        detail["_scene"] = row["scene"] or "other"
        detail["_scene_raw"] = row["scene_raw"] or ""
        detail["_decision"] = row["decision"]
        return detail

    @staticmethod
    def _visible_breakdown(row) -> dict[str, float]:
        raw = row["visible_breakdown_json"]
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def _open_repository(self, input_dir: str):
        if self.repository is not None:
            return nullcontext(self.repository)
        return SQLiteProcessedRepository(input_dir)
