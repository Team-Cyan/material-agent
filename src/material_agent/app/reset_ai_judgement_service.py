from contextlib import nullcontext

from ..adapters.metadata.exiftool_xmp import ExifToolXMPWriter
from ..adapters.state.processed_sqlite import SQLiteProcessedRepository


class ResetAiJudgementService:
    def __init__(
        self,
        *,
        repository: SQLiteProcessedRepository | None = None,
        writer: ExifToolXMPWriter | None = None,
    ):
        self.repository = repository
        self.writer = writer or ExifToolXMPWriter()

    def run(self, input_dir: str, *, dry_run: bool, clear_xmp: bool = False) -> dict[str, int]:
        with self._open_repository(input_dir) as repository:
            reset_rows = repository.fetch_ai_reset_rows()
            if dry_run:
                return {
                    "files": len(reset_rows),
                    "xmp_cleared": sum(1 for _row in reset_rows if clear_xmp),
                    "processed_rows_deleted": len(reset_rows),
                    "signal_rows_deleted": len(repository.fetch_signal_rows()),
                }

            xmp_cleared = 0
            if clear_xmp:
                for row in reset_rows:
                    self.writer.clear_ai_tags(
                        row["file_path"],
                        expected_fields=row["xmp_payload"],
                        force_scalar_clear=False,
                    )
                    xmp_cleared += 1

            summary = repository.clear_ai_judgement()
            summary["files"] = len(reset_rows)
            summary["xmp_cleared"] = xmp_cleared
            return summary

    def _open_repository(self, input_dir: str):
        if self.repository is not None:
            return nullcontext(self.repository)
        return SQLiteProcessedRepository(input_dir)
