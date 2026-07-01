from __future__ import annotations

from ..app.omlx_harness_service import OMLXHarnessService
from ..app.omlx_instance_service import OMLXInstanceService


def _resolve_models(args, config: dict) -> list[str]:
    models = list(getattr(args, "models", []) or [])
    if not models:
        return [config.get("omlx", {}).get("full_vision_model")]
    if len(models) == 1 and models[0].strip().lower() == "all":
        status = OMLXInstanceService().status(config)
        served_models = status.get("served_models") or []
        if served_models:
            return served_models
    return models


def cmd_harness_omlx(args, config):
    models = [model for model in _resolve_models(args, config) if model]
    if not models:
        raise RuntimeError("No harness models resolved from args or config.")

    service = OMLXHarnessService()
    summary = service.run(
        config,
        models=models,
        sample_set=getattr(args, "sample_set", None) or [],
        result_path=getattr(args, "result_path", None),
        limit=int(getattr(args, "limit", 12)),
        profile_mode=str(getattr(args, "profile_mode", "auto")),
        no_visual_merge=bool(getattr(args, "no_visual_merge", False)),
    )

    print(f"omlx harness complete: {summary['run_dir']}")
    print(f"report: {summary['report_path']}")
    print(f"request snapshot: {summary['request_path']}")
    print(f"config snapshot: {summary['config_snapshot_path']}")
    print(f"models: {', '.join(models)}")
    print(f"samples: {len(summary['sample_paths'])}")
    print(f"recommended order: {', '.join(summary['recommended_order'])}")
    for result in summary.get("results", []):
        print(
            f"{result['model']}: done={result.get('done_count')} "
            f"errors={result.get('error_count')} "
            f"invalid_post={result.get('invalid_post_count')} "
            f"invalid_group={result.get('invalid_group_issue_count')} "
            f"post_repeat={result.get('max_post_repeat')} "
            f"group_repeat={result.get('max_group_repeat')} "
            f"seconds_per_file={result.get('seconds_per_file')}"
        )
