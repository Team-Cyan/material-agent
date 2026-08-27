from material_agent.scorers.base import ScorerResult
from material_agent.scorers.aggregator import Aggregator


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
