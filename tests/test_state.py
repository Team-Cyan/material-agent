import json
import sqlite3
import tempfile
import threading
from pathlib import Path

from material_agent.adapters.state.processed_sqlite import SQLiteProcessedRepository
from material_agent.utils.state import State


def test_state_has_scene_columns():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        cols = [r[1] for r in s.conn.execute("PRAGMA table_info(processed)").fetchall()]
        assert "scene" in cols
        assert "scene_raw" in cols
        assert "decision" in cols
        assert "decision_reasons" in cols
        assert "screening_prior" in cols
        assert "visible_breakdown_json" in cols
        assert "policy_version" in cols
        assert "score_clarity" in cols
        assert "score_lighting" in cols
        assert "score_depth" in cols
        assert "score_mood" in cols
        assert "score_metadata_json" in cols
        assert "score_metadata_version" in cols
        assert "file_size" in cols
        assert "mtime_ns" in cols
        assert "score_cache_key" in cols
        assert "xmp_payload_json" in cols
        for table in ("exif_cache", "visual_hash_cache"):
            cache_cols = {
                row[1] for row in s.conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            assert {"file_size", "mtime_ns"} <= cache_cols
        score_signal_tables = [
            row[0]
            for row in s.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='score_signals'"
            ).fetchall()
        ]
        assert score_signal_tables == ["score_signals"]


def test_legacy_state_wrapper_uses_processed_sqlite_adapter():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        assert isinstance(s, SQLiteProcessedRepository)
        s.close()


def test_state_mark_scored_with_scene():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.mark_scored(
            "/foo/bar.arw",
            total_score=7.5,
            scores={"composition": 8.0, "clarity": 7.0},
            metadata={},
            scene="people",
            scene_raw="舞台上的人物",
        )
        row = s.conn.execute(
            "SELECT scene, scene_raw, score_clarity FROM processed WHERE file_path='/foo/bar.arw'"
        ).fetchone()
        assert row[0] == "people"
        assert row[1] == "舞台上的人物"
        assert row[2] == 7.0


def test_state_mark_done_with_scene():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.mark_done(
            "/foo/bar.arw",
            total_score=7.5,
            star_rating=4,
            group_boosted=False,
            scores={"clarity": 9.0, "mood": 6.0},
            metadata={},
            group_info={},
            scene="animals",
            scene_raw="飞行中的鸟",
        )
        row = s.conn.execute(
            "SELECT scene, scene_raw, score_clarity, score_mood FROM processed WHERE file_path='/foo/bar.arw'"
        ).fetchone()
        assert row[0] == "animals"
        assert row[1] == "飞行中的鸟"
        assert row[2] == 9.0
        assert row[3] == 6.0


def test_state_mark_done_persists_commentary_fields_in_final_write():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.mark_done(
            "/foo/bar.arw",
            total_score=7.5,
            star_rating=4,
            group_boosted=False,
            scores={"clarity": 9.0},
            metadata={},
            group_info={},
            commentary_group_issues="整体偏暗",
            commentary_shooting="拍摄时补一点面光",
            commentary_post="后期把阴影提一点",
        )
        row = s.conn.execute(
            "SELECT commentary_group_issues, commentary_shooting, commentary_post "
            "FROM processed WHERE file_path='/foo/bar.arw'"
        ).fetchone()
        assert tuple(row) == (
            "整体偏暗",
            "拍摄时补一点面光",
            "后期把阴影提一点",
        )


