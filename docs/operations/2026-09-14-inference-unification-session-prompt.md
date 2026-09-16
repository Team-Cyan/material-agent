> Status 2026-09-16: Phase 1 Gates 0–3 are completed. The user superseded semantic grouping with adjacent time AND hash proximity (hash threshold 0 means time only). Use the [current full-plan status](2026-09-16-plan-status.md) for remaining work; the prompt below is the original scoped task.

# Session Prompt: Unify Local Inference Before Multi-Model Expansion

Copy this prompt into a separate implementation session.

```md
# Task: Phase 1 Local-Inference Unification With Baseline Parity

Work in the current `material-agent` checkout. Inspect the live checkout before
changing it: read `AGENTS.md`, `docs/ai/shared-context.md`,
`docs/ai/inference-runtime.md`, `docs/ai/model-selection.md`,
`docs/ai/modules/scoring-engine.md`, `docs/ai/modules/xmp-writer.md`, and the
canonical decision record
`docs/operations/2026-09-14-design-review-decisions.zh-CN.md`. Read the
relevant implementation, tests, and configuration after that. Treat the
decision record as product direction, not as a claim that its proposed
behavior is already implemented.

Preserve unrelated worktree changes. Re-check the current code and tests rather
than relying on old architecture descriptions. Do not commit, push, publish,
deploy, operate a live service, alter a container, or change private-machine
configuration.

## Product Direction

The product's main value is automatic preselection while avoiding destructive
false rejects. A substitutable candidate group is strict: it contains the same
subject performing the same action, not merely images close in time or visually
similar. Event/context groups and file-version groups remain distinct concepts.

For example, a session can contain ten dishes with one to five photos of each.
At least one photo of every dish must remain a keep candidate even if the
technical or aesthetic score is low. The same coverage rule applies to each
distinct action. The system must keep independent concepts for technical/
aesthetic evidence, group recommendation role, and keep/reject/preselection
status. A coverage keep or group fallback is not evidence that the image has
high quality.

This task is the prerequisite to later multi-model fusion. First unify the
actual inference implementation, then add models one at a time with measurable
evidence. Do not use this task to add a production VLM default, tune selection
thresholds, or claim a quality/acceptance improvement.

## What “Unify Inference” Means

It does **not** mean adding one interface while leaving model adapters with
different hidden execution behavior. Establish a shared, exercised execution
lifecycle and contract for eligible local models:

1. model declaration and compatibility validation;
2. model-specific but declared preview/ROI preprocessing;
3. compilation/session creation and a bounded persistent compiled-model cache;
4. bounded batch/request scheduling that preserves input-to-output association;
5. output normalization, error/fallback handling, and cacheable result records;
6. complete, truthful provenance and stage timing.

Native OpenVINO is the canonical accelerated execution implementation for Intel
models. CPU fallback must continue to work. Plain ONNX Runtime is a portable
adapter only where a particular model/export/platform justifies it; it is not a
reason to replace native OpenVINO on Intel. Do not force a model through
OpenVINO or ONNX Runtime when its operators, export, package support, or
preprocessing contract are unsupported. Preserve an explicit model-specific
adapter or a declared unavailable/fallback result in that case.

Keep the current supported baseline behavior working (including its deterministic
heuristics and currently supported OpenVINO components). A successful package
probe is not proof of model execution. Requested device, compiled device, and
actual execution devices must remain separate. If execution-device readback is
unavailable, record it as `unknown`; never copy the requested device into the
actual field.

## Scope: Implement a Bounded Phase 1

Implement the smallest complete local change that makes the shared lifecycle
real for the existing eligible inference paths. Start with an inventory that
maps each current model path to its real runtime, preprocessing, batching,
result cache, compiled cache, fallback, and provenance behavior. Use that
inventory to select the narrowest safe migration seam. The likely seams are the
local client, OpenVINO model adapters, configuration validation/normalization,
score/result DTOs, and their focused tests, but let the live checkout determine
the exact files.

The shared contract must cover, where applicable:

- a model identity that includes model name, version/revision, immutable asset
  digest, runtime/provider, and preprocessing revision;
- explicit input shape/layout, color-space, resize/crop/normalization, and ROI
  policy owned by the model declaration rather than accidental call-site code;
- batch size, request-pool/concurrency bounds, final-partial-batch behavior,
  ordering guarantees, and the requested versus actual batch strategy;
- a content-addressed result-cache key that includes every output-affecting
  factor, especially model asset and preprocessing/policy revisions; keep this
  distinct from the device-specific compiled-model cache;
- compile, preprocess, infer, and postprocess timing without double-counting a
  shared asynchronous run for every image;
- normalized success, unavailable, and fallback records. Fallback must state
  whether OpenVINO internally selected a device or the application compiled an
  explicit fallback after a failure, plus a bounded reason;
- provenance with the model identity, requested/compiled/actual execution
  devices, runtime version when available, fallback state, cache identities and
  hit/miss state, batching/request settings, preprocessing revision, and any
  unknown/missing evidence.

Do not flatten model semantics just to satisfy the contract. In particular,
object/face/eye evidence, aesthetics, embeddings, and semantic classification
can retain distinct output schemas. The contract should share execution facts
and lifecycle, then return each model's typed normalized result.

Preserve or introduce the smallest compatible state migration needed for these
provenance records. The persisted SQLite appdata is user data: do not reset,
delete, recreate, or relocate it. Keep SQLite local to persisted appdata and
preserve its migration/compatibility guarantees.

## XMP, Source Media, and External Boundaries

Input media is read-only. Do not write RAW files, XMP sidecars, or source image
metadata in this session. Do not run the production review command merely as a
"dry run" because it can write runtime job state; use the isolated
`benchmark-local` contract for side-effect-free evaluation.

The future projection policy is confirmed:

- fill only missing XMP rating fields or an explicit zero rating; zero is
  confirmed by the user as unrated, including a rating cleared back to zero;
- never overwrite an existing nonzero rating, including an old AI rating;
- replace only the material-agent-owned tag namespace on a rerun, preserving
  all unrelated human/DAM tags and fields;
- keep AI recommendation, imported human decision, effective result, and write
  record distinct so professional consumers such as Photoshop, Adobe Camera
  Raw, Bridge, and Capture One can consume a standard projection.

The zero-rating definition is resolved. Preserve any existing nonzero value,
including an external reject value such as -1; fail closed on malformed XMP.
Use only the exact app-owned keep/reject keywords for the future visible
projection, preserving all other keywords. Detailed machine provenance remains
separate. XMP write/import work belongs to a separate compatibility slice and
fixture validation, not this inference refactor.

## Evidence Semantics

For a back view or silhouette, face/eye evidence is *not applicable* when
enough contextual evidence establishes that the attribute cannot reasonably be
observed. For an undetected face/eye without that contextual evidence, record
`unknown`. Missing eyes alone must not apply a penalty. Keep confidence,
evidence source, and applicability separate so a later model does not turn an
absence of detection into a false negative.

## Evaluation and GPT Proxy Boundary

The user has authorized first-phase GPT proxy evaluation using relevant
personal photos or public datasets in principle. This inference task should
prepare the protocol and may use already available scoped fixtures for parity.
At evaluation execution time, resolve the actual sample location and available
review channel, record the selected scope, and preserve private identifiers.
Do not expand this to ongoing whole-library external transmission. A production
VLM is out of scope.

If you add the evaluation harness or schema, label each observation explicitly
as `model_generated` or `human_reference`. Prefer independently available
public dataset labels for `human_reference`. Split train/tuning and holdout by
shooting event/candidate group, never by individual file path. Compare baseline
and candidate judgments blind to the evaluator, preserve the judgment record,
and report the proxy result as a proxy only. Do not claim it proves subjective
human acceptance, professional preference, or production readiness.

If evaluation lacks an API key, accessible samples, or a defined review
channel, report the specific missing input and continue the local unification
path. Do not ask again for authorization already supplied by the user.

## Required Stage Gates

### Gate 0 — Checkout and contract inventory

Report the current worktree state and the inventory of actual model execution
paths. Identify any mismatch between documentation, configuration, and code.
Do not assume every documented model is active.

### Gate 1 — Design and compatibility plan

Before broad refactoring, state the selected lifecycle seam, compatibility
strategy for existing result/state payloads, cache-key changes, and the focused
test plan. Keep the change local and reversible. If a necessary decision would
alter grouping semantics, XMP ownership, persisted-data meaning, or external
behavior, identify it as a blocker rather than inventing policy.

### Gate 2 — Phase 1 implementation and parity tests

Implement the selected shared lifecycle. Add focused tests that prove at least:

- declared preprocessing and model identity affect result/compiled-cache
  identity as appropriate;
- a batched run preserves order and maps every result to its source image;
- partial batches and unavailable/unsupported models have explicit behavior;
- CPU fallback remains usable and its provenance differs from internal
  OpenVINO device selection;
- actual-device readback is `unknown` when unavailable;
- result-cache reuse cannot cross an output-affecting revision;
- existing baseline scores, group/ranking semantics, and result payload
  consumers retain compatibility for covered fixtures;
- no test or command writes XMP/source media.

Run the repository-required checks appropriate to the touched modules. Include
focused unit/integration tests, lint if Python changes, `git diff --check`, and
the repository-boundary test when public repository paths or operational
guidance change. Use `uv run python` rather than bare `python` where needed.
Report exact commands and results; do not call a check passed when it was not
run.

### Gate 3 — Measurable Phase 2 readiness, not Phase 2 implementation

Produce a concise model-by-model expansion matrix for the next session. For
each candidate, state its business hypothesis, supported runtime(s), input and
preprocessing contract, expected provenance, fixture/holdout requirement,
baseline comparison, resource budget, failure behavior, and promotion metric.
The first candidate must be added only after this Phase 1 parity baseline is
green. Do not silently add multiple models or fuse scores in this task.

## Deliverables

1. The focused implementation, migrations only if required, tests, and
   task-relevant documentation updates.
2. A concise before/after execution-path inventory.
3. The Phase 2 expansion matrix and evaluation protocol, with GPT proxy scope
   clearly separated from human-reference evidence.
4. An explicit readiness report containing:
   - completed gates and commands/results;
   - baseline-parity evidence and its limits;
   - changed files;
   - unresolved implementation items, including XMP compatibility fixtures,
     group/coverage persistence details if not already modeled, evaluation
     sample/channel availability, and unsupported model/runtime combinations;
     do not list the confirmed zero-rating rule as unresolved;
   - a clear recommendation of whether the next model-by-model experiment is
     ready to begin.

Do not include private filesystem paths, hosts, tokens, photo names, or other
private identifiers in committed artifacts or reports. Keep all repository
pointers relative.
```
