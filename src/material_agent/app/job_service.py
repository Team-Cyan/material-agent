from typing import Any

from .dto import JobStage, JobStatus, JobType


class JobService:
    def __init__(self, repository):
        self.repository = repository

    def create_job(
        self,
        *,
        session_id: str,
        job_type: JobType,
        initial_stage: JobStage,
        status: JobStatus = JobStatus.QUEUED,
    ) -> str:
        job_id = self.repository.create_job(
            session_id=session_id,
            job_type=job_type,
            stage=initial_stage,
            status=status,
        )
        self.repository.append_event(
            session_id=session_id,
            job_id=job_id,
            event_type="job_created",
            payload={"job_type": job_type.value, "stage": initial_stage.value},
        )
        return job_id

    def update_job(
        self,
        job_id: str,
        *,
        stage: JobStage | None = None,
        status: JobStatus | None = None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        self.repository.update_job(job_id, stage=stage, status=status, summary=summary)

    def list_jobs(self, session_id: str):
        return self.repository.list_jobs(session_id)

    def list_job_files(self, job_id: str):
        return self.repository.list_job_files(job_id)

    def list_artifacts(self, job_id: str):
        return self.repository.list_artifacts(job_id)

    def list_events(self, job_id: str):
        return self.repository.list_events(job_id)
