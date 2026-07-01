import pytest
import numpy as np

from material_agent.scorers.base import ScorerResult
from material_agent.scorers.exposure import ExposureScorer
from material_agent.scorers.sharpness import SharpnessScorer


def test_scorer_result_fields():
    r = ScorerResult(name="exposure", score=7.5, enabled=True, weight=0.25)
    assert r.name == "exposure"
    assert r.score == 7.5
    assert r.enabled is True
    assert r.weight == 0.25
    assert r.metadata == {}


def test_scorer_result_default_metadata():
    r = ScorerResult(name="sharpness", score=5.0, enabled=True, weight=0.2)
    assert isinstance(r.metadata, dict)


def _exposure_cfg(**kw):
    cfg = {
        "enabled": True,
        "weight": 0.25,
        "min_score": 0.0,
        "overexpose_threshold": 0.02,
        "overexpose_hard_limit": 2.0,
        "underexpose_threshold": 0.20,
        "underexpose_hard_limit": 2.0,
    }
    cfg.update(kw)
    return cfg


def test_exposure_normal():
    pixels = np.full((100, 100), 32768, dtype=np.uint16)
    result = ExposureScorer(_exposure_cfg()).score_pixels(pixels)
    assert result.score >= 8.0


def test_exposure_overexposed():
    pixels = np.full((100, 100), 100, dtype=np.uint16)
    pixels[:5, :] = 65535  # 5% 过曝
    result = ExposureScorer(_exposure_cfg()).score_pixels(pixels)
    assert result.score < 8.0
    assert "overexpose_ratio" in result.metadata


def test_exposure_hard_limit():
    pixels = np.full((100, 100), 65535, dtype=np.uint16)
    result = ExposureScorer(_exposure_cfg()).score_pixels(pixels)
    assert result.score == 0.0


def test_exposure_dual_penalty_independent():
    """同时存在过曝和欠曝时，分数不应接近满分。"""
    # 5% 过曝 + 25% 欠曝（超过 underexpose_threshold=20%）
    pixels = np.full((100, 100), 32768, dtype=np.uint16)
    pixels[:5, :] = 65535    # 5% 过曝
    pixels[5:30, :] = 100    # 25% 欠曝
    result = ExposureScorer(_exposure_cfg()).score_pixels(pixels)
    assert result.score < 9.0
    assert result.metadata["overexpose_ratio"] > 0.0
    assert result.metadata["underexpose_ratio"] > 0.20


def _sharpness_cfg(**kw):
    cfg = {
        "enabled": True,
        "weight": 0.20,
        "min_score": 0.0,
        "min_variance": 50,
        "max_variance": 1000,
    }
    cfg.update(kw)
    return cfg


def test_sharpness_sharp_image():
    img = np.zeros((100, 100), dtype=np.uint8)
    img[::2, :] = 255
    result = SharpnessScorer(_sharpness_cfg()).score_image(img)
    assert result.score >= 8.0
    assert "laplacian_variance" in result.metadata


def test_sharpness_blurry_image():
    img = np.full((100, 100), 128, dtype=np.uint8)
    result = SharpnessScorer(_sharpness_cfg()).score_image(img)
    assert result.score == 0.0


def test_sharpness_clamp_max():
    img = np.zeros((100, 100), dtype=np.uint8)
    img[::2, :] = 255
    result = SharpnessScorer(_sharpness_cfg(max_variance=1)).score_image(img)
    assert result.score == 10.0


# ---------------------------------------------------------------------------
# Parametrized exposure boundary tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("over_pct,expected_lt", [
    # exactly at threshold (2%) → no penalty
    (0.02, 10.1),
    # just above threshold → partial penalty, still > 0
    (0.03, 10.0),
    # half of hard limit (ratio=1.0) → penalty = 5.0, score = 5.0
    (0.06, 6.0),
])
def test_exposure_overexpose_threshold_boundary(over_pct, expected_lt):
    """At or above overexpose_threshold the score should be below expected_lt."""
    total_pixels = 10000
    over_count = int(total_pixels * over_pct)
    pixels = np.full(total_pixels, 100, dtype=np.uint16).reshape(100, 100)
    pixels.flat[:over_count] = 65535
    result = ExposureScorer(_exposure_cfg()).score_pixels(pixels)
    assert result.score < expected_lt


