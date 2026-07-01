import tempfile

import pytest

from material_agent.domain.layered_decision import summarize_signals
from material_agent.main import cmd_rescore
from material_agent.utils.state import State


class _Args:
    def __init__(self, d):
        self.dir = d


def test_layered_summary_penalizes_a_single_obviously_weak_dimension():
    config = {
        "scene_profiles": {
            "default": {
                "aesthetic_weights": {
                    "subject_moment": 0.25,
                    "composition": 0.15,
                    "lighting": 0.20,
                    "color": 0.15,
                    "depth_separation": 0.10,
                    "mood_story": 0.15,
                }
            }
        },
        "decision_policy": {
            "keep_threshold": 7.5,
            "review_threshold": 5.5,
            "hard_reject": {
                "technical_quality_below": 1.5,
                "subject_focus_below": 1.5,
            },
        },
        "screening_policy": {"weight": 0.10},
    }
    signals = [
        {"stage": "technical", "signal_key": "technical_quality", "value": 7.5},
        {"stage": "aggregate", "signal_key": "subject_focus", "value": 7.4},
        {"stage": "screening", "signal_key": "screening_prior", "value": 7.5},
        {"stage": "aesthetic", "signal_key": "subject_moment", "value": 8.0},
        {"stage": "aesthetic", "signal_key": "composition", "value": 8.0},
        {"stage": "aesthetic", "signal_key": "lighting", "value": 8.0},
        {"stage": "aesthetic", "signal_key": "color", "value": 8.0},
        {"stage": "aesthetic", "signal_key": "depth_separation", "value": 3.5},
        {"stage": "aesthetic", "signal_key": "mood_story", "value": 8.0},
    ]

    summary = summarize_signals(signals, scene="default", config=config)

    assert summary.total_score < 7.2
    assert summary.decision == "review"


def test_rescore_updates_total_without_ai():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.conn.execute("""
            INSERT INTO processed (file_path, status, scene,
                score_subject, score_composition, score_lighting, score_color,
                score_clarity, score_depth, score_mood)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, ("/fake/a.jpg", "done", "people", 9.0, 8.0, 7.0, 7.0, 9.0, 0.0, 0.0))
        s.conn.commit()

        cfg = {"scene_weights": {"people": {"clarity": 1.0}}}
        cmd_rescore(_Args(d), cfg)

        row = s.conn.execute(
            "SELECT total_score, decision, star_rating, policy_version "
            "FROM processed WHERE file_path='/fake/a.jpg'"
        ).fetchone()
        assert row[0] == pytest.approx(7.08, abs=0.01)
        assert row[1] == "review"
        assert row[2] == 4
        assert row[3] == "layered-v1"


def test_rescore_falls_back_to_default():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.conn.execute("""
            INSERT INTO processed (file_path, status, scene,
                score_subject, score_composition, score_lighting, score_color,
                score_clarity, score_depth, score_mood)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, ("/fake/b.jpg", "done", "unknown", 0.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0))
        s.conn.commit()

        cfg = {"scene_weights": {"default": {"composition": 1.0}}}
        cmd_rescore(_Args(d), cfg)

        row = s.conn.execute(
            "SELECT total_score, decision, visible_breakdown_json "
            "FROM processed WHERE file_path='/fake/b.jpg'"
        ).fetchone()
        assert row[0] == pytest.approx(3.68, abs=0.01)
        assert row[1] == "reject"
        assert '"composition": 10.0' in row[2]


