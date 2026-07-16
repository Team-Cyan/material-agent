from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import yaml

from ..adapters.state.sqlite_runtime import SQLiteRuntimeRepository, redact_secrets
from ..commands.scoring import load_config
from ..domain.scoring_engine import decode_raw
from ..io.scanner import scan_arw_files
from .model_catalog_service import (
    DEFAULT_MODEL_CATALOG,
    ModelCatalogService,
    load_model_catalog,
)


_REDACTED = "[REDACTED]"
_TERMINAL_TASK_STATES = {"finished", "failed", "cancelled", "interrupted"}


def _json_value(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _safe_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, parsed))


def _restore_redacted(existing, proposed):
    if proposed == _REDACTED:
        return existing
    if isinstance(existing, dict) and isinstance(proposed, dict):
        return {
            key: _restore_redacted(existing.get(key), value)
            for key, value in proposed.items()
        }
    if isinstance(proposed, list):
        return [
            _restore_redacted(existing[index] if isinstance(existing, list) and index < len(existing) else None, value)
            for index, value in enumerate(proposed)
        ]
    return proposed


class WebLibraryRepository:
    def __init__(self, db_path: str | Path, input_root: str | Path):
        self.db_path = Path(db_path)
        self.input_root = Path(input_root).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._bootstrap()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _bootstrap(self) -> None:
        runtime_repository = SQLiteRuntimeRepository(self.db_path)
        runtime_repository.conn.close()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS library_index (
                    id TEXT PRIMARY KEY,
                    root_path TEXT NOT NULL,
                    file_path TEXT NOT NULL UNIQUE,
                    relative_path TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    scan_generation TEXT NOT NULL,
                    indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_library_root_relative "
                "ON library_index(root_path, relative_path)"
            )

    def refresh_index(self, extensions: list[str]) -> dict:
        generation = uuid.uuid4().hex
        files = scan_arw_files(str(self.input_root), extensions)
        rows = []
        for file_path in files:
            path = Path(file_path).resolve()
            try:
                relative = path.relative_to(self.input_root)
                stat = path.stat()
            except (OSError, ValueError):
                continue
            rows.append(
                (
                    hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:32],
                    str(self.input_root),
                    str(path),
                    str(relative),
                    path.suffix.lstrip(".").upper(),
                    int(stat.st_size),
                    int(stat.st_mtime_ns),
                    generation,
                )
            )
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO library_index (
                    id, root_path, file_path, relative_path, extension,
                    file_size, mtime_ns, scan_generation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    root_path=excluded.root_path,
                    relative_path=excluded.relative_path,
                    extension=excluded.extension,
                    file_size=excluded.file_size,
                    mtime_ns=excluded.mtime_ns,
                    scan_generation=excluded.scan_generation,
                    indexed_at=CURRENT_TIMESTAMP
                """,
                rows,
            )
            connection.execute(
                "DELETE FROM library_index WHERE root_path=? AND scan_generation<>?",
                (str(self.input_root), generation),
            )
        return {"indexed": len(rows), "root": str(self.input_root), "generation": generation}

    @staticmethod
    def _latest_scores_cte() -> str:
        return """
            WITH ranked_scores AS (
                SELECT
                    jf.id AS job_file_id,
                    jf.file_path,
                    jf.status,
                    jf.group_id,
                    jf.rank,
                    jf.score_total,
                    jf.scene,
                    jf.scene_raw,
                    jf.error_code,
                    jf.error_message,
                    j.id AS job_id,
                    j.stage AS job_stage,
                    j.status AS job_status,
                    j.started_at,
                    j.finished_at,
                    a.metadata_json,
                    ROW_NUMBER() OVER (
                        PARTITION BY jf.file_path
                        ORDER BY j.started_at DESC, jf.rowid DESC
                    ) AS score_order
                FROM job_files jf
                JOIN jobs j ON j.id = jf.job_id
                LEFT JOIN artifacts a
                  ON a.job_file_id = jf.id AND a.kind = 'score_payload'
            ), latest_scores AS (
                SELECT * FROM ranked_scores WHERE score_order = 1
            )
        """

    def summary(self) -> dict:
        with self._connect() as connection:
            indexed = connection.execute(
                "SELECT COUNT(*) FROM library_index WHERE root_path=?",
                (str(self.input_root),),
            ).fetchone()[0]
            row = connection.execute(
                self._latest_scores_cte()
                + """
                SELECT
                    COUNT(*) AS scored,
                    SUM(CASE WHEN score_total IS NOT NULL THEN 1 ELSE 0 END) AS with_score,
                    SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors,
                    AVG(score_total) AS average_score
                FROM latest_scores ls
                JOIN library_index li ON li.file_path=ls.file_path
                WHERE li.root_path=?
                """,
                (str(self.input_root),),
            ).fetchone()
            scenes = connection.execute(
                self._latest_scores_cte()
                + """
                SELECT COALESCE(scene, 'unscored') AS scene, COUNT(*) AS count
                FROM latest_scores ls
                JOIN library_index li ON li.file_path=ls.file_path
                WHERE li.root_path=?
                GROUP BY COALESCE(scene, 'unscored')
                ORDER BY count DESC, scene ASC LIMIT 20
                """,
                (str(self.input_root),),
            ).fetchall()
        return {
            "indexed": int(indexed),
            "scored": int(row["with_score"] or 0),
            "score_records": int(row["scored"] or 0),
            "errors": int(row["errors"] or 0),
            "average_score": None if row["average_score"] is None else round(float(row["average_score"]), 3),
            "scenes": [{"scene": item["scene"], "count": item["count"]} for item in scenes],
        }

    def list_items(self, query: dict[str, list[str]]) -> dict:
        page = _safe_int(query.get("page", [1])[0], default=1, minimum=1, maximum=1_000_000)
        page_size = _safe_int(
            query.get("page_size", [48])[0], default=48, minimum=1, maximum=200
        )
        search = query.get("search", [""])[0].strip()
        scene = query.get("scene", [""])[0].strip()
        decision = query.get("decision", [""])[0].strip()
        scored = query.get("scored", [""])[0].strip().lower()
        order = query.get("order", ["path"])[0].strip().lower()
        where = ["li.root_path=?"]
        params: list[object] = [str(self.input_root)]
        if search:
            where.append("li.relative_path LIKE ? ESCAPE '\\'")
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        if scene:
            where.append("COALESCE(ls.scene, '')=?")
            params.append(scene)
        if decision:
            where.append("COALESCE(json_extract(ls.metadata_json, '$.decision'), '')=?")
            params.append(decision)
        if scored == "yes":
            where.append("ls.score_total IS NOT NULL")
        elif scored == "no":
            where.append("ls.score_total IS NULL")
        order_sql = {
            "score_desc": "ls.score_total DESC NULLS LAST, li.relative_path ASC",
            "score_asc": "ls.score_total ASC NULLS LAST, li.relative_path ASC",
            "newest": "li.mtime_ns DESC, li.relative_path ASC",
            "path": "li.relative_path ASC",
        }.get(order, "li.relative_path ASC")
        cte = self._latest_scores_cte()
        tables = (
            " FROM library_index li "
            "LEFT JOIN latest_scores ls ON ls.file_path=li.file_path "
        )
        where_sql = " WHERE " + " AND ".join(where)
        with self._connect() as connection:
            total = connection.execute(
                cte + "SELECT COUNT(*)" + tables + where_sql, params
            ).fetchone()[0]
            rows = connection.execute(
                cte
                + """
                SELECT li.id, li.relative_path, li.extension, li.file_size, li.mtime_ns,
                       ls.job_file_id, ls.job_id, ls.status, ls.score_total, ls.scene,
                       ls.scene_raw, ls.rank, ls.group_id,
                       json_extract(ls.metadata_json, '$.decision') AS decision,
                       json_extract(ls.metadata_json, '$.star_rating') AS star_rating,
                       json_extract(
                           ls.metadata_json,
                           '$.meta.subject_focus.primary_target.label'
                       ) AS target
                """
                + tables
                + where_sql
                + f" ORDER BY {order_sql} LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return {
            "items": [dict(row) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": int(total),
            "pages": max(1, (int(total) + page_size - 1) // page_size),
        }

    def detail(self, item_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                self._latest_scores_cte()
                + """
                SELECT li.id, li.file_path, li.relative_path, li.extension,
                       li.file_size, li.mtime_ns, ls.*
                FROM library_index li
                LEFT JOIN latest_scores ls ON ls.file_path=li.file_path
                WHERE li.root_path=? AND li.id=?
                """,
                (str(self.input_root), item_id),
            ).fetchone()
        if row is None:
            return None
        payload = _json_value(row["metadata_json"], {})
        return {
            "id": row["id"],
            "file_path": row["file_path"],
            "relative_path": row["relative_path"],
            "extension": row["extension"],
            "file_size": row["file_size"],
            "mtime_ns": row["mtime_ns"],
            "job_file_id": row["job_file_id"],
            "job_id": row["job_id"],
            "status": row["status"],
            "score_total": row["score_total"],
            "scene": row["scene"],
            "scene_raw": row["scene_raw"],
            "rank": row["rank"],
            "group_id": row["group_id"],
            "error_code": row["error_code"],
            "error_message": row["error_message"],
            "score": payload,
        }

    def item_path(self, item_id: str) -> Path | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT file_path FROM library_index WHERE root_path=? AND id=?",
                (str(self.input_root), item_id),
            ).fetchone()
        if row is None:
            return None
        path = Path(row["file_path"]).resolve()
        try:
            path.relative_to(self.input_root)
        except ValueError:
            return None
        return path

    def list_jobs(self, limit: int = 30) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT j.id, j.session_id, j.type, j.stage, j.status, j.summary_json,
                       j.started_at, j.finished_at,
                       COUNT(jf.id) AS file_count,
                       SUM(CASE WHEN jf.score_total IS NOT NULL THEN 1 ELSE 0 END) AS scored_count,
                       SUM(CASE WHEN jf.status='error' THEN 1 ELSE 0 END) AS error_count
                FROM jobs j LEFT JOIN job_files jf ON jf.job_id=j.id
                GROUP BY j.id ORDER BY j.started_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                **{key: row[key] for key in row.keys() if key != "summary_json"},
                "summary": _json_value(row["summary_json"], {}),
            }
            for row in rows
        ]


@dataclass
class WebTask:
    id: str
    status: str
    created_at: float
    command: list[str]
    config_path: str
    log_path: str
    max_files: int | None
    pid: int | None = None
    exit_code: int | None = None
    finished_at: float | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class WebTaskManager:
    def __init__(
        self,
        *,
        input_root: str | Path,
        config_path: str | Path,
        work_dir: str | Path,
        executable: str = "material-agent",
    ):
        self.input_root = Path(input_root).resolve()
        self.config_path = Path(config_path).resolve()
        self.work_dir = Path(work_dir).resolve()
        self.executable = executable
        self.web_dir = self.work_dir / "web"
        self.config_dir = self.web_dir / "task-configs"
        self.log_dir = self.web_dir / "logs"
        self.state_path = self.web_dir / "tasks.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._tasks = self._load()
        for task in self._tasks.values():
            if task.status in {"queued", "running", "cancelling"}:
                task.status = "interrupted"
                task.finished_at = time.time()
        self._persist()

    def _load(self) -> dict[str, WebTask]:
        if not self.state_path.exists():
            return {}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return {item["id"]: WebTask(**item) for item in payload if isinstance(item, dict)}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {}

    def _persist(self) -> None:
        self.web_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps([task.as_dict() for task in self._tasks.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.state_path)

    def list(self) -> list[dict]:
        with self._lock:
            return [
                task.as_dict()
                for task in sorted(self._tasks.values(), key=lambda item: item.created_at, reverse=True)
            ]

    def active(self) -> dict | None:
        with self._lock:
            for task in self._tasks.values():
                if task.status not in _TERMINAL_TASK_STATES:
                    return task.as_dict()
        return None

    def start(self, *, max_files: int | None, reprocess: bool, no_visual_merge: bool) -> dict:
        with self._lock:
            if self.active() is not None:
                raise ValueError("another scoring task is already active")
            task_id = uuid.uuid4().hex
            raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                raise ValueError("runtime config root must be a mapping")
            review = raw.setdefault("review_pipeline", {})
            if not isinstance(review, dict):
                raise ValueError("review_pipeline must be a mapping")
            if max_files is None:
                review.pop("max_files", None)
            else:
                review["max_files"] = _safe_int(max_files, default=128, minimum=1, maximum=1_000_000)
            task_config = self.config_dir / f"{task_id}.yaml"
            task_config.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
            load_config(str(task_config))
            log_path = self.log_dir / f"{task_id}.log"
            command = [
                self.executable,
                "run",
                str(self.input_root),
                "--config",
                str(task_config),
                "--dry-run",
            ]
            if reprocess:
                command.append("--reprocess")
            if no_visual_merge:
                command.append("--no-visual-merge")
            task = WebTask(
                id=task_id,
                status="queued",
                created_at=time.time(),
                command=command,
                config_path=str(task_config),
                log_path=str(log_path),
                max_files=max_files,
            )
            self._tasks[task_id] = task
            self._persist()
            try:
                log_handle = log_path.open("ab", buffering=0)
                process = subprocess.Popen(
                    command,
                    cwd=str(self.work_dir),
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError as error:
                if "log_handle" in locals():
                    log_handle.close()
                task.status = "failed"
                task.error = str(error)
                task.finished_at = time.time()
                self._persist()
                raise ValueError(str(error)) from error
            task.status = "running"
            task.pid = process.pid
            self._processes[task_id] = process
            self._persist()
            threading.Thread(
                target=self._wait_for_process,
                args=(task_id, process, log_handle),
                daemon=True,
            ).start()
            return task.as_dict()

    def _wait_for_process(self, task_id: str, process: subprocess.Popen, log_handle) -> None:
        exit_code = process.wait()
        log_handle.close()
        with self._lock:
            task = self._tasks[task_id]
            task.exit_code = exit_code
            task.finished_at = time.time()
            if task.status == "cancelling":
                task.status = "cancelled"
            else:
                task.status = "finished" if exit_code == 0 else "failed"
            self._processes.pop(task_id, None)
            self._persist()

    def cancel(self, task_id: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if task.status in _TERMINAL_TASK_STATES:
                return task.as_dict()
            process = self._processes.get(task_id)
            if process is None or process.poll() is not None:
                task.status = "interrupted"
                task.finished_at = time.time()
                self._persist()
                return task.as_dict()
            task.status = "cancelling"
            self._persist()
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            return task.as_dict()

    def log_tail(self, task_id: str, maximum_bytes: int = 64_000) -> str:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(task_id)
        path = Path(task.log_path)
        if not path.exists():
            return ""
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - maximum_bytes))
            return handle.read().decode("utf-8", errors="replace")


class MaterialWebServer(ThreadingHTTPServer):
    def __init__(
        self,
        address,
        *,
        library: WebLibraryRepository,
        tasks: WebTaskManager,
        model_service: ModelCatalogService,
        config_path: Path,
        thumbnail_dir: Path,
    ):
        super().__init__(address, MaterialWebHandler)
        self.library = library
        self.tasks = tasks
        self.model_service = model_service
        self.config_path = config_path
        self.thumbnail_dir = thumbnail_dir
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)


class MaterialWebHandler(BaseHTTPRequestHandler):
    server: MaterialWebServer
    static_root = Path(__file__).resolve().parent.parent / "web"

    def do_GET(self) -> None:  # noqa: N802
        split = urlsplit(self.path)
        path = split.path
        if path in {"/", "/index.html", "/app.js", "/styles.css", "/output-preview.css"}:
            self._static("index.html" if path in {"/", "/index.html"} else path.lstrip("/"))
            return
        if path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
        elif path == "/api/overview":
            self._json(
                HTTPStatus.OK,
                {
                    "library": self.server.library.summary(),
                    "active_task": self.server.tasks.active(),
                    "tasks": self.server.tasks.list()[:10],
                    "jobs": self.server.library.list_jobs(10),
                },
            )
        elif path == "/api/config":
            self._json(HTTPStatus.OK, self._read_config())
        elif path == "/api/jobs":
            self._json(HTTPStatus.OK, {"jobs": self.server.library.list_jobs(50)})
        elif path == "/api/tasks":
            self._json(HTTPStatus.OK, {"tasks": self.server.tasks.list()})
        elif path.startswith("/api/tasks/") and path.endswith("/log"):
            task_id = path.split("/")[3]
            try:
                log = self.server.tasks.log_tail(task_id)
            except KeyError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "task_not_found"})
                return
            self._json(HTTPStatus.OK, {"task_id": task_id, "log": log})
        elif path == "/api/library":
            self._json(HTTPStatus.OK, self.server.library.list_items(parse_qs(split.query)))
        elif path.startswith("/api/library/") and path.endswith("/thumbnail"):
            self._thumbnail(path.split("/")[3])
        elif path.startswith("/api/library/"):
            item = self.server.library.detail(unquote(path.split("/")[3]))
            if item is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "item_not_found"})
            else:
                self._json(HTTPStatus.OK, item)
        elif path == "/api/models":
            self._json(HTTPStatus.OK, {"models": self.server.model_service.list_models()})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_PUT(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/api/config":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            body = self._body()
            proposed = body.get("config")
            if not isinstance(proposed, dict):
                raise ValueError("config must be a JSON object")
            existing = yaml.safe_load(self.server.config_path.read_text(encoding="utf-8")) or {}
            merged = _restore_redacted(existing, proposed)
            temporary = self.server.config_path.with_suffix(".web.tmp")
            backup = self.server.config_path.with_suffix(".web.bak")
            temporary.write_text(
                yaml.safe_dump(merged, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
            load_config(str(temporary))
            shutil.copy2(self.server.config_path, backup)
            os.replace(temporary, self.server.config_path)
        except (OSError, ValueError, yaml.YAMLError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._json(HTTPStatus.OK, self._read_config())

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        try:
            if path == "/api/library/index":
                config = load_config(str(self.server.config_path))
                result = self.server.library.refresh_index(config.get("raw_extensions", ["ARW"]))
            elif path == "/api/tasks":
                body = self._body()
                raw_max_files = body.get("max_files")
                max_files = None if raw_max_files in {None, "", "all"} else int(raw_max_files)
                result = self.server.tasks.start(
                    max_files=max_files,
                    reprocess=bool(body.get("reprocess", False)),
                    no_visual_merge=bool(body.get("no_visual_merge", False)),
                )
            elif path.startswith("/api/tasks/") and path.endswith("/cancel"):
                result = self.server.tasks.cancel(path.split("/")[3])
            elif path.startswith("/api/models/"):
                parts = path.strip("/").split("/")
                if len(parts) != 4:
                    raise KeyError(path)
                model_id, action = parts[2], parts[3]
                if action == "install":
                    result = self.server.model_service.install(model_id)
                elif action == "select":
                    result = self.server.model_service.select(model_id)
                else:
                    raise KeyError(path)
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
        except KeyError:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        except (OSError, TypeError, ValueError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._json(HTTPStatus.OK, result)

    def do_DELETE(self) -> None:  # noqa: N802
        split = urlsplit(self.path)
        parts = split.path.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["api", "models"]:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        force = parse_qs(split.query).get("force", ["false"])[0].lower() in {"1", "true", "yes"}
        try:
            result = self.server.model_service.delete(parts[2], force=force)
        except (OSError, ValueError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._json(HTTPStatus.OK, result)

    def _read_config(self) -> dict:
        raw = yaml.safe_load(self.server.config_path.read_text(encoding="utf-8")) or {}
        return {"config": redact_secrets(raw), "path": str(self.server.config_path)}

    def _thumbnail(self, item_id: str) -> None:
        source = self.server.library.item_path(item_id)
        if source is None or not source.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "item_not_found"})
            return
        target = self.server.thumbnail_dir / f"{item_id}.jpg"
        try:
            if not target.exists() or target.stat().st_mtime_ns < source.stat().st_mtime_ns:
                frame = decode_raw(
                    str(source),
                    {
                        "prefer_embedded": True,
                        "max_size": 640,
                        "focus_max_size": 640,
                        "jpeg_quality": 82,
                    },
                )
                temporary = target.with_suffix(".tmp")
                temporary.write_bytes(frame.jpeg_bytes)
                os.replace(temporary, target)
            body = target.read_bytes()
        except (OSError, RuntimeError, ValueError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self.send_response(HTTPStatus.OK.value)
        self._security_headers()
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "private, max-age=86400")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, name: str) -> None:
        path = self.static_root / name
        if not path.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        body = path.read_bytes()
        media_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
        }.get(path.suffix, "application/octet-stream")
        self.send_response(HTTPStatus.OK.value)
        self._security_headers()
        self.send_header("Content-Type", media_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        if length < 0 or length > 1_048_576:
            raise ValueError("request body exceeds 1 MiB")
        if length == 0:
            return {}
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'",
        )

    def _json(self, status: HTTPStatus, payload, *, extra_headers: dict | None = None) -> None:
        body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self.send_response(status.value)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def serve_web(
    *,
    host: str,
    port: int,
    input_root: str | Path,
    config_path: str | Path,
    work_dir: str | Path,
    registry_dir: str | Path,
    catalog_path: str | Path | None = None,
    executable: str = "material-agent",
) -> None:
    work_path = Path(work_dir).resolve()
    library = WebLibraryRepository(work_path / "state.db", input_root)
    tasks = WebTaskManager(
        input_root=input_root,
        config_path=config_path,
        work_dir=work_path,
        executable=executable,
    )
    catalog = load_model_catalog(catalog_path) if catalog_path else DEFAULT_MODEL_CATALOG
    model_service = ModelCatalogService(registry_dir, catalog=catalog)
    server = MaterialWebServer(
        (host, port),
        library=library,
        tasks=tasks,
        model_service=model_service,
        config_path=Path(config_path).resolve(),
        thumbnail_dir=work_path / "web" / "thumbnails",
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
