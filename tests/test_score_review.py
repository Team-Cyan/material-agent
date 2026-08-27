import io
import json
import os
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from material_agent.commands.score_review import build_score_review
from material_agent.domain.scoring_engine import RawFrame


def _seed_runtime_database(path: Path, photos: list[Path]) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY, kind TEXT, input_root TEXT, config_snapshot TEXT,
            status TEXT, created_at TEXT, finished_at TEXT
        );
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY, session_id TEXT, type TEXT, stage TEXT, status TEXT,
            summary_json TEXT, started_at TEXT, finished_at TEXT
        );
        CREATE TABLE job_files (
            id TEXT PRIMARY KEY, job_id TEXT, file_path TEXT, group_id TEXT, rank INTEGER,
            status TEXT, score_total REAL, scene TEXT, scene_raw TEXT
        );
        CREATE TABLE artifacts (
            id TEXT PRIMARY KEY, job_id TEXT, job_file_id TEXT, kind TEXT,
            uri TEXT, metadata_json TEXT, created_at TEXT
        );
        """
    )
    config = {
        "preview": {"prefer_embedded": True, "max_size": 1024, "jpeg_quality": 85},
        "grouping": {"enabled": True},
    }
    connection.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?)",
        ("session", "review", str(photos[0].parent), json.dumps(config), "finished", "1", "2"),
    )
    connection.execute(
        "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)",
        ("job", "session", "review_photos", "finalize", "finished", "{}", "1", "2"),
    )
    for index, photo in enumerate(photos):
        file_id = f"file-{index}"
        connection.execute(
            "INSERT INTO job_files VALUES (?,?,?,?,?,?,?,?,?)",
            (
                file_id,
                "job",
                str(photo),
                "group-a" if index < 2 else f"group-{index}",
                index + 1,
                "done",
                float(index + 1),
                "people" if index % 2 == 0 else "other",
                "fixture",
            ),
        )
        connection.execute(
            "INSERT INTO artifacts VALUES (?,?,?,?,?,?,?)",
            (
                f"artifact-{index}",
                "job",
                file_id,
                "score_payload",
                "memory://score",
                json.dumps(
                    {
                        "scores": {"aesthetic": float(index + 1)},
                        "decision": "keep" if index > 2 else "review",
                        "meta": {"aesthetic": {"runtime": "openvino", "device": "CPU"}},
                    }
                ),
                "1",
            ),
        )
    connection.commit()
    connection.close()


def test_build_score_review_preserves_reconstructed_scoring_preview(
    tmp_path: Path, monkeypatch
) -> None:
    input_root = tmp_path / "photos"
    input_root.mkdir()
    photos = []
    for index in range(8):
        photo = input_root / f"{index:02d}.ARW"
        photo.write_bytes(b"fixture")
        photos.append(photo)
    database = tmp_path / "state.db"
    _seed_runtime_database(database, photos)

    preview = tmp_path / "preview.jpg"
    Image.new("RGB", (32, 24), (200, 50, 25)).save(preview, "JPEG")
    preview_bytes = preview.read_bytes()
    monkeypatch.setattr(
        "material_agent.commands.score_review.decode_raw",
        lambda *_args, **_kwargs: RawFrame(
            jpeg_bytes=preview_bytes,
            gray=None,
            preview_source="embedded",
            original_size=(6000, 4000),
            preview_size=(32, 24),
        ),
    )

    output = tmp_path / "review"
    result = build_score_review(
        input_root=input_root,
        database_path=database,
        output_root=output,
        sample_count=6,
    )

    assert result["schema"] == "material-agent-score-review-v2"
    assert result["sample_count_rendered"] == 6
    assert result["distribution"]["groups"]["multi_photo_count"] == 1
    assert result["execution"]["runtimes"] == {"openvino": 8}
    assert result["config"]["grouping"] == {"enabled": True}
    assert "historical JPEG byte identity cannot be proven" in result["image_note"]
    assert (output / "contact-sheet.jpg").is_file()
    assert (output / "review.json").is_file()
    assert (output / "samples" / "01.jpg").read_bytes() == preview_bytes
    assert os.stat(output).st_mode & 0o777 == 0o700
    assert os.stat(output / "review.json").st_mode & 0o777 == 0o600
    assert os.stat(output / "samples" / "01.jpg").st_mode & 0o777 == 0o600


def test_build_score_review_rejects_database_path_outside_input_root(
    tmp_path: Path, monkeypatch
) -> None:
    input_root = tmp_path / "photos"
    input_root.mkdir()
    outside = tmp_path / "outside.ARW"
    outside.write_bytes(b"fixture")
    photos = [outside, outside, outside, outside, outside, outside]
    database = tmp_path / "state.db"
    _seed_runtime_database(database, photos)
    monkeypatch.setattr(
        "material_agent.commands.score_review.decode_raw",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("decode must not run")),
    )

    result = build_score_review(
        input_root=input_root,
        database_path=database,
        output_root=tmp_path / "review",
        sample_count=6,
    )

    assert result["sample_count_rendered"] == 0
    assert all("escapes input root" in sample["image_error"] for sample in result["samples"])


def test_score_distribution_treats_missing_group_ids_as_singletons(tmp_path: Path, monkeypatch) -> None:
    input_root = tmp_path / "photos"
    input_root.mkdir()
    photos = []
    for index in range(6):
        photo = input_root / f"{index:02d}.ARW"
        photo.write_bytes(b"fixture")
        photos.append(photo)
    database = tmp_path / "state.db"
    _seed_runtime_database(database, photos)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE job_files SET group_id=NULL")
    preview_bytes = io.BytesIO()
    Image.new("RGB", (8, 8), (20, 30, 40)).save(preview_bytes, "JPEG")
    monkeypatch.setattr(
        "material_agent.commands.score_review.decode_raw",
        lambda *_args, **_kwargs: RawFrame(
            jpeg_bytes=preview_bytes.getvalue(),
            gray=None,
            preview_source="embedded",
            original_size=(8, 8),
            preview_size=(8, 8),
        ),
    )

    result = build_score_review(
        input_root=input_root,
        database_path=database,
        output_root=tmp_path / "review",
        sample_count=6,
    )

    assert result["distribution"]["groups"] == {
        "count": 6,
        "singleton_count": 6,
        "multi_photo_count": 0,
        "maximum_size": 1,
    }


def test_build_score_review_rejects_output_inside_input_root(tmp_path: Path) -> None:
    input_root = tmp_path / "photos"
    input_root.mkdir()
    photos = []
    for index in range(6):
        photo = input_root / f"{index:02d}.ARW"
        photo.write_bytes(b"fixture")
        photos.append(photo)
    database = tmp_path / "state.db"
    _seed_runtime_database(database, photos)

    with pytest.raises(ValueError, match="outside the photo input root"):
        build_score_review(
            input_root=input_root,
            database_path=database,
            output_root=input_root / "review",
            sample_count=6,
        )
