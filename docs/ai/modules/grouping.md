# Grouping Module Contract

## Purpose

This module groups photos into review sets before scoring and write-back ranking.

The current strategy is adjacent time AND perceptual-hash proximity.
`grouping.time_gap_seconds` bounds adjacent capture-time gaps;
`grouping.hash_threshold` is an integer Hamming-distance limit (0..64).
Zero skips all hash reads and groups by time alone. Positive limits require
both timestamps and both hashes; missing evidence splits the group.
Comparisons use consecutive photos in stable capture-time order, not a group
centroid or all-pairs test. Total group duration may exceed the adjacent gap.
No semantic label or embedding similarity participates in grouping.

Legacy `visual_similarity.enabled/hash_threshold` settings map to the new
threshold only when `grouping.hash_threshold` is absent (disabled maps to 0).
`max_merge_gap_minutes` and `embedding_similarity` no longer affect grouping.
The retained CLI flag `--no-visual-merge` sets the new threshold to 0.

## Main Files

- `src/material_agent/domain/grouper.py`
- `tests/test_grouper.py`

## Responsibilities

- read `DateTimeOriginal` values with cache support
- split at any adjacent time or enabled hash mismatch
- cache successful 64-bit perceptual hashes for RAW previews and standard images
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
- hash similarity never bypasses the time limit; embedding never bypasses either limit
- missing EXIF timestamps must not crash grouping
- bulk EXIF reads must use bounded batches so large libraries do not exceed the
  operating-system command-line limit
- one failed EXIF batch may fall back per file without forcing successful
  batches through the slower path
- EXIF cache updates should remain opportunistic and safe, including caching a
  valid absence of `DateTimeOriginal`
- a timeout, non-zero ExifTool exit, malformed bulk response, or omitted bulk
  row is not proof that metadata is absent; retry omitted rows individually and
  never persist a transient read failure as a cached absence
- cache lookups for large libraries must split SQLite `IN` queries below the
  engine parameter limit
- `grouping.best_candidate_review.enabled` is scoped by `grouping.enabled`;
  when grouping is enabled, it may still preserve the only candidate in a
  genuine singleton group, but it must not affect the synthetic singletons
  produced when the entire grouping stage is disabled

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

- EXIF reading still mixes bounded bulk `exiftool` calls and per-file fallback
  logic inside one module.
- Hashing preserves the standard-image and embedded-preview fast paths. Missing or
  unsupported RAW thumbnails use one read-only half-size postprocess with camera
  white balance and 8-bit output, then the same 256-pixel thumbnail and 64-bit
  pHash. Successful results use the existing cache; failed decoding stays missing.
  Threshold zero bypasses all hash/decode work. Half-size decoding can be expensive
  on large sensors and must be profiled rather than treated as a free fallback.
- pHash tolerates some exposure variation but not arbitrary clipping or lost
  detail. A failed exposure-only match can create a singleton with coverage keep;
  quality rejection and selection retention remain separate. Do not widen the
  threshold or bypass hashing silently to hide this limitation.
- Consecutive similarity can chain; semantic distinctions are deliberately outside the current user-defined grouping rule.
