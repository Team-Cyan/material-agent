import sqlite3

import pytest

from material_agent.adapters.metadata.exiftool_xmp import ExifToolXMPWriter
from material_agent.adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from material_agent.app.dto import JobFileStatus, JobStage, JobStatus, JobType, SessionKind
from material_agent.app.job_service import JobService
from material_agent.app.rescore_service import RescoreService
from material_agent.app.scene_service import SceneDbService
from material_agent.app.review_service import ReviewRunService
from material_agent.app.rewrite_xmp_service import RewriteXmpService
from material_agent.app.session_service import SessionService
from material_agent.utils.runtime_paths import build_runtime_paths


def test_session_service_creates_runtime_session(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    service = SessionService(repo)

    session_id = service.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
    )

    row = repo.conn.execute(
        "SELECT kind, input_root, status FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    assert tuple(row) == ("cli", "/tmp/photos", "open")


def test_job_service_creates_review_job_and_emits_lifecycle_event(tmp_path):
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

    job_row = repo.conn.execute(
        "SELECT type, stage, status FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    event_row = repo.conn.execute(
        "SELECT event_type, payload_json FROM events WHERE job_id = ? ORDER BY created_at ASC, id ASC LIMIT 1",
        (job_id,),
    ).fetchone()

    assert tuple(job_row) == ("review_photos", "discover", "queued")
    assert event_row[0] == "job_created"
    assert '"job_type": "review_photos"' in event_row[1]


def test_job_service_updates_stage_and_status(tmp_path):
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

    job_service.update_job(job_id, stage=JobStage.SCORE, status=JobStatus.RUNNING)
    row = repo.conn.execute("SELECT stage, status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    assert tuple(row) == ("score", "running")


def test_app_services_list_runtime_entities_for_future_gui(tmp_path):
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
    job_file_id = repo.upsert_job_file(
        job_id=job_id,
        file_path="/tmp/photos/a.ARW",
        status=JobFileStatus.SCORED,
        score_total=7.5,
        scene="people",
        scene_raw="舞台上的主唱",
    )
    repo.conn.execute(
        "INSERT INTO artifacts (id, job_id, job_file_id, kind, uri, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
        ("art1", job_id, job_file_id, "score_payload", "memory://score/a", '{"score_total": 7.5}'),
    )
    repo.conn.commit()
    repo.append_event(
        session_id=session_id,
        job_id=job_id,
        job_file_id=job_file_id,
        event_type="job_file_scored",
        payload={"score_total": 7.5},
    )

    sessions = session_service.list_sessions()
    jobs = job_service.list_jobs(session_id)
    job_files = job_service.list_job_files(job_id)
    artifacts = job_service.list_artifacts(job_id)
    events = job_service.list_events(job_id)

    assert [session.id for session in sessions] == [session_id]
    assert [job.id for job in jobs] == [job_id]
    assert [str(job_file.file_path) for job_file in job_files] == ["/tmp/photos/a.ARW"]
    assert [artifact.id for artifact in artifacts] == ["art1"]
    assert [event["event_type"] for event in events] == ["job_created", "job_file_scored"]


def test_review_run_service_creates_runtime_records_and_runs_executor(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    service = ReviewRunService(repo)
    called = {}

    class _FakeState:
        def is_done(self, _path):
            return False

    class _FakeExecutor:
        def run(self, job_id, file_paths):
            called["job_id"] = job_id
            called["file_paths"] = list(file_paths)
            return {"status": "finished"}

    job_id = service.run(
        input_dir="/tmp/photos",
        config={"backend": "omlx"},
        state=_FakeState(),
        progress=None,
        dry_run=False,
        file_paths=["/tmp/photos/a.ARW", "/tmp/photos/b.ARW"],
        build_executor=lambda **kwargs: _FakeExecutor(),
    )

    assert called["file_paths"] == ["/tmp/photos/a.ARW", "/tmp/photos/b.ARW"]
    assert called["job_id"] == job_id

    session_row = repo.conn.execute(
        "SELECT kind, input_root, status, finished_at FROM sessions ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchone()
    job_row = repo.conn.execute(
        "SELECT type, stage, status FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()

    assert tuple(session_row[:3]) == ("cli", "/tmp/photos", "finished")
    assert session_row["finished_at"] is not None
    assert tuple(job_row) == ("review_photos", "discover", "queued")


def test_review_run_service_limits_deterministic_pilot_input(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    service = ReviewRunService(repo)
    called = {}

    class _FakeState:
        def is_done(self, _path):
            return False

    class _FakeExecutor:
        def run(self, job_id, file_paths):
            called["file_paths"] = list(file_paths)
            return {"status": "finished"}

    service.run(
        input_dir="/tmp/photos",
        config={"backend": "local", "review_pipeline": {"max_files": 2}},
        state=_FakeState(),
        progress=None,
        dry_run=True,
        file_paths=["/tmp/photos/a.ARW", "/tmp/photos/b.ARW", "/tmp/photos/c.ARW"],
        build_executor=lambda **kwargs: _FakeExecutor(),
    )

    assert called["file_paths"] == ["/tmp/photos/a.ARW", "/tmp/photos/b.ARW"]


def test_review_run_service_marks_session_finished_with_errors_from_job_result(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    service = ReviewRunService(repo)

    class _FakeState:
        def is_done(self, _path):
            return False

    class _FakeExecutor:
        def run(self, job_id, file_paths):
            return {"status": "finished_with_errors", "error_files": 1}

    service.run(
        input_dir="/tmp/photos",
        config={"backend": "omlx"},
        state=_FakeState(),
        progress=None,
        dry_run=False,
        file_paths=["/tmp/photos/a.ARW"],
        build_executor=lambda **kwargs: _FakeExecutor(),
    )

    session_row = repo.conn.execute(
        "SELECT status, finished_at FROM sessions ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchone()

    assert session_row["status"] == "finished_with_errors"
    assert session_row["finished_at"] is not None


@pytest.mark.parametrize("executor_result", [None, {}, {"status": "unexpected"}])
def test_review_run_service_fails_when_executor_result_status_is_missing_or_invalid(tmp_path, executor_result):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    service = ReviewRunService(repo)

    class _FakeState:
        def is_done(self, _path):
            return False

    class _FakeExecutor:
        def run(self, job_id, file_paths):
            return executor_result

    with pytest.raises(RuntimeError, match="invalid job result status"):
        service.run(
            input_dir="/tmp/photos",
            config={"backend": "omlx"},
            state=_FakeState(),
            progress=None,
            dry_run=False,
            file_paths=["/tmp/photos/a.ARW"],
            build_executor=lambda **kwargs: _FakeExecutor(),
        )

    job_row = repo.conn.execute(
        "SELECT stage, status, summary_json FROM jobs ORDER BY started_at DESC, id DESC LIMIT 1"
    ).fetchone()
    session_row = repo.conn.execute(
        "SELECT status, finished_at FROM sessions ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchone()

    assert tuple(job_row[:2]) == ("finalize", "failed")
    assert "invalid job result status" in job_row["summary_json"]
    assert session_row["status"] == "failed"
    assert session_row["finished_at"] is not None


def test_review_run_service_runs_preflight_hook_before_scan_and_persists_probe_metadata(
    tmp_path,
    monkeypatch,
):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    service = ReviewRunService(repo)
    calls = []

    class _FakeState:
        def is_done(self, _path):
            return False

    def _preflight(session_id, job_id):
        calls.append(("preflight", session_id, job_id))
        repo.append_event(
            session_id=session_id,
            job_id=job_id,
            event_type="runtime_probe_passed",
            payload={"capability_valid": True, "failure_guidance": None},
        )
        repo.upsert_artifact(
            job_id=job_id,
            job_file_id=None,
            kind="runtime_probe",
            uri="omlx://runtime-probe/passed",
            metadata={"capability_valid": True, "failure_guidance": None},
        )

    def _fake_scan(input_dir, extensions):
        calls.append(("scan", input_dir, tuple(extensions or [])))
        return ["/tmp/photos/a.ARW"]

    monkeypatch.setattr("material_agent.app.review_service.scan_arw_files", _fake_scan)

    class _FakeExecutor:
        def run(self, job_id, file_paths):
            calls.append(("executor", job_id, list(file_paths)))
            return {"status": "finished"}

    job_id = service.run(
        input_dir="/tmp/photos",
        config={"backend": "omlx", "omlx": {"runtime": {"probe_on_run": True}}},
        state=_FakeState(),
        progress=None,
        dry_run=False,
        file_paths=None,
        preflight_hook=_preflight,
        build_executor=lambda **kwargs: _FakeExecutor(),
    )

    assert [step[0] for step in calls] == ["preflight", "scan", "executor"]
    events = repo.list_events(job_id)
    artifacts = repo.list_artifacts(job_id)
    assert [event["event_type"] for event in events] == ["job_created", "runtime_probe_passed"]
    assert artifacts[0].kind == "runtime_probe"
    assert artifacts[0].metadata["capability_valid"] is True


def test_review_run_service_aborts_before_scan_when_preflight_hook_fails(tmp_path, monkeypatch):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    service = ReviewRunService(repo)
    calls = []

    class _FakeState:
        def is_done(self, _path):
            return False

    def _preflight(session_id, job_id):
        calls.append(("preflight", session_id, job_id))
        repo.append_event(
            session_id=session_id,
            job_id=job_id,
            event_type="runtime_probe_failed",
            payload={
                "capability_valid": False,
                "failure_guidance": "Open /Applications/oMLX.app or start the dedicated OMLX runtime, then retry.",
            },
        )
        repo.upsert_artifact(
            job_id=job_id,
            job_file_id=None,
            kind="runtime_probe",
            uri="omlx://runtime-probe/failed",
            metadata={
                "capability_valid": False,
                "failure_guidance": "Open /Applications/oMLX.app or start the dedicated OMLX runtime, then retry.",
            },
        )
        raise RuntimeError(
            "OMLX runtime probe failed: Open /Applications/oMLX.app or start the dedicated OMLX runtime, then retry."
        )

    def _unexpected_scan(*_args, **_kwargs):
        raise AssertionError("scan should not run after a failed runtime probe")

    monkeypatch.setattr("material_agent.app.review_service.scan_arw_files", _unexpected_scan)

    class _UnexpectedExecutor:
        def run(self, *_args, **_kwargs):
            raise AssertionError("executor should not run after a failed runtime probe")

    with pytest.raises(RuntimeError, match="OMLX runtime probe failed"):
        service.run(
            input_dir="/tmp/photos",
            config={"backend": "omlx", "omlx": {"runtime": {"probe_on_run": True}}},
            state=_FakeState(),
            progress=None,
            dry_run=False,
            file_paths=None,
            preflight_hook=_preflight,
            build_executor=lambda **kwargs: _UnexpectedExecutor(),
        )

    assert [step[0] for step in calls] == ["preflight"]
    job_row = repo.conn.execute(
        "SELECT id, stage, status, summary_json FROM jobs ORDER BY started_at DESC, id DESC LIMIT 1"
    ).fetchone()
    session_row = repo.conn.execute(
        "SELECT status, finished_at FROM sessions ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchone()
    events = repo.list_events(job_row["id"])
    artifacts = repo.list_artifacts(job_row["id"])

    assert tuple(job_row[1:3]) == ("finalize", "failed")
    assert "Open /Applications/oMLX.app or start the dedicated OMLX runtime" in job_row["summary_json"]
    assert session_row["status"] == "failed"
    assert session_row["finished_at"] is not None
    assert [event["event_type"] for event in events] == [
        "job_created",
        "runtime_probe_failed",
        "job_failed",
    ]
    assert artifacts[0].kind == "runtime_probe"
    assert artifacts[0].metadata["capability_valid"] is False


def test_review_run_service_marks_job_failed_and_records_event(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    service = ReviewRunService(repo)

    class _FakeState:
        def is_done(self, _path):
            return False

    class _FailingExecutor:
        def run(self, job_id, file_paths):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        service.run(
            input_dir="/tmp/photos",
            config={"backend": "omlx"},
            state=_FakeState(),
            progress=None,
            dry_run=False,
            file_paths=["/tmp/photos/a.ARW"],
            build_executor=lambda **kwargs: _FailingExecutor(),
        )

    job_row = repo.conn.execute(
        "SELECT stage, status, summary_json FROM jobs ORDER BY started_at DESC, id DESC LIMIT 1"
    ).fetchone()
    session_row = repo.conn.execute(
        "SELECT status, finished_at FROM sessions ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchone()
    event_row = repo.conn.execute(
        "SELECT event_type, payload_json FROM events WHERE event_type = 'job_failed' LIMIT 1"
    ).fetchone()

    assert tuple(job_row[:2]) == ("finalize", "failed")
    assert '"error": "boom"' in job_row["summary_json"]
    assert session_row["status"] == "failed"
    assert session_row["finished_at"] is not None
    assert event_row["event_type"] == "job_failed"
    assert '"error": "boom"' in event_row["payload_json"]


def test_review_run_service_scans_from_input_dir_when_file_paths_omitted(tmp_path, monkeypatch):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    service = ReviewRunService(repo)
    scanned = {}
    called = {}

    class _FakeState:
        def is_done(self, _path):
            return False

    class _FakeExecutor:
        def run(self, job_id, file_paths):
            called["job_id"] = job_id
            called["file_paths"] = list(file_paths)
            return {"status": "finished"}

    def _fake_scan(input_dir, extensions):
        scanned["input_dir"] = input_dir
        scanned["extensions"] = extensions
        return ["/tmp/photos/a.ARW"]

    monkeypatch.setattr("material_agent.app.review_service.scan_arw_files", _fake_scan)

    service.run(
        input_dir="/tmp/photos",
        config={"backend": "omlx", "raw_extensions": [".ARW"]},
        state=_FakeState(),
        progress=None,
        dry_run=False,
        file_paths=None,
        build_executor=lambda **kwargs: _FakeExecutor(),
    )

    assert scanned == {"input_dir": "/tmp/photos", "extensions": [".ARW"]}
    assert called["file_paths"] == ["/tmp/photos/a.ARW"]


def test_review_run_service_marks_session_failed_when_scan_fails(tmp_path, monkeypatch):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    service = ReviewRunService(repo)

    class _FakeState:
        def is_done(self, _path):
            return False

    def _failing_scan(_input_dir, _extensions):
        raise RuntimeError("scan failed")

    monkeypatch.setattr("material_agent.app.review_service.scan_arw_files", _failing_scan)

    with pytest.raises(RuntimeError, match="scan failed"):
        service.run(
            input_dir="/tmp/photos",
            config={"backend": "omlx", "raw_extensions": [".ARW"]},
            state=_FakeState(),
            progress=None,
            dry_run=False,
            file_paths=None,
            build_executor=lambda **kwargs: None,
        )

    session_row = repo.conn.execute(
        "SELECT status, finished_at FROM sessions ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchone()
    job_row = repo.conn.execute(
        "SELECT stage, status, summary_json FROM jobs ORDER BY started_at DESC, id DESC LIMIT 1"
    ).fetchone()

    assert session_row["status"] == "failed"
    assert session_row["finished_at"] is not None
    assert tuple(job_row[:2]) == ("finalize", "failed")
    assert '"error": "scan failed"' in job_row["summary_json"]


def test_rewrite_xmp_service_rewrites_done_rows_to_xmp(tmp_path):
    photo = tmp_path / "cat.ARW"
    photo.write_bytes(b"fake")
    db_path = build_runtime_paths(tmp_path).db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE processed (
                file_path TEXT PRIMARY KEY,
                status TEXT,
                scene TEXT,
                scene_raw TEXT,
                total_score REAL,
                star_rating INTEGER,
                group_rank INTEGER,
                group_size INTEGER,
                group_boosted INTEGER,
                group_id TEXT,
                decision TEXT,
                decision_reasons TEXT,
                screening_prior REAL,
                visible_breakdown_json TEXT,
                policy_version TEXT,
                score_exposure REAL,
                score_sharpness REAL,
                score_subject REAL,
                score_composition REAL,
                score_lighting REAL,
                score_color REAL,
                score_clarity REAL,
                score_depth REAL,
                score_mood REAL,
                commentary_group_issues TEXT,
                commentary_shooting TEXT,
                commentary_post TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO processed (
                file_path, status, scene, scene_raw, total_score, star_rating, group_rank, group_size,
                group_boosted, group_id, score_exposure, score_sharpness, score_subject, score_composition,
                score_lighting, score_color, score_clarity, score_depth, score_mood,
                commentary_group_issues, commentary_shooting, commentary_post,
                decision, decision_reasons, screening_prior, visible_breakdown_json, policy_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(photo), "done", "animals", "猫趴在窗边", 8.0, 4, 1, 1,
                0, "group_1", 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0,
                "【组内问题】整体偏暗。", "【拍摄建议】拍摄时稳一点。", "【后期指导】把阴影提一点。",
                "keep", '["sharp enough"]', 7.4,
                '{"technical_quality": 8.0, "composition": 8.0, "lighting": 8.0, "color": 8.0, "space_depth": 8.0, "mood_story": 8.0, "subject_moment": 8.0}',
                "layered-v1",
            ),
        )
        conn.commit()

    summary = RewriteXmpService().run(str(tmp_path), dry_run=False)

    assert summary == {"ok": 1, "err": 0}
    content = (tmp_path / "cat.xmp").read_text(encoding="utf-8")
    assert "pj:decision=keep" in content
    assert "pj:scene=动物" in content
    assert "技术质量:8.0" in content
    assert "构图:8.0" in content
    assert "【拍摄建议】拍摄时稳一点。" in content


def test_scene_db_service_scans_scene_distribution(tmp_path):
    db_path = build_runtime_paths(tmp_path).db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE processed (file_path TEXT PRIMARY KEY, status TEXT, scene TEXT, scene_raw TEXT)")
        conn.executemany(
            "INSERT INTO processed (file_path, status, scene, scene_raw) VALUES (?,?,?,?)",
            [
                ("/a.arw", "done", "people", "舞台上的主唱特写"),
                ("/b.arw", "done", "people", "全身人像"),
                ("/c.arw", "done", "landscape", "山间日落"),
            ],
        )
        conn.commit()

    grouped = SceneDbService().scan_distribution(str(tmp_path))

    assert grouped["people"] == [("舞台上的主唱特写", 1), ("全身人像", 1)]
    assert grouped["landscape"] == [("山间日落", 1)]


def test_rewrite_xmp_preserves_existing_sidecar_when_rewrite_fails(tmp_path):
    db_path = build_runtime_paths(tmp_path).db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    photo = tmp_path / "cat.ARW"
    photo.write_bytes(b"raw")
    xmp_path = tmp_path / "cat.xmp"
    original = "original-xmp"
    xmp_path.write_text(original, encoding="utf-8")

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE processed (
                file_path TEXT PRIMARY KEY,
                status TEXT,
                scene TEXT,
                scene_raw TEXT,
                total_score REAL,
                star_rating INTEGER,
                group_rank INTEGER,
                group_size INTEGER,
                group_boosted INTEGER,
                group_id TEXT,
                decision TEXT,
                decision_reasons TEXT,
                screening_prior REAL,
                visible_breakdown_json TEXT,
                policy_version TEXT,
                score_exposure REAL,
                score_sharpness REAL,
                score_subject REAL,
                score_composition REAL,
                score_lighting REAL,
                score_color REAL,
                score_clarity REAL,
                score_depth REAL,
                score_mood REAL,
                commentary_group_issues TEXT,
                commentary_shooting TEXT,
                commentary_post TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO processed (
                file_path, status, scene, scene_raw, total_score, star_rating, group_rank, group_size,
                group_boosted, group_id, score_exposure, score_sharpness, score_subject, score_composition,
                score_lighting, score_color, score_clarity, score_depth, score_mood,
                commentary_group_issues, commentary_shooting, commentary_post,
                decision, decision_reasons, screening_prior, visible_breakdown_json, policy_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(photo), "done", "animals", "猫趴在窗边", 8.0, 4, 1, 1,
                0, "group_1", 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0,
                "【组内问题】整体偏暗。", "【拍摄建议】拍摄时稳一点。", "【后期指导】把阴影提一点。",
                "keep", '["sharp enough"]', 7.4,
                '{"technical_quality": 8.0, "composition": 8.0, "lighting": 8.0, "color": 8.0, "space_depth": 8.0, "mood_story": 8.0, "subject_moment": 8.0}',
                "layered-v1",
            ),
        )
        conn.commit()

    class _FailingWriter(ExifToolXMPWriter):
        def _write_minimal_xmp(self, xmp_path, rating, subject_tags, instructions, description):
            raise RuntimeError("disk full")

    summary = RewriteXmpService(writer=_FailingWriter()).run(str(tmp_path), dry_run=False)

    assert summary == {"ok": 0, "err": 1}
    assert xmp_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "cat.xmp.tmp").exists()


def test_rescore_service_recalculates_totals_without_ai(tmp_path):
    from material_agent.adapters.state.processed_sqlite import SQLiteProcessedRepository

    repo = SQLiteProcessedRepository(tmp_path)
    repo.conn.execute(
        """
        INSERT INTO processed (file_path, status, scene, score_subject, score_composition,
            score_lighting, score_color, score_clarity, score_depth, score_mood)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        ("/fake/a.jpg", "done", "people", 9.0, 8.0, 7.0, 7.0, 9.0, 0.0, 0.0),
    )
    repo.conn.commit()

    updated = RescoreService(repo).run(
        scene_filters=["people"],
        scene_weights={"people": {"clarity": 1.0}},
        scoring_config={"pixel_weight": 0.3, "vision_weight": 0.7},
        scorers_config={
            "exposure": {"enabled": True, "weight": 0.5, "min_score": 0.0},
            "sharpness": {"enabled": True, "weight": 0.5, "min_score": 0.0},
        },
    )

    row = repo.conn.execute(
        "SELECT total_score, decision, star_rating FROM processed WHERE file_path='/fake/a.jpg'"
    ).fetchone()

    assert updated == 1
    assert abs(row[0] - 7.08) < 0.01
    assert row[1] == "review"
    assert row[2] == 4
