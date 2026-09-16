# Audited implementation status, 2026-09-16

This separates the completed bounded inference task from the broader product
plan in the September 14 design decisions. Status is based on current code and
local tests, not on the roadmap's historical deployment summaries.

## Current product rule and execution boundary

Grouping is consecutive capture-time proximity AND perceptual-hash proximity.
`grouping.hash_threshold: 0` bypasses hashing. There is no semantic, embedding,
all-pairs or same-action veto. The previous strict semantic grouping requirement
has been superseded by the user; do not treat it as unfinished implementation.
The broader distinction between image quality and selection role still matters.

Preserve the dirty checkout. No commit, push, deployment, production review,
photo/XMP write, private-host mutation or existing-database migration has been
performed in this continuation. In-memory XML and mocked command construction
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
| D05 evidence applicability and selective refinement | Implemented locally; refinement opt-in | Explicit observed/unknown/context-supported not_applicable; generic eye proxies removed. One-pass candidate/time/size bounds, baseline retention, no-resolution-gain guard and review reasons tested. Six real public RAWs show no larger half-size focus image, so refinement stays disabled pending quality acceptance |
| D06 remaining model experiments/fusion | Not executed | TOPIQ/MUSIQ/MediaPipe/other candidates need separate frozen task-relevant datasets and resource comparisons. Stanford40 action labels do not validate technical quality or personal preference. No production fusion added |
| D07 state/container resilience | Existing implementation, target revalidation outstanding | Appdata paths and state tests exist. No live backup/restore/container recreation or library-relocation migration was performed here; keep those separate from local code proof |
| D08 GPT proxy acceptance | Not executed; channel/data gap verified | No callable model-completion connector, API key/base URL environment, or local .env was available in this continuation. Six public RAWs lack burst preference labels; Stanford40 is action classification. Need a relevant frozen subset and independent model judgments with order reversal and baseline comparison |

## Work completed in this continuation

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

Verification:

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
   Image subset and independent GPT channel remain unavailable. Photo Triage is
   task-relevant but its official download service failed this access check.
   Run blinded/order-reversal comparison only after those inputs are available.
5. Run further model candidates individually only against a matching frozen
   benchmark. Personal ranker training still requires genuine preference labels.
6. Separately authorize and verify professional-software round trips and target
   hardware/storage operations. Do not label these complete from local tests.

The plan is therefore **not fully complete**. The original inference task is
complete; the broader business closure and external acceptance remain explicit
work items rather than being hidden behind a generic “production ready” label.
