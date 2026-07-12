# XMP Writer Module Contract

## Purpose

This module translates review results into Adobe-compatible XMP sidecar updates
while preserving user-authored metadata when possible.

## Main Files

- `src/material_agent/adapters/metadata/exiftool_xmp.py`
- `src/material_agent/app/rewrite_xmp_service.py`
- `tests/test_writer.py`

## Responsibilities

- map score totals to star ratings
- build deterministic `pj:*` machine tags
- preserve non-machine subject tags already stored in XMP
- write standard `xmp:Rating`, Photoshop instructions, `x-default`
  description, creator/lifecycle fields, XMP document IDs, clean user keywords,
  and machine identifiers
- update an existing `.xmp` or `.XMP` sidecar instead of creating a duplicate
- support full XMP regeneration through rewrite flows

## Non-Goals

- deciding scores or ranks
- commentary policy
- CLI parser behavior
- SQLite runtime event emission
- direct proprietary RAW file metadata mutation

## Inputs

- file path
- star rating
- generated subject tags
- score/instruction summary
- combined commentary text

## Outputs

- updated or newly created `.xmp` sidecar files

## Invariants

- non-machine subject tags should be preserved whenever readable
- generated `pj:*` tags should be deterministic for the same score payload
- generated `pj:*` tags should be stored in `xmp:Identifier`, not normal
  `dc:subject` keywords, so DAM apps do not show machine data as user keywords
- `dc:subject` should contain only preserved user-authored keywords by default
- new sidecars should write `dc:description` as `rdf:Alt` with `xml:lang="x-default"`
- new sidecars should include `xmp:CreatorTool`, `xmp:MetadataDate`, `xmp:ModifyDate`, `xmpMM:DocumentID`, and `xmpMM:InstanceID`
- new sidecars should write a standard XMP packet header and an explicit
  `xmp:Rating` element
- existing sidecar updates should write descriptions through the explicit `x-default` language alternative
- existing sidecar updates should write `photoshop:Instructions` through the explicit Photoshop namespace
- existing sidecar updates should clear stale `pj:*` data from `dc:subject`
  while preserving non-machine user keywords
- XMP output must stay compatible with ExifTool writes and rewrite flows

## Typical Safe Changes

- add one more generated `pj:` tag
- improve preservation of existing user metadata
- adjust how instructions or descriptions are assembled
- improve error messaging around write failures

## Risky Changes

- changing XML structure without checking existing readers
- removing preservation behavior for user keywords
- depending on ExifTool behavior that differs between updating an existing file and creating a new file
- writing ratings directly into proprietary RAW files; use sidecars unless a
  format-specific, opt-in, verified writeback path exists

## Files Usually Safe To Edit Together

- `src/material_agent/adapters/metadata/exiftool_xmp.py`
- `src/material_agent/app/rewrite_xmp_service.py`
- `tests/test_writer.py`

## Minimal Verification

- `pytest tests/test_writer.py tests/test_state.py`

## Known Tensions / Technical Debt

- The writer currently uses both ExifTool writes and direct XML generation, which means there are effectively two write paths to keep aligned.
- `RewriteXmpService` reaches into writer internals such as `_read_non_ai_subject_tags()` and `_write_minimal_xmp()`, which is practical but leaky.
- Description formatting is assembled in runtime wiring rather than owned entirely by the writer boundary.
- New sidecars now include creator/lifecycle metadata and XMPMM IDs, but the existing-file ExifTool update path intentionally avoids overwriting `xmpMM:DocumentID` until a preservation/migration policy exists.
- `pj:*` machine data now lives in `xmp:Identifier`. This avoids polluting
  user keyword lists but still keeps deterministic machine tags in a standard
  XMP Basic bag readable by ExifTool.
- DaVinci Resolve compatibility is not guaranteed by this module. The target is
  standards-based XMP that common DAM/photo tools can read; Resolve should be
  verified with a real fixture matrix before claiming support.
