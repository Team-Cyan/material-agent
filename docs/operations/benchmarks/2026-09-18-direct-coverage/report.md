# Direct coverage baseline: rejected for promotion

The bounded experiment is complete. The frozen SIFT/geometry/residual predicate
fails a small-content control and retains all six fresh RAW photos. Its direct
keeper selector satisfies the structural contract, but that does not establish
correct coverage. Production adjacent time AND hash grouping is unchanged.

Authoritative artifacts: [plan](plan.json), [inputs](inputs.json),
[results](results.json), [summary](summary.json),
[independent blind panels](blind-references.json), [source/license audit](sources.md).
Implementation/protocol commit: `7661372`. No thresholds were tuned on these
results. Earlier execution was repeated only to correct RAW hash parity and add
full-recomputation mutation checks; the frozen relation thresholds were unchanged.

## Separate acceptance measures

Across 40 cases / 263 frame instances (including repeated video pairs), there
are 1,164 directed candidate relations: 70 tentative cover and 1,094 unknown
(**93.99% abstention**).

| Measure | Result | Interpretation |
| --- | --- | --- |
| Structural violations | 0 / 13 selected rejects | Each reject has a direct edge from an actual final keeper; no transitive witness |
| Independent negative cover edges | 2 | Both directions of the 4x4 symbolic content patch are incorrectly covered |
| Independently checked selected rejects | 2 / 13 | One identity duplicate correct; one small-patch reject incorrect |
| Selected false coverage | 1 | Separate from the zero structural violations |
| Unjudged selected rejects | 11 / 13 | Video same-action/unlabeled frames do not establish duplicate content |
| Known final unique-content loss | 1 control | `synthetic-expression`; symbolic patch, not real facial-expression accuracy |
| Construction-positive duplicate reduction | 1 of 4 redundant photos | 25% of available redundancy; 12.5% of eight input photos; below 50% gate either way |
| Fresh real event count | 2 / required 10 | Diagnostic only, independently insufficient for promotion |

The 12x12 symbolic gesture patch abstains; the 4x4 patch passes mean/percentile/tile
residual thresholds. These are known-content controls, not realistic portrait
labels. Gray residuals also cannot establish preservation of color-only content.
The failure is recorded rather than hidden by changing thresholds or reference
labels. `covered_by` is provenance, never ground truth.

## Full path and ablations

All variants share production heuristic scoring and frozen previews. The
production column executes actual adjacent grouping plus group selection; RAW
hashes use `Grouper._hash_file`, video hashes use the prior frozen preview recipe.
This is the configured local heuristic path, not an evaluation of disabled learned
quality models. Old selectors have no direct-witness contract, so their structural
metrics are unavailable rather than fabricated zeros.

| Case | Production retained | pHash + direct selector | SIFT + direct selector | SIFT connected groups + old selector |
| --- | ---: | ---: | ---: | ---: |
| 63-frame cooking window | 2 | 15 | 58 | 57 |
| 121-frame cooking window | 7 | 30 | 115 | 114 |
| Fresh RAW event 1, three frames | 3 | 1 | 3 | 3 |
| Fresh RAW event 2, three frames | 3 | 1 | 3 | 3 |
| Real exposure bracket, three frames | 3 | 3 | 3 | 3 |
| Small-content negative, two frames | 2 | 1 | 1 | 2 |

In the 121-frame window, production retains **2/12** labeled action classes;
pHash with the direct selector retains **8/12**; both SIFT variants retain
**12/12** and all labeled segments. The direct-selector improvement alone is not
sufficient: pHash still proposes 58 independently negative directed edges and
uses seven as reject witnesses in that window. SIFT retains nearly everything;
zero lost action labels does not establish preservation of every gesture/frame.
All eleven video rejects remain unjudged for actual content equivalence.

The prior 25 isolated cooking pairs all retain both frames with SIFT. Eleven pairs
have disjoint official action labels; the others are unknown, never positive
coverage truth. Exact parity against the previous benchmark was checked for all
25 pair previews/production selections and all 184 full-sequence previews,
production selections and group sizes. Pair success alone is not sequence closure.

## Exposure, nuisances and independent RAW holdout

