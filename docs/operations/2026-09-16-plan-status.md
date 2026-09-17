# Audited implementation status, 2026-09-16

This separates the completed bounded inference task from the broader product
plan in the September 14 design decisions. Updated through the September 17 review continuation. Status is based on current code and
local tests, not on the roadmap's historical deployment summaries.

## Current product rule and execution boundary

Grouping is consecutive capture-time proximity AND perceptual-hash proximity.
`grouping.hash_threshold: 0` bypasses hashing. There is no semantic, embedding,
all-pairs or same-action veto. The previous strict semantic grouping requirement
has been superseded by the user; do not treat it as unfinished implementation.
The broader distinction between image quality and selection role still matters.

Local commits are authorized and have been made in reviewed batches. No push,
deployment, production review, source-photo/XMP write, private-host mutation or
existing-database migration has been performed in this continuation. In-memory XML and mocked command construction
are permitted local verification; they are not physical interoperability proof.

## Completion audit

| Plan area | Current status | Concrete evidence / remaining work |
| --- | --- | --- |
| Phase 1 Gate 0/1 | Complete | Actual-path inventory and approved migration seam in `2026-09-15-inference-unification-gates-0-1.md` |
| Phase 1 Gate 2 | Complete for covered local baseline | Shared native OpenVINO lifecycle, bounded caches, provenance, real CPU parity and state compatibility; see readiness report |
| Phase 1 Gate 3 | Complete | Candidate matrix and evaluation protocol delivered; this gate never required implementing every candidate |
| Revised grouping | Implemented | Both domain and compatibility entrypoints use adjacent time/hash; zero bypasses reads; embedding and cross-time merges removed; normalized legacy config and CLI compatibility tested |
| First additional model experiment | Complete as diagnostic | MobileCLIP: fixed 200-image Stanford40 test subset, 84.5% top-1 / 97% top-5, text cache p95 0.393 to 0.120 s, 8,000 probabilities identical |
| D01 / retained per-group preselection closure | Implemented locally | Readable scored groups retain an explicit keep, including all-defect groups; error-only groups remain errors. Versioned quality/selection metadata persists through cache and rescore; no score/star inflation. Grouping/fallback switches remain supported |
| D03 missing/zero rating and keywords | Implemented locally in this continuation | Ordinary write and rewrite protect nonzero ratings; malformed/duplicate declarations fail; exact visible keep/reject projection; 36 no-write policy/integration tests |
| D03 import/effective/write ledger | Implemented for projection attempts locally | Versioned imported/requested/planned/effective fields, unknown authorship, nonzero conflicts and field outcomes; independent append-only ledger survives processed errors; rewrite persists receipts and scalar ownership. External change watching and crash reconciliation are not implemented |
| D04 professional-software handoff | Unverified | No actual Bridge/Camera Raw/Photoshop or Capture One readback/writeback matrix has been run here; real XMP writes remain outside current authorization |
| D05 evidence applicability and selective refinement | Implemented locally; refinement opt-in | Observed/unknown implemented; context-supported not_applicable is a consumer contract with no local context producer. Generic eye proxies removed. One-pass candidate/time/size bounds, baseline retention, no-resolution-gain guard and review reasons tested. The later 100-frame holdout has 18 larger-focus completions and 22 no-gain attempts; ranking gain remains unproven and refinement stays disabled |
| D06 remaining model experiments/fusion | Three candidates compared diagnostically | TOPIQ/MUSIQ/MediaPipe ran on 100 frozen HDR+ frames. Resource results are recorded; unstable proxy references fail the promotion gate. No fusion/default change; personal ranker still lacks personal labels |
| D07 state/container resilience | Existing implementation, target revalidation outstanding | Appdata paths and state tests exist. No live backup/restore/container recreation or library-relocation migration was performed here; keep those separate from local code proof |
| D08 GPT proxy acceptance | Controlled pilot complete; full acceptance pending | Two fresh-context Codex panels each viewed 12 controlled candidates. Baseline and reversed-order preferences agree 6/6; zero false rejects among 6 proxy-acceptable candidates per panel. Missing-thumbnail hashing is fixed in accad08. A larger 20-event/100-frame holdout has A 20/20 and B 17/20 panels; quota blocks the last three groups and order agreement is poor. Full acceptance and missing case categories remain unverified. [Report](benchmarks/2026-09-16-codex-blind-pilot/report.md) |

## Historical September 16 projection batch

`exiftool_xmp.py` now checks all rating declarations before building an update.
Only missing or numeric-zero values permit a Rating argument. Any nonzero
integer value is preserved, including an earlier AI value or external -1.
Empty, malformed, nested or duplicate declarations stop the file before the
ExifTool command. The existing atomic-copy/identity-check/replace path remains.

Recognized `pj:decision=keep|review|reject` values produce exactly one visible
`material-agent:keep|reject` keyword; review maps to conservative keep without
changing its quality rating. Other keywords, including similarly prefixed
values, are preserved. Detailed provenance remains in `xmp:Identifier`.
Calls without a selection decision preserve existing visible selection tags.
Explicit AI tag cleanup also removes the two owned keywords.

An ordinary successful write returns requested/effective rating and projection
status. Review persistence keeps the AI score unchanged, stores the receipt in
metadata, and omits an untouched external rating from `xmp_payload_json`'s
AI-owned fields. The receipt is emitted only after atomic replacement succeeds.
This is not a claim that an existing rating was authored by a human.

Verification for that historical batch (not the latest suite):

