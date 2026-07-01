from pathlib import Path

from ..adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from ..app.review_service import ReviewRunService
from ..io.scanner import scan_arw_files
from ..utils.config_validator import normalize_config
from ..utils.progress import ProgressCallback, RichProgress
from ..utils.runtime_paths import ensure_runtime_paths
from ..utils.state import State


class Pipeline:
    def __init__(
        self,
        config: dict,
        state: State = None,
        progress: ProgressCallback = None,
        log_path: str = None,
        dry_run: bool = False,
    ):
        self.config = normalize_config(config)
        self.state = state
        self.dry_run = dry_run
        self.progress = progress or RichProgress(log_path=log_path)

    def run(self, files: list[str] = None):
        cfg = self.config
        if files is None:
            files = scan_arw_files(cfg.get("input_dir", ""), cfg.get("raw_extensions"))
        if not files:
            return

        if self.state:
            new_files = [f for f in files if not self.state.is_done(f) and not self.state.is_scored(f)]
            scored_files = [f for f in files if self.state.is_scored(f)]
            done_files = [f for f in files if self.state.is_done(f)]
        else:
            new_files, scored_files, done_files = files, [], []
        for file_path in done_files:
            self.progress.on_file_start(file_path, 0)
            self.progress.on_file_done(file_path, 0.0, skipped=True)
        runtime_db_path = ensure_runtime_paths(Path(cfg.get("input_dir", "") or ".")).db_path
        runtime_repo = SQLiteRuntimeRepository(runtime_db_path)
        review_service = ReviewRunService(runtime_repo)
        review_service.run(
            input_dir=cfg.get("input_dir", ""),
            config=cfg,
            state=self.state,
            progress=self.progress,
            dry_run=self.dry_run,
            file_paths=new_files + scored_files,
        )
