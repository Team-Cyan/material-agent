import json
import logging
import sqlite3
import threading
from pathlib import Path

from ...utils.constants import (
    AESTHETIC_SOURCE_MAP,
    LEGACY_SCENE_MIGRATIONS,
    SCENE_LABELS,
    SCENE_LIST,
    VISION_DIMS,
)
from ...utils.runtime_paths import build_runtime_paths, ensure_runtime_paths

_log = logging.getLogger("material_agent")

_VISION_COLUMNS = [f"score_{dim}" for dim in VISION_DIMS]
_BASE_SCORE_COLUMNS = ["score_exposure", "score_sharpness"] + _VISION_COLUMNS


def _file_fingerprint(file_path: str) -> tuple[int, int]:
    try:
        stat = Path(file_path).stat()
    except OSError:
        return -1, -1
    return int(stat.st_size), int(stat.st_mtime_ns)

DDL = f"""
CREATE TABLE IF NOT EXISTS processed (
    file_path TEXT PRIMARY KEY,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT,
    error_message TEXT,
    scene TEXT,
    scene_raw TEXT,
    total_score REAL,
    star_rating INTEGER,
    decision TEXT,
    decision_reasons TEXT,
    screening_prior REAL,
    visible_breakdown_json TEXT,
    policy_version TEXT,
    group_boosted INTEGER,
    group_id TEXT,
    group_rank INTEGER,
    group_size INTEGER,
    {", ".join(f"{column} REAL" for column in _BASE_SCORE_COLUMNS)},
    overexpose_ratio REAL,
    underexpose_ratio REAL,
    laplacian_variance REAL,
    commentary_group_issues TEXT,
    commentary_shooting TEXT,
    commentary_post TEXT
);
CREATE TABLE IF NOT EXISTS exif_cache (
    file_path TEXT PRIMARY KEY,
    datetime_original TEXT
);
CREATE TABLE IF NOT EXISTS visual_hash_cache (
    file_path TEXT PRIMARY KEY,
    phash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS embedding_cache (
    file_path TEXT NOT NULL,
    model_key TEXT NOT NULL,
    vector_json TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT -1,
    mtime_ns INTEGER NOT NULL DEFAULT -1,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_path, model_key)
);
CREATE TABLE IF NOT EXISTS score_signals (
    file_path TEXT NOT NULL,
    stage TEXT NOT NULL,
    signal_key TEXT NOT NULL,
    value REAL,
    confidence REAL,
    source TEXT,
    model_name TEXT,
    model_version TEXT,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_path, stage, signal_key)
);
"""


