import sqlite3

from material_agent.utils.runtime_paths import build_runtime_paths
from material_agent.utils.runtime_paths import ensure_runtime_paths


def test_runtime_paths_use_hidden_workdir(tmp_path):
    paths = build_runtime_paths(tmp_path)

    assert paths.work_dir == tmp_path / ".material-agent"
    assert paths.db_path == tmp_path / ".material-agent" / "state.db"
    assert paths.log_path == tmp_path / ".material-agent" / "run.log"


def test_ensure_runtime_paths_migrates_legacy_db_and_sidecars(tmp_path):
    legacy_db_path = tmp_path / "material-agent.db"
    with sqlite3.connect(legacy_db_path) as conn:
        conn.execute("CREATE TABLE processed (file_path TEXT PRIMARY KEY, status TEXT)")
        conn.execute("INSERT INTO processed (file_path, status) VALUES ('/a.arw', 'done')")
        conn.commit()
    legacy_db_path.with_name("material-agent.db-wal").write_bytes(b"legacy wal")
    legacy_db_path.with_name("material-agent.db-shm").write_bytes(b"legacy shm")

    paths = ensure_runtime_paths(tmp_path)

    assert paths.db_path.exists()
    assert not legacy_db_path.exists()
    assert not legacy_db_path.with_name("material-agent.db-wal").exists()
    assert not legacy_db_path.with_name("material-agent.db-shm").exists()
    assert paths.db_path.with_name("state.db-wal").exists()
    assert paths.db_path.with_name("state.db-shm").exists()
    with sqlite3.connect(paths.db_path) as conn:
        row = conn.execute("SELECT status FROM processed WHERE file_path='/a.arw'").fetchone()
    assert row[0] == "done"
