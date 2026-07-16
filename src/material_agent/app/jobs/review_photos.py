from concurrent.futures import Future, ThreadPoolExecutor
import hashlib

from ..dto import JobFileStatus, JobStage, JobStatus


class _ScorePreparationPool(ThreadPoolExecutor):
    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None and not issubclass(exc_type, Exception):
            self.shutdown(wait=False, cancel_futures=True)
            return False
        return super().__exit__(exc_type, exc_value, traceback)


def _aggregate_timings(
    repository,
    job_files: list[object],
    *,
    job_id: str | None = None,
) -> dict:
    totals = {
        "raw_decode_seconds": 0.0,
        "score_seconds": 0.0,
        "local_heuristic_seconds": 0.0,
        "model_preprocess_seconds": 0.0,
        "model_inference_seconds": 0.0,
        "model_postprocess_seconds": 0.0,
        "model_compile_seconds": 0.0,
    }
    seen_inference_runs: set[object] = set()
    run_kinds: set[str] = set()
    seen_runs_by_kind: dict[str, set[object]] = {}
    found = False
    list_metadata = getattr(repository, "list_artifact_metadata", None)
    if callable(list_metadata) and job_id is not None:
        payloads = list_metadata(job_id=job_id, kind="score_payload")
    else:
        payloads = [
            repository.get_artifact_metadata(
                job_file_id=job_file.id,
                kind="score_payload",
            )
            for job_file in job_files
        ]
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        meta = payload.get("meta")
        if not isinstance(meta, dict):
            continue
        stage_timing = meta.get("timing")
        if isinstance(stage_timing, dict):
            for key in ("raw_decode_seconds", "score_seconds", "local_heuristic_seconds"):
                value = stage_timing.get(key)
                if isinstance(value, int | float):
                    totals[key] += float(value)
                    found = True
        subject_focus = meta.get("subject_focus")
        if isinstance(subject_focus, dict):
            value = subject_focus.get("timing_seconds")
            if isinstance(value, int | float):
                totals["subject_focus_seconds"] = totals.get("subject_focus_seconds", 0.0) + float(
                    value
                )
                found = True
        for kind in ("detection", "aesthetic", "embedding"):
            model = meta.get(kind)
            if not isinstance(model, dict):
                continue
            run_id = model.get("inference_run_id")
            if run_id is None or run_id in seen_inference_runs:
                continue
            seen_inference_runs.add(run_id)
            run_kinds.add(kind)
            seen_runs_by_kind.setdefault(kind, set()).add(run_id)
            model_timing = model.get("timing")
            if not isinstance(model_timing, dict):
                continue
            for source in ("preprocess_seconds", "inference_seconds", "postprocess_seconds"):
                value = model_timing.get(source)
                if isinstance(value, int | float):
                    totals[f"model_{source}"] += float(value)
                    category_key = f"{kind}_{source}"
                    totals[category_key] = totals.get(category_key, 0.0) + float(value)
                    found = True
            compile_seconds = model_timing.get("compile_seconds")
            if isinstance(compile_seconds, int | float):
                totals["model_compile_seconds"] = max(
                    totals["model_compile_seconds"], float(compile_seconds)
                )
                category_key = f"{kind}_compile_seconds"
                totals[category_key] = max(totals.get(category_key, 0.0), float(compile_seconds))
                found = True
    if not found:
        return {}
    result = {key: round(value, 6) for key, value in totals.items()}
    result["model_runs"] = len(seen_inference_runs)
    for kind in run_kinds:
        result[f"{kind}_runs"] = len(seen_runs_by_kind[kind])
    return result


