# Whole-sequence grouping and final reference coverage

The earlier pair experiment is a diagnostic, not full-sequence selection proof.
This follow-up groups each sampled video window once, then selects across each
resulting complete group. Current adjacent time/hash logic works as designed;
that design does not guarantee preservation of different actions.

## Frozen sequence scope

Reuse the two original videos, official annotations and unchanged scoring config
from the [pair experiment](../2026-09-18-cooking-hashes/report.md). Sample frame
`round(t * 29.4)` for integer seconds `t=0..120`, stopping at the video's actual
end: 63 frames in `s07-d72`, 121 in `s22-d23`. No per-pair reset, semantic veto,
all-pairs gate or invented camera EXIF is used. Relative video spacing is retained.
Frames outside annotated actions remain in the sequence and may bridge groups;
their reference labels are unknown. Multiple overlapping annotations are retained.

The videos were inspected in the preceding experiment. This is a newly frozen
sequence diagnostic on known inputs, **not a new independent holdout**. One-second
sampling can miss short actions; reference coverage denominators include only
labels/segments actually represented by sampled frames. It is also not full-rate
video or real camera burst acceptance. No source content is redistributed.

`plan.json` fixes candidates, thresholds, preprocessing, sampling bounds and exact
input/config/manifest fingerprints. The runner requires and validates that plan,
rejects unsupported parameters and sampling drift, and records actual parameters
plus plan/input/config/manifest/runner/protocol SHA-256. All 25 historical pair
rows and their summaries remain exactly reproducible in this same run. Historical
artifacts are retained unchanged; they do not acquire the new provenance retroactively.

## Sequence results

Visible retention means selection keep or review. Reference loss means no sampled
frame carrying that action/segment survives as visible retention. These are
annotation-coverage metrics, not human quality/preference false-reject estimates.
Groups may contain multiple action labels even when every adjacent hash passes.

| Sequence / candidate | Frames | Group sizes | Cross-action groups | Lost action classes | Lost sampled segments |
| --- | ---: | --- | ---: | ---: | ---: |
| s07-d72 / pHash | 63 | 22, 41 | 2 | 2/3 | 4/5 |
| s07-d72 / equalized | 63 | 9, 1, 5, 7, 41 | 1 | 2/3 | 2/5 |
| s07-d72 / dHash | 63 | 9, 54 | 1 | 2/3 | 4/5 |
| s22-d23 / pHash | 121 | 32, 21, 2, 9, 32, 7, 18 | 5 | 10/12 | 14/17 |
| s22-d23 / equalized | 121 | 32, 21, 2, 9, 2, 29, 1, 7, 1, 17 | 5 | 9/12 | 13/17 |
| s22-d23 / dHash | 121 | 121 | 1 | 11/12 | 16/17 |

The dark wide-view footage receives poor heuristic quality scores. Group coverage
rescues one candidate when there is no quality keep; it does not rescue each
reference action. Thus lost coverage combines grouping with the existing scoring/
selection policy, rather than being a hash-distance metric alone. Raw scores,
quality, selection, group membership and lost references are preserved in JSON.

Endpoint distances can exceed threshold within a group because intermediate
frames connect them. The runner also reports each group's maximum pair distance
as an observation; neither diagnostic changes the adjacent-link rule. A group
whose endpoints look similar can still contain different intermediate content.

## Deterministic regressions and verification

A generated brightness-adjustment sequence at factors 1, 4, 4.2 and 4.4 has
adjacent pHash distances below ten but first/last distance above ten. The full
chain forms one group and selects once; removing intermediate frames produces
two singleton keeps. A time break still splits the chain. These synthetic tests
use controlled scores to verify selection behavior, not photographic quality.
Action labels deliberately differ and remain irrelevant to grouping. Input score
metadata stays unchanged across candidate runs.

Eight focused tests cover these behaviors plus accepted plans, changed input/
manifest/config fingerprints, unsupported candidates and sampling drift even
when an input digest is updated. The full real sequence run checks original video
hashes before/after, frame seek positions and exact parity of historical pair
results. Ruff and repository boundary checks also pass. No production code,
photo metadata, job database or writer changes occur.

```sh
uv run --no-sync python scripts/benchmark_cooking_hashes.py \
  --videos .local/mpii-cooking \
  --inputs docs/operations/benchmarks/2026-09-18-cooking-sequences/inputs.json \
  --plan docs/operations/benchmarks/2026-09-18-cooking-sequences/plan.json \
  --video-manifest docs/operations/benchmarks/2026-09-18-cooking-hashes/videos.json \
  --config docs/operations/benchmarks/2026-09-17-hdrplus-holdout/config.json \
  --output-dir .local/cooking-sequence-reproduction
```

## Convergence decision

Freeze the negative conclusion for current pHash replacements: equalization and
dHash do not meet the intended action-coverage outcome. No more threshold fitting
on these known videos, and no default promotion. This batch prepares no additional
candidate experiment. First resolve whether adjacent-chain behavior is acceptable
when actions differ, or whether a different visual group constraint is desired;
changing that constraint is a product rule change, not a hidden bug fix. The
separate severe-detail-loss time-only exception is still not approved. Preserve
current rules while those decisions and broader independent acceptance remain open.
