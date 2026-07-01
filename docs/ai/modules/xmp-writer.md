# XMP Writer Module Contract

## Purpose

This module translates review results into XMP sidecar updates while preserving user-authored keywords when possible.

## Main Files

- `src/material_agent/adapters/metadata/exiftool_xmp.py`
- `src/material_agent/app/rewrite_xmp_service.py`
- `tests/test_writer.py`

## Responsibilities

- map score totals to star ratings
- build `pj:*` machine subject tags
- preserve non-machine subject tags already stored in XMP
- write rating, Photoshop instructions, `x-default` description, creator/lifecycle fields, XMP document IDs, and subject tags
- support full XMP regeneration through rewrite flows

## Non-Goals

- deciding scores or ranks
- commentary policy
- CLI parser behavior
- SQLite runtime event emission

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
- new sidecars should write `dc:description` as `rdf:Alt` with `xml:lang="x-default"`
- new sidecars should include `xmp:CreatorTool`, `xmp:MetadataDate`, `xmp:ModifyDate`, `xmpMM:DocumentID`, and `xmpMM:InstanceID`
- existing sidecar updates should write descriptions through the explicit `x-default` language alternative
- existing sidecar updates should write `photoshop:Instructions` through the explicit Photoshop namespace
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
- `pj:*` machine data still lives in `dc:subject`; a future profile/schema pass should move authoritative machine fields into a custom namespace while preserving a small compatibility mirror if needed.
- New sidecars now include creator/lifecycle metadata and XMPMM IDs, but the existing-file ExifTool update path intentionally avoids overwriting `xmpMM:DocumentID` until a preservation/migration policy exists.
