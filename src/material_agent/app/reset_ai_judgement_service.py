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

    def run(self, input_dir: str, *, dry_run: bool, clear_xmp: bool = True) -> dict[str, int]:
        with self._open_repository(input_dir) as repository:
            file_paths = repository.fetch_ai_file_paths()
            if dry_run:
                return {
                    "files": len(file_paths),
                    "xmp_cleared": sum(1 for path in file_paths if clear_xmp),
                    "processed_rows_deleted": len(file_paths),
                    "signal_rows_deleted": len(repository.fetch_signal_rows()),
                }

            xmp_cleared = 0
            if clear_xmp:
                for file_path in file_paths:
                    self.writer.clear_ai_tags(file_path)
                    xmp_cleared += 1

            summary = repository.clear_ai_judgement()
            summary["files"] = len(file_paths)
            summary["xmp_cleared"] = xmp_cleared
            return summary

    def _open_repository(self, input_dir: str):
        if self.repository is not None:
            return nullcontext(self.repository)
        return SQLiteProcessedRepository(input_dir)
