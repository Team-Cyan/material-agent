"""Isolated, offline MobileCLIP experiment against a frozen local baseline.

Uses benchmark-local's service, never a production repository or XMP writer.
The checked checkpoint replaces only OpenCLIP's asset downloader; the official
pretrained tag still selects its original preprocessing configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import os
import resource
import statistics
import subprocess
import sys
import time
from unittest.mock import patch


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def worker(args):
    from material_agent.app.local_benchmark_service import run_local_benchmark

    config = json.loads(Path(args.baseline_config).read_text())
    config["semantic"] = {"enabled": False}
    samples = []
    execution = {}
    original_adapter = None
    if args.worker == "candidate":
        import open_clip
        import torch
        from importlib.metadata import version
        from material_agent.adapters.models.openclip_semantic import _OpenClipRuntime

        original_init = _OpenClipRuntime.__init__
        original_classify = _OpenClipRuntime.classify
        expected_pretrained = open_clip.get_pretrained_cfg("MobileCLIP2-S0", "dfndr2b")
        execution.update(
            model="MobileCLIP2-S0", pretrained="dfndr2b", asset_sha256=args.checkpoint_sha256,
            asset_revision=args.checkpoint_revision, pretrained_config=expected_pretrained,
            versions={p: version(p) for p in ("open-clip-torch", "torch", "torchvision", "timm")},
            torch_threads=torch.get_num_threads(), visual_input_devices=[], visual_output_devices=[],
        )

        def checked_asset(config, **kwargs):
            if config != expected_pretrained:
                raise RuntimeError("unexpected pretrained asset request")
            return str(Path(args.checkpoint).resolve())

        def devices(value):
            if isinstance(value, torch.Tensor):
                return [str(value.device)]
            if isinstance(value, (tuple, list)):
                return sorted({d for child in value for d in devices(child)})
            if isinstance(value, dict):
                return devices(list(value.values()))
            return []

        def initialize(self, **kwargs):
            started = time.perf_counter()
            original_init(self, **kwargs)
            execution["model_load_seconds"] = time.perf_counter() - started
            execution["preprocessing"] = repr(self.preprocess)
            execution["parameter_devices"] = sorted({str(p.device) for p in self.model.parameters()})

            def observed(module, inputs, output):
                execution["visual_input_devices"] = devices(inputs)
                execution["visual_output_devices"] = devices(output)

            self.model.visual.register_forward_hook(observed)

        def classify(self, image, prompts):
            started = time.perf_counter()
            result = original_classify(self, image, prompts)
            samples.append(time.perf_counter() - started)
            execution["prompt_bank_sha256"] = hashlib.sha256(
                json.dumps(prompts, ensure_ascii=False).encode()).hexdigest()
            return result

        original_adapter = (open_clip, _OpenClipRuntime, checked_asset, initialize, classify)
        config["semantic"] = {
            "enabled": True, "enforce_available": True, "model_name": "MobileCLIP2-S0",
            "pretrained": "dfndr2b", "device": "cpu", "min_confidence": 0.30,
        }

    out = Path(args.output_dir) / args.worker
    if original_adapter:
        module, runtime, asset, initialize, classify = original_adapter
        with patch.object(module.factory, "download_pretrained", asset), \
             patch.object(runtime, "__init__", initialize), \
             patch.object(runtime, "classify", classify):
            _, _, report = run_local_benchmark(args.manifest, out, repeat_count=args.repeat,
                                               client_config=config)
    else:
        _, _, report = run_local_benchmark(args.manifest, out, repeat_count=args.repeat,
                                           client_config=config)
    count = report["metrics"]["item_count"]
    warm = samples[count:]
    # Nearest-rank p95; small-sample uncertainty remains explicit.
    import math
    p95 = sorted(warm)[max(0, math.ceil(0.95 * len(warm)) - 1)] if warm else None
    evidence = {"reference_kind": args.reference_kind,
                "peak_rss_bytes": peak_rss_bytes(), "execution": execution,
                "warm_classify_p95_seconds": p95, "warm_classify_count": len(warm),
                "warm_classify_median_seconds": statistics.median(warm) if warm else None,
                "model_calls": len(samples)}
    (out / "execution-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")


def compare(baseline, candidate, base_evidence, candidate_evidence):
    count = baseline["metrics"]["item_count"]
    if ({r["id"] for r in baseline["items"]} != {r["id"] for r in candidate["items"]}
            or candidate["metrics"]["item_count"] != count):
        raise ValueError("baseline and candidate must contain identical items")
    rss_delta = candidate_evidence["peak_rss_bytes"] - base_evidence["peak_rss_bytes"]
    latency = candidate_evidence["warm_classify_p95_seconds"]
    return {
        "schema": "material-agent.single-model-experiment.v1",
        "candidate": "MobileCLIP2-S0", "reference_kind": candidate_evidence["reference_kind"],
        "item_count": count,
        "baseline_scene_accuracy": baseline["metrics"]["scene_accuracy"],
        "candidate_scene_accuracy": candidate["metrics"]["scene_accuracy"],
        "baseline_screenshot_separation": baseline["metrics"]["screenshot_photo_separation"],
        "candidate_screenshot_separation": candidate["metrics"]["screenshot_photo_separation"],
        "aggregate_score_equal": {r["id"]: r["score"] for r in baseline["items"]}
                               == {r["id"]: r["score"] for r in candidate["items"]},
        "deterministic": candidate["metrics"]["deterministic_scores"],
        "incremental_peak_rss_bytes": rss_delta,
        "warm_classify_p95_seconds": latency,
        "warm_classify_count": candidate_evidence["warm_classify_count"],
        "resource_gate_passed": rss_delta <= 2 * 1024**3 and latency is not None and latency <= 2,
        "promotion": "not_ready",
        "unmeasured": ["event_holdout_wrong_merge_rate", "independent_action_subject_coverage",
                       "human_preference", "Intel_target_performance"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--baseline-config", required=True, help="Local client config JSON")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--checkpoint-revision", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--reference-kind", required=True, choices=["model_generated", "human_reference"])
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--worker", choices=["baseline", "candidate"])
    args = parser.parse_args()
    if Path(args.checkpoint).suffix != ".safetensors":
        parser.error("retain the .safetensors suffix so OpenCLIP selects its safe tensor loader")
    if args.repeat < 2:
        parser.error("at least two repetitions are required")
    if sha256(args.checkpoint) != args.checkpoint_sha256:
        parser.error("checkpoint checksum mismatch")
    if len(args.checkpoint_revision) != 40 or any(c not in "0123456789abcdef" for c in args.checkpoint_revision):
        parser.error("checkpoint revision must be an immutable commit SHA")
    if args.worker:
        worker(args)
        return
    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        parser.error("output directory must be new or empty")
    out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    for phase in ("baseline", "candidate"):
        subprocess.run([sys.executable, __file__, *sys.argv[1:], "--worker", phase],
                       check=True, env=env, timeout=600)
    def load(phase, name):
        return json.loads((out / phase / name).read_text())
    summary = compare(load("baseline", "benchmark-report.json"), load("candidate", "benchmark-report.json"),
                      load("baseline", "execution-evidence.json"), load("candidate", "execution-evidence.json"))
    summary["inputs"] = {"manifest_sha256": sha256(args.manifest),
                         "baseline_config_sha256": sha256(args.baseline_config),
                         "checkpoint_sha256": args.checkpoint_sha256,
                         "checkpoint_revision": args.checkpoint_revision}
    (out / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
