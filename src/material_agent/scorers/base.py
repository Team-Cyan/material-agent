from dataclasses import dataclass, field


@dataclass
class ScorerResult:
    name: str
    score: float  # 0-10
    enabled: bool
    weight: float
    min_score: float = 0.0
    metadata: dict = field(default_factory=dict)
