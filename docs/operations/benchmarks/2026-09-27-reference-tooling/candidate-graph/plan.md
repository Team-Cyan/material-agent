# Constructed candidate graph experiment

This is the constructed-graph portion of Batch 2. All IDs, times, quality values
and directed labels in `manifest.json` are constructed. There are no photographs,
human judgments, image features or model results. This cannot satisfy G1, full
G2, a population safety claim or product acceptance.

## Frozen comparison

- Use the same time graph, independent quality records and directed oracle labels
  for all three arms. Eligibility is absolute time distance <= 10 seconds. Both
  directions can be evaluated for each unordered candidate pair. Missing time
  isolates a frame; missing relation is unknown, including an omitted candidate.
- `historical`: call the unchanged `direct_coverage.candidates` with nearest-three
  forward and global cap 4. The historical function cannot accept missing times;
  this harness excludes missing-time frames for all arms and retains them. This
  explicit preprocessing is not a claim of unmodified legacy missing-time support.
- `all_eligible`: enumerate every eligible pair within the hard 64-frame bound.
- `per_event`: cap each supplied event bucket at 4 pairs, sorted by time distance,
  earlier timestamp and stable IDs. A pair belongs to the earlier endpoint's event
  (equal time uses ID); cross-event pairs retain temporal eligibility and have one
  budget owner. There is no global cap beyond the hard input-size bound.
- All arms call the unchanged historical `select` and `quality_allows`: quality
  never changes a relation, a rejected item needs a direct final-keeper witness,
  and incomplete quality cannot authorize rejection. The selector's stable ID
  tie breaker is retained. No production function or default changes.

Known fixture event IDs are required input. An unrelated inserted event has a
distinct supplied event ID and no eligible time edges to existing frames. The
locality result says nothing about discovering real events. Reusing an event ID
across disconnected windows can share its budget and is not covered by the claim.
Per-event caps can still omit useful pairs within one event.

## Correctness and bounds

Rebuild undirected temporal eligibility components on every snapshot and rerun
the entire selector in every component, including isolated vertices. Compare
with one full selector call on the same candidate edges. No cache, incremental
update, fixed-radius update or stale decision reuse is implemented. Temporal
components can include unknown edges and therefore conservatively over-approximate
selection dependencies. Also compare decisions against all-eligible selection;
capped arms are explicitly allowed to differ from that separate oracle.

Limits: 1 MiB input, 32 cases, 64 frames per case, at most 2,016 unordered / 4,032
directed pairs per case, configurable component bound <= 64. Positive finite
parameters and strict field/ID/quality validation fail closed before output.
Exhaustive permutations are limited to <= 6 frames; larger cases use 12 seeded
shuffles (seed 20260927). Tests additionally generate 24 seeded graphs (seed 52).
The CLI accepts only a new explicit output directory and never overwrites an
existing input/report/symlink target. It reads only its JSON manifest and code;
it does not access photo, XMP, application runtime state or network services.
Existing historical imports require the already-installed repository dependencies;
no inference functions or dependency installation are invoked.

## Evidence and acceptance boundary

Fixtures cover chains, cycles, score ties, missing quality/time/relation, unique
low quality A with duplicate high quality B/C, keeper deletion, component bridge
insertion/removal, selection cascades and historical cap displacement. Tests
also check distinct unrelated events before and after every existing event,
cross-event bucket ownership, candidate omission accounting, strict budgets,
direct witness quality, reproducible CLI bytes and safe output paths.

Structural success requires no direct-witness violation, permutation stability,
new-arm candidate locality and component/full equivalence. The all-eligible
oracle comparison must expose cap loss rather than force capped-arm parity.
Real labeled-oracle diagnostics remain pending G1. Synthetic `cover` is never
renamed human gold; missing labels are never completed from actions or scores.

Reproduce into a fresh output directory:

```sh
env -u PYTHONPATH UV_NO_SYNC=1 uv run python scripts/benchmark_candidate_graph.py \
  --manifest docs/operations/benchmarks/2026-09-27-reference-tooling/candidate-graph/manifest.json \
  --output-dir docs/operations/benchmarks/2026-09-27-reference-tooling/candidate-graph/run-1 \
  --window-seconds 10 --global-pairs 4 --event-pairs 4 --max-component-frames 64
```

Use a new output basename for a subsequent run; existing output is refused.
