# Batch 1 reference tooling result — 2026-09-27

Status: implementation and local contract checks complete; **actual browser
interaction/download acceptance remains unverified**. G1 remains
`reference_insufficient`. No new human labels, photo collection, model experiment,
production run, XMP write, source-photo change, commit, push or deployment occurred.
Batch 2 is reported separately by its owner in `candidate-graph/`.

## Delivered files and behavior

- `scripts/human_reference.py`: schema/semantic validator, source/preview byte
  checks, frozen identity, G1 quota diagnostic, neutral viewer generation,
  append-only export merge and per-annotator resume.
- `scripts/human_reference_viewer.html`: self-contained two-image viewer,
  correspondence and both directional labels, independent quality judgment,
  visible-region coordinates, reasons, timestamps, save/export and unsaved-change
  guards. No prior labels, paths, source targets or algorithm scores are exposed.
- `scripts/human_reference_demo.py`: reproducible original geometric fixtures;
  only writes ignored local output and refuses existing output collisions.
- `tests/test_human_reference.py`: 48 focused tests.
- This directory: `schema.json`, `synthetic-example.json`, `rubric.md`,
  `README.md`, and this report. No image data is stored here.

The manifest keeps raw independent judgments and later adjudication separately.
Two independently generated bundles can merge into the same accumulated
manifest because identity binds immutable membership and annotator registry,
not the changing annotation array. Duplicate records/imports, stale identities
and wrong mappings fail. Partial export/merge/resume skips the same annotator's
submitted pairs and leaves other annotators' judgments hidden. When no pairs
remain, viewer generation returns an explicit completion-of-input message;
that message is never a G1 pass.

Counting excludes historical/model/synthetic/video events, nonhuman or nonfresh
annotation origins, ambiguous directions, unseen/limited regions and unresolved
disagreement. Families and related lineage cannot cross splits; repeated source
or preview content cannot be relabeled as another event. Duplicate/reversed pairs
and renamed identical content pairs cannot inflate the denominator. Source bytes
are unchanged during rendering and embedded images have source metadata removed.
The CLI checks image dimensions/orientation and requires prepared sRGB RGB
PNG/JPEG previews without ICC profiles. RAW preview production is a separate,
authorized curator operation and is not silently added here.

## Actual verification

| Command/check | Actual result |
| --- | --- |
| `uv run pytest -q tests/test_human_reference.py tests/test_repository_boundary.py` | 50 passed (48 focused + 2 repository boundary), 0.21 seconds |
| `make check` | `All checks passed!` |
| `git diff --check` | Exit 0 |
| `node --check .local/reference-tooling-demo/viewer-syntax.js` | Exit 0; extracted generated inline JavaScript only, no browser execution |
| `uv run python scripts/human_reference_demo.py --out .local/reference-tooling-demo` | Six geometric PNGs, empty synthetic manifest, development viewer and private mapping generated locally |
| CLI `merge` → `validate` → resumed `viewer` on constructed export | All exit 0; original manifest preserved; resumed viewer contains only P002 |
| New-file boundary/whitespace scan | All nine Batch 1 public text files passed; checked separately because repository boundary tests enumerate tracked files |

The local CLI smoke used `synthetic-export.json` with explicit `origin:
synthetic`, not a human or browser-generated annotation. Its merged validation
reports `schema_valid: true`, `files_verified: true`, `eligible_pairs: 0`,
`independent_families: 0`, `g1: reference_insufficient`, and
`human_authenticity: not_machine_verifiable`. Unit fixtures that deliberately
satisfy declared quotas return only `quota_ready_pending_human_audit`; those
fixtures are synthetic software tests, never evidence of real human gold.

The exact CLI smoke can be reproduced after generating a fresh private demo and
constructing a schema-valid export, or inspected in the saved local artifacts:

```sh
uv run python scripts/human_reference.py merge .local/reference-tooling-demo/manifest.json \
  --mapping .local/reference-tooling-demo/viewer.mapping.json \
  --annotations .local/reference-tooling-demo/synthetic-export.json \
  --out .local/reference-tooling-demo/merged-smoke.json
uv run python scripts/human_reference.py validate .local/reference-tooling-demo/merged-smoke.json
uv run python scripts/human_reference.py viewer .local/reference-tooling-demo/merged-smoke.json \
  --split development --annotator demo_operator \
  --out .local/reference-tooling-demo/resume-smoke.html
```

Existing output names intentionally cause failure; use fresh names to rerun.
The Python tests reproduce these identity/merge/resume contracts with isolated
fixtures and cover both consistent independent judgments and disagreement.

## Browser acceptance gap

The attempted actual CUA navigation to the demo's `file://` URL was blocked by
the browser URL policy: only HTTP/HTTPS are allowed, and the rejection explicitly
forbids achieving the same outcome through workarounds/alternate surfaces.
No HTTP server, second browser, CDP or other workaround was used. Therefore
actual pointer dragging, visual layout, UI validation, browser download and a
**real browser export** round trip are not verified. Static JavaScript syntax,
HTML payload blinding, coordinate validation and constructed export import tests
are narrower evidence and do not replace that acceptance. The main task
explicitly accepted recording this remaining dependency.

## Limits and next inputs

This validator checks declared provenance, schema and bytes. It cannot prove a
human's identity/honesty, source permission, real camera capture time or complete
lineage declarations, and it does not claim to prevent malicious forgery. A
human curator must audit these facts. Dataset mutations require a new frozen
package; old bundles do not silently transfer. Changing the annotator registry
also changes bundle identity, so declare independent annotators before issuance.

A suitable fresh still-photo source set and independent human annotators remain
required. Begin with the parent plan's 32 pairs/16 events target and inspect
missing quotas before any new algorithm experiment. An allowed browser/manual validation
workflow must finish visual/drag/download acceptance. Testing is already
authorized; the remaining limitation is the browser URL security policy. No complete G1/G2 or
product acceptance is claimed by this batch.

Recovery state is saved atomically in ignored
`.local/task-handoffs/culling-2026-09-27/human-reference.md`. Generated evidence
remains under `.local/reference-tooling-demo/`; there is no need to commit or
publish to preserve this work for the coordinating task.
