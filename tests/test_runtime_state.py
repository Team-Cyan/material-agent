import sqlite3

from material_agent.adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from material_agent.app.dto import JobFileStatus, JobStage, JobStatus, JobType, SessionKind, SessionStatus


def test_runtime_repository_bootstraps_schema(tmp_path):
    db_path = tmp_path / "runtime.db"
    repo = SQLiteRuntimeRepository(db_path)
    rows = repo.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {row[0] for row in rows}
    assert {"sessions", "jobs", "job_files", "artifacts", "events"} <= names
    assert repo.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert repo.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000


def test_runtime_repository_creates_and_updates_runtime_rows(tmp_path):
    db_path = tmp_path / "runtime.db"
    repo = SQLiteRuntimeRepository(db_path)

    session_id = repo.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
        status=SessionStatus.OPEN,
    )
    job_id = repo.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        stage=JobStage.DISCOVER,
        status=JobStatus.QUEUED,
    )
    job_file_id = repo.upsert_job_file(
        job_id=job_id,
        file_path="/tmp/photos/a.ARW",
        status=JobFileStatus.PENDING,
    )
    repo.update_job(job_id, stage=JobStage.SCORE, status=JobStatus.RUNNING)
    repo.upsert_job_file(
        job_id=job_id,
        file_path="/tmp/photos/a.ARW",
        status=JobFileStatus.SCORED,
        score_total=7.5,
        scene="people",
        scene_raw="舞台上的主唱",
    )
    repo.append_event(
        session_id=session_id,
        job_id=job_id,
        job_file_id=job_file_id,
        event_type="job_file_scored",
        payload={"score_total": 7.5},
    )

    session_row = repo.conn.execute(
        "SELECT kind, input_root, status FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    job_row = repo.conn.execute(
        "SELECT stage, status FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    file_row = repo.conn.execute(
        "SELECT status, score_total, scene, scene_raw FROM job_files WHERE id = ?",
        (job_file_id,),
    ).fetchone()
    event_row = repo.conn.execute(
        "SELECT event_type, payload_json FROM events WHERE job_id = ?",
        (job_id,),
    ).fetchone()

    assert tuple(session_row) == ("cli", "/tmp/photos", "open")
    assert tuple(job_row) == ("score", "running")
    assert tuple(file_row) == ("scored", 7.5, "people", "舞台上的主唱")
    assert event_row[0] == "job_file_scored"
    assert '"score_total": 7.5' in event_row[1]


def test_runtime_repository_sets_finished_at_for_terminal_job_and_session_states(tmp_path):
    db_path = tmp_path / "runtime.db"
    repo = SQLiteRuntimeRepository(db_path)

    session_id = repo.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
        status=SessionStatus.OPEN,
    )
    job_id = repo.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        stage=JobStage.DISCOVER,
        status=JobStatus.QUEUED,
    )

    repo.update_job(job_id, stage=JobStage.SCORE, status=JobStatus.RUNNING)
    repo.update_job(job_id, stage=JobStage.FINALIZE, status=JobStatus.FINISHED)
    repo.update_session(session_id, status=SessionStatus.FINISHED)

    job_row = repo.conn.execute(
        "SELECT status, finished_at FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    session_row = repo.conn.execute(
        "SELECT status, finished_at FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()

    assert job_row["status"] == "finished"
    assert job_row["finished_at"] is not None
    assert session_row["status"] == "finished"
    assert session_row["finished_at"] is not None


def test_runtime_repository_treats_finished_with_errors_as_terminal_for_job_and_session(tmp_path):
    db_path = tmp_path / "runtime.db"
    repo = SQLiteRuntimeRepository(db_path)

    session_id = repo.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={"backend": "omlx"},
        status=SessionStatus.OPEN,
    )
    job_id = repo.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        stage=JobStage.DISCOVER,
        status=JobStatus.QUEUED,
    )

    repo.update_job(job_id, stage=JobStage.FINALIZE, status=JobStatus.FINISHED_WITH_ERRORS)
    repo.update_session(session_id, status=SessionStatus.FINISHED_WITH_ERRORS)

    job_row = repo.conn.execute(
        "SELECT status, finished_at FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    session_row = repo.conn.execute(
        "SELECT status, finished_at FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()

    assert job_row["status"] == "finished_with_errors"
    assert job_row["finished_at"] is not None
    assert session_row["status"] == "finished_with_errors"
    assert session_row["finished_at"] is not None


def test_runtime_repository_uses_sqlite_database(tmp_path):
    db_path = tmp_path / "runtime.db"
    repo = SQLiteRuntimeRepository(db_path)
    assert isinstance(repo.conn, sqlite3.Connection)
