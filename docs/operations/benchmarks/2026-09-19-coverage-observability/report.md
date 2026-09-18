# Residual observability: development improves, fresh-burst gate fails

One new attribution-driven hypothesis was frozen and tested. It improves the
new paired synthetic controls, but makes no retention improvement on previously
unused RAW bursts. It is not promoted. Neither production grouping nor the
conservative direct-keeper selector changed. Old experiment results and thresholds
remain intact.

Artifacts: [attribution](attribution.json), [protocol](plan.json),
[development](development.json), [holdout inputs](holdout-inputs.json),
[holdout measurements](holdout.json), [independent panels](holdout-references.json),
[11 video-reference updates](video-references.json), [summary](summary.json).
The hypothesis and development implementation were committed as `efcdbdd` before
fresh RAW evaluation. A rerun added only frozen-baseline comparison and runner
input-bound checks; no relation threshold was retuned.

## Failure attribution without retuning

The diagnostic script recomputes selected existing pairs and captures their
homography to measure residual structure. It does not alter relation thresholds,
select keepers, or write image files. Full source fingerprints remained unchanged.

| Existing pair | Affine residual mean | Mean after sigma-1 smoothing | Mean after quantile photometric mapping |
| --- | ---: | ---: | ---: |
| First fresh RAW burst, frames 0→1 | 3.054 | 1.275 | 3.096 |
| Second fresh RAW burst, frames 0→1 | 2.818 | 2.347 | 2.683 |
| Real dark→bright exposure pair | 15.626 | 15.069 | 8.324 |
| Synthetic exposure, raw arrays | 0.263 | 0.084 | 0.080 |
| Same synthetic exposure, JPEG previews | 5.539 | 0.495 | 5.563 |

These pairs passed geometry, spatial support, overlap and photometric-range gates;
the final residual test abstained. Geometry was not the demonstrated bottleneck.
The controlled array/JPEG comparison establishes a high-frequency encoding effect
in that synthetic pair. RAW burst 1 is also smoothing-sensitive; that alone cannot
separate interpolation, registration error, noise and actual scene motion. RAW
burst 2 remains less explained. In the exposure bracket, a distribution mapping
reduces error but may absorb genuine content changes: it is diagnostic, not a
coverage proof. No causal certainty about real scene changes is inferred from
these aggregate measures or from visual inspection alone.

The original 4x4 patch leaves 12 pixels above residual 24 in one connected region,
yet its tile mean is only 0.757 and global p95 is zero. The predicate discards a
signal that remains observable. At input sizes 320/640/1280, a fixed 4x4 patch after
the 512 cap has peak differences 123/79/26 and total differences 899/410/88:
resizing also attenuates information, but does not explain the 320-pixel failure.
An exact RGB change `[200,0,0]` → `[0,102,0]` has grayscale difference zero and
RGB difference 200: grayscale fundamentally removes that particular evidence.
The script records thresholded component sizes and peak normalized coordinates;
no diagnostic image assets are persisted.

## One frozen hypothesis

Keep the existing geometric gates and final keeper selector. Replace the residual
predicate with an RGB comparison at a 1024-pixel cap: global luminance gain and
robust channel offsets, sigma-1 smoothed global residual limits, and connected
regions of unexplained color/luminance residual. A global MAD noise envelope is
used; local regions cannot fit their own color correction. A region at least eight
pixels returns unknown. This is a nuisance-tolerance hypothesis, not semantic
recognition or a proof that smaller differences are unimportant. Global channel
offsets can also absorb broad color changes; this control set does not establish
safety for that untested category.

Two new seeds, two sizes and seven perturbations give 28 development pairs.
Positive controls are identity, different JPEG quality, noise, subpixel motion and
exposure. Negative controls are small luminance and equal-luminance color patches.
Development evaluates the generated first-to-second direction; it does not claim
all direction/order perturbations. The full JPEG preview recipe is applied. Construction labels describe symbolic
content, not real expressions or human preference.

| Development relation measure | Frozen 512-gray baseline | New RGB/local hypothesis |
| --- | ---: | ---: |
| Positive cover | 12 / 20 | 18 / 20 |
| Negative false cover | 4 / 8 | 0 / 8 |
| Negative abstention | 4 / 8 | 8 / 8 |

