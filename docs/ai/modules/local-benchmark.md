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
between runs.

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
