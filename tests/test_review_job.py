from material_agent.adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from material_agent.app.dto import JobFileStatus, JobStage, JobType, SessionKind
from material_agent.app.job_executor import JobExecutor
from material_agent.app.job_service import JobService
from material_agent.app.jobs.review_photos import ReviewPhotosJob
from material_agent.app.session_service import SessionService
import threading


class _NullEventSink:
    def publish(self, *, event_type, payload, session_id=None, job_id=None, job_file_id=None):
        return None


def test_review_job_runs_stage_flow_and_marks_files_scored(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_service = SessionService(repo)
    job_service = JobService(repo)
    session_id = session_service.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
    )
    job_id = job_service.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        initial_stage=JobStage.DISCOVER,
    )

    def group_files(file_paths):
        return [file_paths]

    def score_file(file_path):
        return {
            "score_total": 6.5 if file_path.endswith("a.ARW") else 5.0,
            "scene": "people",
            "scene_raw": "舞台上的人物",
        }

    def write_file(file_path, score_payload, *, rank, group_id, group_size):
        return None

    review_job = ReviewPhotosJob(
        repository=repo,
        event_sink=_NullEventSink(),
        group_files=group_files,
        score_file=score_file,
        write_file=write_file,
    )
    executor = JobExecutor(review_job)
    result = executor.run(job_id, ["/tmp/photos/a.ARW", "/tmp/photos/b.ARW"])

    job_row = repo.conn.execute(
        "SELECT stage, status FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    file_rows = repo.conn.execute(
        "SELECT file_path, status, score_total, scene, scene_raw FROM job_files WHERE job_id = ? ORDER BY file_path",
        (job_id,),
    ).fetchall()
    events = repo.conn.execute(
        "SELECT event_type FROM events WHERE job_id = ?",
        (job_id,),
    ).fetchall()

    assert tuple(job_row) == ("finalize", "finished")
    assert result == {
        "status": "finished",
        "total_files": 2,
        "written_files": 2,
        "error_files": 0,
        "skipped_files": 0,
        "simulated_files": 0,
        "scored_files": 2,
    }
    assert [tuple(row) for row in file_rows] == [
        ("/tmp/photos/a.ARW", "written", 6.5, "people", "舞台上的人物"),
        ("/tmp/photos/b.ARW", "written", 5.0, "people", "舞台上的人物"),
    ]
    assert {row[0] for row in events} >= {
        "job_started",
        "job_stage_changed",
        "job_file_started",
        "job_file_scored",
        "job_file_written",
        "job_finished",
    }


def test_review_job_persists_error_status_when_file_scoring_fails(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_service = SessionService(repo)
    job_service = JobService(repo)
    session_id = session_service.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
    )
    job_id = job_service.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        initial_stage=JobStage.DISCOVER,
    )

    def group_files(file_paths):
        return [file_paths]

    def score_file(file_path):
        if file_path.endswith("bad.ARW"):
            raise RuntimeError("decode failed")
        return {
            "score_total": 7.0,
            "scene": "people",
            "scene_raw": "舞台上的人物",
        }

    def write_file(file_path, score_payload, *, rank, group_id, group_size):
        return None

    review_job = ReviewPhotosJob(
        repository=repo,
        event_sink=_NullEventSink(),
        group_files=group_files,
        score_file=score_file,
        write_file=write_file,
    )

    executor = JobExecutor(review_job)
    executor.run(job_id, ["/tmp/photos/good.ARW", "/tmp/photos/bad.ARW"])

    file_rows = repo.conn.execute(
        "SELECT file_path, status, error_message FROM job_files WHERE job_id = ? ORDER BY file_path",
        (job_id,),
    ).fetchall()

    assert [tuple(row) for row in file_rows] == [
        ("/tmp/photos/bad.ARW", "error", "decode failed"),
        ("/tmp/photos/good.ARW", "written", None),
    ]


def test_review_job_continues_when_file_write_fails(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_service = SessionService(repo)
    job_service = JobService(repo)
    session_id = session_service.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
    )
    job_id = job_service.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        initial_stage=JobStage.DISCOVER,
    )

    def group_files(file_paths):
        return [file_paths]

    def score_file(_file_path):
        return {
            "score_total": 7.0,
            "scene": "people",
            "scene_raw": "舞台上的人物",
        }

    def write_file(file_path, score_payload, *, rank, group_id, group_size):
        if file_path.endswith("bad.ARW"):
            raise RuntimeError("xmp write failed")
        return None

    review_job = ReviewPhotosJob(
        repository=repo,
        event_sink=_NullEventSink(),
        group_files=group_files,
        score_file=score_file,
        write_file=write_file,
    )

    result = JobExecutor(review_job).run(job_id, ["/tmp/photos/good.ARW", "/tmp/photos/bad.ARW"])

    job_row = repo.conn.execute(
        "SELECT stage, status FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    file_rows = repo.conn.execute(
        "SELECT file_path, status, error_message FROM job_files WHERE job_id = ? ORDER BY file_path",
        (job_id,),
    ).fetchall()

    assert tuple(job_row) == ("finalize", "finished_with_errors")
    assert [tuple(row) for row in file_rows] == [
        ("/tmp/photos/bad.ARW", "error", "xmp write failed"),
        ("/tmp/photos/good.ARW", "written", None),
    ]
    assert result == {
        "status": "finished_with_errors",
        "total_files": 2,
        "written_files": 1,
        "error_files": 1,
        "skipped_files": 0,
        "simulated_files": 0,
        "scored_files": 2,
    }