def test_state_mark_done_persists_xmp_payload_for_provenance_safe_reset(tmp_path):
    owned_photo = tmp_path / "owned.ARW"
    legacy_photo = tmp_path / "legacy.ARW"
    owned_photo.write_bytes(b"owned")
    legacy_photo.write_bytes(b"legacy")
    expected_payload = {
        "rating": 4,
        "instructions": "agent instructions",
        "description": "agent description",
        "ignored": "not an owned scalar field",
    }

    with State(tmp_path) as state:
        state.mark_done(
            str(owned_photo),
            total_score=7.5,
            star_rating=4,
            group_boosted=False,
            scores={},
            metadata={},
            group_info={},
            xmp_payload=expected_payload,
        )
        state.mark_done(
            str(legacy_photo),
            total_score=6.0,
            star_rating=3,
            group_boosted=False,
            scores={},
            metadata={},
            group_info={},
        )

        stored = state.conn.execute(
            "SELECT xmp_payload_json FROM processed WHERE file_path=?", (str(owned_photo),)
        ).fetchone()[0]
        assert json.loads(stored) == {
            "rating": 4,
            "instructions": "agent instructions",
            "description": "agent description",
        }
        assert state.fetch_ai_reset_rows() == [
            {"file_path": str(legacy_photo), "xmp_payload": None},
            {
                "file_path": str(owned_photo),
                "xmp_payload": {
                    "rating": 4,
                    "instructions": "agent instructions",
                    "description": "agent description",
                },
            },
        ]


def test_state_mark_done_persists_layered_summary_and_signals():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.mark_done(
            "/foo/bar.arw",
            total_score=8.2,
            star_rating=4,
            group_boosted=False,
            scores={"clarity": 8.0, "composition": 8.5},
            metadata={},
            group_info={"group_id": "g1", "group_rank": 1, "group_size": 2},
            scene="people",
            scene_raw="舞台上的人物",
            decision="keep",
            decision_reasons=["sharp enough", "best in burst"],
            screening_prior=7.4,
            visible_breakdown={
                "technical_quality": 7.8,
                "subject_focus": 8.1,
                "composition": 8.5,
            },
            policy_version="layered-v1",
            signals=[
                {
                    "stage": "technical",
                    "signal_key": "focus_integrity",
                    "value": 8.1,
                    "confidence": 0.9,
                    "source": "cpu",
                },
                {
                    "stage": "aesthetic",
                    "signal_key": "subject_moment",
                    "value": 8.4,
                    "confidence": 0.8,
                    "source": "vision",
                },
            ],
        )

        row = s.conn.execute(
            "SELECT decision, decision_reasons, screening_prior, visible_breakdown_json, policy_version "
            "FROM processed WHERE file_path='/foo/bar.arw'"
        ).fetchone()
        assert row[0] == "keep"
        assert row[1] == '["sharp enough", "best in burst"]'
        assert abs(row[2] - 7.4) < 0.001
        assert '"technical_quality": 7.8' in row[3]
        assert row[4] == "layered-v1"

        signal_rows = s.conn.execute(
            "SELECT stage, signal_key, value, confidence, source FROM score_signals "
            "WHERE file_path='/foo/bar.arw' ORDER BY stage, signal_key"
        ).fetchall()
        assert [tuple(row) for row in signal_rows] == [
            ("aesthetic", "subject_moment", 8.4, 0.8, "vision"),
            ("technical", "focus_integrity", 8.1, 0.9, "cpu"),
        ]


def test_state_mark_and_check_done():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        assert not s.is_done("/foo/bar.arw")
        s.mark_done(
            "/foo/bar.arw",
            total_score=7.5,
            star_rating=4,
            group_boosted=False,
            scores={},
            metadata={},
            group_info={},
        )
        assert s.is_done("/foo/bar.arw")


def test_state_mark_error():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.mark_error("/foo/bad.arw", "decode failed")
        assert not s.is_done("/foo/bad.arw")


def test_state_reprocess_flag():
    with tempfile.TemporaryDirectory() as d:
        s = State(d, reprocess=True)
        s.mark_done(
            "/foo/bar.arw",
            total_score=5.0,
            star_rating=3,
            group_boosted=False,
            scores={},
            metadata={},
            group_info={},
        )
        assert not s.is_done("/foo/bar.arw")  # reprocess=True 时始终返回 False
        s.mark_scored("/foo/scored.arw", total_score=6.0, scores={}, metadata={})
        assert not s.is_scored("/foo/scored.arw")
        assert s.get_scored("/foo/scored.arw") is None


# ---------------------------------------------------------------------------
# New regression tests
# ---------------------------------------------------------------------------


