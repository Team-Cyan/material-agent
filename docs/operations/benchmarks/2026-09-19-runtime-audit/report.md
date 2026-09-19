# Bounded complexity, efficiency and stability audit

The project did become more complex, but most new repository volume is offline
evidence. Runtime growth is smaller and has a measurable cost in the tested
learned-model path. This audit does not claim zero regression or production
acceptance.

## Baseline and inventory

Baseline `9de0e41` is the verified parent of the first inference-unification
commit `1d76f1e`. Comparison head is `09c5882`; this covers the whole migration,
grouping/selection and XMP work, not just the latest research commits.
[Machine-readable measurements](measurements.json) include Git IDs, inputs,
asset hashes, runtime versions, every trial and ranges. Counts use tracked Git
blobs; text lines include Python, Markdown, JSON, YAML, TOML and shell files,
not semantic complexity or executable instruction counts.

| Tree | Before → after files | Before → after text lines | Before → after bytes |
| --- | ---: | ---: | ---: |
| src | 130 → 133 | 21,921 → 22,943 (+4.7%) | 869,035 → 908,462 |
| scripts | 1 → 15 | 21 → 2,800 | 687 → 116,103 |
| tests | 62 → 74 | 19,378 → 21,274 | 12,301,857 → 12,378,204 |
| docs | 89 → 190 | 12,090 → 139,878 | 537,466 → 4,548,280 |

`pyproject.toml` and `uv.lock` are unchanged across this interval. No new default
model dependency was introduced. Generic defaults still use local heuristics;
the baked Intel profile still enables SSD/YuNet and NIMA CPU. Embeddings and
screening remain disabled there; selective refinement is opt-in. Grouping changed
to adjacent time AND hash as requested, with zero threshold meaning time-only.

`.dockerignore` allowlists runtime src/config/docker assets and excludes offline
scripts, tests and docs. The wheel target contains only `src/material_agent`.
No src references to direct-coverage, observability or spatial-reference research
scripts were found. Their growth affects repository/review maintenance, not
per-photo execution or the runtime image payload.

## Same-machine measurements

Reused `run_local_benchmark` with the four existing synthetic PNG fixtures;
no new media, model download, production review, SQLite or XMP operation.
Both revisions ran with the same interpreter, packages, input/model bytes and
settings on Darwin arm64. Baseline src was extracted to an ignored directory;
imports were verified to come from that directory. Three fresh processes per
profile/revision, alternated AB/BA/AB, five repetitions per process. Persistent
compiled caching was disabled on both sides; result caches were cleared before
each repetition, with normal within-repetition NIMA priming reuse preserved.
Numbers below are medians across three process trials, not confidence intervals.

| Metric | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| Heuristic warm, four images | 67.753 ms | 67.869 ms | +0.17%; effectively flat in this small sample |
| Learned warm, four images | 203.600 ms | 218.145 ms | +7.14%; observed overhead, not a universal throughput estimate |
| Learned first repetition | 1.344 s | 1.531 s | +13.9%; compile/startup sensitive, ranges overlap |
| Learned process peak RSS | 660.8 MB | 672.9 MB | +12.1 MB / 1.83%; process peak, not steady-state allocation |
| Heuristic process peak RSS | 102.2 MB | 103.5 MB | +1.3 MB |
| CLI `--help`, five fresh processes | 39.93 ms | 38.72 ms | No startup regression observed; help avoids model initialization |

Both configurations have exact score, dimensions and scene parity for these
inputs and deterministic scores in every repetition. In each learned process,
both versions initialized NIMA once and SSD once, performed 20 input loads and
20 detection calls, and performed five NIMA batch calls for 20 photo scores.
Thus per-image score cache reuse did not silently replace the intended warm
model inference. These counters do not prove behavior under arbitrary concurrent
clients or long production runs.

A separate diagnostic cProfile run on the same 20-score workload recorded 125
`runtime_version` calls taking about 44 ms cumulative in the current client.
The baseline did not have that helper. Current `_cached_model_results` main-thread
cumulative work was about 39 ms versus about 4 ms for baseline `score_aesthetics`.
This identifies identity/provenance lookup as a contributor worth profiling;
async await/resume counts and overlapping cumulative times must not be summed or
treated as a complete causal decomposition of the measured delta.

