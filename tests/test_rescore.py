import tempfile
import json

import pytest

from material_agent.domain.layered_decision import (
    apply_group_best_candidate_review,
    group_best_candidate_review_enabled,
    summarize_signals,
)
from material_agent.main import cmd_rescore
from material_agent.utils.state import State


class _Args:
    def __init__(self, d):
        self.dir = d


def test_group_coverage_keeps_defective_best_without_changing_quality():
    results = [
        (
            "a",
            {
                "score_total": 1.0,
                "star_rating": 1,
                "decision": "reject",
                "decision_reasons": ["subject_focus_below_threshold"],
            },
        ),
        (
            "b",
            {
                "score_total": 0.0,
                "star_rating": 0,
                "decision": "reject",
                "decision_reasons": ["technical_quality_below_threshold"],
            },
        ),
    ]
    updated = apply_group_best_candidate_review(results)
    best = updated[0][1]
    assert best["decision"] == "keep"
    assert best["score_total"] == 1.0 and best["star_rating"] == 1
    assert best["meta"]["quality_assessment"]["decision"] == "reject"
    assert best["meta"]["quality_assessment"]["reasons"] == ["subject_focus_below_threshold"]
    assert best["meta"]["selection"]["role"] == "group_coverage"
    assert updated[1][1]["decision"] == "reject"
    assert results[0][1]["decision"] == "reject"  # no input mutation
    assert apply_group_best_candidate_review(updated) == updated


@pytest.mark.parametrize("decision", ["reject", "review", "keep"])
def test_group_coverage_singleton_and_disabled(decision):
    results = [("a", {"score_total": 4.2, "decision": decision, "decision_reasons": []})]
    assert apply_group_best_candidate_review(results)[0][1]["decision"] == "keep"
    assert apply_group_best_candidate_review(results, enabled=False)[0][1]["decision"] == decision


def test_group_coverage_does_not_select_errors_or_invalid_scores():
    errors = [
        ("a", {"status": "error", "decision": "reject", "score_total": 9}),
        ("b", {"decision": "reject", "score_total": float("nan")}),
        ("c", {"status": "error"}),
    ]
    assert apply_group_best_candidate_review(errors) == errors
    mixed = apply_group_best_candidate_review(
        errors + [("d", {"score_total": 0, "decision": "reject", "decision_reasons": ["blur"]})]
    )
    assert mixed[-1][1]["decision"] == "keep"


def test_group_coverage_recomputes_cached_choice_and_breaks_ties_by_path():
    first = apply_group_best_candidate_review(
        [("b", {"score_total": 2, "decision": "reject", "decision_reasons": []})]
    )
    combined = first + [("a", {"score_total": 2, "decision": "reject", "decision_reasons": []})]
    updated = dict(apply_group_best_candidate_review(combined))
    assert updated["a"]["decision"] == "keep"
    assert updated["b"]["decision"] == "reject"
    assert updated["b"]["decision_reasons"] == []