def test_get_scored_round_trip():
    """mark_scored followed by get_scored should return all stored values."""
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        scores = {
            "exposure": 7.5,
            "sharpness": 6.0,
            "subject": 9.0,
            "composition": 8.0,
            "lighting": 7.0,
            "color": 7.0,
            "clarity": 8.5,
            "depth": 4.0,
            "mood": 5.5,
        }
        metadata = {
            "overexpose_ratio": 0.01,
            "underexpose_ratio": 0.05,
            "laplacian_variance": 350.2,
            "preview_source": "embedded",
            "runtime": "openvino:GPU.0",
            "embedding": {
                "model_name": "dinov3-vits16",
                "device": "GPU.0",
                "vector": [0.1, 0.2],
            },
            "_embedding_vector": [0.3, 0.4],
        }
        s.mark_scored(
            "/test/photo.arw",
            total_score=7.8,
            scores=scores,
            metadata=metadata,
            scene="people",
            scene_raw="看向镜头的人物",
        )
        result = s.get_scored("/test/photo.arw")
        assert result is not None
        assert abs(result["total"] - 7.8) < 0.001
        assert result["scene"] == "people"
        assert result["scene_raw"] == "看向镜头的人物"
        for key in scores:
            assert abs(result["scores"][key] - scores[key]) < 0.001
        assert abs(result["meta"]["overexpose_ratio"] - 0.01) < 0.001
        assert abs(result["meta"]["laplacian_variance"] - 350.2) < 0.001
        assert result["meta"]["preview_source"] == "embedded"
        assert result["meta"]["runtime"] == "openvino:GPU.0"
        assert result["meta"]["embedding"] == {
            "model_name": "dinov3-vits16",
            "device": "GPU.0",
        }
        assert "_embedding_vector" not in result["meta"]
        metadata_row = s.conn.execute(
            "SELECT score_metadata_json, score_metadata_version FROM processed "
            "WHERE file_path='/test/photo.arw'"
        ).fetchone()
        assert metadata_row["score_metadata_version"] == 1
        stored_metadata = json.loads(metadata_row["score_metadata_json"])
        assert "_embedding_vector" not in stored_metadata
        assert "vector" not in stored_metadata["embedding"]


def test_get_cached_score_payload_loads_done_result_with_group_state(tmp_path):
    photo = tmp_path / "done.ARW"
    photo.write_bytes(b"raw")
    with State(tmp_path, score_cache_key="policy-a") as state:
        state.mark_done(
            str(photo),
            total_score=8.2,
            star_rating=4,
            group_boosted=True,
            scores={"composition": 8.2},
            metadata={"runtime": "openvino:GPU.0"},
            group_info={"group_id": "g1", "group_rank": 2, "group_size": 3},
            scene="people",
            commentary_post="post",
        )

        payload = state.get_cached_score_payload(str(photo))

        assert payload is not None
        assert payload["status"] == "done"
        assert payload["score_total"] == 8.2
        assert payload["star_rating"] == 4
        assert payload["boosted"] is True
        assert payload["meta"] == {"runtime": "openvino:GPU.0"}
        assert payload["group_info"] == {
            "group_id": "g1",
            "group_rank": 2,
            "group_size": 3,
        }
        assert payload["commentary_post"] == "post"
        assert state.get_scored(str(photo)) is None


def test_get_scored_returns_none_for_done_file():
    """get_scored must return None for a file with status='done' (not 'scored')."""
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.mark_done(
            "/foo/done.arw",
            total_score=8.0,
            star_rating=4,
            group_boosted=False,
            scores={"composition": 8.0},
            metadata={},
            group_info={"group_id": "g1", "group_rank": 1, "group_size": 1},
            scene="other",
            scene_raw="繁忙路口",
        )
        assert s.get_scored("/foo/done.arw") is None


def test_get_scored_returns_none_for_unknown():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        assert s.get_scored("/nonexistent/file.arw") is None


