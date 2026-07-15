import json
import sqlite3
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from material_agent.app.web_service import (
    MaterialWebServer,
    WebLibraryRepository,
    WebTaskManager,
    _restore_redacted,
)


def test_library_index_bootstraps_runtime_schema_and_lists_unscored_files(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "one.ARW").write_bytes(b"raw")
    (photos / "two.jpg").write_bytes(b"jpeg")
    repository = WebLibraryRepository(tmp_path / "config" / "state.db", photos)

    assert repository.summary() == {
        "indexed": 0,
        "scored": 0,
        "score_records": 0,
        "errors": 0,
        "average_score": None,
        "scenes": [],
    }
    result = repository.refresh_index(["ARW", "JPG"])
    listing = repository.list_items({"page_size": ["10"]})

    assert result["indexed"] == 2
    assert listing["total"] == 2
    assert {item["relative_path"] for item in listing["items"]} == {"one.ARW", "two.jpg"}
    assert all(item["score_total"] is None for item in listing["items"])


def test_library_returns_latest_complete_score_payload(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    source = photos / "portrait.ARW"
    source.write_bytes(b"raw")
    db_path = tmp_path / "config" / "state.db"
    repository = WebLibraryRepository(db_path, photos)
    repository.refresh_index(["ARW"])
    payload = {
        "decision": "keep",
        "star_rating": 4,
        "tags": ["person", "portrait"],
        "description": "sharp portrait",
        "meta": {"subject_focus": {"primary_target": {"label": "person"}}},
    }
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO sessions(id, kind, input_root, config_snapshot, status) "
            "VALUES('session', 'review', ?, '{}', 'finished')",
            (str(photos),),
        )
        connection.execute(
            "INSERT INTO jobs(id, session_id, type, stage, status) "
            "VALUES('job', 'session', 'review', 'score', 'finished')"
        )
        connection.execute(
            "INSERT INTO job_files(id, job_id, file_path, status, score_total, scene) "
            "VALUES('file', 'job', ?, 'finished', 7.4, 'portrait')",
            (str(source.resolve()),),
        )
        connection.execute(
            "INSERT INTO artifacts(id, job_id, job_file_id, kind, uri, metadata_json) "
            "VALUES('artifact', 'job', 'file', 'score_payload', 'db://score', ?)",
            (json.dumps(payload),),
        )

    listing = repository.list_items({"scored": ["yes"]})
    detail = repository.detail(listing["items"][0]["id"])

    assert listing["items"][0]["target"] == "person"
    assert listing["items"][0]["decision"] == "keep"
    assert detail["score"] == payload
    assert repository.summary()["average_score"] == 7.4


def test_redacted_config_values_preserve_existing_secrets():
    existing = {"api": {"token": "secret", "timeout": 30}, "items": [{"password": "p"}]}
    proposed = {
        "api": {"token": "[REDACTED]", "timeout": 45},
        "items": [{"password": "[REDACTED]"}],
    }
    assert _restore_redacted(existing, proposed) == {
        "api": {"token": "secret", "timeout": 45},
        "items": [{"password": "p"}],
    }


def test_web_tasks_are_always_dry_run_and_can_remove_sample_limit(tmp_path, monkeypatch):
    photos = tmp_path / "photos"
    photos.mkdir()
    config_path = tmp_path / "config.yaml"
    config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    config["review_pipeline"]["max_files"] = 128
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    captured = {}

    class FakeProcess:
        pid = 12345

        def __init__(self, command, **_kwargs):
            captured["command"] = command

        def wait(self):
            return 0

        def poll(self):
            return None

    monkeypatch.setattr("material_agent.app.web_service.subprocess.Popen", FakeProcess)
    manager = WebTaskManager(
        input_root=photos,
        config_path=config_path,
        work_dir=tmp_path / "work",
    )
    task = manager.start(max_files=None, reprocess=False, no_visual_merge=False)

    assert "--dry-run" in captured["command"]
    task_config = yaml.safe_load(Path(task["config_path"]).read_text(encoding="utf-8"))
    assert "max_files" not in task_config["review_pipeline"]

def test_web_api_requires_token_but_static_shell_remains_loadable(tmp_path):
    server = MaterialWebServer(
        ("127.0.0.1", 0),
        library=MagicMock(),
        tasks=MagicMock(),
        model_service=MagicMock(),
        config_path=tmp_path / "config.yaml",
        token="secret",
        thumbnail_dir=tmp_path / "thumbs",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert b"material-agent" in urllib.request.urlopen(base + "/").read()
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + "/health")
        assert error.value.code == 401
        request = urllib.request.Request(
            base + "/health", headers={"Authorization": "Bearer secret"}
        )
        assert json.loads(urllib.request.urlopen(request).read()) == {"status": "ok"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
