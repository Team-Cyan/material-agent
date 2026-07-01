# Scoring Engine Module Contract

## Purpose

This module converts a decoded RAW preview plus backend responses into a stable `ScoreBundle`.

It owns score assembly, early rejection paths, scene-aware exposure rescoring, and layered signal generation.

## Main Files

- `src/material_agent/domain/scoring_engine.py`
- `src/material_agent/domain/layered_decision.py`
- `src/material_agent/scorers/exposure.py`
- `src/material_agent/scorers/sharpness.py`
- `src/material_agent/scorers/aggregator.py`

## Responsibilities

- decode RAW previews into grayscale and JPEG-ready data
- run local pixel scorers
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

- `RawFrame`
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
- scene-aware exposure rescoring happens after the backend returns scene context

## Typical Safe Changes

- tweak score combination logic
- add metadata to `ScoreBundle`
- improve screening failure handling
- adjust visible breakdown generation

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
- Any learned scorer experiment should compare against the current `MUSIQ + VLM` path with group top-1 and pairwise preference metrics before replacing production scoring.