- `PYTHONPATH="$PWD/tests" PYTEST_PLUGINS=inference_readonly_guard uv run --no-sync pytest -q tests/test_xmp_projection_policy.py`: **36 passed**.
- Full guarded suite: **703 passed, 102 skipped in 19.58 s**. Source/XMP-writing
  tests were not executed through their writes; optional missing dependencies
  also account for skips. Log: `.local/phase2-mobileclip/xmp-projection-regression.log`.
- Ruff checks passed. No source photo or XMP was created or modified.

## Ordered remaining work

1. Per-group coverage and quality/selection persistence are implemented and locally
   tested. Continue acceptance against task-relevant frozen preselection samples;
   do not restore semantic grouping.
2. Projection-attempt preview/import/effective-result and per-field ledger are
   locally implemented, including rewrite, conflicts and partial batch failure.
   Actual sidecar/software round trips and crash reconciliation remain unverified.
3. Evidence applicability and bounded optional refinement are implemented. Keep
   refinement disabled until a relevant quality/latency benchmark supports it;
   a RAW half-size decode is not automatically a higher-resolution observation.
4. Rubric v1 is frozen; see [acceptance preflight](2026-09-16-preselection-acceptance-preflight.md).
   The controlled pilot and opposite-order Codex reviews are complete; the real
   burst acceptance remains incomplete. A September 17 HDR+ real-burst subset
   adds new-event evaluation; see the follow-up report linked below. Photo Triage
   remains task-relevant but its official download service failed the access check.
5. Run further model candidates individually only against a matching frozen
   benchmark. Personal ranker training still requires genuine preference labels.
6. Separately authorize and verify professional-software round trips and target
   hardware/storage operations. Do not label these complete from local tests.

The plan is therefore **not fully complete**. The original inference task is
complete; the broader business closure and external acceptance remain explicit
work items rather than being hidden behind a generic “production ready” label.

## September 17 follow-up

See [review and real-burst evidence](2026-09-17-follow-up-validation.md) for shared
rewrite preflight, conservative refinement guards, actual context-producer limits,
new public data, and the latest dated verification. Earlier test counts above are
historical batch evidence and must not be read as the current total.

## September 17 expanded holdout and exposure counterexample

See the [100-frame comparison](benchmarks/2026-09-17-hdrplus-holdout/report.md)
for raw proxy responses, frozen model/resource plans and negative promotion
results. Latest guarded suite: **745 passed, 102 skipped**. All hashes are
available after the RAW fallback; one event still correctly splits on a real
five-hour EXIF discontinuity. No automatic back-view/silhouette producer exists.

The [real CR2 exposure counterexample](benchmarks/2026-09-17-exposure-brackets/report.md)
reproduces a 0.34-second pair with hash distance 24: default threshold 10 splits
it and keeps the dark quality-reject as a singleton. Threshold 24 or zero merges
this pair and rejects the dark frame, but neither is a validated new default.
Exposure-tolerant hash alternatives need labeled same/different-scene controls;
a time-only exception is an unresolved product choice.

[External acceptance steps](2026-09-17-external-acceptance-plan.md) are prepared;
professional-software writeback and target-host recovery remain unexecuted.

The follow-up hash ablation makes histogram-equalized pHash a candidate:
the exposure pair distance falls from 24 to 4 at unchanged threshold 10.
It passes the existing 200 positive/450 easy negative pairs, but these negatives
represent only 18 different-event comparisons and do not cover rapid dish/action
changes. No hash algorithm/default is changed; hard-negative labels and hash-cache
versioning are prerequisites for promotion.

A frozen [synthetic hard-case test](benchmarks/2026-09-17-hash-hardcases/report.md)
now covers 192 pairs from 24 source JPEGs, including fixed-background content
replacement and severe detail loss, with final quality/selection outcomes. On
holdout, equalization reduces brightness splits 16/48 -> 12/48 but leaves 11/24
content-change false merges and one resulting distinct-content reject. All
24 unrecognizable detail-loss frames remain singleton coverage keeps. This
confirms an acceptance gap; it does not authorize an exception or hash promotion.
The reusable read-only-image runner is `scripts/benchmark_hash_hardcases.py`.

## September 18 real action-transition check

[Two official MPII Cooking 2 videos](benchmarks/2026-09-18-cooking-hashes/report.md)
now add 25 frozen real-video pairs/38 unique frames, separate from synthetic
exposure tests. On ten held-out distinct-action boundaries, pHash/equalized
pHash/dHash merge 5/3/10 and each merge loses a distinct action through final
reject. Equalization also introduces a new move-to-peel merge that baseline
avoids. The candidates are not uniformly better and remain unpromoted. This
closes the absence of any natural action negative, not full product acceptance.

Local reproducible runners, frozen inputs and final selection evidence are
committed in reviewed batches. The unresolved work is now:

- Independent B-panel groups 18–20: bounded restoration retry produced no result
  or new error and was interrupted. Last explicit failure was quota; current
  retry cause is unknown. Do not substitute main-context judgments.
- Exposure-robust grouping: candidates improve some positives but fail real and
  synthetic action negatives. A new candidate must have broader independent
  evaluation and preserve time/hash and hash-cache compatibility contracts.
- Completely unrecognizable exposure frames: no time-only exception is approved;
  current conservative split/coverage behavior remains.
- Personal preference labels, automatic context-producer acceptance, actual
  professional-software XMP round trips and authorized target-machine verification
  remain distinct requirements, not implied by these experiments.