def test_exposure_exactly_at_hard_limit():
    """大量高光剪切加大面积死黑应当接近不可用。"""
    total_pixels = 10000
    over_count = 600  # 6%
    pixels = np.full(total_pixels, 100, dtype=np.uint16).reshape(100, 100)
    pixels.flat[:over_count] = 65535
    result = ExposureScorer(_exposure_cfg()).score_pixels(pixels)
    assert result.score < 3.0


def test_exposure_underexpose_threshold_boundary():
    """少量暗部但主体仍清晰可见时，应保持高分而不是直接拉满或归零。"""
    total_pixels = 10000
    under_count = 1500  # 15% < threshold 20%
    pixels = np.full(total_pixels, 32768, dtype=np.uint16).reshape(100, 100)
    pixels.flat[:under_count] = 0
    result = ExposureScorer(_exposure_cfg()).score_pixels(pixels)
    assert result.score >= 8.0


def test_exposure_metadata_keys():
    pixels = np.full((100, 100), 32768, dtype=np.uint16)
    result = ExposureScorer(_exposure_cfg()).score_pixels(pixels)
    assert "overexpose_ratio" in result.metadata
    assert "underexpose_ratio" in result.metadata


def _stage_like_gray():
    gray = np.full((120, 120), 8, dtype=np.uint8)
    gray[25:95, 45:75] = 110
    gray[10:28, 88:110] = 200
    return gray


def test_exposure_scene_aware_people_dark_stage_not_zero():
    result = ExposureScorer(_exposure_cfg()).score_image(_stage_like_gray(), scene="people")
    assert result.score >= 4.0
    assert "luma_p50" in result.metadata
    assert "luma_span" in result.metadata


def test_exposure_scene_aware_people_more_tolerant_than_landscape():
    people_score = ExposureScorer(_exposure_cfg()).score_image(_stage_like_gray(), scene="people").score
    landscape_score = ExposureScorer(_exposure_cfg()).score_image(_stage_like_gray(), scene="landscape").score
    assert people_score > landscape_score


def test_exposure_config_thresholds_still_influence_scene_aware_scores():
    gray = _stage_like_gray()
    strict_cfg = _exposure_cfg(
        underexpose_threshold=0.12,
        underexpose_hard_limit=1.2,
        overexpose_threshold=0.02,
        overexpose_hard_limit=2.0,
    )
    tolerant_cfg = _exposure_cfg(
        underexpose_threshold=0.40,
        underexpose_hard_limit=4.0,
        overexpose_threshold=0.08,
        overexpose_hard_limit=4.0,
    )
    strict_score = ExposureScorer(strict_cfg).score_image(gray, scene="people").score
    tolerant_score = ExposureScorer(tolerant_cfg).score_image(gray, scene="people").score
    assert tolerant_score > strict_score


# ---------------------------------------------------------------------------
# Parametrized sharpness boundary tests
# ---------------------------------------------------------------------------

def test_sharpness_at_min_variance_is_zero():
    """A flat image has variance == 0 < min_variance → score == 0.0."""
    img = np.full((100, 100), 128, dtype=np.uint8)
    result = SharpnessScorer(_sharpness_cfg(min_variance=50)).score_image(img)
    assert result.score == 0.0


def test_sharpness_metadata_key():
    img = np.zeros((100, 100), dtype=np.uint8)
    img[::2, :] = 255
    result = SharpnessScorer(_sharpness_cfg()).score_image(img)
    assert "laplacian_variance" in result.metadata
    assert result.metadata["laplacian_variance"] > 0


@pytest.mark.parametrize("min_v,max_v,expected_score", [
    (0, 1000, 10.0),   # clamp when variance >> max_variance
    (50, 50, 10.0),    # min == max → variance >= max → clamp to 10
])
def test_sharpness_clamp_parametrized(min_v, max_v, expected_score):
    """High-variance image scores 10.0 when variance >= max_variance."""
    img = np.zeros((100, 100), dtype=np.uint8)
    img[::2, :] = 255
    result = SharpnessScorer(_sharpness_cfg(min_variance=min_v, max_variance=max_v)).score_image(img)
    assert result.score == expected_score
