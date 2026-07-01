import cv2
import numpy as np
from .base import ScorerResult


class SharpnessScorer:
    def __init__(self, config: dict):
        self.config = config

    def score_image(self, gray: np.ndarray) -> ScorerResult:
        variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        cfg = self.config
        mn, mx = cfg["min_variance"], cfg["max_variance"]
        if variance <= mn:
            score = 0.0
        elif variance >= mx:
            score = 10.0
        else:
            score = (variance - mn) / (mx - mn) * 10.0
        return ScorerResult(
            name="sharpness",
            score=score,
            enabled=cfg["enabled"],
            weight=cfg["weight"],
            metadata={"laplacian_variance": variance},
        )
