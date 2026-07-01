from importlib import import_module

_EXPORT_MAP = {
    "CommentaryGenerator": "material_agent.core.commentary",
    "Grouper": "material_agent.core.grouper",
    "RawFrame": "material_agent.core.scoring_engine",
    "ScoreBundle": "material_agent.core.scoring_engine",
    "build_score_instructions": "material_agent.core.scoring_engine",
    "build_visible_breakdown_instructions": "material_agent.core.scoring_engine",
    "build_xmp_instructions": "material_agent.core.scoring_engine",
    "compute_scores": "material_agent.core.scoring_engine",
    "decode_raw": "material_agent.core.scoring_engine",
}

__all__ = [
    "CommentaryGenerator",
    "Grouper",
    "RawFrame",
    "ScoreBundle",
    "build_score_instructions",
    "build_visible_breakdown_instructions",
    "build_xmp_instructions",
    "compute_scores",
    "decode_raw",
]


def __getattr__(name: str):
    module_name = _EXPORT_MAP.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module_name), name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
