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