def test_group_best_candidate_review_requires_grouping_and_its_own_switch():
    assert not group_best_candidate_review_enabled(
        {"grouping": {"enabled": False, "best_candidate_review": {"enabled": True}}}
    )
    assert not group_best_candidate_review_enabled(
        {"grouping": {"enabled": True, "best_candidate_review": {"enabled": False}}}
    )
    assert group_best_candidate_review_enabled(
        {"grouping": {"enabled": True, "best_candidate_review": {"enabled": True}}}
    )


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
        s.conn.execute(
            """
            INSERT INTO processed (file_path, status, scene,
                score_subject, score_composition, score_lighting, score_color,
                score_clarity, score_depth, score_mood)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
            ("/fake/a.jpg", "done", "people", 9.0, 8.0, 7.0, 7.0, 9.0, 0.0, 0.0),
        )
        s.conn.commit()

        cfg = {
            "scene_profiles": {
                "people": {
                    "aesthetic_weights": {
                        "subject_moment": 1 / 6,
                        "composition": 1 / 6,
                        "lighting": 1 / 6,
                        "color": 1 / 6,
                        "depth_separation": 1 / 6,
                        "mood_story": 1 / 6,
                    }
                }
            }
        }
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
        s.conn.execute(
            """
            INSERT INTO processed (file_path, status, scene,
                score_subject, score_composition, score_lighting, score_color,
                score_clarity, score_depth, score_mood)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
            ("/fake/b.jpg", "done", "unknown", 0.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        s.conn.commit()

        cfg = {"scene_profiles": {"default": {"aesthetic_weights": {"composition": 1.0}}}}
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
                (
                    "/fake/people.jpg",
                    "screening",
                    "screening_prior",
                    6.1,
                    1.0,
                    "musiq",
                    "musiq",
                    "1",
                ),
                ("/fake/people.jpg", "aesthetic", "subject_moment", 6.0, 1.0, "vision", "vlm", "1"),
                ("/fake/people.jpg", "aesthetic", "composition", 6.0, 1.0, "vision", "vlm", "1"),
                ("/fake/people.jpg", "aesthetic", "lighting", 6.0, 1.0, "vision", "vlm", "1"),
                ("/fake/people.jpg", "aesthetic", "color", 6.0, 1.0, "vision", "vlm", "1"),
                (
                    "/fake/people.jpg",
                    "aesthetic",
                    "depth_separation",
                    6.0,
                    1.0,
                    "vision",
                    "vlm",
                    "1",
                ),
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
            "screening_policy": {"weight": 0.10},
        }

        from material_agent.app.rescore_service import RescoreService
        from material_agent.adapters.state.processed_sqlite import SQLiteProcessedRepository

        repo = SQLiteProcessedRepository(d)
        try:
            updated = RescoreService(repo).run(
                scene_filters=["people"],
                scene_profiles=cfg["scene_profiles"],
                decision_policy=cfg.get("decision_policy", {}),
                screening_policy=cfg.get("screening_policy", {}),
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


def test_filtered_rescore_preserves_group_coverage_and_metadata(tmp_path):
    from material_agent.app.rescore_service import RescoreService
    from material_agent.adapters.state.processed_sqlite import SQLiteProcessedRepository

    repo = SQLiteProcessedRepository(tmp_path / "fixture.db")
    try:
        repo.conn.executemany(
            "INSERT INTO processed (file_path,status,scene,group_id,group_rank,total_score,"
            "star_rating,decision,decision_reasons,score_metadata_json,score_metadata_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("a", "done", "people", "g", 1, 8.0, 4, "keep", "[]", '{"runtime":"fixture"}', 1),
                (
                    "b",
                    "done",
                    "city",
                    "g",
                    2,
                    3.0,
                    2,
                    "reject",
                    '["blur"]',
                    '{"runtime":"other"}',
                    1,
                ),
                ("error", "error", "people", "errors", None, None, None, None, None, None, None),
            ],
        )
        repo.conn.execute(
            "INSERT INTO score_signals (file_path,stage,signal_key,value) VALUES (?,?,?,?)",
            ("a", "technical", "technical_quality", 0.0),
        )
        repo.conn.commit()
        count = RescoreService(repo).run(
            scene_filters=["people"],
            scene_profiles={},
            decision_policy={},
            screening_policy={},
            grouping_config={"enabled": True},
        )
        rows = {r["file_path"]: r for r in repo.conn.execute("SELECT * FROM processed")}
        assert count == 1  # count quality evaluations, not unchanged group context
        assert rows["a"]["decision"] == "reject"
        assert rows["b"]["decision"] == "keep"
        assert rows["b"]["total_score"] == 3.0 and rows["b"]["star_rating"] == 2
        assert rows["b"]["group_rank"] == 2
        meta = json.loads(rows["b"]["score_metadata_json"])
        assert meta["runtime"] == "other"
        assert meta["quality_assessment"]["decision"] == "reject"
        assert meta["quality_assessment"]["reasons"] == ["blur"]
        assert meta["selection"]["role"] == "group_coverage"
        assert rows["error"]["decision"] is None and rows["error"]["status"] == "error"
        # A second pass retains the original quality evidence rather than learning
        # the coverage keep as an independent quality keep.
        RescoreService(repo).run(
            scene_filters=["people"],
            scene_profiles={},
            decision_policy={},
            screening_policy={},
            grouping_config={"enabled": True},
        )
        again = repo.conn.execute(
            "SELECT score_metadata_json FROM processed WHERE file_path='b'"
        ).fetchone()
        assert json.loads(again[0]) == meta
    finally:
        repo.close()


def test_group_selection_survives_processed_cache_round_trip(tmp_path):
    from material_agent.adapters.state.processed_sqlite import SQLiteProcessedRepository

    # A text placeholder supplies a file fingerprint without writing photo data.
    path = tmp_path / "fingerprint.txt"
    path.write_text("fixture")
    repo = SQLiteProcessedRepository(tmp_path / "fixture.db", score_cache_key="fixture")
    payload = apply_group_best_candidate_review(
        [(str(path), {"score_total": 0.5, "decision": "reject", "decision_reasons": ["blur"]})]
    )[0][1]
    try:
        repo.mark_done(
            str(path),
            total_score=0.5,
            star_rating=0,
            group_boosted=False,
            scores={},
            metadata=payload["meta"],
            group_info={},
            decision=payload["decision"],
            decision_reasons=payload["decision_reasons"],
        )
        cached = repo.get_cached_score_payload(str(path))
        assert cached["decision"] == "keep"
        assert cached["meta"]["quality_assessment"]["decision"] == "reject"
        assert cached["meta"]["selection"]["role"] == "group_coverage"
        disabled = apply_group_best_candidate_review([(str(path), cached)], enabled=False)[0][1]
        assert disabled["decision"] == "reject"
        assert disabled["decision_reasons"] == ["blur"]
        assert disabled["score_total"] == 0.5
    finally:
        repo.close()
