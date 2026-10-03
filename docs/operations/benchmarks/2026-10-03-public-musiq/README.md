# Frozen MUSIQ technical-quality diagnostic

This step follows the [controller's complete NIMA self-review](../2026-10-03-public-nima/self-review.md).
It compares one unchanged existing MUSIQ checkpoint against the frozen heuristic
quality cohort. It does not train, fit calibration, tune thresholds, run the
production pipeline or change scoring/grouping defaults.

## Asset, runtime and exposure

The previously acquired single checkpoint `musiq_koniq_ckpt-e95806b9.pth` is
108,610,983 bytes with SHA256
`e95806b9eae5f3814c410f574ba8e552362bd5bc63d758ed5b97860f5d6185aa`.
The [earlier asset receipt](../2026-09-17-hdrplus-holdout/model-assets.json) and
[PyIQA weight source](https://huggingface.co/chaofengc/IQA-PyTorch-Weights)
identify it. Existing isolated runtime: Python 3.14.3, PyIQA 0.1.16, Torch 2.14.0,
torchvision 0.29.0, timm 1.0.29 and transformers 5.17.0. No new model weights or
packages are acquired for this step.

[Google's MUSIQ implementation](https://github.com/google-research/google-research/tree/master/musiq)
and [PyIQA's default configuration](https://github.com/chaofengc/IQA-PyTorch/blob/main/pyiqa/default_model_configs.py)
identify the KonIQ training target. Exact training/test image membership of this
checkpoint has not been audited against this corpus. Therefore **KonIQ metrics
are training-exposed pipeline diagnostics**, even if the script's partitions
have different IDs. KADID is a cross-dataset diagnostic with unaudited source-image
training overlap; it is not certified independent generalization evidence.

The installed MUSIQ architecture accepts an explicit local `pretrained_model_path`
without a second backbone weight. Unlike the production adapter's implicit model
lookup, this experiment passes the verified local file explicitly and denies
Python network/download calls during model loading and inference. It reports raw
MUSIQ scores without the application's normalization, score fusion or fallback.
Actual model parameters, input tensors and outputs must reside on CPU.

## Protocol frozen before inference

`protocol-summary.json` records the full local protocol hash, existing model
digest, unchanged parent baseline and NIMA partition identity. Exactly 1,024
KonIQ and 1,024 KADID images are retained, all 512×384. KonIQ partitions have
512 development / 512 comparison images; KADID has 530 / 494, with all 81 native
reference families kept in one partition (40 / 41 families). Parent labels and
NIMA aggregates were already inspected, so neither partition is a blinded test.

The CPU configuration is fixed to batch 1, four Torch threads and seed 0.
Preprocessing is RGB float32 NCHW `[0,1]` at native corpus resolution, with no
external resize. Installed PyIQA applies its default original/224/384 scales.
The source byte hashes match both the manifest and parent heuristic caches.

Predeclared bounds: at most 2,048 images, one 150 MB model, one million source
pixels per image, 1,800 seconds per process, 2.5 GB observed peak RSS and eight
failures before stopping. Resource stops/incomplete cohorts receive explicit
status and cannot supply a valid improvement delta or confidence interval.
These controls do not prove deployment latency or Intel runtime compatibility.
The runner's elapsed timer starts at run entry after CLI imports, covering
preflight, runtime/model initialization, scoring, checks, statistics and writes.

PLCC/SROCC use native targets and the exact same paired denominator. For each
track and development/comparison/all partition, use 2,000 paired percentile
bootstrap draws, seed 20261003, to describe 95% intervals for the candidate-minus-
heuristic PLCC/SROCC. KADID draws sample complete reference families with
replacement, carrying every selected member together; KonIQ draws image IDs.
The same draw indexes feed both predictors and labels. Invalid constant draws
are reported explicitly. Intervals quantify sampling uncertainty conditional on
this frozen corpus; they do not address training overlap, label reliability or
semantic dependence among KonIQ images.

## Recovery and interpretation

Full protocols, source media/labels, per-image predictions, runtime caches and
controller receipts stay under ignored local roots. Each completed prediction
is saved atomically with input/model/protocol/code/runtime identity. Resume may
reuse only successful intact matching records; failures retry. Parent artifacts
stay unchanged. Shared global model caches are not experiment outputs.

Regenerate the full protocol from the checked-in summary and unchanged NIMA
item recipe, then verify the resulting hash before running:

```python
import json
from pathlib import Path
from scripts.benchmark_public_nima import base, hash_file

summary = json.loads(Path("docs/operations/benchmarks/2026-10-03-public-musiq/protocol-summary.json").read_text())
reference = json.loads(Path(".local/public-nima-20261003/protocol.json").read_text())
plan = {k: v for k, v in summary.items()
        if k not in {"cohort_counts", "items_sha256", "protocol_sha256"}}
plan["items"] = reference["items"]
output = Path(".local/public-musiq-20261003/protocol.json")
base.atomic_json(output, plan)
assert hash_file(output) == summary["protocol_sha256"]
```

Use the existing isolated quality runtime, which must contain the audited
PyIQA/Torch versions, rather than acquiring a different environment:

```sh
.local/phase2-quality-env/bin/python scripts/benchmark_public_musiq.py \
  --root .local/public-benchmark-20261002 \
  --manifest .local/public-benchmark-20261002/composite-manifest.json \
  --baseline .local/public-benchmark-20261002/baseline-1024/report.json \
  --protocol .local/public-musiq-20261003/protocol.json \
  --model-path .local/hdrplus-holdout/torch-cache/hub/pyiqa/musiq_koniq_ckpt-e95806b9.pth \
  --reference-protocol .local/public-nima-20261003/protocol.json \
  --reference-model .local/inference-unification/assets/nima.tflite \
  --output .local/public-musiq-20261003/run
```

The reference protocol/model are read-only cohort-validation inputs; this command
does not rerun NIMA. A controller subprocess deadline additionally bounds native
calls that may defer Python signal delivery. A quota/process interruption preserves
completed prediction files for this same command to resume.

## Measured results and decision

The [aggregate receipt](results.json) records 2,048 successful raw CPU predictions,
zero failures/fallbacks, no resource stop and first-pass cache reuse zero. The
exact same command then reused all 2,048 predictions with identical identity,
provenance, semantic digest, metrics and confidence intervals. All twelve
baseline/MUSIQ correlation pairs and all six paired-bootstrap interval sets were
independently recomputed with SciPy within tolerance 1e-12. Every interval uses
2,000 valid draws, with zero invalid draws in this actual run.

| Dataset / partition | Images | Heuristic SROCC | MUSIQ SROCC | Heuristic PLCC | MUSIQ PLCC | Delta SROCC 95% interval vs heuristic |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| KonIQ / all | 1,024 | 0.3643 | 0.8695 | 0.3846 | 0.8984 | +0.4525 to +0.5578 |
| KonIQ / development | 512 | 0.3838 | 0.8708 | 0.3985 | 0.9024 | +0.4129 to +0.5604 |
| KonIQ / comparison | 512 | 0.3442 | 0.8672 | 0.3677 | 0.8946 | +0.4471 to +0.5998 |
| KADID / all | 1,024 | 0.0694 | 0.5487 | 0.0746 | 0.5648 | +0.3935 to +0.5610 |
| KADID / development | 530 | 0.0739 | 0.5119 | 0.0666 | 0.5511 | +0.3334 to +0.5467 |
| KADID / comparison | 494 | 0.0656 | 0.5964 | 0.0770 | 0.5811 | +0.4045 to +0.6481 |

KonIQ scores remain training-exposed diagnostics; their intervals do not cure
training contamination. KADID shows a positive conditional improvement over the
fixed heuristic under reference-family resampling. Source-image overlap remains
unaudited, and this is not an official leaderboard or directed-coverage test.
The earlier raw NIMA KADID SROCC was 0.3630 on these same images; no paired
MUSIQ-minus-NIMA confidence interval was tested in this protocol.

Observed run-entry elapsed time was 316.71 seconds, including bootstrap and
stability checks; observed peak RSS was 988,086,272 bytes, under the 2.5 GB bound.
Per-prediction scoring/validation/checksum p50/p95 was 163.77/167.67 ms. The lean
Intel image excludes Torch/PyIQA, so these local CPU observations do not establish
deployability or throughput on the production stack. Retain MUSIQ as a diagnostic
quality candidate; evaluate a compatible runtime and product-level utility
before any default, fusion or rejection change.

Full local tests passed (1,167 passed / 10 skipped), with lint. Independent protocol,
code and final aggregate/document/plan reviews passed with no must-fix findings.
Explicit cache/tmp paths preserve `HOME` and environment
restoration is verified. Frozen input/model/source checks and error recovery
are verified by tests and the actual run/resume.

Next evaluate copy correspondence against the frozen 157-original / 229-strong-
query gallery, using one existing embedding candidate after asset/exposure checks.
Keep training, fitting and grouping-policy changes out of that comparison.
Technical-quality runtime feasibility, G1/G2 directed coverage acceptance and
unsupported AlbumBench prediction remain separate.
