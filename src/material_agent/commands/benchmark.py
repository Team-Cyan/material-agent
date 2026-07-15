from __future__ import annotations

import json
from pathlib import Path

import yaml

from ..app.aesthetic_calibration_service import fit_aesthetic_calibration
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


def cmd_fit_aesthetic_calibration(args) -> int:
    with open(args.labels, encoding="utf-8") as labels_file:
        payload = yaml.safe_load(labels_file)
    calibration, report = fit_aesthetic_calibration(
        payload,
        minimum_label_count=args.minimum_label_count,
        minimum_raw_span=args.minimum_raw_span,
        pivot=args.pivot,
        policy_version=args.policy_version,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(calibration, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"Calibration YAML: {output_path}")
    print(f"Labels: {report['total_labels']}; fitted profiles: {report['fitted_profiles']}")
    return 0 if report["fitted_profiles"] > 0 else 2
