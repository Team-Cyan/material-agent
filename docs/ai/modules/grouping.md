# Grouping Module Contract

## Purpose

This module groups photos into review sets before scoring and write-back ranking.

The current strategy is time split first, then optional visual merge.

## Main Files

- `src/material_agent/domain/grouper.py`
- `tests/test_grouper.py`

## Responsibilities

- read `DateTimeOriginal` values with cache support
- split files into temporal groups
- optionally merge adjacent groups using perceptual hash similarity
- report progress for grouping phases

## Non-Goals

- score computation
- commentary generation
- XMP output
- runtime session/job orchestration

## Inputs

- raw file paths
- grouping config
- optional processed-state repository for EXIF cache
- optional progress reporter

## Outputs

- ordered `list[list[str]]` groups for downstream review ranking

## Invariants

- file order inside the grouping result must be stable and time-oriented
- visual merge is only attempted for adjacent groups
- missing EXIF timestamps must not crash grouping
- EXIF cache updates should remain opportunistic and safe

## Typical Safe Changes

- adjust merge thresholds
- improve EXIF fallback behavior
- tighten progress reporting
- optimize hash generation or caching behavior

## Risky Changes

- changing group order semantics
- changing the meaning of time gaps without reviewing user-facing expectations
- introducing expensive image decode work into the fast path without profiling

## Files Usually Safe To Edit Together

- `src/material_agent/domain/grouper.py`
- `tests/test_grouper.py`
- `tests/test_pipeline.py`

## Minimal Verification

- `pytest tests/test_grouper.py tests/test_pipeline.py`

## Known Tensions / Technical Debt

- EXIF reading currently mixes bulk `exiftool` calls and per-file fallback logic inside one module.
- Visual merge depends on thumbnail extraction from RAW files, which can become expensive on large datasets.
- Grouping policy is simple and practical, but scene-aware or burst-aware grouping has not been isolated into separate strategies yet.
