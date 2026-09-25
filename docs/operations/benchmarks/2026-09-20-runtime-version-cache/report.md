# Bounded runtime-version snapshot attempt

This is the single optimization proposed by the prior runtime audit. It does not
change models, scoring, preprocessing, tensor checks, locking, or production
writes. [The frozen plan](plan.json) was recorded before timing the candidate.
The previous `0e84b81` release completed both quality and image publication in
[Actions 35448750398](https://github.com/Team-Cyan/material-agent/actions/runs/35448750398);
no deployment took place.

## Semantic boundary and implementation

The attempted change moves the existing five-package version dictionary into a
lazy snapshot owned by one `AsyncLocalClient` instance. Package installations are
fixed for that client lifetime, including `unknown` for an absent distribution.
After installing/upgrading packages, callers must construct a new client; no
process-global negative cache is added. Empty calls and heuristic-only clients
do not query the metadata. The package set and identity JSON fields are unchanged.

This snapshot is evidence about installed packages, not proof of a selected
execution provider. Configured runtime/device, model assets and preprocessing
still contribute to each result identity. Their changes still invalidate cached
results and adapter selection. Execution provenance and actual device readback
continue through their existing paths. Missing-package metadata does not turn a
fallback into successful inference, nor fabricate a version.

The candidate adds one instance field and moves the existing dictionary
construction (net six runtime source lines including comments); it introduces no
new dependency, lock abstraction, global cache or model default.

Tests cover lazy/empty behavior, reuse of missing-version evidence, independent
fresh-client snapshots, result identity changes after package-environment changes
between clients, live asset/runtime/inference-config invalidation, and explicit
`unknown` when package metadata is unavailable. Existing lifecycle regressions
cover preprocessing/revision partitions, bounded caches, ordering and fallback.

## Measurement boundary

Both revisions use the same current machine/interpreter/packages and four
existing PNG inputs, with existing NIMA/SSD/YuNet weights. Four fresh-process pairs
per profile alternate AB/BA/AB/BA; each process has five repetitions and its own
initially absent compiled-cache directory. The existing audit harness clears
result caches between repetitions while preserving normal NIMA priming within
each repetition. No media/XMP, production DB or live-service operations occur.

The comparison is `0e84b81` against its frozen source plus this one client change.
The previous pre-unification comparison (6.3% slower, +18.8 MB) remains a separate
four-PNG macOS diagnostic; this attempt must not be compared across different
sampling windows or treated as RAW/target-hardware acceptance. Profile cumulative
time is diagnostic only, never a complete causal account of end-to-end latency.

Acceptance requires unchanged scores/scenes/dimensions and model call counts,
at least three of four learned-profile pairs faster, and at least 2% improvement
in the median learned warm time. If not met, restore the baseline runtime file,
retain the measurements and stop without trying a different optimization.

## Results and decision

[Results](results.json) and [input/runtime fingerprints](provenance.json) retain
all sixteen process trials and the separate metadata-only diagnostic. The frozen
gate passed, so this narrow candidate is retained; no additional optimization
was attempted.

| Same-session metric (four-process median) | Baseline | Candidate |
| --- | ---: | ---: |
| Learned warm, four PNGs | 779.595 ms | 762.427 ms (2.20% faster) |
| Learned first repetition, fresh compiled cache | 15.783 s | 15.791 s (essentially unchanged) |
| Learned full process, five repetitions | 20.156 s | 20.071 s |
| Learned peak RSS | 679.35 MB | 676.12 MB |
| Heuristic warm, four PNGs | 273.812 ms | 278.731 ms (1.80% slower) |

Learned warm pairs, in frozen trial order, are 759.051→767.386,
779.104→757.467, 780.086→689.723 and 791.045→770.721 ms. Three of four improve,
but trial variation is substantial and the median improvement only narrowly
clears the 2% threshold. Heuristic measurements do not show a speedup and all
four paired differences are slower; the new version snapshot is not queried on
that path. Do not claim statistical significance, general speedup, reduced
steady-state memory, or a target-hardware improvement from these numbers.

Scores, scenes and dimensions are exactly equal across variants and repetitions.
Every learned process has one NIMA initialization, one SSD initialization, five
NIMA batch calls, twenty detection calls and twenty input loads. Same-environment
synthetic adapter probes also give byte-equivalent serialized miss/hit results
and identical result-cache identities between frozen baseline and candidate.

The isolated metadata diagnostic performs 25 dictionary uses: baseline queries
package metadata 125 times, candidate five times. Its four-trial median is
74.95→2.77 ms. This verifies avoidable lookup work; it is not an additive causal
explanation of the observed process or warm-run delta. No inference timings are
substituted with metadata-loop timings.

## Verification and release boundary

Seventeen focused lifecycle/snapshot tests passed. The full media-write-guarded
suite passed **803 tests**, with **102 skipped**; this is not a claim that skipped
photo/XMP fixture paths ran. Ruff and diff checks passed. Guarded command:

```sh
uv run --no-sync python -m pytest -q -p tests.inference_readonly_guard --tb=short
```

The three new tests are ordinary repository tests, not a runtime probe feature.
The source candidate was frozen before timing; its client-file SHA256 is in
provenance. Input/model hashes match the prior audit. No photos/XMP were written,
no private host was accessed, and no closed spatial-reference work was restarted.
The batch was pushed as `a2db712`. Its first CI attempt had one failure in an
existing SIGTERM cancellation test: the task returned and recorded `cancelled`,
but a fixed 0.5-second wall-clock assertion measured 1.09 seconds on the runner.
That test passed three isolated local repetitions. A retry of the same commit
passed remote quality, immutable-image smoke and image publication in
[Actions 35515765580](https://github.com/Team-Cyan/material-agent/actions/runs/35515765580).
No deployment occurred. A subsequent review replaced the cancellation test's
wall-clock assertion with a direct check that the preparation worker is still
blocked when cancellation returns; its release wait remains bounded. No
additional hardware or RAW I/O experiment was started.
