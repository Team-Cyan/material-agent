from pathlib import Path
from collections.abc import Callable

from ..adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from ..app.dto import JobStage, JobStatus, JobType, SessionKind, SessionStatus
from ..app.job_service import JobService
from ..app.review_runtime import build_review_job_executor
from ..app.session_service import SessionService
from ..io.scanner import scan_arw_files


class ReviewRunService:
    def __init__(self, repository: SQLiteRuntimeRepository):
        self.repository = repository
        self.session_service = SessionService(repository)
        self.job_service = JobService(repository)

    @staticmethod
    def _resolve_session_status(job_result: object) -> SessionStatus:
        if not isinstance(job_result, dict):
            raise RuntimeError(f"invalid job result status: {job_result!r}")
        result_status = job_result.get("status")
        if result_status == JobStatus.FINISHED.value:
            return SessionStatus.FINISHED
        if result_status == JobStatus.FINISHED_WITH_ERRORS.value:
            return SessionStatus.FINISHED_WITH_ERRORS
        raise RuntimeError(f"invalid job result status: {result_status!r}")

    def run(
        self,
        *,
        input_dir: str,
        config: dict,
        state,
        progress,
        dry_run: bool,
        file_paths: list[str] | None = None,
        preflight_hook: Callable[[str, str], None] | None = None,
        build_executor=build_review_job_executor,
    ) -> str:
        input_path = Path(input_dir)
        session_id = self.session_service.create_session(
            kind=SessionKind.CLI,
            input_root=str(input_path),
            config_snapshot=config,
        )
        job_id = self.job_service.create_job(
            session_id=session_id,
            job_type=JobType.REVIEW_PHOTOS,
            initial_stage=JobStage.DISCOVER,
        )
        self.session_service.update_session(session_id, status=SessionStatus.RUNNING)
        try:
            if preflight_hook is not None:
                preflight_hook(session_id, job_id)
            files = file_paths
            if files is None:
                files = scan_arw_files(str(input_path), config.get("raw_extensions"))
            max_files = config.get("review_pipeline", {}).get("max_files")
            if max_files is not None:
                max_files = int(max_files)
                if max_files < 1:
                    raise ValueError("review_pipeline.max_files must be at least 1")
                files = files[:max_files]
            pending_files = [file_path for file_path in files if not state.is_done(file_path)]
            executor = build_executor(
                repository=self.repository,
                config=config,
                state=state,
                progress=progress,
                dry_run=dry_run,
            )
            job_result = executor.run(job_id, pending_files)
            session_status = self._resolve_session_status(job_result)
        except Exception as error:
            self.job_service.update_job(
                job_id,
                stage=JobStage.FINALIZE,
                status=JobStatus.FAILED,
                summary={"error": str(error)},
            )
            self.repository.append_event(
                session_id=session_id,
                job_id=job_id,
                event_type="job_failed",
                payload={"error": str(error)},
            )
            self.session_service.update_session(session_id, status=SessionStatus.FAILED)
            raise
        self.session_service.update_session(session_id, status=session_status)
        return job_id