def test_rescore_uses_score_signals_to_update_decision_and_group_rank():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.conn.executemany(
            """
            INSERT INTO processed (
                file_path, status, scene, total_score, star_rating, group_id, group_rank, group_size
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                ("/fake/a.jpg", "done", "people", 0.0, 0, "g1", 2, 2),
                ("/fake/b.jpg", "done", "people", 0.0, 0, "g1", 1, 2),
            ],
        )
        s.conn.executemany(
            """
            INSERT INTO score_signals (
                file_path, stage, signal_key, value, confidence, source, model_name, model_version
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                ("/fake/a.jpg", "technical", "technical_quality", 8.8, 1.0, "cpu", None, None),
                ("/fake/a.jpg", "aggregate", "subject_focus", 8.4, 1.0, "cpu", None, None),
                ("/fake/a.jpg", "screening", "screening_prior", 7.6, 1.0, "musiq", "musiq", "1"),
                ("/fake/a.jpg", "aesthetic", "subject_moment", 8.8, 1.0, "vision", "vlm", "1"),
                ("/fake/a.jpg", "aesthetic", "composition", 8.0, 1.0, "vision", "vlm", "1"),
                ("/fake/a.jpg", "aesthetic", "lighting", 7.8, 1.0, "vision", "vlm", "1"),
                ("/fake/a.jpg", "aesthetic", "color", 7.6, 1.0, "vision", "vlm", "1"),
                ("/fake/a.jpg", "aesthetic", "depth_separation", 7.4, 1.0, "vision", "vlm", "1"),
                ("/fake/a.jpg", "aesthetic", "mood_story", 8.1, 1.0, "vision", "vlm", "1"),
                ("/fake/b.jpg", "technical", "technical_quality", 5.1, 1.0, "cpu", None, None),
                ("/fake/b.jpg", "aggregate", "subject_focus", 4.8, 1.0, "cpu", None, None),
                ("/fake/b.jpg", "screening", "screening_prior", 5.2, 1.0, "musiq", "musiq", "1"),
                ("/fake/b.jpg", "aesthetic", "subject_moment", 5.0, 1.0, "vision", "vlm", "1"),
                ("/fake/b.jpg", "aesthetic", "composition", 5.2, 1.0, "vision", "vlm", "1"),
                ("/fake/b.jpg", "aesthetic", "lighting", 4.9, 1.0, "vision", "vlm", "1"),
                ("/fake/b.jpg", "aesthetic", "color", 5.1, 1.0, "vision", "vlm", "1"),
                ("/fake/b.jpg", "aesthetic", "depth_separation", 4.7, 1.0, "vision", "vlm", "1"),
                ("/fake/b.jpg", "aesthetic", "mood_story", 5.0, 1.0, "vision", "vlm", "1"),
            ],
        )
        s.conn.commit()

        cfg = {
            "scene_profiles": {
                "default": {
                    "aesthetic_weights": {
                        "subject_moment": 0.25,
                        "composition": 0.15,
                        "lighting": 0.20,
                        "color": 0.15,
                        "depth_separation": 0.10,
                        "mood_story": 0.15,
                    }
                }
            },
            "decision_policy": {
                "keep_threshold": 7.5,
                "review_threshold": 5.5,
                "hard_reject": {
                    "technical_quality_below": 1.5,
                    "subject_focus_below": 1.5,
                },
            },
            "screening_policy": {"weight": 0.10},
        }

        cmd_rescore(_Args(d), cfg)

        rows = s.conn.execute(
            "SELECT file_path, total_score, star_rating, decision, group_rank, visible_breakdown_json "
            "FROM processed ORDER BY file_path"
        ).fetchall()
        assert rows[0][0] == "/fake/a.jpg"
        assert rows[0][1] > rows[1][1]
        assert rows[0][2] == 4
        assert rows[0][3] == "keep"
        assert rows[0][4] == 1
        assert '"subject_moment": 8.8' in rows[0][5]
        assert rows[1][2] == 2
        assert rows[1][3] == "reject"
        assert rows[1][4] == 2


