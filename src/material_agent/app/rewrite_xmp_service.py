from contextlib import nullcontext
from pathlib import Path

from ..adapters.metadata.exiftool_xmp import ExifToolXMPWriter
from ..adapters.state.processed_sqlite import SQLiteProcessedRepository
from ..domain.commentary import rank_description
from ..domain.scoring_engine import build_visible_breakdown_instructions, build_xmp_instructions
from ..utils.constants import VISION_DIMS, scene_label
from ..utils.runtime_paths import ensure_runtime_paths


class RewriteXmpService:
    def __init__(
        self,
        writer: ExifToolXMPWriter | None = None,
        repository: SQLiteProcessedRepository | None = None,
    ):
        self.writer = writer or ExifToolXMPWriter()
        self.repository = repository

    def run(self, input_dir: str, *, dry_run: bool, output_language: str = "zh", progress=None) -> dict[str, int]:
        db_path = ensure_runtime_paths(input_dir).db_path
        if not db_path.exists():
            raise FileNotFoundError(db_path)

        ok = err = 0
        with self._open_repository(input_dir) as repository:
            rows = repository.fetch_rewrite_rows()

        if progress:
            progress.on_phase_start("rewrite-xmp", len(rows))
        for row in rows:
            arw_path = Path(row["file_path"])
            xmp_path = self.writer._sidecar_path(arw_path)
            user_keywords = self.writer._read_non_pj_subject_tags(xmp_path) if xmp_path.exists() else []
            user_identifiers = (
                self.writer._read_non_pj_identifier_tags(xmp_path) if xmp_path.exists() else []
            )
            user_hierarchical = (
                self.writer._read_non_pj_hierarchical_subject_tags(xmp_path)
                if xmp_path.exists()
                else []
            )

            if dry_run:
                print(
                    f"[dry-run] {arw_path.name}: rating={row['star_rating']} "
                    f"score={row['total_score']:.1f} preserve={user_keywords}"
                )
                continue

            boosted = bool(row["group_boosted"])
            subject_tags = self.writer.build_subject_tags(
                score=row["total_score"],
                rank=row["group_rank"],
                group_size=row["group_size"],
                group_id=row["group_id"],
                boosted=boosted,
                decision=row["decision"],
            )
            if row["scene"]:
                subject_tags.append(f"pj:scene={scene_label(row['scene'], output_language)}")

            visible_breakdown = {}
            if row["visible_breakdown_json"]:
                import json

                visible_breakdown = json.loads(row["visible_breakdown_json"])
            if visible_breakdown:
                instructions = build_visible_breakdown_instructions(visible_breakdown, output_language=output_language)
            else:
                db_scores = {dim: row[f"score_{dim}"] for dim in VISION_DIMS}
                db_scores["exposure"] = row["score_exposure"]
                db_scores["sharpness"] = row["score_sharpness"]
                instructions = build_xmp_instructions(
                    {dim: score for dim, score in db_scores.items() if score is not None},
                    output_language=output_language,
                )

            parts = [part for part in [row["commentary_group_issues"], row["commentary_shooting"]] if part]
            group_commentary = "\n".join(parts)
            post_commentary = row["commentary_post"] or ""
            description = (
                f"{rank_description(row['group_rank'], row['group_size'], output_language)}\n\n"
                f"{group_commentary}\n\n{post_commentary}"
            ).strip()

            try:
                self._rewrite_xmp_atomically(
                    xmp_path=xmp_path,
                    rating=row["star_rating"],
                    subject_tags=user_keywords,
                    identifier_tags=user_identifiers + subject_tags,
                    hierarchical_subject_tags=user_hierarchical,
                    instructions=instructions,
                    description=description,
                )
                ok += 1
                if progress:
                    progress.on_write_done(str(arw_path), float(row["total_score"]))
            except Exception as error:
                print(f"ERROR writing {xmp_path}: {error}")
                err += 1
                if progress:
                    progress.on_error(str(arw_path), error)
            else:
                if progress:
                    progress.on_phase_advance()

        return {"ok": ok, "err": err}

    def _rewrite_xmp_atomically(
        self,
        *,
        xmp_path: Path,
        rating: int,
        subject_tags: list[str],
        identifier_tags: list[str],
        hierarchical_subject_tags: list[str],
        instructions: str,
        description: str,
    ) -> None:
        temp_path = xmp_path.with_name(f"{xmp_path.name}.tmp")
        try:
            temp_path.unlink(missing_ok=True)
            self.writer._write_minimal_xmp(
                temp_path,
                rating,
                subject_tags,
                identifier_tags,
                hierarchical_subject_tags,
                instructions,
                description,
            )
            temp_path.replace(xmp_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _open_repository(self, input_dir: str):
        if self.repository is not None:
            return nullcontext(self.repository)
        return SQLiteProcessedRepository(input_dir)
