from __future__ import annotations

import yaml

from ..app.local_benchmark_service import run_local_benchmark
from ..app.openvino_model_service import materialize_openvino_bundle
from ..utils.config_validator import normalize_config, validate_config


def cmd_benchmark_local(args) -> int:
    client_config = None
    if args.config:
        with open(args.config, encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
        validate_config(config)
        normalized = normalize_config(config)
        if normalized.get("backend") != "local":
            raise ValueError("benchmark-local --config requires backend: local")
        client_config = {
            **normalized.get("local", {}),
            "output_language": normalized.get("output_language", "en"),
            "inference": normalized.get("inference", {}),
            "preview": normalized.get("preview", {}),
        }
    json_path, markdown_path, report = run_local_benchmark(
        args.manifest,
        args.output_dir,
        repeat_count=args.repeat_count,
        reject_threshold=args.reject_threshold,
        quality_reject_threshold=args.quality_reject_threshold,
        client_config=client_config,
    )
    metrics = report["metrics"]
    print(f"Benchmark JSON: {json_path}")
    print(f"Benchmark Markdown: {markdown_path}")
    print(f"Deterministic scores: {metrics['deterministic_scores']}")
    return 0 if metrics["deterministic_scores"] else 1


def cmd_prepare_openvino_model(args) -> int:
    result = materialize_openvino_bundle(
        args.source_model,
        args.source_processor,
        args.output_dir,
    )
    print(f"OpenVINO bundle: {result['bundle_path']}")
    print(f"Model digest: {result['model_digest']}")
    return 0
