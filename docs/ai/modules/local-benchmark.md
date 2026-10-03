# Local Benchmark Module Contract

## Purpose

This module provides an isolated, report-only evaluation path for local scoring
implementations. It exists so model and policy changes can be compared before
they enter the production review pipeline.

## Main Files

- `src/material_agent/app/local_benchmark_service.py`
- `src/material_agent/commands/benchmark.py`
- `docs/ai/templates/local-benchmark-manifest.yaml`
- `tests/test_local_benchmark.py`

## Responsibilities

- validate a versioned YAML fixture manifest;
- resolve fixture paths relative to the manifest;
- decode supported proprietary RAW files through the production embedded-preview
  path while accepting JPEG/PNG fixtures directly;
- run the selected local scorer repeatedly;
- calculate group top-1, pairwise, reject, scene, and non-photo metrics;
- record scorer/runtime provenance and manifest digest;
- write machine-readable JSON and generated Markdown reports;
- detect score or scene nondeterminism between repeated runs.
- clear the bounded in-process embedding-result cache before every repetition so
  warm timings still execute model inference instead of measuring a result-cache hit.

## Non-Goals

- production XMP writes;
- production SQLite sessions or resumability;
- downloading private fixtures or model weights;
- choosing score calibration thresholds without reviewed labels;
- treating elapsed-time equality as a determinism requirement.

## Isolation Invariant

`benchmark-local` must not construct a production runtime repository, processed
repository, or XMP writer. Reports go only to the explicit output directory.
This differs from `run --dry-run`, which still records runtime job state.
For read-only Docker pilots, mount the photo library read-only and set
`MATERIAL_AGENT_WORK_DIR` to a writable appdata volume so that dry-run state and
logs never land beside the source photos.

## Manifest Contract

The current schema is `material-agent.local-benchmark.v1`. Every item requires
an ID, image path, and group. Relative paths are preferred for portable public
fixtures; absolute paths are accepted for ignored private manifests. Optional reviewed labels cover scene,
face presence, non-photo status, and reject intent. Group preferences and
pairwise preferences reference item IDs.

Private fixtures should live outside Git with a checked-in manifest only when
paths can remain portable. Public or synthetic fixtures may be checked in when
their license and repository-size impact are known.

## Report Contract

JSON is the authoritative artifact. Markdown is a generated summary. A report
must include:

- schema and manifest version/digest;
- actual scoring mode and runtime;
- Python/platform provenance;
- repeat count and reject threshold;
- quality metrics and determinism result;
- per-item dimensions, score, scene, and provenance.
- per-item input decode format, preview source, original size, and preview size.

Timing fields are observational and are not expected to be byte-identical
between runs. A persistent compiled-model cache may remain warm across
repetitions; the per-image embedding-result cache may not. The corrected
OpenVINO CPU synthetic report is
`docs/operations/benchmarks/2026-07-13-openvino-dinov3-quantized-cpu-synthetic-v2/`.
The older 2026-07-11 v1 report is retained as history, but its 0.07-second warm
timing is cache-contaminated and must not be used as throughput evidence.

## Safe Extension Order

1. Add new optional labels without invalidating v1 manifests.
2. Add model-specific predictions to per-item results.
3. Calculate a metric only when both labels and predictions exist.
4. Introduce a new schema version for incompatible field changes.

## Minimal Verification

```bash
uv run pytest tests/test_local_benchmark.py tests/test_main.py
uv run ruff check src/material_agent/app/local_benchmark_service.py \
  src/material_agent/commands/benchmark.py tests/test_local_benchmark.py
```

## Public composite diagnostics

`scripts/prepare_public_composite.py` and `scripts/benchmark_public_composite.py`
use the separate `material-agent.public-composite.v1` schema. They preserve
native KonIQ MOS, KADID DMOS, Copydays correspondences and AlbumBench tasks;
they do not extend or reinterpret the local-benchmark v1 reject labels.
Media, raw targets and feature checkpoints stay in an ignored local corpus.
Preparation bounds compressed input to 8 GB and expanded archives to 15 GB,
validates joins and freezes per-image checksums. The runner has deterministic
bounded selection, preserves the complete copy gallery, and reports native
metrics separately. Missing query-conditioned predictions remain unsupported.

See the [frozen protocol and recovery commands](../../operations/benchmarks/2026-10-02-public-composite/README.md).
Verify changes with `tests/test_prepare_public_composite.py`,
`tests/test_public_composite.py` and the existing local-benchmark checks.

`scripts/benchmark_public_nima.py` compares the pinned existing native aesthetic
adapter against that unchanged heuristic quality cohort. Its separate frozen
protocol keeps KADID reference families in one development/comparison partition;
the labels were already available, so these are not blinded holdouts. It accepts
only a non-empty, at most 50 MB, single-file TFLite model with `TFL3` magic and
verifies model, input, protocol, parent-cache, code and runtime identities.
Each successful native CPU prediction is atomic and resumable; missing execution
evidence, invalid distributions or errors cannot become fallback scores or valid
improvement deltas. It writes only experiment-owned outputs/caches, reports raw
aesthetic/native-MOS agreement, and does not change production scoring or G1/G2.
See the [fixed comparison and measured limits](../../operations/benchmarks/2026-10-03-public-nima/README.md).
Verify runner changes with `tests/test_public_nima.py` and the parent checks.

`scripts/benchmark_public_musiq.py` pins a separate single-checkpoint protocol and
reads the NIMA protocol/model only to validate the unchanged heuristic cohort.
It initializes the existing PyIQA metric offline with an explicit local weight;
experiment-owned cache/tmp paths preserve `HOME`. Actual CPU parameters/tensors,
threads, seed and deterministic state are checked. Raw technical-quality scores
are separate from deployed normalization/fusion. KonIQ remains training-exposed.
The 2,000-draw paired percentile bootstrap uses identical indexes for predictor,
heuristic and target, with entire KADID reference families sampled together.
Any failure, budget stop or identity drift invalidates the run's deltas/intervals.
Atomic successful records resume only with intact matching identities. The
controller must also supply the frozen external process deadline because native
calls may defer Python signals. See the [protocol, bounds and results](../../operations/benchmarks/2026-10-03-public-musiq/README.md).
Verify changes with `tests/test_public_musiq.py` and the immutable helper tests.

`scripts/benchmark_public_copydays.py` compares one pinned existing OpenVINO
embedding with the immutable pHash operator on all 157 gallery originals and
229 strong queries. CPU execution, no fallback, normalized finite vectors,
protocol/source/model/parent identities and output isolation are mandatory.
The frozen parent runtime is distinct from actual target runtime provenance;
`COPYDAYS_PROTOCOL_SHA256` must come from a reviewed controller package index.
Successful atomic predictions resume only with intact identities. Incomplete
runs cannot publish valid deltas/intervals. Paired bootstrap resamples complete
native source families with the gallery fixed. Correspondence does not authorize
semantic grouping, directed coverage or rejection. Verify with
`tests/test_public_copydays.py`; see the [target runtime results](../../operations/benchmarks/2026-10-03-unraid-public/README.md).

The homelab controller owns authorized target transport/deployment through its
fixed approved-plan wrapper. Source files and models are root-owned read-only;
experiments run unprivileged with separate reports/caches and process deadlines.
The native default-stack pilot uses the baked configuration with only compilation
cache paths relocated; reviewed culling labels are not inferred from MOS or copies.