def test_is_scored_true_only_for_scored_status():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        assert not s.is_scored("/foo/bar.arw")
        s.mark_scored("/foo/bar.arw", total_score=5.0, scores={}, metadata={})
        assert s.is_scored("/foo/bar.arw")
        # After mark_done the status changes to 'done' → is_scored should be False
        s.mark_done(
            "/foo/bar.arw",
            total_score=5.0,
            star_rating=3,
            group_boosted=False,
            scores={},
            metadata={},
            group_info={},
        )
        assert not s.is_scored("/foo/bar.arw")


def test_state_context_manager_closes_connection():
    """State used as context manager should close the connection on exit."""
    with tempfile.TemporaryDirectory() as d:
        with State(d) as s:
            s.mark_error("/x.arw", "test")
        # After exit, further operations should raise
        import pytest

        with pytest.raises(Exception):
            s.conn.execute("SELECT 1")


def test_state_wal_mode_enabled():
    """State should enable WAL journal mode for better concurrency."""
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        assert s.db_path == Path(d) / ".material-agent" / "state.db"
        row = s.conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"
        s.close()


def test_state_accepts_explicit_db_file_path():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "custom.db"
        with SQLiteProcessedRepository(db_path) as repository:
            assert repository.db_path == db_path
            assert db_path.exists()


def test_state_adopts_legacy_root_db_for_directory_input():
    with tempfile.TemporaryDirectory() as d:
        legacy_db_path = Path(d) / "material-agent.db"
        with sqlite3.connect(legacy_db_path) as conn:
            conn.execute("CREATE TABLE processed (file_path TEXT PRIMARY KEY, status TEXT)")
            conn.execute(
                "INSERT INTO processed (file_path, status) VALUES ('/foo/bar.arw', 'done')"
            )
            conn.commit()

        with State(d) as s:
            assert s.db_path == Path(d) / ".material-agent" / "state.db"
            assert s.is_done("/foo/bar.arw")

        assert not legacy_db_path.exists()
        assert (Path(d) / ".material-agent" / "state.db").exists()


def test_state_recovers_from_orphaned_wal_and_shm_files():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / ".material-agent" / "state.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.with_name("state.db-wal").write_bytes(b"stale wal")
        db_path.with_name("state.db-shm").write_bytes(b"stale shm")

        with State(d) as s:
            assert s.get_exif_cache(["/foo/bar.arw"]) == {}

        assert db_path.exists()
        assert not db_path.with_name("state.db-wal").exists()
        assert not db_path.with_name("state.db-shm").exists()


