import pytest

from material_agent.scorers.base import ScorerResult
from material_agent.scorers.aggregator import Aggregator, GroupGuard


def _r(name, score, weight, enabled=True, min_score=0.0):
    r = ScorerResult(name=name, score=score, enabled=enabled, weight=weight)
    r.min_score = min_score
    return r


def test_aggregator_weighted():
    results = [_r("exposure", 8.0, 0.5), _r("sharpness", 6.0, 0.5)]
    total = Aggregator.aggregate(results)
    assert total == 7.0


def test_aggregator_disabled_scorer_excluded():
    results = [_r("exposure", 10.0, 0.5), _r("sharpness", 0.0, 0.5, enabled=False)]
    total = Aggregator.aggregate(results)
    assert total == 10.0


def test_aggregator_min_score_cap():
    # exposure 得 2.0，min_score=3.0 → 总分上限 3.0
    results = [_r("exposure", 2.0, 0.5, min_score=3.0), _r("sharpness", 9.0, 0.5)]
    total = Aggregator.aggregate(results)
    assert total <= 3.0


def test_group_guard_boost():
    scores = [1.5, 2.0, 2.8]
    boosted = GroupGuard.apply(scores, min_score=7.0)
    assert max(boosted) == 7.0
    assert boosted.index(7.0) == scores.index(max(scores))


def test_group_guard_no_boost_needed():
    scores = [3.5, 5.0, 7.0]
    boosted = GroupGuard.apply(scores, min_score=7.0)
    assert boosted == scores


def test_aggregate_with_scene_uses_scene_weights():
    scene_weights = {
        "default": {"composition": 0.5, "color": 0.5},
        "concert": {"composition": 0.1, "color": 0.9},
    }
    pixel_results = []  # no exposure/sharpness
    vision_scores = {"composition": 10.0, "color": 0.0}

    total_default = Aggregator.aggregate_with_scene(pixel_results, vision_scores, "landscape", scene_weights)
    total_concert = Aggregator.aggregate_with_scene(pixel_results, vision_scores, "concert", scene_weights)

    # concert weights color heavily (0.0), default weights composition heavily (10.0)
    assert total_concert < total_default


def test_aggregate_with_scene_falls_back_to_default():
    scene_weights = {
        "default": {"composition": 1.0},
    }
    vision_scores = {"composition": 8.0}
    total = Aggregator.aggregate_with_scene([], vision_scores, "unknown_scene", scene_weights)
    assert total == 8.0


def test_aggregate_with_scene_combines_pixel_and_vision():
    scene_weights = {
        "default": {"composition": 0.5, "color": 0.5},
    }
    pixel_results = [_r("exposure", 6.0, 0.5), _r("sharpness", 4.0, 0.5)]
    vision_scores = {"composition": 10.0, "color": 10.0}
    total = Aggregator.aggregate_with_scene(pixel_results, vision_scores, "other", scene_weights)
    # pixel total = 5.0, vision total = 10.0, combined = 5.0*0.3 + 10.0*0.7 = 8.5
    assert total == 8.5


def test_group_guard_empty_list():
    assert GroupGuard.apply([], min_score=7.0) == []


def test_group_guard_single_score_boosted():
    result = GroupGuard.apply([1.0], min_score=7.0)
    assert result == [7.0]


def test_group_guard_single_score_no_boost():
    result = GroupGuard.apply([8.0], min_score=7.0)
    assert result == [8.0]


def test_group_guard_requires_explicit_min_score():
    with pytest.raises(TypeError):
        GroupGuard.apply([1.0, 2.0, 3.0])


def test_aggregate_with_scene_no_vision():
    # When vision_weight_sum == 0, falls back to pixel_total only.
    scene_weights = {"default": {}}  # no dims → weight_sum = 0
    pixel_results = [_r("exposure", 6.0, 1.0)]
    vision_scores = {}
    total = Aggregator.aggregate_with_scene(pixel_results, vision_scores, "other", scene_weights)
    assert total == 6.0


def test_aggregate_with_scene_custom_weights():
    scene_weights = {"default": {"composition": 1.0}}
    pixel_results = [_r("exposure", 4.0, 1.0)]
    vision_scores = {"composition": 8.0}
    # pixel_weight=0.5, vision_weight=0.5 → (4.0 + 8.0) / 2 = 6.0
    total = Aggregator.aggregate_with_scene(
        pixel_results, vision_scores, "other", scene_weights,
        pixel_weight=0.5, vision_weight=0.5,
    )
    assert total == 6.0