class SQLiteProcessedRepository:
    def __init__(self, input_dir: str | Path, reprocess: bool = False):
        self.reprocess = reprocess
        self._lock = threading.RLock()
        try:
            input_path = Path(input_dir)
            self.db_path = ensure_runtime_paths(input_path).db_path if input_path.is_dir() or not input_path.suffix else input_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connect(str(self.db_path))
        except OSError:
            self.db_path = build_runtime_paths(Path.home()).db_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connect(str(self.db_path))

    def _connect(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def _initialize_schema(self):
        self.conn.executescript(DDL)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        for column, column_type in [
            ("scene", "TEXT"),
            ("scene_raw", "TEXT"),
            ("decision", "TEXT"),
            ("decision_reasons", "TEXT"),
            ("screening_prior", "REAL"),
            ("visible_breakdown_json", "TEXT"),
            ("policy_version", "TEXT"),
            *[(column, "REAL") for column in _VISION_COLUMNS],
        ]:
            try:
                self.conn.execute(f"ALTER TABLE processed ADD COLUMN {column} {column_type}")
            except sqlite3.OperationalError:
                pass
        for column in ("file_size", "mtime_ns"):
            try:
                self.conn.execute(
                    f"ALTER TABLE embedding_cache ADD COLUMN {column} INTEGER NOT NULL DEFAULT -1"
                )
            except sqlite3.OperationalError:
                pass
        self._commit()

    def _cleanup_sidecars(self):
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                self.db_path.with_name(f"{self.db_path.name}{suffix}").unlink()
            except FileNotFoundError:
                pass

    def _recover_disk_io_error(self, error: sqlite3.OperationalError) -> bool:
        if "disk i/o error" not in str(error).lower():
            return False
        _log.warning("State hit SQLite disk I/O error; cleaning sidecars and reconnecting")
        try:
            self.conn.close()
        except Exception:
            pass
        self._cleanup_sidecars()
        self._connect(str(self.db_path))
        return True

    def _execute_once(self, sql: str, params=()):
        with self._lock:
            return self.conn.execute(sql, params)

    def _executemany_once(self, sql: str, params):
        with self._lock:
            return self.conn.executemany(sql, params)

    def _execute(self, sql: str, params=()):
        try:
            return self._execute_once(sql, params)
        except sqlite3.OperationalError as error:
            if not self._recover_disk_io_error(error):
                raise
            return self._execute_once(sql, params)

    def _executemany(self, sql: str, params):
        try:
            return self._executemany_once(sql, params)
        except sqlite3.OperationalError as error:
            if not self._recover_disk_io_error(error):
                raise
            return self._executemany_once(sql, params)

    def close(self):
        with self._lock:
            self.conn.close()

    def _commit(self):
        with self._lock:
            self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def get_exif_cache(self, file_paths: list[str]) -> dict[str, str | None]:
        if not file_paths:
            return {}
        placeholders = ",".join("?" * len(file_paths))
        rows = self._execute(
            f"SELECT file_path, datetime_original FROM exif_cache WHERE file_path IN ({placeholders})",
            file_paths,
        ).fetchall()
        return {row["file_path"]: row["datetime_original"] for row in rows}

    def set_exif_cache(self, entries: dict[str, str | None]):
        self._executemany(
            "INSERT OR REPLACE INTO exif_cache (file_path, datetime_original) VALUES (?,?)",
            [(k, v) for k, v in entries.items()],
        )
        self._commit()

    def get_visual_hash_cache(self, file_paths: list[str]) -> dict[str, str]:
        if not file_paths:
            return {}
        placeholders = ",".join("?" * len(file_paths))
        rows = self._execute(
            f"SELECT file_path, phash FROM visual_hash_cache WHERE file_path IN ({placeholders})",
            file_paths,
        ).fetchall()
        return {
            row["file_path"]: row["phash"]
            for row in rows
            if row["phash"]
        }

    def set_visual_hash_cache(self, entries: dict[str, str]):
        if not entries:
            return
        self._executemany(
            "INSERT OR REPLACE INTO visual_hash_cache (file_path, phash) VALUES (?,?)",
            [(k, v) for k, v in entries.items() if v],
        )
        self._commit()

    def get_embedding_cache(
        self, file_paths: list[str], model_key: str
    ) -> dict[str, list[float]]:
        if not file_paths:
            return {}
        placeholders = ",".join("?" * len(file_paths))
        rows = self._execute(
            f"SELECT file_path, vector_json, file_size, mtime_ns FROM embedding_cache "
            f"WHERE model_key=? AND file_path IN ({placeholders})",
            [model_key, *file_paths],
        ).fetchall()
        loaded: dict[str, list[float]] = {}
        for row in rows:
            if (row["file_size"], row["mtime_ns"]) != _file_fingerprint(row["file_path"]):
                continue
            try:
                vector = json.loads(row["vector_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(vector, list) and vector:
                loaded[row["file_path"]] = [float(value) for value in vector]
        return loaded

    def set_embedding_cache(
        self, entries: dict[str, list[float]], model_key: str
    ) -> None:
        if not entries:
            return
        self._executemany(
            "INSERT OR REPLACE INTO embedding_cache "
            "(file_path, model_key, vector_json, file_size, mtime_ns) VALUES (?,?,?,?,?)",
            [
                (
                    file_path,
                    model_key,
                    json.dumps(vector),
                    *_file_fingerprint(file_path),
                )
                for file_path, vector in entries.items()
                if vector
            ],
        )
        self._commit()

    def is_done(self, file_path: str) -> bool:
        if self.reprocess:
            return False
        row = self._execute(
            "SELECT status FROM processed WHERE file_path=?",
            (file_path,),
        ).fetchone()
        return row is not None and row["status"] == "done"

    def is_scored(self, file_path: str) -> bool:
        if self.reprocess:
            return False
        row = self._execute(
            "SELECT status FROM processed WHERE file_path=? AND status='scored'",
            (file_path,),
        ).fetchone()
        return row is not None

    def get_scored(self, file_path: str) -> dict | None:
        score_columns = ", ".join(_BASE_SCORE_COLUMNS)
        row = self._execute(
            f"SELECT total_score, star_rating, group_boosted, {score_columns}, "
            "overexpose_ratio, underexpose_ratio, laplacian_variance, scene, scene_raw, "
            "decision, decision_reasons, screening_prior, visible_breakdown_json, policy_version "
            "FROM processed WHERE file_path=? AND status='scored'",
            (file_path,),
        ).fetchone()
        if row is None:
            return None

        scores = {}
        for key, val in zip(["exposure", "sharpness", *VISION_DIMS], row[3 : 3 + len(_BASE_SCORE_COLUMNS)]):
            if val is not None:
                scores[key] = val

        meta = {}
        over_idx = 3 + len(_BASE_SCORE_COLUMNS)
        if row[over_idx] is not None:
            meta["overexpose_ratio"] = row[over_idx]
        if row[over_idx + 1] is not None:
            meta["underexpose_ratio"] = row[over_idx + 1]
        if row[over_idx + 2] is not None:
            meta["laplacian_variance"] = row[over_idx + 2]

        return {
            "total": row["total_score"],
            "star": row["star_rating"],
            "boosted": bool(row["group_boosted"]),
            "scores": scores,
            "meta": meta,
            "scene": row["scene"] or "other",
            "scene_raw": row["scene_raw"] or "",
            "decision": row["decision"] if "decision" in row.keys() else None,
            "decision_reasons": json.loads(row["decision_reasons"]) if "decision_reasons" in row.keys() and row["decision_reasons"] else [],
            "screening_prior": row["screening_prior"] if "screening_prior" in row.keys() else None,
            "visible_breakdown": json.loads(row["visible_breakdown_json"]) if "visible_breakdown_json" in row.keys() and row["visible_breakdown_json"] else {},
            "policy_version": row["policy_version"] if "policy_version" in row.keys() else "layered-v1",
            "signals": self.fetch_signals(file_path),
        }

    def mark_scored(
        self,
        file_path: str,
        total_score: float,
        scores: dict,
        metadata: dict,
        scene: str = "other",
        scene_raw: str = "",
        decision: str | None = None,
        decision_reasons: list[str] | None = None,
        screening_prior: float | None = None,
        visible_breakdown: dict | None = None,
        policy_version: str | None = None,
        signals: list[dict] | None = None,
    ):
        score_value_columns = ", ".join(_BASE_SCORE_COLUMNS)
        score_placeholders = ", ".join(f":{column}" for column in _BASE_SCORE_COLUMNS)
        payload = self._score_payload(scores)
        payload.update(
            {
                "file_path": file_path,
                "status": "scored",
                "total_score": total_score,
                "overexpose_ratio": metadata.get("overexpose_ratio"),
                "underexpose_ratio": metadata.get("underexpose_ratio"),
                "laplacian_variance": metadata.get("laplacian_variance"),
                "scene": scene,
                "scene_raw": scene_raw,
                "decision": decision,
                "decision_reasons": json.dumps(decision_reasons or [], ensure_ascii=False),
                "screening_prior": screening_prior,
                "visible_breakdown_json": json.dumps(visible_breakdown or {}, ensure_ascii=False),
                "policy_version": policy_version,
            }
        )
        self._execute(
            f"""
            INSERT OR REPLACE INTO processed
            (file_path, status, total_score, {score_value_columns},
             overexpose_ratio, underexpose_ratio, laplacian_variance, scene, scene_raw,
             decision, decision_reasons, screening_prior, visible_breakdown_json, policy_version)
            VALUES (:file_path, :status, :total_score, {score_placeholders},
                    :overexpose_ratio, :underexpose_ratio, :laplacian_variance, :scene, :scene_raw,
                    :decision, :decision_reasons, :screening_prior, :visible_breakdown_json, :policy_version)
            """,
            payload,
        )
        if signals is not None:
            self.replace_signals(file_path, signals)
        self._commit()

    def mark_done(
        self,
        file_path: str,
        total_score: float,
        star_rating: int,
        group_boosted: bool,
        scores: dict,
        metadata: dict,
        group_info: dict,
        scene: str = "other",
        scene_raw: str = "",
        decision: str | None = None,
        decision_reasons: list[str] | None = None,
        screening_prior: float | None = None,
        visible_breakdown: dict | None = None,
        policy_version: str | None = None,
        signals: list[dict] | None = None,
        commentary_group_issues: str | None = None,
        commentary_shooting: str | None = None,
        commentary_post: str | None = None,
    ):
        score_value_columns = ", ".join(_BASE_SCORE_COLUMNS)
        score_placeholders = ", ".join(f":{column}" for column in _BASE_SCORE_COLUMNS)
        payload = self._score_payload(scores)
        payload.update(
            {
                "file_path": file_path,
                "status": "done",
                "total_score": total_score,
                "star_rating": star_rating,
                "group_boosted": int(group_boosted),
                "overexpose_ratio": metadata.get("overexpose_ratio"),
                "underexpose_ratio": metadata.get("underexpose_ratio"),
                "laplacian_variance": metadata.get("laplacian_variance"),
                "group_id": group_info.get("group_id"),
                "group_rank": group_info.get("group_rank"),
                "group_size": group_info.get("group_size"),
                "scene": scene,
                "scene_raw": scene_raw,
                "decision": decision,
                "decision_reasons": json.dumps(decision_reasons or [], ensure_ascii=False),
                "screening_prior": screening_prior,
                "visible_breakdown_json": json.dumps(visible_breakdown or {}, ensure_ascii=False),
                "policy_version": policy_version,
                "commentary_group_issues": commentary_group_issues,
                "commentary_shooting": commentary_shooting,
                "commentary_post": commentary_post,
            }
        )
        self._execute(
            f"""
            INSERT OR REPLACE INTO processed
            (file_path, status, total_score, star_rating, group_boosted,
             {score_value_columns}, overexpose_ratio, underexpose_ratio, laplacian_variance,
             group_id, group_rank, group_size, scene, scene_raw,
             decision, decision_reasons, screening_prior, visible_breakdown_json, policy_version,
             commentary_group_issues, commentary_shooting, commentary_post)
            VALUES (:file_path, :status, :total_score, :star_rating, :group_boosted,
                    {score_placeholders}, :overexpose_ratio, :underexpose_ratio, :laplacian_variance,
                    :group_id, :group_rank, :group_size, :scene, :scene_raw,
                    :decision, :decision_reasons, :screening_prior, :visible_breakdown_json, :policy_version,
                    :commentary_group_issues, :commentary_shooting, :commentary_post)
            """,
            payload,
        )
        if signals is not None:
            self.replace_signals(file_path, signals)
        self._commit()

    def mark_error(self, file_path: str, error_message: str):
        self._execute(
            "INSERT OR REPLACE INTO processed (file_path, status, error_message) "
            "VALUES (:file_path, :status, :error_message)",
            {"file_path": file_path, "status": "error", "error_message": error_message},
        )
        self._commit()

    def update_commentary(self, file_path: str, group_issues: str, shooting: str, post: str):
        self._execute(
            """
            UPDATE processed SET commentary_group_issues=:issues, commentary_shooting=:shooting,
            commentary_post=:post WHERE file_path=:file_path
        """,
            {"issues": group_issues, "shooting": shooting, "post": post, "file_path": file_path},
        )
        self._commit()

    def update_commentary_batch(self, updates: list[dict]):
        if not updates:
            return
        self._executemany(
            """
            UPDATE processed
            SET commentary_group_issues=:issues,
                commentary_shooting=:shooting,
                commentary_post=:post
            WHERE file_path=:file_path
            """,
            updates,
        )
        self._commit()

    def update_total_scores_batch(self, updates: list[tuple[float, str]]):
        self._executemany("UPDATE processed SET total_score=? WHERE file_path=?", updates)
        self._commit()

    def update_rejudge_batch(self, updates: list[dict]):
        self._executemany(
            """
            UPDATE processed
            SET total_score=:total_score,
                star_rating=:star_rating,
                decision=:decision,
                decision_reasons=:decision_reasons,
                screening_prior=:screening_prior,
                visible_breakdown_json=:visible_breakdown_json,
                policy_version=:policy_version,
                group_rank=:group_rank
            WHERE file_path=:file_path
            """,
            updates,
        )
        self._commit()

    def fetch_rescore_rows(self, *, scene_filters: list[str] | None = None) -> list[sqlite3.Row]:
        query = (
            "SELECT file_path, scene, group_id, group_rank, group_size, score_exposure, score_sharpness, "
            + ", ".join(f"score_{d}" for d in VISION_DIMS)
            + " FROM processed WHERE status IN ('done','scored')"
        )
        params: list[str] = []
        if scene_filters:
            placeholders = ",".join("?" * len(scene_filters))
            query += f" AND scene IN ({placeholders})"
            params.extend(scene_filters)
        return self._execute(query, params).fetchall()

    def fetch_signal_rows(self, file_path: str | None = None) -> list[sqlite3.Row]:
        params: list[str] = []
        query = (
            "SELECT file_path, stage, signal_key, value, confidence, source, model_name, model_version "
            "FROM score_signals"
        )
        if file_path is not None:
            query += " WHERE file_path=?"
            params.append(file_path)
        query += " ORDER BY file_path, stage, signal_key"
        return self._execute(query, params).fetchall()

    def fetch_signals(self, file_path: str) -> list[dict]:
        rows = self.fetch_signal_rows(file_path)
        return [
            {
                "stage": row["stage"],
                "signal_key": row["signal_key"],
                "value": row["value"],
                "confidence": row["confidence"],
                "source": row["source"],
                "model_name": row["model_name"],
                "model_version": row["model_version"],
            }
            for row in rows
        ]

    def fetch_rewrite_rows(self) -> list[sqlite3.Row]:
        return self._execute(
            "SELECT file_path, total_score, star_rating, scene, group_id, group_rank, "
            "group_size, group_boosted, score_exposure, score_sharpness, "
            + ", ".join(f"score_{dim}" for dim in VISION_DIMS) + ", "
            "commentary_group_issues, commentary_shooting, commentary_post, "
            "decision, decision_reasons, visible_breakdown_json "
            "FROM processed WHERE status='done'"
        ).fetchall()

    def fetch_done_commentary_rows(self) -> list[sqlite3.Row]:
        return self._execute(
            "SELECT file_path, total_score, scene, scene_raw, decision, group_id, group_rank, "
            "group_size, score_exposure, score_sharpness, "
            + ", ".join(f"score_{dim}" for dim in VISION_DIMS) + ", "
            "visible_breakdown_json, commentary_group_issues, commentary_shooting, commentary_post "
            "FROM processed WHERE status='done' ORDER BY group_id, group_rank, file_path"
        ).fetchall()

    def fetch_ai_file_paths(self) -> list[str]:
        rows = self._execute(
            "SELECT file_path FROM processed WHERE status IN ('done', 'scored', 'error') ORDER BY file_path"
        ).fetchall()
        return [row["file_path"] for row in rows]

    def clear_ai_judgement(self) -> dict[str, int]:
        processed_count = self._execute("SELECT COUNT(*) FROM processed").fetchone()[0]
        signal_count = self._execute("SELECT COUNT(*) FROM score_signals").fetchone()[0]
        self._execute("DELETE FROM processed")
        self._execute("DELETE FROM score_signals")
        self._commit()
        return {
            "processed_rows_deleted": processed_count,
            "signal_rows_deleted": signal_count,
        }

    def scan_distribution(self) -> dict[str, list[tuple[str, int]]]:
        rows = self._execute(
            "SELECT scene, scene_raw, COUNT(*) as cnt FROM processed "
            "WHERE scene IS NOT NULL GROUP BY scene, scene_raw ORDER BY scene, cnt DESC"
        ).fetchall()
        grouped: dict[str, list[tuple[str, int]]] = {}
        for row in rows:
            grouped.setdefault(row["scene"], []).append((row["scene_raw"], row["cnt"]))
        return grouped

    def remap_scene(self, *, from_raw: str, to_scene: str) -> int:
        cur = self._execute("UPDATE processed SET scene=? WHERE scene_raw=?", (to_scene, from_raw))
        self._commit()
        return cur.rowcount

    def suggest_scene_raws(self, *, limit: int, min_count: int) -> list[tuple[str, int]]:
        rows = self._execute(
            "SELECT scene_raw, COUNT(*) as cnt FROM processed "
            "WHERE status IN ('done', 'scored') AND scene='other' AND TRIM(COALESCE(scene_raw, '')) != '' "
            "GROUP BY scene_raw ORDER BY cnt DESC, scene_raw ASC"
        ).fetchall()
        suggestions = []
        for row in rows:
            if row["cnt"] < min_count:
                continue
            suggestions.append((row["scene_raw"], row["cnt"]))
            if len(suggestions) >= limit:
                break
        return suggestions

    def fix_db(self) -> dict[str, int]:
        r1 = self._execute(
            "UPDATE processed SET star_rating = ROUND(total_score / 2.0) "
            "WHERE star_rating IS NULL AND total_score IS NOT NULL"
        )
        r2 = self._execute(
            "UPDATE processed SET group_rank=1, group_size=1 "
            "WHERE group_rank IS NULL AND status='done'"
        )
        migration_count = 0
        for old_scene, new_scene in LEGACY_SCENE_MIGRATIONS.items():
            cur = self._execute(
                "UPDATE processed SET scene=? WHERE LOWER(TRIM(scene))=LOWER(TRIM(?))",
                (new_scene, old_scene),
            )
            migration_count += cur.rowcount

        clearable_scene_names = sorted(set(SCENE_LIST) | set(LEGACY_SCENE_MIGRATIONS))
        scene_placeholders = ",".join("?" * len(clearable_scene_names))
        scene_label_placeholders = ",".join("?" * len(SCENE_LABELS))
        r3 = self._execute(
            f"UPDATE processed SET scene_raw='' "
            f"WHERE LOWER(TRIM(scene_raw)) IN ({scene_placeholders}) "
            f"OR TRIM(scene_raw) IN ({scene_label_placeholders})",
            [scene.lower() for scene in clearable_scene_names] + list(SCENE_LABELS.values()),
        )
        self._commit()
        return {
            "star_rating_repaired": r1.rowcount,
            "group_info_repaired": r2.rowcount,
            "scene_migrated": migration_count,
            "bad_scene_raw_cleared": r3.rowcount,
        }

    @staticmethod
    def compute_star_rating(total_score: float | None) -> int | None:
        if total_score is None:
            return None
        return int(float(total_score) / 2 + 0.5)

    @staticmethod
    def _score_payload(scores: dict) -> dict:
        payload = {
            "score_exposure": scores.get("exposure"),
            "score_sharpness": scores.get("sharpness"),
        }
        for dim in VISION_DIMS:
            payload[f"score_{dim}"] = scores.get(dim)
        return payload

    def replace_signals(self, file_path: str, signals: list[dict]) -> None:
        self._execute("DELETE FROM score_signals WHERE file_path=?", (file_path,))
        rows = []
        for signal in signals:
            rows.append(
                (
                    file_path,
                    signal["stage"],
                    signal["signal_key"],
                    signal.get("value"),
                    signal.get("confidence"),
                    signal.get("source"),
                    signal.get("model_name"),
                    signal.get("model_version"),
                )
            )
        if rows:
            self._executemany(
                """
                INSERT OR REPLACE INTO score_signals
                (file_path, stage, signal_key, value, confidence, source, model_name, model_version)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                rows,
            )

    @staticmethod
    def legacy_scores_to_signals(row: sqlite3.Row) -> list[dict]:
        focus_source = [value for value in [row["score_sharpness"], row["score_clarity"]] if value is not None]
        focus_integrity = round(sum(focus_source) / len(focus_source), 2) if focus_source else None
        signals: list[dict] = []
        def add(stage: str, signal_key: str, value: float | None, source: str) -> None:
            if value is None:
                return
            signals.append(
                {
                    "stage": stage,
                    "signal_key": signal_key,
                    "value": float(value),
                    "confidence": 1.0,
                    "source": source,
                }
            )

        add("technical", "technical_quality", SQLiteProcessedRepository._average_known(
            [row["score_exposure"], focus_integrity, row["score_clarity"], row["score_clarity"]]
        ), "legacy")
        add("aggregate", "subject_focus", focus_integrity, "legacy")
        add("screening", "screening_prior", row["score_clarity"] or row["score_sharpness"], "legacy")
        for public_dim, legacy_dim in AESTHETIC_SOURCE_MAP.items():
            add("aesthetic", public_dim, row[f"score_{legacy_dim}"], "legacy")
        return signals

    @staticmethod
    def _average_known(values: list[float | None]) -> float | None:
        known = [float(value) for value in values if value is not None]
        if not known:
            return None
        return round(sum(known) / len(known), 2)