def test_state_retries_after_disk_io_error_and_cleans_sidecars(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / ".material-agent" / "state.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        wal_path = db_path.with_name("state.db-wal")
        shm_path = db_path.with_name("state.db-shm")

        s = State(d)
        wal_path.write_bytes(b"stale wal")
        shm_path.write_bytes(b"stale shm")

        original_execute_once = s._execute_once
        seen = {"raised": False}

        def flaky_execute(sql: str, params=()):
            if not seen["raised"] and "FROM exif_cache" in sql:
                seen["raised"] = True
                raise sqlite3.OperationalError("disk I/O error")
            return original_execute_once(sql, params)

        monkeypatch.setattr(s, "_execute_once", flaky_execute)

        assert s.get_exif_cache(["/foo/bar.arw"]) == {}
        assert seen["raised"] is True
        if wal_path.exists():
            assert wal_path.read_bytes() != b"stale wal"
        if shm_path.exists():
            assert shm_path.read_bytes() != b"stale shm"
        s.close()


def test_visual_hash_cache_round_trip():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        assert s.get_visual_hash_cache(["/foo/a.arw", "/foo/b.arw"]) == {}
        s.set_visual_hash_cache(
            {
                "/foo/a.arw": "0123456789abcdef",
                "/foo/b.arw": "fedcba9876543210",
            }
        )
        assert s.get_visual_hash_cache(["/foo/a.arw", "/foo/b.arw"]) == {
            "/foo/a.arw": "0123456789abcdef",
            "/foo/b.arw": "fedcba9876543210",
        }


def test_exif_cache_skips_none_and_invalidates_when_file_changes(tmp_path):
    image_path = tmp_path / "image.raw"
    image_path.write_bytes(b"first")
    with State(tmp_path) as state:
        state.set_exif_cache({str(image_path): None})
        assert state.conn.execute("SELECT COUNT(*) FROM exif_cache").fetchone()[0] == 0

        state.set_exif_cache({str(image_path): "2026:07:13 10:00:00"})
        assert state.get_exif_cache([str(image_path)]) == {str(image_path): "2026:07:13 10:00:00"}

        image_path.write_bytes(b"replacement-with-different-size")

        assert state.get_exif_cache([str(image_path)]) == {}


def test_visual_hash_cache_invalidates_when_file_changes(tmp_path):
    image_path = tmp_path / "image.raw"
    image_path.write_bytes(b"first")
    with State(tmp_path) as state:
        state.set_visual_hash_cache({str(image_path): "0123456789abcdef"})
        assert state.get_visual_hash_cache([str(image_path)]) == {
            str(image_path): "0123456789abcdef"
        }

        image_path.write_bytes(b"replacement-with-different-size")

        assert state.get_visual_hash_cache([str(image_path)]) == {}


def test_embedding_cache_is_versioned_by_model_key():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.set_embedding_cache({"/foo/a.arw": [0.1, 0.2]}, "dino-v1")

        assert s.get_embedding_cache(["/foo/a.arw"], "dino-v1") == {"/foo/a.arw": [0.1, 0.2]}
        assert s.get_embedding_cache(["/foo/a.arw"], "dino-v2") == {}


def test_embedding_cache_invalidates_when_file_changes(tmp_path):
    image_path = tmp_path / "image.raw"
    image_path.write_bytes(b"first")
    s = State(tmp_path)
    s.set_embedding_cache({str(image_path): [0.1, 0.2]}, "dino-v1")
    assert s.get_embedding_cache([str(image_path)], "dino-v1") == {str(image_path): [0.1, 0.2]}

    image_path.write_bytes(b"replacement-with-different-size")

    assert s.get_embedding_cache([str(image_path)], "dino-v1") == {}


def test_processed_cache_invalidates_when_file_changes(tmp_path):
    done_path = tmp_path / "done.raw"
    scored_path = tmp_path / "scored.raw"
    done_path.write_bytes(b"done-first")
    scored_path.write_bytes(b"scored-first")
    with State(tmp_path) as state:
        state.mark_done(
            str(done_path),
            total_score=8.0,
            star_rating=4,
            group_boosted=False,
            scores={},
            metadata={},
            group_info={},
        )
        state.mark_scored(
            str(scored_path),
            total_score=7.0,
            scores={},
            metadata={},
        )
        assert state.is_done(str(done_path))
        assert state.is_scored(str(scored_path))

        done_path.write_bytes(b"done-replacement-with-different-size")
        scored_path.write_bytes(b"scored-replacement-with-different-size")

        assert not state.is_done(str(done_path))
        assert not state.is_scored(str(scored_path))
        assert state.get_cached_score_payload(str(done_path)) is None
        assert state.get_scored(str(scored_path)) is None


def test_score_cache_key_invalidates_done_and_scored_rows(tmp_path):
    done_path = tmp_path / "done.raw"
    scored_path = tmp_path / "scored.raw"
    done_path.write_bytes(b"done")
    scored_path.write_bytes(b"scored")
    db_path = tmp_path / "state.db"

    with SQLiteProcessedRepository(db_path, score_cache_key="policy-a") as state:
        state.mark_done(
            str(done_path),
            total_score=8.0,
            star_rating=4,
            group_boosted=False,
            scores={},
            metadata={},
            group_info={},
        )
        state.mark_scored(str(scored_path), total_score=7.0, scores={}, metadata={})

    with SQLiteProcessedRepository(db_path, score_cache_key="policy-a") as matching:
        assert matching.is_done(str(done_path))
        assert matching.is_scored(str(scored_path))
        assert matching.get_cached_score_payload(str(done_path)) is not None

    with SQLiteProcessedRepository(db_path, score_cache_key="policy-b") as changed:
        assert not changed.is_done(str(done_path))
        assert not changed.is_scored(str(scored_path))
        assert changed.get_cached_score_payload(str(done_path)) is None
        assert changed.get_scored(str(scored_path)) is None

    # Maintenance callers that do not supply a production key retain read access.
    with SQLiteProcessedRepository(db_path) as unversioned_reader:
        assert unversioned_reader.is_done(str(done_path))
        assert unversioned_reader.is_scored(str(scored_path))


def test_state_adds_integrity_columns_to_legacy_cache_tables(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE processed (file_path TEXT PRIMARY KEY, status TEXT)")
        conn.execute("CREATE TABLE exif_cache (file_path TEXT PRIMARY KEY, datetime_original TEXT)")
        conn.execute("CREATE TABLE visual_hash_cache (file_path TEXT PRIMARY KEY, phash TEXT)")
        conn.execute("INSERT INTO processed VALUES ('/legacy.raw', 'done')")
        conn.commit()

    with SQLiteProcessedRepository(db_path) as state:
        processed_columns = {
            row[1] for row in state.conn.execute("PRAGMA table_info(processed)").fetchall()
        }
        exif_columns = {
            row[1] for row in state.conn.execute("PRAGMA table_info(exif_cache)").fetchall()
        }
        hash_columns = {
            row[1] for row in state.conn.execute("PRAGMA table_info(visual_hash_cache)").fetchall()
        }

        assert {
            "score_metadata_json",
            "score_metadata_version",
            "file_size",
            "mtime_ns",
            "score_cache_key",
            "xmp_payload_json",
        } <= processed_columns
        assert {"file_size", "mtime_ns"} <= exif_columns
        assert {"file_size", "mtime_ns"} <= hash_columns
        assert state.is_done("/legacy.raw")


def test_clear_ai_judgement_preserves_non_ai_caches():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.set_exif_cache({"/foo/bar.arw": "2026:04:14 10:00:00"})
        s.set_visual_hash_cache({"/foo/bar.arw": "abcd1234"})
        s.set_embedding_cache({"/foo/bar.arw": [0.1, 0.2]}, "dino-v1")
        s.mark_done(
            "/foo/bar.arw",
            total_score=8.0,
            star_rating=4,
            group_boosted=False,
            scores={"composition": 8.0},
            metadata={},
            group_info={"group_id": "g1", "group_rank": 1, "group_size": 1},
            signals=[
                {
                    "stage": "aesthetic",
                    "signal_key": "subject_moment",
                    "value": 8.2,
                    "confidence": 0.9,
                    "source": "vision",
                }
            ],
        )

        summary = s.clear_ai_judgement()

        assert summary == {"processed_rows_deleted": 1, "signal_rows_deleted": 1}
        assert s.conn.execute("SELECT COUNT(*) FROM processed").fetchone()[0] == 0
        assert s.conn.execute("SELECT COUNT(*) FROM score_signals").fetchone()[0] == 0
        assert (
            s.conn.execute("SELECT datetime_original FROM exif_cache").fetchone()[0]
            == "2026:04:14 10:00:00"
        )
        assert s.conn.execute("SELECT phash FROM visual_hash_cache").fetchone()[0] == "abcd1234"
        assert (
            s.conn.execute("SELECT vector_json FROM embedding_cache").fetchone()[0] == "[0.1, 0.2]"
        )


def test_state_allows_processed_access_from_worker_thread():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        errors = []

        def worker():
            try:
                s.mark_scored(
                    "/foo/threaded.arw",
                    total_score=7.1,
                    scores={"composition": 7.1},
                    metadata={},
                    scene="people",
                    scene_raw="舞台上的人物",
                )
                cached = s.get_scored("/foo/threaded.arw")
                assert cached is not None
                assert cached["scene"] == "people"
            except Exception as error:  # pragma: no cover - assertion path
                errors.append(error)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

        assert errors == []
