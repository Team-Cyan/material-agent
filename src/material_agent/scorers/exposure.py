import numpy as np
from .base import ScorerResult


class ExposureScorer:
    _SHADOW_CLIP_CUTOFF = 0.04
    _HIGHLIGHT_CLIP_CUTOFF = 0.98
    _DEFAULT_CONFIG = {
        "overexpose_threshold": 0.02,
        "overexpose_hard_limit": 2.0,
        "underexpose_threshold": 0.20,
        "underexpose_hard_limit": 2.0,
    }
    _SCENE_PROFILES = {
        "default": {
            "shadow_soft": 0.45,
            "shadow_hard": 0.75,
            "highlight_soft": 0.03,
            "highlight_hard": 0.12,
            "median_target": 0.42,
            "median_tolerance": 0.30,
            "span_bad": 0.02,
            "span_good": 0.12,
            "weights": {"shadow": 0.30, "highlight": 0.20, "median": 0.45, "span": 0.05},
        },
        "people": {
            "shadow_soft": 0.80,
            "shadow_hard": 0.95,
            "highlight_soft": 0.06,
            "highlight_hard": 0.18,
            "median_target": 0.18,
            "median_tolerance": 0.22,
            "span_bad": 0.02,
            "span_good": 0.12,
            "weights": {"shadow": 0.10, "highlight": 0.20, "median": 0.45, "span": 0.25},
        },
        "indoor": {
            "shadow_soft": 0.72,
            "shadow_hard": 0.92,
            "highlight_soft": 0.05,
            "highlight_hard": 0.16,
            "median_target": 0.24,
            "median_tolerance": 0.20,
            "span_bad": 0.02,
            "span_good": 0.10,
            "weights": {"shadow": 0.15, "highlight": 0.20, "median": 0.45, "span": 0.20},
        },
        "landscape": {
            "shadow_soft": 0.35,
            "shadow_hard": 0.65,
            "highlight_soft": 0.03,
            "highlight_hard": 0.12,
            "median_target": 0.42,
            "median_tolerance": 0.18,
            "span_bad": 0.04,
            "span_good": 0.16,
            "weights": {"shadow": 0.35, "highlight": 0.20, "median": 0.30, "span": 0.15},
        },
        "city": {
            "shadow_soft": 0.45,
            "shadow_hard": 0.72,
            "highlight_soft": 0.04,
            "highlight_hard": 0.14,
            "median_target": 0.32,
            "median_tolerance": 0.18,
            "span_bad": 0.03,
            "span_good": 0.14,
            "weights": {"shadow": 0.30, "highlight": 0.25, "median": 0.30, "span": 0.15},
        },
        "sports": {
            "shadow_soft": 0.55,
            "shadow_hard": 0.82,
            "highlight_soft": 0.05,
            "highlight_hard": 0.16,
            "median_target": 0.30,
            "median_tolerance": 0.18,
            "span_bad": 0.03,
            "span_good": 0.12,
            "weights": {"shadow": 0.20, "highlight": 0.25, "median": 0.35, "span": 0.20},
        },
        "detail": {
            "shadow_soft": 0.60,
            "shadow_hard": 0.86,
            "highlight_soft": 0.05,
            "highlight_hard": 0.16,
            "median_target": 0.28,
            "median_tolerance": 0.20,
            "span_bad": 0.03,
            "span_good": 0.10,
            "weights": {"shadow": 0.18, "highlight": 0.22, "median": 0.38, "span": 0.22},
        },
        "animals": {
            "shadow_soft": 0.55,
            "shadow_hard": 0.82,
            "highlight_soft": 0.05,
            "highlight_hard": 0.16,
            "median_target": 0.30,
            "median_tolerance": 0.20,
            "span_bad": 0.03,
            "span_good": 0.12,
            "weights": {"shadow": 0.20, "highlight": 0.22, "median": 0.38, "span": 0.20},
        },
        "other": {
            "shadow_soft": 0.50,
            "shadow_hard": 0.80,
            "highlight_soft": 0.04,
            "highlight_hard": 0.14,
            "median_target": 0.34,
            "median_tolerance": 0.22,
            "span_bad": 0.03,
            "span_good": 0.12,
            "weights": {"shadow": 0.25, "highlight": 0.22, "median": 0.38, "span": 0.15},
        },
    }

    def __init__(self, config: dict):
        self.config = config

    @staticmethod
    def _clamp_ratio(value: float) -> float:
        return max(0.0, min(0.999, value))

    @classmethod
    def _scale_soft_hard(
        cls,
        soft: float,
        hard: float,
        *,
        threshold: float,
        threshold_default: float,
        hard_limit: float,
        hard_limit_default: float,
    ) -> tuple[float, float]:
        threshold_ratio = threshold / threshold_default if threshold_default > 0 else 1.0
        hard_ratio = hard_limit / hard_limit_default if hard_limit_default > 0 else 1.0
        scaled_soft = cls._clamp_ratio(soft * threshold_ratio)
        extra = max(0.0, hard - soft)
        scaled_extra = extra * threshold_ratio * hard_ratio
        scaled_hard = cls._clamp_ratio(max(scaled_soft, scaled_soft + scaled_extra))
        return scaled_soft, scaled_hard

    def _profile(self, scene: str | None) -> dict:
        key = scene if scene and scene in self._SCENE_PROFILES else "default"
        profile = dict(self._SCENE_PROFILES[key])
        profile["weights"] = dict(profile["weights"])

        over_threshold = float(
            self.config.get(
                "overexpose_threshold",
                self._DEFAULT_CONFIG["overexpose_threshold"],
            )
        )
        over_hard_limit = float(
            self.config.get(
                "overexpose_hard_limit",
                self._DEFAULT_CONFIG["overexpose_hard_limit"],
            )
        )
        under_threshold = float(
            self.config.get(
                "underexpose_threshold",
                self._DEFAULT_CONFIG["underexpose_threshold"],
            )
        )
        under_hard_limit = float(
            self.config.get(
                "underexpose_hard_limit",
                self._DEFAULT_CONFIG["underexpose_hard_limit"],
            )
        )

        profile["highlight_soft"], profile["highlight_hard"] = self._scale_soft_hard(
            profile["highlight_soft"],
            profile["highlight_hard"],
            threshold=over_threshold,
            threshold_default=self._DEFAULT_CONFIG["overexpose_threshold"],
            hard_limit=over_hard_limit,
            hard_limit_default=self._DEFAULT_CONFIG["overexpose_hard_limit"],
        )
        profile["shadow_soft"], profile["shadow_hard"] = self._scale_soft_hard(
            profile["shadow_soft"],
            profile["shadow_hard"],
            threshold=under_threshold,
            threshold_default=self._DEFAULT_CONFIG["underexpose_threshold"],
            hard_limit=under_hard_limit,
            hard_limit_default=self._DEFAULT_CONFIG["underexpose_hard_limit"],
        )
        return profile

    @staticmethod
    def _descending_score(value: float, soft: float, hard: float) -> float:
        if value <= soft:
            return 10.0
        if value >= hard:
            return 0.0
        return 10.0 * (1.0 - (value - soft) / (hard - soft))

    @staticmethod
    def _centered_score(value: float, target: float, tolerance: float) -> float:
        distance = abs(value - target)
        if distance >= tolerance:
            return 0.0
        return 10.0 * (1.0 - distance / tolerance)

    @staticmethod
    def _ascending_score(value: float, bad: float, good: float) -> float:
        if value <= bad:
            return 0.0
        if value >= good:
            return 10.0
        return 10.0 * (value - bad) / (good - bad)

    def score_pixels(self, pixels: np.ndarray, scene: str | None = None) -> ScorerResult:
        if np.issubdtype(pixels.dtype, np.integer):
            max_val = np.iinfo(pixels.dtype).max
        else:
            max_val = float(np.max(pixels)) or 1.0
        gray = np.clip((pixels.astype(np.float32) / float(max_val)) * 255.0, 0, 255).astype(np.uint8)
        return self.score_image(gray, scene=scene)

    def score_image(self, gray: np.ndarray, scene: str | None = None) -> ScorerResult:
        luma = gray.astype(np.float32) / 255.0
        shadow_ratio = float(np.mean(luma <= self._SHADOW_CLIP_CUTOFF))
        highlight_ratio = float(np.mean(luma >= self._HIGHLIGHT_CLIP_CUTOFF))
        p5, p50, p95 = [float(v) for v in np.percentile(luma, [5, 50, 95])]
        span = max(0.0, p95 - p5)
        profile = self._profile(scene)
        weights = profile["weights"]

        score_shadow = self._descending_score(
            shadow_ratio, profile["shadow_soft"], profile["shadow_hard"]
        )
        score_highlight = self._descending_score(
            highlight_ratio, profile["highlight_soft"], profile["highlight_hard"]
        )
        score_median = self._centered_score(
            p50, profile["median_target"], profile["median_tolerance"]
        )
        score_span = self._ascending_score(span, profile["span_bad"], profile["span_good"])

        score = (
            score_shadow * weights["shadow"]
            + score_highlight * weights["highlight"]
            + score_median * weights["median"]
            + score_span * weights["span"]
        )
        if shadow_ratio >= 0.98 or highlight_ratio >= 0.98:
            score = 0.0
        cfg = self.config

        return ScorerResult(
            name="exposure",
            score=max(0.0, min(10.0, score)),
            enabled=cfg["enabled"],
            weight=cfg["weight"],
            metadata={
                "overexpose_ratio": highlight_ratio,
                "underexpose_ratio": shadow_ratio,
                "luma_p5": p5,
                "luma_p50": p50,
                "luma_p95": p95,
                "luma_span": span,
                "exposure_scene": scene or "default",
            },
        )
