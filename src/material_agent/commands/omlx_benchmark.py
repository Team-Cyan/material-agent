from __future__ import annotations

from ..app.omlx_benchmark_service import OMLXBenchmarkService
from ..app.omlx_instance_service import OMLXInstanceService


def _coerce_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


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


def cmd_benchmark_omlx(args, config):
    models = [model for model in _resolve_models(args, config) if model]
    if not models:
        raise RuntimeError("No benchmark models resolved from args or config.")

    service = OMLXBenchmarkService()
    summary = service.run(
        config,
        models=models,
        mode=args.mode,
        repeat_count=args.repeat_count,
        sample_set=getattr(args, "sample_set", None),
        result_path=getattr(args, "result_path", None),
        contract_modes=getattr(args, "contract_modes", None),
        prompt_presets=getattr(args, "prompt_presets", None),
        vision_temperatures=getattr(args, "vision_temperatures", None),
        commentary_temperatures=getattr(args, "commentary_temperatures", None),
        vision_max_tokens=getattr(args, "vision_max_tokens", None),
        post_commentary_max_tokens=getattr(args, "post_commentary_max_tokens", None),
        image_max_edges=getattr(args, "image_max_edges", None),
        vision_jpeg_qualities=getattr(args, "vision_jpeg_qualities", None),
        enable_thinking_options=(
            [_coerce_bool(value) for value in args.enable_thinking_options]
            if getattr(args, "enable_thinking_options", None)
            else None
        ),
    )

    print(f"omlx benchmark complete: {summary['run_dir']}")
    print(f"mode: {summary['mode']}")
    print(f"models: {', '.join(models)}")
    print(f"samples: {', '.join(summary['sample_paths'])}")
    print(f"attempt log: {summary['attempts_path']}")
    runtime_support = summary.get("runtime_contract_support", {})
    if runtime_support:
        print(
            "runtime: "
            f"server_version={runtime_support.get('server_version')} "
            f"xgrammar={runtime_support.get('xgrammar_available')} "
            f"structured_outputs={runtime_support.get('structured_outputs_available')}"
        )
    for model, best in summary.get("best_by_model", {}).items():
        candidate = best["candidate"]
        contract_execution = best.get("contract_execution", {})
        print(
            f"{model}: schema_success={best['overall_schema_success_rate']:.2%} "
            f"avg_latency_ms={best['overall_average_latency_ms']:.2f} "
            f"contract_mode={candidate['contract_mode']} prompt_preset={candidate['prompt_preset']} "
            f"constraint_path={contract_execution.get('effective_constraint_path', 'unknown')}"
        )
        if best["mode"] == "single_fixture":
            print(f"{model}: post_quality_average={best['post_quality_average']:.2f}/5.00")
