from .base import ScorerResult


class Aggregator:
    @staticmethod
    def aggregate(results: list[ScorerResult]) -> float:
        enabled = [r for r in results if r.enabled]
        if not enabled:
            return 0.0
        weight_sum = sum(r.weight for r in enabled)
        total = sum(r.score * r.weight / weight_sum for r in enabled)
        # min_score 强制压分
        for r in enabled:
            min_s = getattr(r, "min_score", 0.0)
            if min_s > 0 and r.score < min_s:
                total = min(total, min_s)
        return round(total, 2)

    @staticmethod
    def aggregate_with_scene(
        pixel_results: list[ScorerResult],
        vision_scores: dict,
        scene: str,
        scene_weights: dict,
        pixel_weight: float = 0.3,
        vision_weight: float = 0.7,
    ) -> float:
        """合并像素分和 vision 维度分，vision 部分按 scene 权重加权"""
        weights = scene_weights.get(scene) or scene_weights.get("default") or {}

        # vision 部分
        vision_weight_sum = sum(weights.get(d, 0.0) for d in vision_scores)
        if vision_weight_sum > 0:
            vision_total = sum(
                vision_scores[d] * weights.get(d, 0.0) / vision_weight_sum
                for d in vision_scores
            )
        else:
            vision_total = 0.0

        # 像素部分
        pixel_total = Aggregator.aggregate(pixel_results)

        # 合并：按 pixel_weight/vision_weight 比例，若无像素分则全用 vision
        if not pixel_results:
            return round(vision_total, 2)
        if vision_weight_sum == 0:
            return round(pixel_total, 2)
        w_sum = pixel_weight + vision_weight
        return round((pixel_total * pixel_weight + vision_total * vision_weight) / w_sum, 2)


class GroupGuard:
    @staticmethod
    def apply(scores: list[float], min_score: float) -> list[float]:
        if not scores:
            return []
        if max(scores) >= min_score:
            return scores
        result = list(scores)
        idx = result.index(max(result))
        result[idx] = min_score
        return result
