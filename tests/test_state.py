import tempfile
from pathlib import Path
import sqlite3
import threading
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


# ---------------------------------------------------------------------------
# New regression tests
# ---------------------------------------------------------------------------

def test_get_scored_round_trip():
    """mark_scored followed by get_scored should return all stored values."""
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        scores = {
            "exposure": 7.5, "sharpness": 6.0,
            "subject": 9.0, "composition": 8.0, "lighting": 7.0,
            "color": 7.0, "clarity": 8.5, "depth": 4.0, "mood": 5.5,
        }
        metadata = {
            "overexpose_ratio": 0.01,
            "underexpose_ratio": 0.05,
            "laplacian_variance": 350.2,
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
            "/foo/bar.arw", total_score=5.0, star_rating=3, group_boosted=False,
            scores={}, metadata={}, group_info={},
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
            conn.execute("INSERT INTO processed (file_path, status) VALUES ('/foo/bar.arw', 'done')")
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


def test_clear_ai_judgement_preserves_non_ai_caches():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.set_exif_cache({"/foo/bar.arw": "2026:04:14 10:00:00"})
        s.set_visual_hash_cache({"/foo/bar.arw": "abcd1234"})
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
        assert s.conn.execute("SELECT datetime_original FROM exif_cache").fetchone()[0] == "2026:04:14 10:00:00"
        assert s.conn.execute("SELECT phash FROM visual_hash_cache").fetchone()[0] == "abcd1234"


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
