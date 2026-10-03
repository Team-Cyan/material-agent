# Frozen public benchmark on the Unraid runtime

The user explicitly authorized corpus storage on Unraid, latest-version
deployment and real-environment testing. Native DockerMan deployed reviewed
image revision `098ccb044e9c1bc642baf132ebf1c5ab30d28319`; template backup,
previous registry digest, rollback plan and operation receipts stay in the
homelab controller. The input mount remains read-only. No production scoring,
grouping or discard setting was promoted from these experiments.

[Results](results.json) are aggregate evidence; the [protocol summary](protocol-summary.json)
omits individual IDs and labels. Media, complete protocol, predictions, logs
and recovery checkpoints stay outside Git.

## Corpus and execution

The existing composite corpus now has a verified target copy: 20,965 actual
media files, 23,414 total files including original CSV/manifest, frozen parent
feature records, model assets, protocols and two experiment scripts. Content is
4,164,688,472 bytes on SSD appdata. The package excludes 136 macOS metadata files;
original inputs were retained. Whole-package and per-file SHA256 verification
passed, followed by root-owned read-only permissions. Reports/caches use a
separate writable experiment directory. Every target run checks the full corpus
before and after execution and runs as UID/GID 99:100.

The application repository owns algorithm code, protocols and metrics. The
homelab controller owns fixed-root transport, approved storage plans, audit and
native DockerMan operations. Its documented `material-public-benchmark.py`
wrapper has no arbitrary command/path interface; it provides fixed `baseline`,
`copydays` and `stack` variants with process-group deadlines and RSS observation.
API idleness is checked before execution; these experiments do not acquire the
production scheduler lease and should not overlap a user-started analysis.

The immutable baseline reran all 2,434 selected images: 1,024 KonIQ, 1,024 KADID,
157 Copydays gallery originals and 229 strong queries, with zero failures.
Selected IDs/input hashes match the original baseline. Copy metrics are exact;
quality correlation differences are at most `2.22e-16` floating-point rounding.
AlbumBench's 5,124 retained tasks remain unsupported; image/query prediction
acceptance is not claimed.

## One fixed embedding candidate

The existing standard-operator quantized DINOv3 ViT-S/16 bundle consists of:

| Asset | Bytes | SHA256 |
| --- | ---: | --- |
| ONNX graph | 183,889 | `7686e8c849202c4fdd67d1cd336449c29bdddbcca535d765d3014f50d04d516d` |
| External weights | 21,762,048 | `51572f7fc3c272eb574a70509ea1eeb7e674e5ca2cd96fec1632edb38983d529` |
| Processor | 585 | `960c41d1f3a7778b936365769a2d90550b318a6c0a53a0296957adacfe5e0dd7` |

The [DINOv3 model card](https://github.com/facebookresearch/dinov3/blob/main/MODEL_CARD.md)
describes LVD public-image pretraining. Exact Copydays training overlap is
unknown. The existing local bundle does not record the upstream immutable export
revision or quantization recipe; these exact local bytes are pinned. This is a
fixed-corpus diagnostic, not training-isolated generalization.

`scripts/benchmark_public_copydays.py` uses the installed production
`OpenVinoEmbeddingAdapter`, with native CPU, batch/request 1, no fallback,
224×224 RGB ImageNet preprocessing and L2-normalized CLS vectors. It ranks
cosine similarity descending, then lexicographic gallery ID; pHash uses Hamming
distance ascending with the same tie rule. No thresholds, fusion or calibration
were fitted. The full 157-image gallery is retained for every query.

Protocol SHA256 is
`519ecb1a6f5f1d1c0858ec515731264f1be79f08439ca8df1f74e13db729b4b5`.
`COPYDAYS_PROTOCOL_SHA256` must come from the controller-approved package index.
The original baseline Python/NumPy/Pillow/ImageHash pins remain in the protocol;
target versions belong to the candidate identity. This allows a legitimately
different Linux runtime without relaxing source/cache integrity checks.

| Predictor | Top-1 | MRR | First-place ties |
| --- | ---: | ---: | ---: |
| Frozen pHash | 47/229 = 0.2052 | 0.2558 | 87 |
| Frozen DINOv3 | 191/229 = 0.8341 | 0.8792 | 0 |

Paired bootstrap samples all 157 native source families, including every query
member of each chosen family, while keeping the gallery fixed. With 2,000 draws
and seed 20261003, top-1 delta is `+0.6288`, 95% percentile interval
`[+0.5636, +0.6936]`; MRR delta is `+0.6234`, interval `[+0.5654, +0.6807]`.
These intervals describe conditional corpus uncertainty, not training exposure,
semantic grouping safety or reliable discard evidence.

All 386 predictions succeeded with actual CPU readback and zero fallback.
First run-entry elapsed time was 46.37 seconds and observed peak RSS
1,055,096,832 bytes, under the frozen 1,800-second / 2 GB limits. The timer includes
preflight/model/scoring/statistics but excludes initial CLI imports; it is not a
controlled throughput comparison. Exact-command resume reused all 386 records
with identical identity, provenance, ranks, metrics, intervals and semantic digest.

## Current default scoring stack

The baked NIMA/SSD/YuNet profile ran two repetitions on 256 deterministic public
quality fixtures: the first 128 IDs per quality track within the unchanged parent
cohort. Only compilation-cache paths differ from the baked configuration. No
reviewed scene, preference, reject or culling labels were invented.

All 256 NIMA and SSD records have successful native CPU execution and no fallback.
YuNet's model-specific records succeeded for all 256, but actual device readback
is missing; its device remains `unknown`. Scores were deterministic across the
two repetitions. Total in-service benchmark time was 31.89 seconds: cold 18.69,
warm 13.20, observational 16.06 images/second and wrapper-observed peak RSS
579,842,048 bytes. Repetitions clear result caches; the compiled model cache can
remain warm. This measures runtime/determinism, not photographic selection quality.

## Verification and recovery

Controller self-review corrected original-parent runtime portability and transport
compatibility before inference. Separate reviewer and implementation sessions hit
their usage limit; the controller completed saved work. Do not describe this as
a completed independent code review. Application checks passed 1,183 / ten skipped;
50 controller-wrapper checks and lint passed.

A separate verification script recomputed every source/record checksum, all
386 pHashes and native execution facts, all 229 ranks using SciPy cosine distance,
all aggregate metrics and family-expanded bootstrap intervals within `1e-12`.
First/resume semantic digest and identities match. Its script SHA256 is
`45236779ed184e8d28cad9618be49536ae2abb8635f7ee7783a34c39642e508f`.
The original 40,620 indexed/scored library records, zero errors and idle task state
are unchanged after testing; the service remains reachable and photos read-only.

Recovery uses ignored `.local/unraid-benchmark-20261003/` inputs/results and the
controller's approved package plan/receipts. Partial transport and successful
predictions are retained. Generate the complete protocol with `build_protocol`
from the exact parent corpus, baseline and pinned assets, verify its hash, then
use the documented controller's fixed variants. No target state or credentials
belong in this public repository.

Next evaluate technical-quality runtime feasibility on Intel for the existing
MUSIQ candidate in a separate bounded environment. The lean production image
still excludes Torch/PyIQA. Grouping, directed-coverage G1/G2 references, real
culling utility and professional-tool XMP round trips remain separate acceptance
work; this copy diagnostic does not pass those gates.
