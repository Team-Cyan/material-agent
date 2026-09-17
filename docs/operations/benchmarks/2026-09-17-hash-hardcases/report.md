# Synthetic exposure and fixed-background content-change stress test

Histogram-equalized pHash reduces some exposure-induced splits, but does not
solve fixed-background/different-content grouping. This experiment includes the
real selection stage: one synthetic false merge loses distinct original content
through a final reject. No production hash, threshold or coverage policy changes.

## Frozen source and labels

Use the official [Stanford40 action dataset](http://vision.stanford.edu/Datasets/40actions.html),
already downloaded and integrity-checked in the earlier action experiment.
Take the first four lexicographic filenames from each official train/test split
for `cutting_vegetables`, `cooking`, and `washing_dishes`: 24 original JPEGs,
12 calibration and 12 holdout. Source SHA-256 values are in the frozen plan.
No image content is redistributed. Source bytes are checked before and after.

Each source creates eight paired cases entirely in memory:

- Four display-RGB brightness multipliers: 0.125, 0.5, 2 and 8, with clipping.
  Label: same source content. These are not physically simulated RAW exposure,
  sensor noise or ground-truth aesthetic preferences.
- Two severe-detail-loss controls: `uint8(rgb * 0.002)` and
  `uint8(254 + rgb * 0.002)`. These become uniform near-black/near-white after
  quantization. Label: same source origin, although observable correspondence
  has been destroyed. A conservative split is explicitly allowed by current
  policy; the origin-based false-split count does not imply a safe fix exists.
- Two central replacements from the next action class in the same split, using
  the first selected donor. Patch width/height are 30% or 60% of the source,
  meaning 9% or 36% of its area. Background outside the rectangle is unchanged.
  Label: different central content by construction. These are conspicuous
  synthetic collages, not natural motion, real dish changes or camera bursts.

All 192 cases use explicitly synthetic five-second timestamps, time gate ten
seconds and hash threshold ten. No source EXIF is changed. All candidates use the
same JPEG bytes as scoring, decoded and resized with the production 256-pixel
hash thumbnail rule. Candidates are ordinary pHash, grayscale histogram-equalized
pHash and dHash. Scoring uses the previous frozen heuristic config, JPEG quality
85, a maximum 768-pixel image and that same grayscale as focus input. This is a
controlled JPEG diagnostic, not the production RAW focus-resolution benchmark.

The real `Grouper._group_with_times` consumes candidate hash values; the real
`compute_scores` and `apply_group_best_candidate_review` produce quality and
selection. There is no database, writer or cross-case selection state. Each
variant receives a fresh deep copy of scoring metadata. No threshold fitting
occurs on either partition. Self-review corrected an initial harness mismatch
so hashes decode the exact JPEG bytes passed to scoring; only corrected results
are retained here. The reusable runner reproduced every row and summary exactly.

## Holdout results: 12 independent originals, 96 derived pairs

Pairs sharing an original or donor are correlated. Counts must not be treated as
96 independent natural capture events. A keep can have quality reject because
readable-group coverage remains active. Review also remains visible to the user.

| Candidate | Brightness splits / 48 | Detail-loss splits / 24 | Central-content false merges / 24 | False merges causing a final reject / 24 |
| --- | ---: | ---: | ---: | ---: |
| Current pHash | 16 | 24 | 11 | 1 |
| Equalized pHash | 12 | 24 | 11 | 1 |
| dHash | 13 | 24 | 12 | 1 |

For brightness pairs, quality-reject altered frames still selected keep number
15 (pHash), 12 (equalized) and 13 (dHash). Altered frames finally selected reject
number 25, 28 and 27 respectively; these are policy outputs, not independently
labeled true/false rejects. No original is selected reject in the holdout
brightness cases. All 24 completely detail-lost altered frames have quality
reject and final keep through singleton coverage, for every variant.

The lost-content counterexample is `washing_dishes_009.jpg` with a 30%-width/
height central replacement from `cutting_vegetables_001.jpg`. Distances are
6/8/8 for pHash/equalized/dHash. Both originals have quality reject under the
heuristic scorer (original 2.38, composite 3.86); erroneous grouping keeps the
composite and rejects the distinct original. This is a concrete synthetic
coverage loss, not proof that the original is photographically good.

Calibration results are included in JSON: brightness splits 15/10/13 of 48,
central-content false merges 5/6/12 of 24, and detail-loss splits 24/24 for every
variant. Equalization therefore trades some exposure robustness for at least
one additional calibration false merge; it is not uniformly superior.

## Reproduction and decision

From the repository root, with the already downloaded dataset:

```sh
uv run --no-sync python scripts/benchmark_hash_hardcases.py \
  --dataset .local/datasets/stanford40 \
  --config docs/operations/benchmarks/2026-09-17-hdrplus-holdout/config.json \
  --output-dir .local/hash-hardcases-reproduction
```

The output directory must be new/empty and outside the dataset. Only plan/result
JSON is written. The config SHA-256 is recorded. The runner was executed against
all 192 cases, matched the frozen rows exactly, passed Ruff, and refused both
existing result directories and output inside the source dataset.

The [real CR2 experiment](../2026-09-17-exposure-brackets/report.md) remains
separate: equalization recovers that observed 0.34-second exposure pair. These
synthetic stress tests explain why one successful real pair plus easy negatives
cannot justify default promotion. Natural rapid action/dish changes and a wider
set of real exposure-adjustment sequences still lack independent grouping labels.

Maintain existing time AND hash semantics, threshold-zero bypass and conservative
missing/detail-insufficient behavior. No time-only exception has been accepted.
A replacement hash also requires cache revision separation before implementation.

The subsequent [real cooking-video check](../2026-09-18-cooking-hashes/report.md)
adds natural action boundaries using official annotations. It separately finds
5/10 current-pHash and 3/10 equalized-pHash false merges on the small holdout,
including a new equalization regression. Synthetic results above remain synthetic.