The real dark/bright bracket remains 0.34 seconds apart with production pHash
distance 24. It enters the hash-bypass route, matches geometry, but unexplained
registered residuals prevent coverage. The third frame is 50.07 seconds later
and correctly has no candidate edge. No EXIF time was synthesized to join it.
Shared scene identity is not proof of unchanged person pose.

Pure-array moderate exposure passes the relation unit test; after the frozen
JPEG preprocessing, the benchmark exposure control abstains. This difference is
why a full preview path is measured. Noise, shadow, foliage-like and water-like
texture, parallax and occlusion all produce unknown, not semantic difference.
Residual is not treated as proof of unique content.

Two independent Codex subagents viewed six new rendered RAW photos in opposite
orders, without scores/implementation/source labels. Both agreed on all twelve
directed cover references, six quality ties, and each singleton keeper set.
These model judgments are not human truth. SIFT abstains on every directed edge,
retaining three per event, **two extra per event** versus the agreed sets. pHash
plus the direct selector retains one per event, but fails the small-content
negative elsewhere. No method is promoted from these two scenes.

## Budgets, cost and mutations

Frozen caps: 10-second window, nearest three forward neighbors, 256 frames,
600 unordered candidate pairs, 90 seconds per case and 2,000,000,000 bytes RSS.
The nearest-neighbor cap omits 382 eligible pairs in the 63-frame window and 785
in the 121-frame window; no coverage claim is made for omitted pairs. Hash does
not gate eligibility: 108 high-hash directed comparisons consumed 1.046 seconds
of matching, versus 1,056 low-hash comparisons / 10.388 seconds. Feature extraction
is shared per image and cannot be uniquely allocated to the bypass route.

| Window | Decode | Score | SIFT features | Directed matching | Whole case including mutation reruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| 63 frames | 4.92 s | 2.28 s | 1.37 s | 3.62 s | 22.46 s |
| 121 frames | 9.84 s | 4.48 s | 2.64 s | 7.00 s | 43.59 s |

Observed peak RSS: **773,259,264 bytes**; no case exceeded its budget. Timings
include warm library effects and are local diagnostic observations, not target
hardware throughput. OpenCV native calls cannot be forcibly interrupted: budgets
are checked at call boundaries, an overrun invalidates a relation, and exhausted
case preparation aborts without an acceptance result. RSS is sampled, not an OS
hard memory limit.

Five real/sequence cases were fully recomputed after deleting the middle input
and reinserting it in reversed order. All restored decisions matched; this one
mutation per case does not prove incremental locality. Dedicated tests cover
permutation, cycles, component bridging, missing quality, quality tradeoffs,
and an insertion that changes later keepers through a chain. Another test shows
a global pair cap can displace an unrelated later candidate. No local recompute
guarantee is offered.

## Review, checks and stopping decision

Self-review corrected feature-extraction failure handling (`unknown`), removed a
nonfinite residual fallback, aligned RAW comparison hashes with production, and
applied the case budget to preparation and mutation runs. Focused guarded tests:
**32 passed**, including repository boundary tests. `make check` and
`git diff --check` passed. Source bytes match before/after hashes. No photo/XMP
write, production session, deployment or push was performed.

Admission fails on independently false cover, known unique loss, insufficient
duplicate reduction and insufficient fresh events. The useful result is a tested
selector contract and a falsified coverage predicate. More matching models are
not automatically justified: the observed abstentions occur after successful
geometry, at residual interpretation. LightGlue/DINO adoption is deferred; no
model rotation or further threshold tuning on these inspected cases is scheduled.
Future work needs a separately frozen small-content/visibility representation
hypothesis and fresh references. This bounded batch is complete, not blocked on
the old product-decision questions.

## Reproduction

Use source roots outside the output directory and a new empty output directory.
Images/videos are not supplied in this repository; exact identifiers/digests and
license boundaries are above. Run from the repository root:

```sh
uv run --no-sync python scripts/benchmark_direct_coverage.py \
  --plan docs/operations/benchmarks/2026-09-18-direct-coverage/plan.json \
  --inputs docs/operations/benchmarks/2026-09-18-direct-coverage/inputs.json \
  --config docs/operations/benchmarks/2026-09-17-hdrplus-holdout/config.json \
  --videos .local/mpii-cooking --exposure .local/exposure-brackets \
  --holdout .local/direct-coverage/holdout \
  --output-dir .local/direct-coverage/reproduction
```
