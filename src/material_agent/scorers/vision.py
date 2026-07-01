from .base import ScorerResult
from ..utils.constants import VISION_DIMS


class VisionScorer:
    def __init__(self, config: dict, client):
        self.config = config
        self.client = client

    def score_jpeg(self, jpeg_bytes: bytes) -> tuple[list[ScorerResult], str, str]:
        """返回 (results, scene, scene_raw)"""
        raw = self.client.score_image(jpeg_bytes)
        scene = raw.get("scene", "other")
        scene_raw = raw.get("scene_raw", "")
        results = []
        for dim in VISION_DIMS:
            cfg = self.config.get(dim, {})
            try:
                score = max(0.0, min(10.0, float(raw.get(dim, 0))))
            except (TypeError, ValueError):
                score = 0.0
            r = ScorerResult(
                name=dim,
                score=score,
                enabled=self.config.get("enabled", True),
                weight=cfg.get("weight", 0.1),
                min_score=cfg.get("min_score", 0.0),
            )
            results.append(r)
        return results, scene, scene_raw
