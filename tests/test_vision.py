from unittest.mock import MagicMock
from material_agent.scorers.vision import VisionScorer

ALL_DIMS = ["subject", "composition", "lighting", "color", "clarity", "depth", "mood"]


def _vision_cfg():
    return {
        "enabled": True,
        "subject": {"weight": 0.10, "min_score": 0.0},
        "composition": {"weight": 0.20, "min_score": 0.0},
        "lighting": {"weight": 0.10, "min_score": 0.0},
        "color": {"weight": 0.15, "min_score": 0.0},
        "clarity": {"weight": 0.20, "min_score": 0.0},
        "depth": {"weight": 0.05, "min_score": 0.0},
        "mood": {"weight": 0.20, "min_score": 0.0},
    }


def _full_raw(scene="people", scene_raw="舞台上的人物"):
    return {d: 7.0 for d in ALL_DIMS} | {"scene": scene, "scene_raw": scene_raw}


def test_vision_scorer_returns_nine_results():
    client = MagicMock()
    client.score_image.return_value = _full_raw()
    scorer = VisionScorer(_vision_cfg(), client)
    results, scene, scene_raw = scorer.score_jpeg(b"fake_jpeg")
    assert len(results) == 7
    assert {r.name for r in results} == set(ALL_DIMS)
    assert scene == "people"
    assert scene_raw == "舞台上的人物"


def test_vision_scorer_returns_scene():
    client = MagicMock()
    client.score_image.return_value = _full_raw(scene="detail", scene_raw="寿司特写")
    scorer = VisionScorer(_vision_cfg(), client)
    _, scene, scene_raw = scorer.score_jpeg(b"fake_jpeg")
    assert scene == "detail"
    assert scene_raw == "寿司特写"


def test_vision_scorer_clamps_score():
    client = MagicMock()
    raw = _full_raw()
    raw["composition"] = 15
    raw["color"] = -1
    client.score_image.return_value = raw
    scorer = VisionScorer(_vision_cfg(), client)
    results, _, _ = scorer.score_jpeg(b"fake_jpeg")
    scores = {r.name: r.score for r in results}
    assert scores["composition"] == 10.0
    assert scores["color"] == 0.0
