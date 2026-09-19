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
profile/revision, alternated AB/BA/AB, five repetitions per process. Each process used its own initially empty compiled-cache directory; persistent
cache storage was retained only inside that process. Result caches were cleared before
each repetition, with normal within-repetition NIMA priming reuse preserved.
Numbers below are medians across three process trials, not confidence intervals.

| Metric | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| Heuristic warm, four images | 68.369 ms | 68.806 ms | +0.64%; effectively flat in this small sample |
| Learned warm, four images | 191.745 ms | 203.821 ms | +6.30%; observed overhead, not a universal throughput estimate |
| Learned first repetition | 3.066 s | 3.184 s | +3.87%; fresh compiled cache, OS cache not flushed |
| Learned process peak RSS | 664.5 MB | 683.3 MB | +18.8 MB / 2.84%; process peak, not steady-state allocation |
| Heuristic process peak RSS | 102.2 MB | 103.4 MB | +1.2 MB |
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

## Release-gate correction batch

The quality container now marks only `/app` as a safe Git directory, allowing
tracked-file boundary checks on the bind-mounted checkout without disabling Git
ownership checks globally. XMP projection preflight wraps bounded parser failures
in the writer's prior `RuntimeError` contract and retains the underlying cause;
it still refuses malformed, entity-bearing or oversized inputs before copying
or invoking ExifTool. Failure receipts remain attached.

Three added regressions feed invalid XML through the real parser from BytesIO;
they create no media or sidecar files and assert no copy or external writer call.
Focused guarded validation: **53 passed** (new preflight tests, projection policy,
projection ledger, repository boundaries), Ruff and diff checks passed. This
batch does not tune runtime models, thresholds or cache policy. Remote quality
and image outcomes must be checked separately after push.

## Measurement self-review correction

The first audit harness passed `compiled_cache_dir=None`. Both adapter versions
stringified it into a directory named `None`, so the original claim of disabled
persistent caching was false. Later processes reused compiled blobs. The
[initial measurements in the superseded commit](https://github.com/Team-Cyan/material-agent/blob/931154cca3b05d56f1a764f07a8e7a67491e476f/docs/operations/benchmarks/2026-09-19-runtime-audit/measurements.json) are retained and explicitly
superseded; their cold-start numbers must not be used. The generated cache was
moved into the ignored audit scratch directory; no user file was removed.

The corrected harness uses a unique, asserted-absent cache under each process
output directory. All twelve benchmark processes were repeated with the exact
frozen baseline/candidate source trees and same inputs/settings. The table and
`measurements.json` now contain only this corrected run: learned warm overhead
6.30%, first repetition 3.87%, peak RSS +18.8 MB. This remains a small diagnostic
observation, not a statistical or target-hardware performance guarantee.

Release correction `70ab08f` was pushed and its remote quality job passed;
[image publication](https://github.com/Team-Cyan/material-agent/actions/runs/35448595251)
was still running when this measurement correction was recorded. A push or
quality success alone is not a successful image release or deployment.
