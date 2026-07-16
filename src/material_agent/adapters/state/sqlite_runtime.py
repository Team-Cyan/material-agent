import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ...app.dto import (
    ArtifactRef,
    JobFileRecord,
    JobFileStatus,
    JobRecord,
    JobStage,
    JobStatus,
    JobType,
    SessionKind,
    SessionRecord,
    SessionStatus,
)
from ...utils.file_security import secure_sqlite_files


_REDACTED_VALUE = "[REDACTED]"
_SECRET_KEYS = {
    "access_key",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "password",
    "private_key",
    "secret",
    "token",
}


def _is_secret_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    compact = "".join(character for character in normalized if character.isalnum())
    return normalized in _SECRET_KEYS or compact.endswith(
        ("accesskey", "apikey", "credential", "credentials", "password", "privatekey", "secret", "token")
    )


def redact_secrets(value: Any) -> Any:
    """Return a JSON-compatible copy with credential-like values removed."""

    if isinstance(value, dict):
        return {
            key: _REDACTED_VALUE if _is_secret_key(key) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    return value


class SQLiteRuntimeRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._batch_commit_every: int | None = None
        self._pending_logical_commits = 0
        self._bootstrap()

    def _commit(self) -> None:
        if self._batch_commit_every is None:
            self.conn.commit()
            return
        self._pending_logical_commits += 1
        if self._pending_logical_commits >= self._batch_commit_every:
            self.conn.commit()
            self._pending_logical_commits = 0

    @contextmanager
    def batched_commits(self, commit_every: int = 2048):
        """Coalesce chatty runtime writes while preserving bounded recovery."""

        if self._batch_commit_every is not None:
            yield
            return
        self._batch_commit_every = max(1, int(commit_every))
        self._pending_logical_commits = 0
        try:
            yield
        except BaseException:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()
        finally:
            self._batch_commit_every = None
            self._pending_logical_commits = 0

    @staticmethod
    def _is_terminal_session_status(status: str) -> bool:
        return status in {
            SessionStatus.FINISHED.value,
            SessionStatus.FINISHED_WITH_ERRORS.value,
            SessionStatus.FAILED.value,
            SessionStatus.CANCELLED.value,
        }

    @staticmethod
    def _is_terminal_job_status(status: str) -> bool:
        return status in {
            JobStatus.FINISHED.value,
            JobStatus.FINISHED_WITH_ERRORS.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        }

    def _bootstrap(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                input_root TEXT NOT NULL,
                config_snapshot TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                type TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                summary_json TEXT,
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );
            CREATE TABLE IF NOT EXISTS job_files (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                group_id TEXT,
                rank INTEGER,
                status TEXT NOT NULL,
                error_code TEXT,
                error_message TEXT,
                score_total REAL,
                scene TEXT,
                scene_raw TEXT,
                UNIQUE(job_id, file_path),
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                job_file_id TEXT,
                kind TEXT NOT NULL,
                uri TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                job_file_id TEXT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_artifacts_job_file_kind
                ON artifacts(job_file_id, kind);
            CREATE INDEX IF NOT EXISTS idx_artifacts_job_kind
                ON artifacts(job_id, kind);
            """
        )
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self._commit()
        secure_sqlite_files(self.db_path)

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    def create_session(
        self,
        *,
        kind: SessionKind,
        input_root: str,
        config_snapshot: dict[str, Any],
        status: SessionStatus,
    ) -> str:
        session_id = self._new_id()
        self.conn.execute(
            "INSERT INTO sessions (id, kind, input_root, config_snapshot, status) VALUES (?, ?, ?, ?, ?)",
            (
                session_id,
                kind.value,
                input_root,
                json.dumps(redact_secrets(config_snapshot), ensure_ascii=False),
                status.value,
            ),
        )
        self._commit()
        return session_id

    def get_job_result(self, job_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT status, summary_json FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return {
            "status": row["status"],
            "summary": json.loads(row["summary_json"] or "{}"),
        }

    def reconcile_abandoned_runs(self) -> dict[str, int]:
        """Cancel non-terminal rows left behind before the run lock was acquired."""

        active_session_statuses = (
            SessionStatus.OPEN.value,
            SessionStatus.RUNNING.value,
        )
        active_job_statuses = (
            JobStatus.QUEUED.value,
            JobStatus.RUNNING.value,
            JobStatus.PAUSED.value,
        )
        session_rows = self.conn.execute(
            "SELECT id FROM sessions WHERE status IN (?, ?)",
            active_session_statuses,
        ).fetchall()
        job_rows = self.conn.execute(
            """
            SELECT jobs.id, jobs.session_id, jobs.summary_json
            FROM jobs
            JOIN sessions ON sessions.id = jobs.session_id
            WHERE sessions.status IN (?, ?)
              AND jobs.status IN (?, ?, ?)
            """,
            (*active_session_statuses, *active_job_statuses),
        ).fetchall()

        reason = "abandoned_before_current_run"
        for row in job_rows:
            summary = json.loads(row["summary_json"] or "{}")
            summary["cancellation_reason"] = reason
            self.conn.execute(
                """
                UPDATE jobs
                SET stage = ?, status = ?, summary_json = ?, finished_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    JobStage.FINALIZE.value,
                    JobStatus.CANCELLED.value,
                    json.dumps(summary, ensure_ascii=False),
                    row["id"],
                ),
            )
            self.conn.execute(
                """
                INSERT INTO events (id, session_id, job_id, event_type, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self._new_id(),
                    row["session_id"],
                    row["id"],
                    "job_reconciled_cancelled",
                    json.dumps({"reason": reason}, ensure_ascii=False),
                ),
            )

        for row in session_rows:
            self.conn.execute(
                """
                UPDATE sessions
                SET status = ?, finished_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (SessionStatus.CANCELLED.value, row["id"]),
            )
        self._commit()
        return {"sessions": len(session_rows), "jobs": len(job_rows)}

    def close(self) -> None:
        self.conn.close()

    def create_job(
        self,
        *,
        session_id: str,
        job_type: JobType,
        stage: JobStage,
        status: JobStatus,
    ) -> str:
        job_id = self._new_id()
        self.conn.execute(
            "INSERT INTO jobs (id, session_id, type, stage, status, summary_json) VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, session_id, job_type.value, stage.value, status.value, json.dumps({}, ensure_ascii=False)),
        )
        self._commit()
        return job_id

    def update_session(self, session_id: str, *, status: SessionStatus) -> None:
        row = self.conn.execute("SELECT status FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(session_id)
        next_status = status.value
        next_finished_at = "CURRENT_TIMESTAMP" if self._is_terminal_session_status(next_status) else "NULL"
        self.conn.execute(
            f"UPDATE sessions SET status = ?, finished_at = {next_finished_at} WHERE id = ?",
            (next_status, session_id),
        )
        self._commit()

    def update_job(
        self,
        job_id: str,
        *,
        stage: JobStage | None = None,
        status: JobStatus | None = None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        row = self.conn.execute("SELECT stage, status, summary_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        next_stage = stage.value if stage is not None else row["stage"]
        next_status = status.value if status is not None else row["status"]
        next_summary = json.dumps(summary if summary is not None else json.loads(row["summary_json"] or "{}"), ensure_ascii=False)
        next_finished_at = "CURRENT_TIMESTAMP" if self._is_terminal_job_status(next_status) else "NULL"
        self.conn.execute(
            f"UPDATE jobs SET stage = ?, status = ?, summary_json = ?, finished_at = {next_finished_at} WHERE id = ?",
            (next_stage, next_status, next_summary, job_id),
        )
        self._commit()

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
    ) -> str:
        existing = self.conn.execute(
            "SELECT id FROM job_files WHERE job_id = ? AND file_path = ?",
            (job_id, file_path),
        ).fetchone()
        if existing is None:
            job_file_id = self._new_id()
            self.conn.execute(
                """
                INSERT INTO job_files (
                    id, job_id, file_path, group_id, rank, status, error_code,
                    error_message, score_total, scene, scene_raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_file_id,
                    job_id,
                    file_path,
                    group_id,
                    rank,
                    status.value,
                    error_code,
                    error_message,
                    score_total,
                    scene,
                    scene_raw,
                ),
            )
        else:
            job_file_id = existing["id"]
            self.conn.execute(
                """
                UPDATE job_files
                SET group_id = ?, rank = ?, status = ?, error_code = ?, error_message = ?,
                    score_total = ?, scene = ?, scene_raw = ?
                WHERE id = ?
                """,
                (
                    group_id,
                    rank,
                    status.value,
                    error_code,
                    error_message,
                    score_total,
                    scene,
                    scene_raw,
                    job_file_id,
                ),
            )
        self._commit()
        return job_file_id

    def append_event(
        self,
        *,
        session_id: str,
        job_id: str,
        event_type: str,
        payload: dict[str, Any],
        job_file_id: str | None = None,
    ) -> str:
        event_id = self._new_id()
        self.conn.execute(
            "INSERT INTO events (id, session_id, job_id, job_file_id, event_type, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, session_id, job_id, job_file_id, event_type, json.dumps(payload, ensure_ascii=False)),
        )
        self._commit()
        return event_id

    def get_job_session_id(self, job_id: str) -> str:
        row = self.conn.execute("SELECT session_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return row["session_id"]

    def get_job_file(self, *, job_id: str, file_path: str) -> JobFileRecord | None:
        row = self.conn.execute(
            """
            SELECT id, job_id, file_path, status, group_id, rank, error_code,
                   error_message, score_total, scene, scene_raw
            FROM job_files
            WHERE job_id = ? AND file_path = ?
            """,
            (job_id, file_path),
        ).fetchone()
        if row is None:
            return None
        return JobFileRecord(
            id=row["id"],
            job_id=row["job_id"],
            file_path=Path(row["file_path"]),
            status=JobFileStatus(row["status"]),
            group_id=row["group_id"],
            rank=row["rank"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            score_total=row["score_total"],
            scene=row["scene"],
            scene_raw=row["scene_raw"],
        )

    def upsert_artifact(
        self,
        *,
        job_id: str,
        job_file_id: str | None,
        kind: str,
        uri: str,
        metadata: dict[str, Any],
    ) -> str:
        existing = None
        if job_file_id is not None:
            existing = self.conn.execute(
                "SELECT id FROM artifacts WHERE job_file_id = ? AND kind = ?",
                (job_file_id, kind),
            ).fetchone()
        if existing is None:
            artifact_id = self._new_id()
            self.conn.execute(
                """
                INSERT INTO artifacts (id, job_id, job_file_id, kind, uri, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    job_id,
                    job_file_id,
                    kind,
                    uri,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
        else:
            artifact_id = existing["id"]
            self.conn.execute(
                """
                UPDATE artifacts
                SET uri = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    uri,
                    json.dumps(metadata, ensure_ascii=False),
                    artifact_id,
                ),
            )
        self._commit()
        return artifact_id

    def get_artifact_metadata(self, *, job_file_id: str, kind: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT metadata_json
            FROM artifacts
            WHERE job_file_id = ? AND kind = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (job_file_id, kind),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["metadata_json"] or "{}")

    def list_artifact_metadata(self, *, job_id: str, kind: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT metadata_json
            FROM artifacts
            WHERE job_id = ? AND kind = ?
            ORDER BY rowid ASC
            """,
            (job_id, kind),
        ).fetchall()
        return [json.loads(row["metadata_json"] or "{}") for row in rows]

    def list_sessions(self) -> list[SessionRecord]:
        rows = self.conn.execute(
            "SELECT id, kind, input_root, config_snapshot, status, created_at, finished_at "
            "FROM sessions ORDER BY created_at ASC, rowid ASC"
        ).fetchall()
        return [
            SessionRecord(
                id=row["id"],
                kind=SessionKind(row["kind"]),
                input_root=Path(row["input_root"]),
                config_snapshot=json.loads(row["config_snapshot"] or "{}"),
                status=SessionStatus(row["status"]),
                created_at=row["created_at"],
                finished_at=row["finished_at"],
            )
            for row in rows
        ]

    def list_jobs(self, session_id: str) -> list[JobRecord]:
        rows = self.conn.execute(
            "SELECT id, session_id, type, stage, status, summary_json, started_at, finished_at "
            "FROM jobs WHERE session_id = ? ORDER BY started_at ASC, rowid ASC",
            (session_id,),
        ).fetchall()
        return [
            JobRecord(
                id=row["id"],
                session_id=row["session_id"],
                type=JobType(row["type"]),
                stage=JobStage(row["stage"]),
                status=JobStatus(row["status"]),
                summary=json.loads(row["summary_json"] or "{}"),
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
            for row in rows
        ]

    def list_job_files(self, job_id: str) -> list[JobFileRecord]:
        rows = self.conn.execute(
            """
            SELECT id, job_id, file_path, status, group_id, rank, error_code,
                   error_message, score_total, scene, scene_raw
            FROM job_files
            WHERE job_id = ?
            ORDER BY file_path ASC
            """,
            (job_id,),
        ).fetchall()
        return [
            JobFileRecord(
                id=row["id"],
                job_id=row["job_id"],
                file_path=Path(row["file_path"]),
                status=JobFileStatus(row["status"]),
                group_id=row["group_id"],
                rank=row["rank"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                score_total=row["score_total"],
                scene=row["scene"],
                scene_raw=row["scene_raw"],
            )
            for row in rows
        ]

    def list_artifacts(self, job_id: str) -> list[ArtifactRef]:
        rows = self.conn.execute(
            "SELECT id, kind, uri, metadata_json FROM artifacts WHERE job_id = ? ORDER BY created_at ASC, rowid ASC",
            (job_id,),
        ).fetchall()
        return [
            ArtifactRef(
                id=row["id"],
                kind=row["kind"],
                uri=row["uri"],
                metadata=json.loads(row["metadata_json"] or "{}"),
            )
            for row in rows
        ]

    def list_events(self, job_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, session_id, job_id, job_file_id, event_type, payload_json, created_at
            FROM events
            WHERE job_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (job_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "job_id": row["job_id"],
                "job_file_id": row["job_file_id"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
