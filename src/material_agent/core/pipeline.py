from contextlib import nullcontext
from pathlib import Path

from ..adapters.state.processed_sqlite import SQLiteProcessedRepository
from ..adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from ..app.review_service import ReviewRunService
from ..commands.scoring import build_score_cache_key
from ..io.scanner import scan_arw_files
from ..utils.config_validator import normalize_config
from ..utils.progress import ProgressCallback, RichProgress
from ..utils.run_control import exclusive_run_lock, sigterm_as_cancellation
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

        runtime_paths = ensure_runtime_paths(Path(cfg.get("input_dir", "") or "."))
        runtime_paths.work_dir.mkdir(parents=True, exist_ok=True)
        with exclusive_run_lock(runtime_paths.work_dir / "run.lock"):
            runtime_repo = SQLiteRuntimeRepository(runtime_paths.db_path)
            try:
                runtime_repo.reconcile_abandoned_runs()
                review_service = ReviewRunService(runtime_repo)
                state_context = (
                    nullcontext(self.state)
                    if self.state is not None
                    else SQLiteProcessedRepository(
                        runtime_paths.db_path,
                        reprocess=cfg.get("reprocess", False),
                        score_cache_key=build_score_cache_key(cfg),
                    )
                )
                with state_context as state, sigterm_as_cancellation():
                    job_id = review_service.run(
                        input_dir=cfg.get("input_dir", ""),
                        config=cfg,
                        state=state,
                        progress=self.progress,
                        dry_run=self.dry_run,
                        file_paths=list(files),
                    )
                job_result = runtime_repo.get_job_result(job_id)
                return {
                    "job_id": job_id,
                    "status": job_result["status"],
                    "summary": job_result["summary"],
                }
            finally:
                runtime_repo.close()
