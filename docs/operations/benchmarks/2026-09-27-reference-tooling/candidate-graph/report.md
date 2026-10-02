# Constructed candidate/selector result — September 27, 2026

The bounded constructed-graph structural checks passed. This is only the
structural portion of Batch 2: G1 human references, human-labeled oracle G2 and
product acceptance remain pending. Nothing here measures image interpretation,
real event segmentation, population safety or production performance.

Inputs and protocol: [manifest](manifest.json), [plan](plan.md).
Authoritative compact output: [run-1/results.json](run-1/results.json), 64,349 bytes.
The 14 fixture snapshots contain 53 eligible unordered pairs in total; repeated
mutation snapshots are not independent samples. Every arm uses the same times,
quality and explicitly constructed directed labels. Missing labels stay unknown.

| Arm | Eligible | Selected | Omitted | Reachable constructed cover directions | Cases matching all-eligible decisions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Historical nearest-3 / global cap 4 | 53 | 40 | 13 | 26 / 31 | 11 / 14 |
| Bounded all eligible | 53 | 53 | 0 | 31 / 31 | 14 / 14 |
| Deterministic per-event budget 4 | 53 | 41 | 12 | 27 / 31 | 10 / 14 |

These are constructed diagnostic counts, not accuracy estimates. Per-event
budgeting fixes this locality failure but does not dominate the historical arm
or solve within-event omission. Raising its budget to cover every eligible pair
matches all-eligible selection in the focused tests. No new production policy is
selected or promoted.

## Evidence

- Historical displacement: `global_cap_before` selects `(a,b), (a,c), (a,d),
  (b,c)` for the late event at seconds 100–103. Insert the disconnected event
  `(x,y)` at seconds 0–1: the selected list becomes `(a,b), (a,c), (a,d), (x,y)`.
  `(b,c)` is omitted for `global_pair_cap`; c changes from rejection with direct
  keeper b to keep. Both new arms preserve all preexisting selected pairs and
  decisions. Tests insert unrelated events both before and after every fixture.
- Nearest-three omission: even with global cap 100, `(a,e)` is omitted in the
  five-frame fixture. The sole `a -> e` cover cannot be a witness when not
  selected; e stays kept. All-eligible selection uses that direct witness.
  Per-event cap 4 also omits this useful pair, explicitly reported as cap loss.
- Nontransitive chain: a covers b and b covers c; a rejects b, c remains kept.
  Delete keeper a and fully recompute: b becomes keeper and can directly reject c.
  No deleted witness survives. Cycles, tied quality, incomplete quality and
  unique low-quality a with high-quality duplicate b/c retain the required items.
- Component bridge/split: temporal components grow from sizes `[2,2]` to `[5]`
  after x insertion and return to `[2,2]` after removal. At a component bound of
  4, the merged case fails closed. In the all-eligible merged snapshot x rejects
  c, so c cannot continue witnessing d; d becomes kept. A separate chain insertion
  flips decisions several steps away, demonstrating why a fixed-radius update is
  not established.
- Every rejection records the actual directed edge consumed by the selector,
  its final keeper and successful quality comparison in `direct_witnesses`.
  There are zero witness violations. Each of 42 arm/snapshot evaluations has
  exact component-recompute/full-selection equality on its own candidate graph.
  This equality is separate from the table's all-eligible oracle comparison.
- CLI checks all 1,208 frame permutations across these <= 6-frame fixtures for
  each arm (3,624 comparisons), including reversed oracle ordering. Tests also
  check 12 deterministic shuffles of a larger graph and 24 seeded graphs.
  Candidate locality depends on known, distinct event IDs; discovering real
  events and changes to event assignment are not evaluated.

## Verification

- `env -u PYTHONPATH UV_NO_SYNC=1 uv run pytest -q tests/test_candidate_graph.py`:
  **51 passed** in 1.49 s, independently of historical test collection. Both the
  tool and tests resolve modules by explicit file paths, without relying on
  cwd, `PYTHONPATH`, or another test's `sys.modules["direct_coverage"]` registration.
- `UV_NO_SYNC=1 make check`: **passed**.
- `UV_NO_SYNC=1 uv run pytest -q tests/test_repository_boundary.py`: **2 passed**.
- The [plan's CLI command](plan.md) completed with exit 0 and wrote only the new
  `run-1` output directory. Tests verify byte-identical repeated CLI output,
  unchanged manifest bytes, refusal of existing/source/symlink output paths,
  input and component caps, and no calls to historical image/inference functions.
- `git diff --check`: **passed**. Ownership review found no edits from this task
  to historical scripts, application code, config, dependencies or status/plan
  ledgers. Other tasks' edits remain untouched.

Provenance recorded in the JSON:

- Manifest SHA-256: `df89ba6fee35755e9ea43bea7c293bc67e14bdc5610c8047b93e4415caa40c1d`
- Unmodified historical `direct_coverage.py` SHA-256:
  `54387bfe9b887d978bb7d13ea0bfb92eff9bf9303fe8060c2a774b623a0632fb`

No real photo, XMP, runtime-state write, model inference, new dependency,
network request, commit, push or deployment was performed. There is no
incremental production algorithm; every mutation snapshot is recomputed fully.