def test_review_job_emits_stage_changes_in_execution_order(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_service = SessionService(repo)
    job_service = JobService(repo)
    session_id = session_service.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
    )
    job_id = job_service.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        initial_stage=JobStage.DISCOVER,
    )

    review_job = ReviewPhotosJob(
        repository=repo,
        event_sink=_NullEventSink(),
        group_files=lambda file_paths: [file_paths],
        score_file=lambda _file_path: {
            "score_total": 7.0,
            "scene": "people",
            "scene_raw": "舞台上的人物",
        },
        finalize_group=lambda group_results, *, group_id: group_results,
        write_file=lambda file_path, score_payload, *, rank, group_id, group_size: None,
    )

    JobExecutor(review_job).run(job_id, ["/tmp/photos/one.ARW"])

    stage_events = [
        event["payload"]
        for event in repo.list_events(job_id)
        if event["event_type"] == "job_stage_changed"
    ]

    assert stage_events == [
        {"stage": "group", "status": "running"},
        {"stage": "score", "status": "running"},
        {"stage": "comment", "status": "running"},
        {"stage": "write", "status": "running"},
        {"stage": "finalize", "status": "finished"},
    ]


def test_review_job_finished_summary_counts_files_that_reached_scoring(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_service = SessionService(repo)
    job_service = JobService(repo)
    session_id = session_service.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
    )
    job_id = job_service.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        initial_stage=JobStage.DISCOVER,
    )

    def score_file(file_path):
        return {
            "score_total": 7.0 if file_path.endswith("good.ARW") else 6.0,
            "scene": "people",
            "scene_raw": "舞台上的人物",
        }

    def write_file(file_path, score_payload, *, rank, group_id, group_size):
        if file_path.endswith("bad.ARW"):
            raise RuntimeError("xmp write failed")
        return None

    review_job = ReviewPhotosJob(
        repository=repo,
        event_sink=_NullEventSink(),
        group_files=lambda file_paths: [file_paths],
        score_file=score_file,
        finalize_group=lambda group_results, *, group_id: group_results,
        write_file=write_file,
    )

    result = JobExecutor(review_job).run(job_id, ["/tmp/photos/good.ARW", "/tmp/photos/bad.ARW"])

    job_row = repo.conn.execute(
        "SELECT stage, status, summary_json FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    finished_event = next(
        event["payload"]
        for event in reversed(repo.list_events(job_id))
        if event["event_type"] == "job_finished"
    )

    assert tuple(job_row[:2]) == ("finalize", "finished_with_errors")
    assert job_row[2] == (
        '{"status": "finished_with_errors", "total_files": 2, "written_files": 1, "error_files": 1, "skipped_files": 0, "simulated_files": 0, "scored_files": 2}'
    )
    assert finished_event == {
        "status": "finished_with_errors",
        "total_files": 2,
        "written_files": 1,
        "error_files": 1,
        "skipped_files": 0,
        "simulated_files": 0,
        "scored_files": 2,
    }
    assert result == finished_event