def test_rescore_scene_filter_preserves_existing_group_rank_without_full_group_context():
    with tempfile.TemporaryDirectory() as d:
        s = State(d)
        s.conn.executemany(
            """
            INSERT INTO processed (
                file_path, status, scene, total_score, star_rating, group_id, group_rank, group_size
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                ("/fake/people.jpg", "done", "people", 0.0, 0, "g1", 2, 2),
                ("/fake/city.jpg", "done", "city", 0.0, 0, "g1", 1, 2),
            ],
        )
        s.conn.executemany(
            """
            INSERT INTO score_signals (
                file_path, stage, signal_key, value, confidence, source, model_name, model_version
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                ("/fake/people.jpg", "technical", "technical_quality", 6.2, 1.0, "cpu", None, None),
                ("/fake/people.jpg", "aggregate", "subject_focus", 6.0, 1.0, "cpu", None, None),
                ("/fake/people.jpg", "screening", "screening_prior", 6.1, 1.0, "musiq", "musiq", "1"),
                ("/fake/people.jpg", "aesthetic", "subject_moment", 6.0, 1.0, "vision", "vlm", "1"),
                ("/fake/people.jpg", "aesthetic", "composition", 6.0, 1.0, "vision", "vlm", "1"),
                ("/fake/people.jpg", "aesthetic", "lighting", 6.0, 1.0, "vision", "vlm", "1"),
                ("/fake/people.jpg", "aesthetic", "color", 6.0, 1.0, "vision", "vlm", "1"),
                ("/fake/people.jpg", "aesthetic", "depth_separation", 6.0, 1.0, "vision", "vlm", "1"),
                ("/fake/people.jpg", "aesthetic", "mood_story", 6.0, 1.0, "vision", "vlm", "1"),
                ("/fake/city.jpg", "technical", "technical_quality", 8.8, 1.0, "cpu", None, None),
                ("/fake/city.jpg", "aggregate", "subject_focus", 8.6, 1.0, "cpu", None, None),
                ("/fake/city.jpg", "screening", "screening_prior", 8.7, 1.0, "musiq", "musiq", "1"),
                ("/fake/city.jpg", "aesthetic", "subject_moment", 8.8, 1.0, "vision", "vlm", "1"),
                ("/fake/city.jpg", "aesthetic", "composition", 8.8, 1.0, "vision", "vlm", "1"),
                ("/fake/city.jpg", "aesthetic", "lighting", 8.8, 1.0, "vision", "vlm", "1"),
                ("/fake/city.jpg", "aesthetic", "color", 8.8, 1.0, "vision", "vlm", "1"),
                ("/fake/city.jpg", "aesthetic", "depth_separation", 8.8, 1.0, "vision", "vlm", "1"),
                ("/fake/city.jpg", "aesthetic", "mood_story", 8.8, 1.0, "vision", "vlm", "1"),
            ],
        )
        s.conn.commit()

        cfg = {
            "scene_profiles": {
                "default": {
                    "aesthetic_weights": {
                        "subject_moment": 0.25,
                        "composition": 0.15,
                        "lighting": 0.20,
                        "color": 0.15,
                        "depth_separation": 0.10,
                        "mood_story": 0.15,
                    }
                }
            },
            "decision_policy": {
                "keep_threshold": 7.5,
                "review_threshold": 5.5,
                "hard_reject": {
                    "technical_quality_below": 1.5,
                    "subject_focus_below": 1.5,
                },
            },
            "screening_policy": {"weight": 0.10, "top1_review_fallback": True},
        }

        from material_agent.app.rescore_service import RescoreService
        from material_agent.adapters.state.processed_sqlite import SQLiteProcessedRepository

        repo = SQLiteProcessedRepository(d)
        try:
            updated = RescoreService(repo).run(
                scene_filters=["people"],
                scene_weights=cfg["scene_profiles"],
                scoring_config=cfg,
                scorers_config={},
            )
        finally:
            repo.close()

        row = s.conn.execute(
            "SELECT total_score, decision, group_rank FROM processed WHERE file_path='/fake/people.jpg'"
        ).fetchone()
        city_row = s.conn.execute(
            "SELECT total_score, group_rank FROM processed WHERE file_path='/fake/city.jpg'"
        ).fetchone()

        assert updated == 1
        assert row[0] > 0.0
        assert row[2] == 2
        assert city_row[0] == 0.0
        assert city_row[1] == 1
