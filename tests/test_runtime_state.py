import json
import sqlite3
import stat

import pytest

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
    indexes = {
        row[0]
        for row in repo.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_artifacts_job_file_kind" in indexes
    assert "idx_artifacts_job_kind" in indexes
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


def test_runtime_repository_batches_logical_commits_with_bounded_visibility(tmp_path):
    db_path = tmp_path / "runtime.db"
    repo = SQLiteRuntimeRepository(db_path)
    observer = sqlite3.connect(db_path)

    with repo.batched_commits(commit_every=10):
        repo.create_session(
            kind=SessionKind.CLI,
            input_root="/tmp/photos",
            config_snapshot={},
            status=SessionStatus.OPEN,
        )
        assert observer.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0

    assert observer.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


def test_runtime_repository_lists_job_artifacts_in_one_query(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_id = repo.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={},
        status=SessionStatus.OPEN,
    )
    job_id = repo.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        stage=JobStage.SCORE,
        status=JobStatus.RUNNING,
    )
    job_file_id = repo.upsert_job_file(
        job_id=job_id,
        file_path="/tmp/photos/a.ARW",
        status=JobFileStatus.SCORED,
    )
    repo.upsert_artifact(
        job_id=job_id,
        job_file_id=job_file_id,
        kind="score_payload",
        uri="memory://score/a",
        metadata={"score_total": 7.5},
    )

    assert repo.list_artifact_metadata(job_id=job_id, kind="score_payload") == [
        {"score_total": 7.5}
    ]


def test_runtime_repository_redacts_nested_secrets_from_config_snapshot(tmp_path):
    db_path = tmp_path / "runtime.db"
    repo = SQLiteRuntimeRepository(db_path)

    session_id = repo.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={
            "api_key": "top-secret",
            "nested": {
                "Authorization": "Bearer nested-secret",
                "clientSecret": "camel-secret",
                "max_tokens": 512,
                "items": [{"refresh_token": "refresh-secret"}],
            },
        },
        status=SessionStatus.OPEN,
    )

    raw_snapshot = repo.conn.execute(
        "SELECT config_snapshot FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()[0]
    snapshot = json.loads(raw_snapshot)

    assert "top-secret" not in raw_snapshot
    assert "nested-secret" not in raw_snapshot
    assert "camel-secret" not in raw_snapshot
    assert "refresh-secret" not in raw_snapshot
    assert snapshot["api_key"] == "[REDACTED]"
    assert snapshot["nested"]["Authorization"] == "[REDACTED]"
    assert snapshot["nested"]["clientSecret"] == "[REDACTED]"
    assert snapshot["nested"]["max_tokens"] == 512


def test_runtime_repository_get_job_result_returns_status_and_summary(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_id = repo.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={},
        status=SessionStatus.OPEN,
    )
    job_id = repo.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        stage=JobStage.DISCOVER,
        status=JobStatus.QUEUED,
    )
    repo.update_job(
        job_id,
        stage=JobStage.FINALIZE,
        status=JobStatus.FINISHED_WITH_ERRORS,
        summary={"error_files": 1},
    )

    assert repo.get_job_result(job_id) == {
        "status": "finished_with_errors",
        "summary": {"error_files": 1},
    }
    with pytest.raises(KeyError):
        repo.get_job_result("missing")


def test_runtime_repository_reconciles_abandoned_jobs_and_sessions(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    session_id = repo.create_session(
        kind=SessionKind.CLI,
        input_root="/tmp/photos",
        config_snapshot={},
        status=SessionStatus.RUNNING,
    )
    job_id = repo.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        stage=JobStage.SCORE,
        status=JobStatus.RUNNING,
    )
    paused_job_id = repo.create_job(
        session_id=session_id,
        job_type=JobType.REVIEW_PHOTOS,
        stage=JobStage.SCORE,
        status=JobStatus.PAUSED,
    )

    assert repo.reconcile_abandoned_runs() == {"sessions": 1, "jobs": 2}

    session = repo.conn.execute(
        "SELECT status, finished_at FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    job = repo.conn.execute(
        "SELECT stage, status, summary_json, finished_at FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    event = repo.conn.execute(
        "SELECT event_type, payload_json FROM events WHERE job_id = ?", (job_id,)
    ).fetchone()
    paused_job = repo.conn.execute(
        "SELECT stage, status, finished_at FROM jobs WHERE id = ?", (paused_job_id,)
    ).fetchone()
    assert session["status"] == "cancelled"
    assert session["finished_at"] is not None
    assert tuple(job[:2]) == ("finalize", "cancelled")
    assert job["finished_at"] is not None
    assert json.loads(job["summary_json"])["cancellation_reason"] == (
        "abandoned_before_current_run"
    )
    assert event["event_type"] == "job_reconciled_cancelled"
    assert json.loads(event["payload_json"])["reason"] == "abandoned_before_current_run"
    assert tuple(paused_job[:2]) == ("finalize", "cancelled")
    assert paused_job["finished_at"] is not None
    assert repo.reconcile_abandoned_runs() == {"sessions": 0, "jobs": 0}


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