def test_review_job_resumes_written_and_scored_files_from_artifacts(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_service = SessionService(repo)
    job_service = JobService(repo)
    session_id = session_service.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
    )
    job_id = job_service.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        initial_stage=JobStage.DISCOVER,
    )

    written_job_file_id = repo.upsert_job_file(
        job_id=job_id,
        file_path="/tmp/photos/already-written.ARW",
        status=JobFileStatus.WRITTEN,
        group_id="group_0001",
        rank=1,
        score_total=8.0,
        scene="people",
        scene_raw="舞台上的人物",
    )
    repo.upsert_artifact(
        job_id=job_id,
        job_file_id=written_job_file_id,
        kind="score_payload",
        uri="memory://score/already-written",
        metadata={
            "score_total": 8.0,
            "scene": "people",
            "scene_raw": "舞台上的人物",
            "scores": {"subject": 8.0},
            "meta": {},
            "instructions": "subject:8.0",
            "boosted": False,
        },
    )

    scored_job_file_id = repo.upsert_job_file(
        job_id=job_id,
        file_path="/tmp/photos/already-scored.ARW",
        status=JobFileStatus.SCORED,
        group_id="group_0002",
        score_total=6.0,
        scene="people",
        scene_raw="舞台上的人物",
    )
    repo.upsert_artifact(
        job_id=job_id,
        job_file_id=scored_job_file_id,
        kind="score_payload",
        uri="memory://score/already-scored",
        metadata={
            "score_total": 6.0,
            "scene": "people",
            "scene_raw": "舞台上的人物",
            "scores": {"subject": 6.0},
            "meta": {},
            "instructions": "subject:6.0",
            "boosted": False,
        },
    )

    score_calls = []
    write_calls = []
    finalize_calls = []

    def group_files(file_paths):
        return [[file_paths[0]], [file_paths[1]]]

    def score_file(file_path):
        score_calls.append(file_path)
        return {
            "score_total": 3.0,
            "scene": "other",
            "scene_raw": "不应重新评分",
        }

    def finalize_group(group_results, *, group_id):
        finalize_calls.append((group_id, [file_path for file_path, _ in group_results]))
        return group_results

    def write_file(file_path, score_payload, *, rank, group_id, group_size):
        write_calls.append((file_path, rank, group_id, group_size, score_payload["score_total"]))

    review_job = ReviewPhotosJob(
        repository=repo,
        event_sink=_NullEventSink(),
        group_files=group_files,
        score_file=score_file,
        finalize_group=finalize_group,
        write_file=write_file,
    )

    JobExecutor(review_job).run(
        job_id,
        ["/tmp/photos/already-written.ARW", "/tmp/photos/already-scored.ARW"],
    )

    scored_group_id = ReviewPhotosJob._group_id(["/tmp/photos/already-scored.ARW"])
    assert score_calls == []
    assert finalize_calls == [(scored_group_id, ["/tmp/photos/already-scored.ARW"])]
    assert write_calls == [
        ("/tmp/photos/already-scored.ARW", 1, scored_group_id, 1, 6.0),
    ]

    file_rows = repo.conn.execute(
        "SELECT file_path, status, rank, score_total FROM job_files WHERE job_id = ? ORDER BY file_path",
        (job_id,),
    ).fetchall()
    assert [tuple(row) for row in file_rows] == [
        ("/tmp/photos/already-scored.ARW", "written", 1, 6.0),
        ("/tmp/photos/already-written.ARW", "written", 1, 8.0),
    ]


def test_review_job_refreshes_rank_and_group_metadata_for_already_written_files_in_ranked_group(
    tmp_path,
):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_service = SessionService(repo)
    job_service = JobService(repo)
    session_id = session_service.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
    )
    job_id = job_service.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        initial_stage=JobStage.DISCOVER,
    )

    written_job_file_id = repo.upsert_job_file(
        job_id=job_id,
        file_path="/tmp/photos/already-written.ARW",
        status=JobFileStatus.WRITTEN,
        group_id="stale_group",
        rank=99,
        score_total=5.0,
        scene="people",
        scene_raw="舞台上的人物",
    )
    repo.upsert_artifact(
        job_id=job_id,
        job_file_id=written_job_file_id,
        kind="score_payload",
        uri="memory://score/already-written",
        metadata={
            "score_total": 5.0,
            "scene": "people",
            "scene_raw": "舞台上的人物",
            "scores": {"subject": 5.0},
            "meta": {},
            "instructions": "subject:5.0",
            "boosted": False,
        },
    )

    scored_job_file_id = repo.upsert_job_file(
        job_id=job_id,
        file_path="/tmp/photos/already-scored.ARW",
        status=JobFileStatus.SCORED,
        group_id="old_group",
        rank=7,
        score_total=9.0,
        scene="people",
        scene_raw="舞台上的人物",
    )
    repo.upsert_artifact(
        job_id=job_id,
        job_file_id=scored_job_file_id,
        kind="score_payload",
        uri="memory://score/already-scored",
        metadata={
            "score_total": 9.0,
            "scene": "people",
            "scene_raw": "舞台上的人物",
            "scores": {"subject": 9.0},
            "meta": {},
            "instructions": "subject:9.0",
            "boosted": False,
        },
    )

    review_job = ReviewPhotosJob(
        repository=repo,
        event_sink=_NullEventSink(),
        group_files=lambda file_paths: [file_paths],
        score_file=lambda _file_path: {"score_total": 0.0, "scene": "other", "scene_raw": ""},
        finalize_group=lambda group_results, *, group_id: group_results,
        write_file=lambda file_path, score_payload, *, rank, group_id, group_size: None,
    )

    JobExecutor(review_job).run(
        job_id,
        ["/tmp/photos/already-written.ARW", "/tmp/photos/already-scored.ARW"],
    )

    file_rows = repo.conn.execute(
        "SELECT file_path, status, group_id, rank FROM job_files WHERE job_id = ? ORDER BY file_path",
        (job_id,),
    ).fetchall()

    current_group_id = ReviewPhotosJob._group_id(
        ["/tmp/photos/already-written.ARW", "/tmp/photos/already-scored.ARW"]
    )
    assert [tuple(row) for row in file_rows] == [
        ("/tmp/photos/already-scored.ARW", "written", current_group_id, 1),
        ("/tmp/photos/already-written.ARW", "written", current_group_id, 2),
    ]


