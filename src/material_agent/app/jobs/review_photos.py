from concurrent.futures import Future, ThreadPoolExecutor
import hashlib

from ..dto import JobFileStatus, JobStage, JobStatus


class _ScorePreparationPool(ThreadPoolExecutor):
    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None and not issubclass(exc_type, Exception):
            self.shutdown(wait=False, cancel_futures=True)
            return False
        return super().__exit__(exc_type, exc_value, traceback)


class ReviewPhotosJob:
    def __init__(
        self,
        *,
        repository,
        event_sink,
        group_files=None,
        prepare_score=None,
        score_prepared=None,
        score_file=None,
        finalize_group=None,
        write_file=None,
        score_prefetch_window: int = 1,
        write_outputs: bool = True,
    ):
        self.repository = repository
        self.event_sink = event_sink
        self.group_files = group_files or (lambda file_paths: [file_paths])
        if prepare_score is None and score_prepared is None:
            self.prepare_score = lambda file_path: file_path
            self.score_prepared = score_file or (
                lambda file_path: {"score_total": 0.0, "scene": "other", "scene_raw": ""}
            )
        else:
            self.prepare_score = prepare_score or (lambda file_path: file_path)
            self.score_prepared = score_prepared or (
                lambda prepared: {"score_total": 0.0, "scene": "other", "scene_raw": ""}
            )
        self.finalize_group = finalize_group or (lambda group_results, *, group_id: group_results)
        self.write_file = write_file or (lambda file_path, score_payload, *, rank, group_id, group_size: None)
        self.score_prefetch_window = min(32, max(1, int(score_prefetch_window)))
        self.write_outputs = bool(write_outputs)

    def _emit(self, *, session_id: str, job_id: str, event_type: str, payload: dict, job_file_id: str | None = None):
        self.repository.append_event(
            session_id=session_id,
            job_id=job_id,
            job_file_id=job_file_id,
            event_type=event_type,
            payload=payload,
        )
        self.event_sink.publish(
            session_id=session_id,
            job_id=job_id,
            job_file_id=job_file_id,
            event_type=event_type,
            payload=payload,
        )

    def _update_stage(self, job_id: str, stage: JobStage, status: JobStatus, *, session_id: str) -> None:
        self.repository.update_job(job_id, stage=stage, status=status)
        self._emit(
            session_id=session_id,
            job_id=job_id,
            event_type="job_stage_changed",
            payload={"stage": stage.value, "status": status.value},
        )

    def _build_summary(
        self,
        *,
        status: JobStatus,
        total_files: int,
        written_files: int,
        error_files: int,
        skipped_files: int,
        simulated_files: int,
        job_id: str,
    ) -> dict:
        scored_files = sum(
            1 for job_file in self.repository.list_job_files(job_id) if job_file.score_total is not None
        )
        return {
            "status": status.value,
            "total_files": total_files,
            "written_files": written_files,
            "error_files": error_files,
            "skipped_files": skipped_files,
            "simulated_files": simulated_files,
            "scored_files": scored_files,
        }

    def _load_score_payload(self, *, job_id: str, file_path: str):
        job_file = self.repository.get_job_file(job_id=job_id, file_path=file_path)
        if job_file is None:
            return None, None
        payload = self.repository.get_artifact_metadata(job_file_id=job_file.id, kind="score_payload")
        if payload is None and job_file.score_total is not None:
            payload = {
                "score_total": float(job_file.score_total),
                "scene": job_file.scene or "other",
                "scene_raw": job_file.scene_raw or "",
                "scores": {},
                "meta": {},
                "instructions": "",
                "boosted": False,
            }
        return job_file, payload

    @staticmethod
    def _group_id(group: list[str]) -> str:
        members = "\0".join(sorted(str(file_path) for file_path in group)).encode("utf-8")
        return f"group_{hashlib.sha256(members).hexdigest()[:16]}"

    @staticmethod
    def _refresh_cached_done_write_flags(
        group_results: list[tuple[str, dict]],
        *,
        group_id: str,
    ) -> None:
        ranked = sorted(
            group_results,
            key=lambda item: float(item[1].get("score_total", 0.0)),
            reverse=True,
        )
        group_size = len(ranked)
        for rank, (_, payload) in enumerate(ranked, start=1):
            if not payload.get("skip_write"):
                continue
            previous = payload.get("previous_group_info")
            payload["skip_write"] = bool(
                isinstance(previous, dict)
                and previous.get("group_id") == group_id
                and previous.get("group_rank") == rank
                and previous.get("group_size") == group_size
            )

    def _consume_group_scores(self, *, group: list[str], group_id: str, job_id: str, session_id: str):
        group_results: list[tuple[str, dict]] = []
        resumable_job_files: dict[str, object] = {}
        group_can_be_skipped = True
        pending_prepares: dict[str, Future] = {}
        started_files: set[str] = set()
        file_indexes = {file_path: index for index, file_path in enumerate(group)}
        error_files = 0

        def _emit_started(file_path: str) -> None:
            if file_path in started_files:
                return
            job_file_id = self.repository.upsert_job_file(
                job_id=job_id,
                file_path=file_path,
                status=JobFileStatus.PENDING,
                group_id=group_id,
            )
            self._emit(
                session_id=session_id,
                job_id=job_id,
                job_file_id=job_file_id,
                event_type="job_file_started",
                payload={"file_path": file_path, "index": file_indexes[file_path]},
            )
            started_files.add(file_path)

        def _submit_prepare(executor: ThreadPoolExecutor, file_path: str) -> None:
            _emit_started(file_path)
            pending_prepares[file_path] = executor.submit(self.prepare_score, file_path)

        max_workers = min(self.score_prefetch_window, len(group)) or 1
        with _ScorePreparationPool(max_workers=max_workers) as executor:
            submit_index = 0
            for index, file_path in enumerate(group):
                existing_job_file, resumable_payload = self._load_score_payload(job_id=job_id, file_path=file_path)
                if existing_job_file is not None:
                    resumable_job_files[file_path] = existing_job_file
                    if existing_job_file.status is JobFileStatus.WRITTEN:
                        group_results.append((file_path, resumable_payload or {}))
                        continue
                    if existing_job_file.status is JobFileStatus.SCORED and resumable_payload is not None:
                        group_can_be_skipped = False
                        group_results.append((file_path, resumable_payload))
                        continue

                group_can_be_skipped = False
                if file_path not in pending_prepares:
                    _submit_prepare(executor, file_path)
                while submit_index < len(group) and len(pending_prepares) < max_workers:
                    candidate = group[submit_index]
                    submit_index += 1
                    if candidate == file_path or candidate in pending_prepares:
                        continue
                    candidate_job_file, candidate_payload = self._load_score_payload(
                        job_id=job_id,
                        file_path=candidate,
                    )
                    if candidate_job_file is not None:
                        resumable_job_files[candidate] = candidate_job_file
                        if candidate_job_file.status is JobFileStatus.WRITTEN:
                            continue
                        if candidate_job_file.status is JobFileStatus.SCORED and candidate_payload is not None:
                            continue
                    _submit_prepare(executor, candidate)

                try:
                    prepared = pending_prepares.pop(file_path).result()
                    score_payload = self.score_prepared(prepared)
                except Exception as error:
                    job_file_id = self.repository.upsert_job_file(
                        job_id=job_id,
                        file_path=file_path,
                        status=JobFileStatus.ERROR,
                        group_id=group_id,
                        error_message=str(error),
                    )
                    self._emit(
                        session_id=session_id,
                        job_id=job_id,
                        job_file_id=job_file_id,
                        event_type="job_file_failed",
                        payload={"file_path": file_path, "error": str(error)},
                    )
                    error_files += 1
                    continue

                group_results.append((file_path, score_payload))
                job_file_id = self.repository.upsert_job_file(
                    job_id=job_id,
                    file_path=file_path,
                    status=JobFileStatus.SCORED,
                    group_id=group_id,
                    score_total=float(score_payload.get("score_total", 0.0)),
                    scene=score_payload.get("scene"),
                    scene_raw=score_payload.get("scene_raw"),
                )
                self._emit(
                    session_id=session_id,
                    job_id=job_id,
                    job_file_id=job_file_id,
                    event_type="job_file_scored",
                    payload={
                        "file_path": file_path,
                        "score_total": float(score_payload.get("score_total", 0.0)),
                    },
                )
                self.repository.upsert_artifact(
                    job_id=job_id,
                    job_file_id=job_file_id,
                    kind="score_payload",
                    uri=f"memory://job-files/{job_file_id}/score-payload",
                    metadata=score_payload,
                )
                resumable_job_files[file_path] = self.repository.get_job_file(job_id=job_id, file_path=file_path)
        return group_results, resumable_job_files, group_can_be_skipped, error_files

    def run(self, job_id: str, file_paths: list[str]) -> dict:
        session_id = self.repository.get_job_session_id(job_id)
        written_files = 0
        error_files = 0
        skipped_files = 0
        simulated_files = 0
        self.repository.update_job(job_id, stage=JobStage.DISCOVER, status=JobStatus.RUNNING)
        self._emit(
            session_id=session_id,
            job_id=job_id,
            event_type="job_started",
            payload={"file_count": len(file_paths)},
        )

        self._update_stage(job_id, JobStage.GROUP, JobStatus.RUNNING, session_id=session_id)
        groups = self.group_files(file_paths)

        for group in groups:
            self._update_stage(job_id, JobStage.SCORE, JobStatus.RUNNING, session_id=session_id)
            group_id = self._group_id(group)
            (
                group_results,
                resumable_job_files,
                group_can_be_skipped,
                group_error_files,
            ) = self._consume_group_scores(
                group=group,
                group_id=group_id,
                job_id=job_id,
                session_id=session_id,
            )
            error_files += group_error_files

            if group_can_be_skipped:
                for file_path, _ in group_results:
                    job_file = resumable_job_files.get(file_path)
                    if job_file is None:
                        continue
                    skipped_files += 1
                    self._emit(
                        session_id=session_id,
                        job_id=job_id,
                        job_file_id=job_file.id,
                        event_type="job_file_skipped",
                        payload={"file_path": file_path, "reason": "already_written"},
                    )
                continue

            self._refresh_cached_done_write_flags(group_results, group_id=group_id)

            self._update_stage(job_id, JobStage.COMMENT, JobStatus.RUNNING, session_id=session_id)
            finalized_results = (
                group_results
                if group_results and all(payload.get("skip_write") for _, payload in group_results)
                else self.finalize_group(group_results, group_id=group_id)
            )
            ranked_results = sorted(
                finalized_results,
                key=lambda item: float(item[1].get("score_total", 0.0)),
                reverse=True,
            )
            self._update_stage(job_id, JobStage.WRITE, JobStatus.RUNNING, session_id=session_id)
            for rank, (file_path, score_payload) in enumerate(ranked_results, start=1):
                existing_job_file = resumable_job_files.get(file_path)
                already_processed = bool(score_payload.get("skip_write")) or (
                    existing_job_file is not None
                    and existing_job_file.status is JobFileStatus.WRITTEN
                )
                if not self.write_outputs and already_processed:
                    job_file_id = self.repository.upsert_job_file(
                        job_id=job_id,
                        file_path=file_path,
                        status=JobFileStatus.SKIPPED,
                        group_id=group_id,
                        rank=rank,
                        score_total=float(score_payload.get("score_total", 0.0)),
                        scene=score_payload.get("scene"),
                        scene_raw=score_payload.get("scene_raw"),
                    )
                    skipped_files += 1
                    self._emit(
                        session_id=session_id,
                        job_id=job_id,
                        job_file_id=job_file_id,
                        event_type="job_file_skipped",
                        payload={
                            "file_path": file_path,
                            "reason": "already_processed_dry_run",
                        },
                    )
                    continue
                if existing_job_file is not None and existing_job_file.status is JobFileStatus.WRITTEN:
                    job_file_id = self.repository.upsert_job_file(
                        job_id=job_id,
                        file_path=file_path,
                        status=JobFileStatus.WRITTEN,
                        group_id=group_id,
                        rank=rank,
                        score_total=float(score_payload.get("score_total", existing_job_file.score_total or 0.0)),
                        scene=score_payload.get("scene", existing_job_file.scene),
                        scene_raw=score_payload.get("scene_raw", existing_job_file.scene_raw),
                    )
                    skipped_files += 1
                    self._emit(
                        session_id=session_id,
                        job_id=job_id,
                        job_file_id=job_file_id,
                        event_type="job_file_skipped",
                        payload={"file_path": file_path, "reason": "already_written"},
                    )
                    continue
                if score_payload.get("skip_write"):
                    job_file_id = self.repository.upsert_job_file(
                        job_id=job_id,
                        file_path=file_path,
                        status=JobFileStatus.WRITTEN,
                        group_id=group_id,
                        rank=rank,
                        score_total=float(score_payload.get("score_total", 0.0)),
                        scene=score_payload.get("scene"),
                        scene_raw=score_payload.get("scene_raw"),
                    )
                    skipped_files += 1
                    self._emit(
                        session_id=session_id,
                        job_id=job_id,
                        job_file_id=job_file_id,
                        event_type="job_file_skipped",
                        payload={"file_path": file_path, "reason": "already_processed"},
                    )
                    continue
                if not self.write_outputs:
                    self.write_file(
                        file_path,
                        score_payload,
                        rank=rank,
                        group_id=group_id,
                        group_size=len(ranked_results),
                    )
                    job_file_id = self.repository.upsert_job_file(
                        job_id=job_id,
                        file_path=file_path,
                        status=JobFileStatus.SIMULATED,
                        group_id=group_id,
                        rank=rank,
                        score_total=float(score_payload.get("score_total", 0.0)),
                        scene=score_payload.get("scene"),
                        scene_raw=score_payload.get("scene_raw"),
                    )
                    self._emit(
                        session_id=session_id,
                        job_id=job_id,
                        job_file_id=job_file_id,
                        event_type="job_file_simulated",
                        payload={
                            "file_path": file_path,
                            "score_total": float(score_payload.get("score_total", 0.0)),
                            "rank": rank,
                            "group_id": group_id,
                        },
                    )
                    simulated_files += 1
                    continue
                try:
                    self.write_file(
                        file_path,
                        score_payload,
                        rank=rank,
                        group_id=group_id,
                        group_size=len(ranked_results),
                    )
                except Exception as error:
                    job_file_id = self.repository.upsert_job_file(
                        job_id=job_id,
                        file_path=file_path,
                        status=JobFileStatus.ERROR,
                        group_id=group_id,
                        rank=rank,
                        error_message=str(error),
                        score_total=float(score_payload.get("score_total", 0.0)),
                        scene=score_payload.get("scene"),
                        scene_raw=score_payload.get("scene_raw"),
                    )
                    self._emit(
                        session_id=session_id,
                        job_id=job_id,
                        job_file_id=job_file_id,
                        event_type="job_file_failed",
                        payload={"file_path": file_path, "error": str(error)},
                    )
                    error_files += 1
                    continue
                job_file_id = self.repository.upsert_job_file(
                    job_id=job_id,
                    file_path=file_path,
                    status=JobFileStatus.WRITTEN,
                    group_id=group_id,
                    rank=rank,
                    score_total=float(score_payload.get("score_total", 0.0)),
                    scene=score_payload.get("scene"),
                    scene_raw=score_payload.get("scene_raw"),
                )
                self._emit(
                    session_id=session_id,
                    job_id=job_id,
                    job_file_id=job_file_id,
                    event_type="job_file_written",
                    payload={
                        "file_path": file_path,
                        "score_total": float(score_payload.get("score_total", 0.0)),
                        "rank": rank,
                        "group_id": group_id,
                    },
                )
                written_files += 1

        final_status = JobStatus.FINISHED_WITH_ERRORS if error_files > 0 else JobStatus.FINISHED
        summary = self._build_summary(
            status=final_status,
            total_files=len(file_paths),
            written_files=written_files,
            error_files=error_files,
            skipped_files=skipped_files,
            simulated_files=simulated_files,
            job_id=job_id,
        )
        self._update_stage(job_id, JobStage.FINALIZE, final_status, session_id=session_id)
        self.repository.update_job(job_id, summary=summary)
        self._emit(
            session_id=session_id,
            job_id=job_id,
            event_type="job_finished",
            payload=summary,
        )
        return summary
