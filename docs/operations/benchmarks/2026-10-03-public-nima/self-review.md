# Controller self-review and continuation decision

Reviewed October 3, 2026, against commit `6b0b6e9`, the current code, original
native score CSVs, frozen protocols, per-image caches and first/resume reports.
This review covers the composite/NIMA evaluation step; it is not a repository-wide
production acceptance review.

## Checks and findings

- Trace preparation: native KonIQ MOS and KADID DMOS are copied without fitted
  transforms. The [KADID publisher](https://database.mmsp-kn.de/kadid-10k-database.html)
  confirms that its DMOS increases with visual quality. Every labeled manifest
  target was independently joined back to its source CSV; direction is correct.
- Trace selection: stable SHA256 selection precedes both component runs. Exactly
  2,048 selected quality IDs are retained. The frozen recipe separates all 81
  KADID reference families (40 development / 41 comparison), with no family
  crossing; it does not establish semantic independence among KonIQ images.
- Trace inference: raw NIMA expectation uses the existing adapter's RGB 224×224
  preprocessing. The runner validates model identity, ten finite rating buckets,
  expectation agreement and actual CPU/no-fallback execution before accepting a
  score. It does not evaluate deployed fusion or clipping/calibration policy.
- Trace failure and recovery: errors cannot supply fallback scores or improvement
  deltas; failed/corrupt records are retried. All 2,048 actual records passed
  integrity, identity, source-byte and execution checks. The exact-command resume
  retained the semantic digest and complete provenance. Parent heuristic feature
  checksums and `scoring_mode=heuristic` also passed.
- Trace statistics: all twelve baseline/NIMA dataset-partition PLCC/SROCC pairs
  were independently recomputed using SciPy within absolute tolerance 1e-12.
  Public aggregates match first/resume artifacts. The point-estimate regression
  on KonIQ and improvement on KADID are correctly reported; they do not measure
  safe culling, statistical significance or generalization.
- Trace isolation and publication: output guards, atomic writes and existing
  regression tests cover corruption, fallback, split crossing and protected-path
  overlap. The staged scope contains only tooling/tests/docs. Commit `6b0b6e9`
  passed [remote quality and image publication](https://github.com/Team-Cyan/material-agent/actions/runs/37102600128)
  (1,092 passed / 43 skipped, lint, immutable smoke and verified promotion).
  No deployment or production-state/photo/XMP write occurred.

No implementation defect requiring a change was found in this scoped review.
The implementation and original artifacts remain frozen. The local controller
receipt records the replayed checks and its verification-script hash.

## Plan corrections before the next item

Keep the raw NIMA component out of universal technical-quality replacement:
KonIQ SROCC fell from 0.3643 to 0.2806, while KADID rose from 0.0694 to 0.3630.
Neither existing component experiment has a blinded independent holdout or a
training-image overlap audit. Add uncertainty estimates to the next experiment;
resample KADID reference families together and pair candidate/baseline scores on
identical draws. KonIQ image resampling still cannot rule out semantic dependence.
These intervals describe sampling uncertainty conditional on the frozen corpus,
not label reliability, training contamination or production acceptance.

Continue with one existing MUSIQ checkpoint, after verifying its asset and runtime
provenance. A KonIQ-trained checkpoint's KonIQ results are training-exposed
pipeline diagnostics, even if this script's development/comparison IDs differ.
KADID is a cross-dataset diagnostic; source-image overlap remains unaudited. Reuse
the unchanged quality cohort/partitions and report raw technical-IQA agreement
without model fitting, score fusion or culling-policy changes. Fix preprocessing,
CPU/thread settings, offline loading, resource limits and paired-bootstrap recipe
before inference. Save each prediction atomically and independently review the
actual run and resume before the next normal push. Copy retrieval remains a
separate next target; G1/G2 directed-coverage evidence remains a separate gate.