def test_review_job_prefetches_prepare_stage_without_overlapping_score_stage(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_service = SessionService(repo)
    job_service = JobService(repo)
    session_id = session_service.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
    )
    job_id = job_service.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        initial_stage=JobStage.DISCOVER,
    )

    second_prepare_started = threading.Event()
    prepare_calls: list[str] = []
    score_calls: list[str] = []
    locks = {"score_running": False}

    def prepare_score(file_path):
        prepare_calls.append(file_path)
        if file_path.endswith("one.ARW"):
            assert second_prepare_started.wait(timeout=1.0), (
                "next file was not prefetched during prepare"
            )
        else:
            second_prepare_started.set()
        return {"file_path": file_path}

    def score_prepared(prepared):
        file_path = prepared["file_path"]
        assert not locks["score_running"], "score stage overlapped across files"
        locks["score_running"] = True
        score_calls.append(file_path)
        locks["score_running"] = False
        return {
            "score_total": 7.0 if file_path.endswith("one.ARW") else 6.0,
            "scene": "people",
            "scene_raw": "舞台上的人物",
        }

    review_job = ReviewPhotosJob(
        repository=repo,
        event_sink=_NullEventSink(),
        group_files=lambda file_paths: [file_paths],
        prepare_score=prepare_score,
        score_prepared=score_prepared,
        finalize_group=lambda group_results, *, group_id: group_results,
        write_file=lambda file_path, score_payload, *, rank, group_id, group_size: None,
        score_prefetch_window=2,
    )

    result = JobExecutor(review_job).run(
        job_id,
        ["/tmp/photos/one.ARW", "/tmp/photos/two.ARW"],
    )

    assert result["status"] == "finished"
    assert prepare_calls == ["/tmp/photos/one.ARW", "/tmp/photos/two.ARW"]
    assert score_calls == ["/tmp/photos/one.ARW", "/tmp/photos/two.ARW"]


def test_review_job_primes_prefetched_scores_in_bounded_batches(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_service = SessionService(repo)
    job_service = JobService(repo)
    session_id = session_service.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "local"},
    )
    job_id = job_service.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        initial_stage=JobStage.DISCOVER,
    )
    files = [f"/tmp/photos/{index}.ARW" for index in range(5)]
    prime_calls: list[list[str]] = []

    review_job = ReviewPhotosJob(
        repository=repo,
        event_sink=_NullEventSink(),
        group_files=lambda file_paths: [[file_path] for file_path in file_paths],
        prepare_score=lambda file_path: {"file_path": file_path},
        prime_prepared=lambda prepared: prime_calls.append(
            [item["file_path"] for item in prepared]
        ),
        score_prepared=lambda prepared: {
            "score_total": 7.0,
            "scene": "other",
            "scene_raw": "",
        },
        finalize_group=lambda group_results, *, group_id: group_results,
        write_file=lambda file_path, score_payload, *, rank, group_id, group_size: None,
        score_prefetch_window=4,
        write_outputs=False,
    )

    result = JobExecutor(review_job).run(job_id, files)

    assert result["status"] == "finished"
    assert prime_calls == [files[:4], files[4:]]


def test_dry_run_repersist_score_payload_after_output_preview_is_added(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_id = SessionService(repo).create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "local"},
    )
    job_id = JobService(repo).create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        initial_stage=JobStage.DISCOVER,
    )
    file_path = "/tmp/photos/one.ARW"

    def add_output_preview(_file_path, score_payload, **_kwargs):
        score_payload["output_preview"] = {
            "subject_tags": ["pj:decision=keep"],
            "description": "preview only",
        }

    review_job = ReviewPhotosJob(
        repository=repo,
        event_sink=_NullEventSink(),
        group_files=lambda files: [files],
        score_file=lambda _file_path: {
            "score_total": 7.0,
            "scene": "people",
            "scene_raw": "",
        },
        write_file=add_output_preview,
        write_outputs=False,
    )

    JobExecutor(review_job).run(job_id, [file_path])

    job_file = repo.get_job_file(job_id=job_id, file_path=file_path)
    payload = repo.get_artifact_metadata(job_file_id=job_file.id, kind="score_payload")
    assert payload["output_preview"] == {
        "subject_tags": ["pj:decision=keep"],
        "description": "preview only",
    }
