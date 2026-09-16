# Scoring Engine Module Contract

## Purpose

This module converts a bounded image preview plus backend responses into a
stable `ScoreBundle`.

It owns score assembly, early rejection paths, scene-aware exposure rescoring, and layered signal generation.

## Main Files

- `src/material_agent/domain/scoring_engine.py`
- `src/material_agent/domain/layered_decision.py`
- `src/material_agent/scorers/exposure.py`
- `src/material_agent/scorers/sharpness.py`
- `src/material_agent/scorers/aggregator.py`

## Responsibilities

- decode bounded previews into grayscale and JPEG-ready data
- prefer camera-embedded JPEG/thumbnail data before falling back to RAW
  half-size postprocess
- run local pixel scorers
- reject only catastrophic whole-frame blur before learned inference
- measure authoritative subject focus after object detection, with eye ROIs for
  detected faces and spectral-residual saliency as a model-free fallback
- optionally run fast screening
- call the backend client for vision dimensions
- merge pixel and vision scores into one `ScoreBundle`
- produce policy-facing metadata such as decision, reasons, visible breakdown, and signals

## Non-Goals

- CLI argument parsing
- runtime event emission
- database schema management
- XMP writing

## Inputs

- `RawFrame` with JPEG bytes, grayscale preview, preview source, original size,
  and preview size metadata
- backend client implementing `BackendClient`
- normalized config
- optional fast-screening port

## Outputs

- `ScoreBundle` containing:
- numeric scores
- total score
- scene and `scene_raw`
- decision metadata
- signals for later rescore and policy review
- user-facing instruction strings

## Invariants

- output scores should stay bounded to expected numeric ranges
- score bundle shape must remain compatible with runtime persistence and rewrite flows
- rejection paths must still emit enough information for downstream summary and persistence
- normal results and every early-rejection path use the same layered summary as
  the sole authoritative total; there is no separate pixel/vision aggregate
- `scene_profiles` is the canonical scene-weight configuration; legacy
  `scene_weights` is accepted only as a normalization-time input alias
- RAW previews remain RGB for grayscale analysis, but must be converted to BGR
  before OpenCV JPEG encoding so downstream PIL/model consumers receive the
  original RGB colors
- scene-aware exposure rescoring happens after the backend returns scene context
- subject and eye focus use the retained 2048-edge grayscale preview and record
  the ROI source, confidence, bounding box, and Laplacian measurements
- whole-frame sharpness is an early catastrophic-blur guard, not a substitute
  for subject focus

## Group selection contract

Group finalization records versioned `meta.quality_assessment` (original decision
and defect reasons) independently from `meta.selection` (decision, role, reasons).
The compatibility `decision` is the selection result. With grouping and
`best_candidate_review.enabled` enabled, every group containing scored readable
photos has at least one explicit keep. If quality policy kept none, the highest
finite score is retained with role `group_coverage` and reason
`group_coverage_fallback`; ties use file path order. Existing review results and
hard-defect reasons do not block coverage. Scores, stars and original defects
remain unchanged. Decode failures/unscored payloads do not participate.
Refinalization starts from stored quality, so an old fallback is not treated as
an independent quality keep. Disabled grouping/fallback retains quality decisions.

Rescore persists both facts in `score_metadata_json` and preserves other model
metadata. Scene-filtered rescore recomputes only selected quality assessments,
but reconciles selection across their full stored groups when coverage is enabled;
other scenes retain scores/stars/ranks. The returned count counts quality updates.
No rescore action writes photo metadata. The score/output cache revision changes
with this policy to invalidate terminal results produced by the old fallback.

## Evidence applicability and optional refinement

`meta.face_eye_evidence` distinguishes measured `observed`, unresolved `unknown`,
and explicitly supported `not_applicable`. No face detection means unknown, not
poor eyes or a back-view assertion. A back-view/silhouette context needs label,
finite confidence >= 0.9, source, evidence and an evidence_type of
`visual_annotation` or `model_visual_context`. Measured eye ROIs take precedence
if context conflicts. Generic subject/clarity/sharpness scores no longer create
an eye usability signal; rescore ignores legacy `preview_proxy` eye signals.
Unknown/not-applicable is persisted in metadata rather than encoded as a zero.

`focus_integrity.selective_refinement` is opt-in (default disabled until quality
and latency acceptance). It schedules one pass for close top candidates,
insufficient focus resolution, or unknown portrait eye evidence. Defaults are
2 candidates/group, 5 seconds to schedule new work, score gap 0.5, and a 3072-edge
focus image; validated caps are 8 candidates, 60 seconds and 4096 pixels. RAW
half-size decode remains read-only. Record actual focus dimensions; if the new
observation has no greater pixel area, retain baseline evidence and record
`no_resolution_gain`. Never equate a RAW source with a better observation.

Keep pre-refinement scores/signals and trigger/outcome/elapsed-budget metadata.
Failed, exhausted or unresolved candidates carry `review_required`; retries are
not recursive and cached attempted candidates do not repeat the pass. The elapsed
time bound stops starting new callbacks, not a running synchronous decode.
Coverage finalization runs after refinement without inflating the resulting score.
This is local implementation evidence, not proof of improved selection quality.

## Typical Safe Changes

- tweak score combination logic
- add metadata to `ScoreBundle`
- improve screening failure handling
- adjust visible breakdown generation
- add more preview metadata without changing sidecar output directly

## Risky Changes

- changing score field names
- changing decision or signals without updating rescore logic
- changing scene handling without checking constants, labels, and migration paths
- changing decode assumptions in a way that affects backend or scorer expectations

## Files Usually Safe To Edit Together

- `src/material_agent/domain/scoring_engine.py`
- `src/material_agent/domain/layered_decision.py`
- `src/material_agent/scorers/*.py`
- `tests/test_scorers.py`
- `tests/test_dimension_redesign.py`
- `tests/test_rescore.py`

## Minimal Verification

- `pytest tests/test_scorers.py tests/test_rescore.py tests/test_review_job.py`

## Known Tensions / Technical Debt

- `ScoreBundle` currently carries both machine-facing policy fields and user-facing instruction strings, which mixes concerns.
- The module bridges RAW decoding, screening, model invocation, and policy summarization, so it is one of the densest files in the codebase.
- The config contract is powerful but implicit; many scoring changes require careful reading of config normalization and constants.
- The current VLM path is useful for structured scene/dimension scoring and explanation, but future culling improvements should be benchmarked as ranking work rather than assuming a larger VLM is the best main scorer.
- Learned experiments compare against the current heuristic baseline and the enabled Intel SSD/YuNet + NIMA path, using group top-1, pairwise preference and false-reject metrics. MUSIQ + VLM is not the default baseline.
- Subject and eye focus are still measured from a bounded embedded preview, not
  a full-resolution RAW crop. The recorded provenance must remain explicit; a
  future ambiguous-candidate pass may add true sensor-resolution ROI decoding.
