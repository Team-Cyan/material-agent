# Persisted-score audit and finite-quality cache isolation

## Evidence scope

A bounded read-only API audit of the deployed release found that the latest
finished full-library job is dated August 28, 2026. It scored 40,620 files with
zero errors, 40,620 simulated outputs and zero photo writes. The current service
is idle. Library filters report 5,963 review records and zero keeps; these are
historical persisted results, not a rerun of the current policy.

Eight high-score rows and eight lowest-review rows were sampled; two complete
stored payloads were inspected. The highest sample is 7.03 with an inherited
`portrait_face_eye_needs_review` reason, an empty detected-face list and a
`preview_proxy` eye signal. The lowest review sample is 2.69 with the legacy
`top1_review_fallback` reason. Neither inspected payload has the current
`meta.quality_assessment` or `meta.selection` records. These observations confirm
old-result provenance; they do not demonstrate regressions in the current code.

The current scoring contract already separates quality from coverage selection,
retains unavailable eye evidence and ignores legacy proxy eye signals on rescore.
Deployment alone does not recompute stored scores. No scoring, rescore, thumbnail
GET, model inference, database migration or metadata write was performed by this
audit. JSON GET receipts and private file identities remain in ignored controller
storage.

Library API results choose each file's latest job, without a job/status filter.
The current config GET returns raw redacted YAML, not an old job's normalized
effective configuration. Therefore neither result should be used as a frozen
cohort comparison. The latest historical samples can establish outlier existence,
but the full grouping/rank distribution versus the singleton baseline remains
unverified. A future audit must bind explicit job IDs, their session snapshots,
all relevant group rows and full persisted quality/selection fields. The existing
`review-scores` command reads its database without mutation, but selects only the
latest finished job and reconstructs previews with today's decoder; it cannot
prove historical JPEG byte identity or compare an arbitrary prior job.

## Conditional cache defect

The [finite-quality validity fix](2026-10-06-static-lifecycle-quality-validity.md)
rejects bad raw/configuration/aggregate values inside the quality adapter. A
processed score cache is reused earlier in the scoring path when the file
fingerprint and score/output cache key match, so it bypasses that adapter. The
previous key tracks configuration, distributions and model assets but has no
finite-quality evidence revision. If a user previously ran enabled PyIQA quality
and cached invalid evidence, an ordinary later run could reuse it after the fix.
There is no evidence of affected live rows: the default quality block is disabled
and the inspected dry-run jobs did not write processed cache results.

The scoped correction adds a finite-quality evidence revision only when the
backend is local and the quality block is enabled. Enabled quality results made
before the guard no longer match. The global pipeline revision and cache
identities for quality-disabled and nonlocal configurations remain unchanged.
Existing cached rows are retained; this is a future lookup boundary, not a
production rewrite or scoring-policy promotion.

## Verification and continuation

A temporary processed repository verifies that unchanged files with the old
quality key miss, current finite cached results hit, and the old key cannot reuse
the newly written result. Legacy-key comparison and scoped-revision checks prove
that default, disabled-quality and nonlocal identities remain unchanged. No real
quality model is initialized. Checks pass 26 focused cache tests, 1,416 full
tests / ten skipped, three repository-boundary checks and lint.

Complete independent review, normal push, exact-revision CI and authorized native
release verification. The runtime check verifies image/API/library/configuration
integrity; the lean image does not contain PyIQA and does not establish quality
model accuracy.

The next diagnostic improvement is job-pinned comparison of existing stored
results with explicit missing quality/selection evidence. It must not trigger
a production rerun merely to populate a new schema. Independent human references,
actual RAW input acceptance and optional MUSIQ resource admission remain separate
gates; the admin WebUI and closed annotation-viewer branch do not need expansion.
