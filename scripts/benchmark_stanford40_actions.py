"""Diagnostic zero-shot actions on a frozen subset of Stanford40's test split.

Reads JPEGs only; writes reports to a new directory. This is not a grouping,
personal-preference or event-disjoint acceptance benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time
from unittest.mock import patch

from benchmark_mobileclip_candidate import peak_rss_bytes, sha256


def select_test_subset(root, per_class=5):
    """Stable hash order, independent of labels' difficulty or model predictions."""
    splits = root / "ImageSplits"
    files = sorted(p for p in splits.glob("*_test.txt") if p.name != "test.txt")
    if len(files) != 40:
        raise ValueError("expected 40 official class test split files")
    selected = []
    for split in files:
        label = split.stem.removesuffix("_test")
        names = split.read_text().split()
        if len(names) < per_class or len(names) != len(set(names)):
            raise ValueError(f"invalid test split: {label}")
        train = set((splits / f"{label}_train.txt").read_text().split())
        if train.intersection(names):
            raise ValueError(f"train/test overlap: {label}")
        ordered = sorted(names, key=lambda name: hashlib.sha256(
            f"stanford40-diagnostic-v1:{name}".encode()).hexdigest())
        for name in ordered[:per_class]:
            if Path(name).name != name or name.rsplit("_", 1)[0] != label:
                raise ValueError("unexpected image filename")
            selected.append({"file": name, "action": label,
                             "sha256": sha256(root / "JPEGImages" / name)})
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--checkpoint-record", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-peak-rss-bytes", type=int, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("output directory must be new or empty")
    checkpoint = json.loads(args.checkpoint_record.read_text())
    if Path(checkpoint["path"]).suffix != ".safetensors":
        parser.error("checkpoint must retain its .safetensors suffix")
    if sha256(checkpoint["path"]) != checkpoint["sha256"]:
        parser.error("checkpoint checksum mismatch")
    rows = select_test_subset(args.dataset)
    labels = sorted({row["action"] for row in rows})
    prompts = [f"a photograph of a person {label.replace('_', ' ')}" for label in labels]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    protocol = {"schema": "material-agent.stanford40-diagnostic.v1",
                "reference_kind": "human_reference", "reference_source": "official class labels",
                "split": "official test, deterministic SHA256 order, five per class",
                "model": "MobileCLIP2-S0", "pretrained": "dfndr2b",
                "checkpoint_sha256": checkpoint["sha256"],
                "checkpoint_revision": checkpoint["revision"],
                "budgets": {"incremental_peak_rss_bytes": 2*1024**3, "warm_p95_seconds": 2,
                            "baseline_peak_rss_bytes": args.baseline_peak_rss_bytes},
                "prompts": dict(zip(labels, prompts, strict=True)), "items": rows,
                "limits": ["no verified event-disjoint split", "no grouping reference",
                           "no personal preference labels", "pretraining contamination unknown"]}
    # Freeze selection/prompts before importing or executing the candidate.
    (args.output_dir / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    import open_clip
    from PIL import Image
    from material_agent.adapters.models.openclip_semantic import _OpenClipRuntime

    expected = open_clip.get_pretrained_cfg("MobileCLIP2-S0", "dfndr2b")

    def pinned_asset(config, **kwargs):
        if config != expected:
            raise RuntimeError("unexpected pretrained request")
        return checkpoint["path"]

    with patch.object(open_clip.factory, "download_pretrained", pinned_asset):
        runtime = _OpenClipRuntime(model_name="MobileCLIP2-S0", pretrained="dfndr2b",
                                   device="cpu", cache_dir=None)
    results = []
    stop_reason = None
    for index, row in enumerate(rows):
        with Image.open(args.dataset / "JPEGImages" / row["file"]) as source:
            image = source.convert("RGB")
        started = time.perf_counter()
        probabilities = runtime.classify(image, prompts)
        elapsed = time.perf_counter() - started
        ranked = sorted(zip(labels, probabilities, strict=True), key=lambda pair: pair[1], reverse=True)
        results.append({**row, "predicted": ranked[0][0], "top5": [p[0] for p in ranked[:5]],
                        "confidence": ranked[0][1], "seconds": elapsed})
        if (index + 1) % 40 == 0:
            print(f"evaluated {index + 1}/{len(rows)}", flush=True)
        measured = sorted(row["seconds"] for row in results[1:])
        if peak_rss_bytes() - args.baseline_peak_rss_bytes > 2*1024**3:
            stop_reason = "incremental peak RSS exceeded 2 GiB"
        elif len(measured) >= 10 and measured[math.ceil(.95*len(measured))-1] > 2:
            stop_reason = "warm classify p95 exceeded 2 seconds"
        if stop_reason:
            break
    correct = sum(row["predicted"] == row["action"] for row in results)
    n = len(results)
    rate = correct / n
    z = 1.96
    center = (rate + z*z/(2*n)) / (1+z*z/n)
    half = z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n)) / (1+z*z/n)
    warm = sorted(row["seconds"] for row in results[1:])
    report = {"schema": protocol["schema"], "items": n, "classes": len(labels),
              "observed_reference_classes": len({row["action"] for row in results}),
              "completed": n == len(rows), "torch_threads": runtime.torch.get_num_threads(),
              "top1_correct": correct, "top1_accuracy": rate,
              "top1_wilson_95_interval_descriptive": [center-half, center+half],
              "top5_accuracy": sum(row["action"] in row["top5"] for row in results)/n,
              "warm_p95_seconds": warm[math.ceil(.95*len(warm))-1] if warm else None,
              "peak_rss_bytes": peak_rss_bytes(),
              "actual_parameter_devices": sorted({str(p.device) for p in runtime.model.parameters()}),
              "preprocessing": repr(runtime.preprocess), "results": results,
              "stop_reason": stop_reason, "planned_items": len(rows),
              "promotion": "not_ready", "limits": protocol["limits"]}
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"results", "preprocessing"}}, indent=2))


if __name__ == "__main__":
    main()
