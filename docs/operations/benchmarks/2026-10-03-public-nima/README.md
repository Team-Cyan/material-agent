# Fixed NIMA component comparison

This step continues the user's reviewed-step-and-push workflow. It compares the
existing native NIMA aesthetic component with the frozen public-composite
heuristic baseline. No weights are downloaded, no model is trained, and no
production setting, runtime database or photo metadata is changed.

## Asset and target provenance

The existing asset matches the Docker pin: 6,448,632 bytes, SHA256
`a5051a0fcced735682735e3e0fd58ee54c83ed664282a003f52235b3dbcb9320`.
Repository/cache provenance records `litert-community/NIMA-LiteRT` revision
`15308061b353e9ef1de4c9d33b8f0fab0a7e350e`, model version
`litert-community-15308061`. OpenVINO 2026.2.1 can read its dynamic-batch
224×224 RGB NHWC input and ten rating buckets on CPU.

The [exporter's model card](https://huggingface.co/litert-community/NIMA-LiteRT)
identifies the aesthetic variant as MobileNet trained on AVA. Its
[upstream implementation](https://github.com/idealo/image-quality-assessment)
distinguishes AVA aesthetics from TID2013 technical quality. The
[NIMA paper](https://research.google/pubs/nima-neural-image-assessment/)
predicts an opinion-score distribution. This run uses the aesthetic variant's
raw distribution expectation, with the application's existing preprocessing and
without target calibration or score fusion.

KonIQ MOS and KADID DMOS measure visual quality, so this is a component diagnostic
across related targets, not aesthetic ground-truth validation. No training-image
overlap audit against AVA/ImageNet is available. The upstream card's current
contents were reviewed; the pinned card itself was inaccessible through the web
reader here. Asset identity comes from the locally verified file and Docker pin.
Do not claim independent generalization or compare these numbers directly with
published leaderboard metrics.

## Frozen comparison

The [parent corpus and baseline](../2026-10-02-public-composite/README.md) are
preserved. Exactly the same 2,048 labeled quality images are compared. Copydays
and AlbumBench retain their earlier result/unsupported status and are not rerun.

`protocol-summary.json` records the full local protocol's hash, parent identity,
model digest and partition algorithm. KonIQ image IDs are sorted by
SHA256(`public-quality-partition-v1:` + ID); the first half is development and
the remainder comparison (512 / 512). KADID reference IDs use the same ordering;
the first 40 reference families are development and the other 41 comparison
(530 / 494 sampled images). A reference and every selected distortion derived
from it stay in one partition. This is a deterministic family boundary for
KADID; semantic independence among KonIQ images has not been established.

These are diagnostic partitions. The parent aggregate and labels were already
available before this step, so the comparison partition is not a blinded test.
The model, CPU device, batch size 1 and preprocessing are fixed before inference.
No parameters or thresholds are fitted on either partition.

NIMA and the baseline use the exact same cohort. Native PLCC/SROCC are reported
per dataset and partition, along with failure counts. An incomplete NIMA cohort
cannot receive a valid improvement delta. Missing execution evidence, invalid
distributions or model errors are failures, never heuristic fallback scores.
Timing is an observational first pass including startup, not a throughput gain
claim or evidence about Intel deployment.

## Execution and recovery

Full protocols, source IDs, per-image predictions and compiled caches stay under
ignored local roots. The runner validates frozen model/data/protocol/baseline
identities before writing. This scoped runner accepts only a non-empty single-file
TFLite model of at most 50 MB with the `TFL3` identifier; multi-file model containers are rejected.
Each completed inference is checkpointed atomically.
Resume verifies integrity and reuses only matching successful predictions;
failure records are retried. The compiled cache belongs to this experiment.

Regenerate the same full protocol from the unchanged parent artifacts and
verify its hash against `protocol-summary.json` before scoring:

```python
import json
from pathlib import Path
from scripts.benchmark_public_nima import base, freeze_protocol, hash_file

root = Path(".local/public-benchmark-20261002")
model = Path(".local/inference-unification/assets/nima.tflite")
manifest = json.loads((root / "composite-manifest.json").read_text())
baseline = json.loads((root / "baseline-1024/report.json").read_text())
protocol = freeze_protocol(manifest, baseline, hash_file(model), "litert-community-15308061")
base.atomic_json(Path(".local/public-nima-20261003/protocol.json"), protocol)
```

```sh
uv run --no-sync python scripts/benchmark_public_nima.py \
  --root .local/public-benchmark-20261002 \
  --manifest .local/public-benchmark-20261002/composite-manifest.json \
  --baseline .local/public-benchmark-20261002/baseline-1024/report.json \
  --protocol .local/public-nima-20261003/protocol.json \
  --model-path .local/inference-unification/assets/nima.tflite \
  --output .local/public-nima-20261003/run
```

## Measured results and decision

The [aggregate receipt](results.json) records a completed native CLI run: 2,048
successful CPU predictions, zero failures and no fallback. Exact-command resume
reused all 2,048 predictions with identical identity, semantic record digest,
provenance and metrics. All six dataset/partition NIMA PLCC/SROCC pairs were
independently recomputed from cached predictions within tolerance 1e-12.

| Dataset / partition | Images | Heuristic SROCC | NIMA SROCC | Heuristic PLCC | NIMA PLCC |
| --- | ---: | ---: | ---: | ---: | ---: |
| KonIQ / all | 1,024 | 0.3643 | 0.2806 | 0.3846 | 0.2929 |
| KonIQ / development | 512 | 0.3838 | 0.2838 | 0.3985 | 0.2871 |
| KonIQ / comparison | 512 | 0.3442 | 0.2773 | 0.3677 | 0.2976 |
| KADID / all | 1,024 | 0.0694 | 0.3630 | 0.0746 | 0.3491 |
| KADID / development | 530 | 0.0739 | 0.3142 | 0.0666 | 0.2871 |
| KADID / comparison | 494 | 0.0656 | 0.4221 | 0.0770 | 0.4231 |

NIMA improves agreement on sampled synthetic distortions but regresses on sampled
in-the-wild KonIQ quality. These are point estimates without confidence intervals.
The evidence does not support replacing the heuristic quality score with this
raw aesthetic component. It does not evaluate the deployed scoring/fusion policy.
Next inspect an existing technical-IQA candidate's assets and training exposure,
then freeze one comparison on these same inputs before executing it. KonIQ-trained
models cannot provide independent KonIQ generalization evidence. Keep copy
retrieval improvement as a separately frozen experiment with its own target.

The first pass took 18.38 seconds including preflight, startup, inference and
writes, with concurrent tests; this is observational, not a speedup measurement.
Full local tests passed (1,125 passed / 10 skipped), with Ruff. Independent code
review found a multi-file model identity gap; the runner now rejects those
containers before writing, and the fix passed independent re-review.
Final aggregate, provenance, recovery and plan review passed with no must-fix
findings.
Native quality agreement cannot pass G1/G2, certify safe deletion, or authorize
production model changes. Per-image predictions and inputs remain local.

The inherited `d746815` commit's
[CI run](https://github.com/Team-Cyan/material-agent/actions/runs/37018657320)
passed quality (1,068 passed / 43 skipped), image publication, immutable smoke
and verified promotion. No deployment occurred.
