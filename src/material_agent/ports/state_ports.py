from typing import Any, Protocol

from ..app.dto import JobFileStatus, JobStage, JobStatus, JobType, SessionKind, SessionStatus


class SessionRepositoryPort(Protocol):
    def create_session(
        self,
        *,
        kind: SessionKind,
        input_root: str,
        config_snapshot: dict[str, Any],
        status: SessionStatus,
    ) -> str: ...


class JobRepositoryPort(Protocol):
    def create_job(
        self,
        *,
        session_id: str,
        job_type: JobType,
        stage: JobStage,
        status: JobStatus,
    ) -> str: ...

    def update_job(
        self,
        job_id: str,
        *,
        stage: JobStage | None = None,
        status: JobStatus | None = None,
        summary: dict[str, Any] | None = None,
    ) -> None: ...

    def upsert_job_file(
        self,
        *,
        job_id: str,
        file_path: str,
        status: JobFileStatus,
        group_id: str | None = None,
        rank: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        score_total: float | None = None,
        scene: str | None = None,
        scene_raw: str | None = None,
    ) -> str: ...

    def append_event(
        self,
        *,
        session_id: str,
        job_id: str,
        event_type: str,
        payload: dict[str, Any],
        job_file_id: str | None = None,
    ) -> str: ...