Two high-resolution subpixel positives remain unknown. Predeclared development
criteria passed, permitting the untouched holdout; they did not authorize product
promotion. No learned weights, LightGlue or DINO were introduced.

## Independent RAW holdout and stopping result

After excluding the prior 24 burst IDs, the first two eligible lexicographic HDR+
bursts were selected, first three payloads each, under the frozen 200 MB download
cap. Identifiers, public source URLs and hashes are in `holdout-inputs.json`.
The [HDR+ source/license attribution](../2026-09-18-direct-coverage/sources.md)
applies; no photo bytes are committed. Actual EXIF times are used.

Two fresh independent Codex agents saw opposite image orders without scores or
implementation. Both marked all twelve directed relations cover, all six quality
pairs tie, and any singleton as acceptable. Both described stream scenery where
instantaneous water texture changes were not meaningful content changes. These
are model-generated judgments, not human truth. The bursts are only seven seconds
apart and depict similar scenery; they are not independent subject populations
and must not inflate broad photographic acceptance evidence.

Both baseline and new method retain **3/3 in both bursts**. The new method returns
unknown on all twelve relations. Largest unexplained components span 2,878–28,861
pixels; smoothed residual means 4.211–5.306 also exceed the frozen global limit.
Thus a component veto alone does not explain the complete failure: the global
residual gate also fails. No claim is made that all detected regions are water
without spatially reviewed region labels.

- Structural violations: **0**, with **0 rejects**; this is a vacuous structural
  pass, not evidence of safe duplicate reduction.
- Negative-reference cover edges: **0**; neither method proposes any cover.
- Final content loss against the model singleton references: **0**, because all
  photos remain. Extra retention: **two per burst**.
- Events with improved retention: **0**, required **1**. The new hypothesis fails
  its holdout gate. Two correlated bursts also fall short of the separate ten-event
  product requirement.

The runner records decode/score/wall time and sampled peak RSS. No observed
resource overrun occurred. Native calls are checked at boundaries, not forcibly
cancelled; RSS is observational rather than an OS hard cap. The six-frame frozen
input shape and pair cap are validated before decoding.

## Updated independent references for old video rejects

The earlier eleven unjudged video rejects were each reviewed as a two-image
montage by two separate Codex panels with reverse order. All eleven reject-witness
directions received consensus cover, all quality preferences tie. They depict
matching empty kitchen views according to the panels. We retain the original
unjudged report and append these model references separately: **eleven model
references, zero human labels**. This reduces the proxy-reference gap but does not
turn the original false synthetic rejection into a success or establish human
accuracy.

## Verification and next boundary

Self-review kept causal attribution limited, added input cardinality/duplicate
and pair-budget validation, and checked the unchanged selector and geometry
contracts. **31 focused guarded tests passed** (seven new observability tests,
22 direct-coverage tests, two repository-boundary tests); `make check` and
`git diff --check` passed. Fingerprints link results to the frozen code/protocol.
No photos/XMP, production sessions, deployments or pushes were performed.

This single-hypothesis batch is complete with a negative holdout conclusion. It
has not established an automatic way to distinguish dispensable moving texture
from important small subject changes. Another threshold adjustment or model swap
on these scenes would not resolve that reference problem. Preserve this boundary:
future research needs spatially explicit, independent examples of meaningful
versus nuisance change before designing another hypothesis. Production adoption
remains unapproved; current time AND hash behavior continues unchanged.

## Reproduction

From the repository root, with immutable sources available outside output paths:

```sh
uv run --no-sync python scripts/diagnose_coverage_residuals.py \
  --output .local/direct-coverage/attribution-reproduction.json
uv run --no-sync python scripts/benchmark_coverage_observability.py \
  --plan docs/operations/benchmarks/2026-09-19-coverage-observability/plan.json \
  --output .local/direct-coverage/development-reproduction.json
uv run --no-sync python scripts/benchmark_observability_holdout.py \
  --photos .local/direct-coverage/observability-holdout \
  --output .local/direct-coverage/holdout-reproduction.json \
  --plan docs/operations/benchmarks/2026-09-19-coverage-observability/plan.json \
  --development docs/operations/benchmarks/2026-09-19-coverage-observability/development.json \
  --inputs docs/operations/benchmarks/2026-09-19-coverage-observability/holdout-inputs.json \
  --config docs/operations/benchmarks/2026-09-17-hdrplus-holdout/config.json
```