class ReviewPhotosJob:
    def __init__(
        self,
        *,
        repository,
        event_sink,
        group_files=None,
        prepare_score=None,
        prime_prepared=None,
        score_prepared=None,
        score_file=None,
        finalize_group=None,
        write_file=None,
        score_prefetch_window: int = 1,
        write_outputs: bool = True,
        per_group_stage_events: bool = True,
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
        self.prime_prepared = prime_prepared
        self.write_file = write_file or (
            lambda file_path, score_payload, *, rank, group_id, group_size: None
        )
        self.score_prefetch_window = min(32, max(1, int(score_prefetch_window)))
        self.write_outputs = bool(write_outputs)
        self.per_group_stage_events = bool(per_group_stage_events)

    def _emit(
        self,
        *,
        session_id: str,
        job_id: str,
        event_type: str,
        payload: dict,
        job_file_id: str | None = None,
    ):
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

    def _update_stage(
        self, job_id: str, stage: JobStage, status: JobStatus, *, session_id: str
    ) -> None:
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
        job_files = self.repository.list_job_files(job_id)
        scored_files = sum(1 for job_file in job_files if job_file.score_total is not None)
        summary = {
            "status": status.value,
            "total_files": total_files,
            "written_files": written_files,
            "error_files": error_files,
            "skipped_files": skipped_files,
            "simulated_files": simulated_files,
            "scored_files": scored_files,
        }
        timings = _aggregate_timings(self.repository, job_files, job_id=job_id)
        if timings:
            summary["timings"] = timings
        return summary

    def _load_score_payload(self, *, job_id: str, file_path: str):
        job_file = self.repository.get_job_file(job_id=job_id, file_path=file_path)
        if job_file is None:
            return None, None
        payload = self.repository.get_artifact_metadata(
            job_file_id=job_file.id, kind="score_payload"
        )
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

    def _consume_group_scores(
        self,
        *,
        group: list[str],
        group_id: str | None,
        job_id: str,
        session_id: str,
        group_ids: dict[str, str] | None = None,
    ):
        group_results: list[tuple[str, dict]] = []
        resumable_job_files: dict[str, object] = {}
        resolved_group_ids = group_ids or {file_path: str(group_id) for file_path in group}
        group_can_be_skipped = {resolved_group_ids[file_path]: True for file_path in group}
        pending_prepares: dict[str, Future] = {}
        primed_files: set[str] = set()
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
                group_id=resolved_group_ids[file_path],
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
                existing_job_file, resumable_payload = self._load_score_payload(
                    job_id=job_id, file_path=file_path
                )
                if existing_job_file is not None:
                    resumable_job_files[file_path] = existing_job_file
                    if existing_job_file.status is JobFileStatus.WRITTEN:
                        group_results.append((file_path, resumable_payload or {}))
                        continue
                    if (
                        existing_job_file.status is JobFileStatus.SCORED
                        and resumable_payload is not None
                    ):
                        group_can_be_skipped[resolved_group_ids[file_path]] = False
                        group_results.append((file_path, resumable_payload))
                        continue

                group_can_be_skipped[resolved_group_ids[file_path]] = False
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
                        if (
                            candidate_job_file.status is JobFileStatus.SCORED
                            and candidate_payload is not None
                        ):
                            continue
                    _submit_prepare(executor, candidate)

                try:
                    prepared = pending_prepares.pop(file_path).result()
                    if self.prime_prepared is not None and file_path not in primed_files:
                        prime_batch = [prepared]
                        prime_paths = [file_path]
                        for pending_path, future in pending_prepares.items():
                            if pending_path in primed_files:
                                continue
                            try:
                                prime_batch.append(future.result())
                            except Exception:
                                continue
                            prime_paths.append(pending_path)
                        self.prime_prepared(prime_batch)
                        primed_files.update(prime_paths)
                    score_payload = self.score_prepared(prepared)
                except Exception as error:
                    job_file_id = self.repository.upsert_job_file(
                        job_id=job_id,
                        file_path=file_path,
                        status=JobFileStatus.ERROR,
                        group_id=resolved_group_ids[file_path],
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
                    group_id=resolved_group_ids[file_path],
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
                resumable_job_files[file_path] = self.repository.get_job_file(
                    job_id=job_id, file_path=file_path
                )
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

        group_ids = {file_path: self._group_id(group) for group in groups for file_path in group}
        scoring_order = [file_path for group in groups for file_path in group]
        self._update_stage(job_id, JobStage.SCORE, JobStatus.RUNNING, session_id=session_id)
        (
            all_group_results,
            resumable_job_files,
            group_can_be_skipped,
            score_error_files,
        ) = self._consume_group_scores(
            group=scoring_order,
            group_id=None,
            group_ids=group_ids,
            job_id=job_id,
            session_id=session_id,
        )
        error_files += score_error_files
        score_payloads = dict(all_group_results)

        if not self.per_group_stage_events:
            self._update_stage(job_id, JobStage.COMMENT, JobStatus.RUNNING, session_id=session_id)
            self._update_stage(job_id, JobStage.WRITE, JobStatus.RUNNING, session_id=session_id)

        for group in groups:
            group_id = self._group_id(group)
            group_results = [
                (file_path, score_payloads[file_path])
                for file_path in group
                if file_path in score_payloads
            ]

            if group_can_be_skipped.get(group_id, True):
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

            if self.per_group_stage_events:
                self._update_stage(
                    job_id,
                    JobStage.COMMENT,
                    JobStatus.RUNNING,
                    session_id=session_id,
                )
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
            if self.per_group_stage_events:
                self._update_stage(
                    job_id,
                    JobStage.WRITE,
                    JobStatus.RUNNING,
                    session_id=session_id,
                )
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
                    self.repository.upsert_artifact(
                        job_id=job_id,
                        job_file_id=job_file_id,
                        kind="score_payload",
                        uri=f"memory://job-files/{job_file_id}/score-payload",
                        metadata=score_payload,
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
                if (
                    existing_job_file is not None
                    and existing_job_file.status is JobFileStatus.WRITTEN
                ):
                    job_file_id = self.repository.upsert_job_file(
                        job_id=job_id,
                        file_path=file_path,
                        status=JobFileStatus.WRITTEN,
                        group_id=group_id,
                        rank=rank,
                        score_total=float(
                            score_payload.get("score_total", existing_job_file.score_total or 0.0)
                        ),
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
                    self.repository.upsert_artifact(
                        job_id=job_id,
                        job_file_id=job_file_id,
                        kind="score_payload",
                        uri=f"memory://job-files/{job_file_id}/score-payload",
                        metadata=score_payload,
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
                self.repository.upsert_artifact(
                    job_id=job_id,
                    job_file_id=job_file_id,
                    kind="score_payload",
                    uri=f"memory://job-files/{job_file_id}/score-payload",
                    metadata=score_payload,
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
