class RichEventSink:
    def __init__(self, progress):
        self.progress = progress

    def publish(
        self,
        *,
        event_type: str,
        payload: dict,
        session_id: str | None = None,
        job_id: str | None = None,
        job_file_id: str | None = None,
    ) -> None:
        del session_id, job_id, job_file_id
        if event_type == "job_started":
            self.progress.on_start(int(payload.get("file_count", 0)))
        elif event_type == "job_file_started":
            self.progress.on_file_start(payload["file_path"], int(payload.get("index", 0)))
        elif event_type == "job_file_scored":
            self.progress.on_score_done(payload["file_path"], float(payload.get("score_total", 0.0)))
        elif event_type == "job_file_written":
            self.progress.on_write_done(payload["file_path"], float(payload.get("score_total", 0.0)))
        elif event_type == "job_file_simulated":
            self.progress.on_file_done(
                payload["file_path"],
                float(payload.get("score_total", 0.0)),
                skipped=True,
            )
        elif event_type == "job_file_failed":
            self.progress.on_error(payload["file_path"], RuntimeError(payload.get("error", "unknown error")))
        elif event_type == "job_finished":
            self.progress.on_finish()
