from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


class AestheticLabelStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()

    def import_file(self, path: str | Path, *, holdout_percent: int = 20) -> dict[str, Any]:
        if not 0 <= holdout_percent <= 50:
            raise ValueError("holdout_percent must be between 0 and 50")
        source_path = Path(path).expanduser().resolve()
        payload = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("label file must contain an items list")
        normalized = [
            _normalize_item(item, index=index, holdout_percent=holdout_percent)
            for index, item in enumerate(payload["items"])
        ]
        self._ensure_parent()
        with sqlite3.connect(self.database_path) as connection:
            _ensure_schema(connection)
            before = connection.total_changes
            connection.executemany(
                """
                INSERT INTO aesthetic_labels (
                    path, target, raw_score, human_score, split, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    target=excluded.target,
                    raw_score=excluded.raw_score,
                    human_score=excluded.human_score,
                    split=excluded.split,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        item["path"],
                        item["target"],
                        item["raw_score"],
                        item["human_score"],
                        item["split"],
                        str(source_path),
                        datetime.now(UTC).isoformat(),
                    )
                    for item in normalized
                ],
            )
            changed = connection.total_changes - before
            connection.commit()
        return {"input_items": len(normalized), "changed_rows": changed, **self.stats()}

    def export_file(self, path: str | Path, *, split: str | None = None) -> dict[str, Any]:
        if split not in {None, "train", "holdout"}:
            raise ValueError("split must be train or holdout")
        rows = self.items(split=split)
        output_path = Path(path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            yaml.safe_dump({"items": rows}, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return {"output": str(output_path), "items": len(rows), "split": split or "all"}

    def items(self, *, split: str | None = None) -> list[dict[str, Any]]:
        if not self.database_path.exists():
            return []
        query = "SELECT path, target, raw_score, human_score, split FROM aesthetic_labels"
        arguments: tuple[str, ...] = ()
        if split:
            query += " WHERE split = ?"
            arguments = (split,)
        query += " ORDER BY target, path"
        with sqlite3.connect(self.database_path) as connection:
            _ensure_schema(connection)
            return [
                {
                    "path": row[0],
                    "target": row[1],
                    "raw_score": row[2],
                    "human_score": row[3],
                    "split": row[4],
                }
                for row in connection.execute(query, arguments)
            ]

    def stats(self) -> dict[str, Any]:
        rows = self.items()
        targets: dict[str, dict[str, int]] = {}
        for row in rows:
            target = targets.setdefault(row["target"], {"train": 0, "holdout": 0, "total": 0})
            target[row["split"]] += 1
            target["total"] += 1
        return {
            "database": str(self.database_path),
            "total": len(rows),
            "train": sum(row["split"] == "train" for row in rows),
            "holdout": sum(row["split"] == "holdout" for row in rows),
            "targets": targets,
        }

    def _ensure_parent(self) -> None:
        if self.database_path.is_symlink():
            raise ValueError(f"label database must not be a symbolic link: {self.database_path}")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS aesthetic_labels (
            path TEXT PRIMARY KEY,
            target TEXT NOT NULL,
            raw_score REAL NOT NULL CHECK(raw_score BETWEEN 1 AND 10),
            human_score REAL NOT NULL CHECK(human_score BETWEEN 1 AND 10),
            split TEXT NOT NULL CHECK(split IN ('train', 'holdout')),
            source TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL
        )
        """
    )


def _normalize_item(item: object, *, index: int, holdout_percent: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"items[{index}] must be a mapping")
    path = str(item.get("path", "")).strip()
    target = str(item.get("target", "")).strip().lower()
    if not path or not target:
        raise ValueError(f"items[{index}] requires path and target")
    raw_score = _score(item.get("raw_score"), f"items[{index}].raw_score")
    human_value = item.get("human_score")
    if human_value is None and item.get("human_rating") is not None:
        rating = _score(item.get("human_rating"), f"items[{index}].human_rating", maximum=5)
        human_value = rating * 2.0
    human_score = _score(human_value, f"items[{index}].human_score")
    split = str(item.get("split", "")).strip().lower()
    if not split:
        bucket = int(hashlib.sha256(path.encode("utf-8")).hexdigest()[:8], 16) % 100
        split = "holdout" if bucket < holdout_percent else "train"
    if split not in {"train", "holdout"}:
        raise ValueError(f"items[{index}].split must be train or holdout")
    return {
        "path": path,
        "target": target,
        "raw_score": raw_score,
        "human_score": human_score,
        "split": split,
    }


def _score(value: object, name: str, *, maximum: float = 10.0) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric")
    numeric = float(value)
    if not 1.0 <= numeric <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum:g}")
    return numeric