## Runtime and stability trace

- Model adapters remain lazy; instance locks now protect lazy initialization and
  mutable inference state. Shared OpenVINO sessions serialize run state, bound
  work in windows of 32 (or one larger declared batch), validate tensors and
  reconstruct async outputs in input order. Intel settings remain batch 1,
  up to eight in-flight requests and a 32-preview preparation window.
- Review preparation decodes an uncached photo once into a reusable frame;
  NIMA/embedding priming consumes those JPEGs. Each adapter still decodes its own
  model image input. Result LRUs are bounded to 256 entries by default; compile
  storage has an owned 16-entry/2-GiB budget. AssetSnapshot uses stat signatures
  before rehashing assets; it does not hash all weights for every cache hit.
- Priming skips screened work; optional failure falls through to per-photo
  fallback, strict failure propagates. Refinement remains disabled by default;
  its configured extra candidates/time are bounded when enabled.
- Runtime write batches flush before crossing the processed-state SQLite writer
  boundary. XMP projection receipts add append-only DB writes and metadata;
  their I/O cost was not measured here. Actual XMP and SQLite cannot form one
  atomic transaction; crash/recovery and external-app compatibility remain gaps.
- Full local suite with the media-write guard: **797 passed, 102 skipped**.
  This is not a full unguarded success. It skipped real fixture/XMP writes.
  Command: `uv run --no-sync python -m pytest -q -p tests.inference_readonly_guard --tb=short`.
  Direct pytest plugin loading before package-path setup failed; using
  `python -m pytest` loads the existing `tests` package without extra PYTHONPATH.
- Git push through `09c5882` succeeded. Its [CI run](https://github.com/Team-Cyan/material-agent/actions/runs/35448136742)
  failed: **883 passed, 12 skipped, 4 failed**. One failure is Git's `/app`
  ownership check in the quality container; three are XMP parse-rejection tests
  expecting the older RuntimeError contract while preview now raises the parse
  error first. Image publication was skipped. These are confirmed release
  defects, not an inference-quality failure or a successful release.

## At most three priorities

1. Restore the release gate: trust only the known `/app` checkout inside the
   ephemeral CI container; preserve the writer's public parse-failure exception
   contract and cover it with in-memory invalid-XMP tests so the read-only guard
   cannot hide it. No private host deployment.
2. Reduce repeated immutable runtime-version lookup only after verifying cache
   identity/invalidation semantics. The profile supports this narrow candidate;
   do not remove provenance, tensor validation or locking merely for speed.
3. Before a production speed claim, measure a longer existing RAW sequence on
   target hardware with read-only source mounts and independently bounded scratch
   state. Include decode, sustained RSS and projection-ledger I/O; this audit's
   PNG/macOS evidence does not cover those costs. No new dataset search is needed.

The spatial-reference research remains closed and insufficient; performance
measurements do not fill its missing human-reference categories.

## Reproduction

Extract only baseline code/config with `git archive 9de0e41 src config.yaml
docker/config.intel-openvino.yaml` into `.local/complexity-audit/baseline`.
The retained [single-process harness](run_benchmark.py) accepts source root,
`heuristic|intel`, and an ignored report directory, for example:

```sh
uv run --no-sync python docs/operations/benchmarks/2026-09-19-runtime-audit/run_benchmark.py .local/complexity-audit/baseline intel .local/complexity-audit/replay-baseline
uv run --no-sync python docs/operations/benchmarks/2026-09-19-runtime-audit/run_benchmark.py . intel .local/complexity-audit/replay-current
```

Existing ignored NIMA/SSD/YuNet assets are required; their hashes are recorded.
The harness raises on media/DB writes, writes only benchmark JSON/Markdown, and
reports Darwin RSS units. Do not compare numbers across different machines or
interpret compile-cold process runs as disk-cache-cold operating-system runs.
