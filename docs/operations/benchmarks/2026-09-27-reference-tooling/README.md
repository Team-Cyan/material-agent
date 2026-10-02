# Human-reference tooling (Batch 1)

This is an isolated annotation package, not a production culling mode. It needs
no model, download, server, new Python dependency, application database or XMP
write. Batch 2 results have a separate owner in `candidate-graph/`.

- `schema.json`: strict versioned JSON Schema; `scripts/human_reference.py`
  validates its used subset and additional semantic/provenance constraints.
- `rubric.md`: annotation meanings, coordinates, independence and adjudication.
- `synthetic-example.json`: public, empty-label geometric fixture manifest.
  Its image paths become usable after the demo generator runs. It is never gold.
- `report.md`: implementation evidence and remaining acceptance limits.

## Generate and open the offline demonstration

From the repository root:

```sh
uv run python scripts/human_reference_demo.py --out .local/reference-tooling-demo
uv run python scripts/human_reference.py validate .local/reference-tooling-demo/manifest.json
```

Open `.local/reference-tooling-demo/viewer.html` in a normal browser that permits
local HTML. The bundled automation browser may block `file:` URLs; no real
browser interaction is claimed when that happens. The self-contained HTML has
no network calls, fonts, external assets, source filenames, category targets,
algorithm results, scores or prior judgments. Its CSP forbids connections.
The sidecar `viewer.mapping.json` is private and is **not** an annotator-facing
artifact. Do not share that mapping or the source manifest with blind annotators.
Development and holdout must be rendered as separate HTML bundles.

All generated files must remain under ignored `.local/`. Each output is created
exclusively; choose a new filename instead of overwriting an existing bundle or
manifest. Browser downloads use the browser's own download directory: save/move
the exported JSON into the private workspace, never into public docs.

## Use actual local images

A curator creates a private manifest alongside its relative preview paths,
following `schema.json` and the synthetic example. Source paths may also be
absolute. The tool only reads source bytes for SHA-256 verification; it never
rewrites sources or metadata. RAW decoding/preview creation is deliberately
outside this tool: provide an existing, authorized, oriented RGB PNG/JPEG
preview, converted to sRGB with its ICC profile removed. Non-RGB/ICC-bearing
previews and unapplied EXIF orientation are rejected. Record the exact preview
recipe, dimensions, source permission, source hash, preview hash, capture time
with timezone and actual capture-time provenance. Do not use file mtime as
camera metadata. The renderer strips metadata and embeds PNG pixels; annotation
hashes identify the verified input preview, and `human-reference-v1` identifies
the viewer recipe. No letterboxing, crop or geometric resize is applied to the
embedded pixels; browser scaling preserves the image aspect ratio.

Declare `new_still` only for a genuinely fresh still-photo event. Keep previously
inspected inputs as `historical_inspected`; derived/video/model/synthetic sources
have their own origins. Give related bursts, scenes, videos and derived variants
a shared `scene_family` and overlapping `related_sources` lineage IDs. Freeze
split assignments before annotation/evaluation. Declare all intended annotators
up front; their IDs/kinds are part of bundle identity. No category acquisition
target is a human label. The initial pair `annotations` arrays must be empty.

Set `freeze.at` to the actual freeze time; use any 64-character lowercase hex
placeholder for the initial digest, then create a frozen copy beside the input:

```sh
uv run python scripts/human_reference.py freeze .local/my-reference/draft.json \
  --out .local/my-reference/frozen.json
uv run python scripts/human_reference.py viewer .local/my-reference/frozen.json \
  --split development --annotator person1 --out .local/my-reference/person1.html
```

Both source and preview bytes/dimensions are verified by all CLI paths. Missing
inputs fail; there is no model fallback. Rendering a holdout bundle is a curator
operation: only supply development bundles to algorithm developers. The tool
separates bundles but does not provide access-control accounts or encryption.

## Annotate, export, merge and resume

1. Read `rubric.md`. Fill correspondence, both directional labels, both quality
   judgments, quality preference and both reasons. No label is selected by default.
2. Choose region importance, observed phenomenon, visibility and description;
   drag on A or B to record normalized coordinates. Clear regions to redraw.
   Use unknown/unjudgeable/preference-dependent when necessary. A negative
   direction requires an important region on its **target** image.
3. Save the pair, then navigate. Unsaved changes block navigation/export.
   Export saved annotations before closing; the viewer keeps state only in memory.
   A partial export is valid. Empty exports are blocked by the UI and cannot
   manufacture completion in the validator.
4. Merge the browser's JSON into a new local manifest, then validate:

```sh
uv run python scripts/human_reference.py merge .local/my-reference/frozen.json \
  --mapping .local/my-reference/person1.mapping.json \
  --annotations .local/my-reference/human-annotations.json \
  --out .local/my-reference/with-person1.json
uv run python scripts/human_reference.py validate .local/my-reference/with-person1.json
uv run python scripts/human_reference.py viewer .local/my-reference/with-person1.json \
  --split development --annotator person1 --out .local/my-reference/person1-resume.html
```

Resume displays only pairs not yet submitted by that annotator, preserving the
same neutral IDs. Other annotators' judgments stay hidden. If all pairs were
submitted, rendering exits with `no unannotated pairs for this annotator in
selected split` and creates no new bundle. Existing records are immutable on
import: corrections/adjudications need an explicit new record in the local
manifest; do not silently replace or regenerate a submitted independent record.

Independent annotators may generate their bundles from the same frozen dataset,
then merge their exports sequentially into the accumulated manifest. Bundle
identity includes immutable membership, source/preview identities, split and
annotator registry; it excludes appended annotations. Import rejects changed
membership/preview/annotator identities, incorrect mappings and duplicate record
IDs/imports. A failed merge leaves its input manifest unchanged. Manifest output
must share the input directory so relative source paths keep their meaning.

Human adjudication uses the same record schema with `role: adjudication` and
`supersedes` naming **all** independent human records for that pair. It must
start after those records completed. Keep the originals. The current viewer
collects independent annotations only; a curator records adjudication as JSON
and runs the same validator. No automatic majority vote or model adjudication
creates a reference. Additional judgments by the same person require explicit
adjudication/revision handling; they are not independent votes.

## Validator and gate interpretation

A validation command exits 0 for a structurally valid manifest even when G1 is
insufficient. Inspect `g1` and `missing`; do not interpret exit status as a gate
pass. Invalid schema/provenance/files exit 2. There is no accepted `complete` flag.

G1 quota calculations require fresh still events, new human-origin records with
human-declared annotators, verified files, resolved judgments, clear regions,
24–40 pairs and 12–20 independent **scene families** (a conservative counting
unit). They require six definite directions of each class across three families
in each split, visible illumination nuisance and hand/expression change in both
splits and at least two families overall for each, plus two nuisance types.
Unknown/unjudgeable/preference-dependent directions do not fill either quota;
an abstention-only pair also supplies neither a labeled pair nor a scene family
to the overall minimum. A pair with one definite direction counts once, and only
that definite direction contributes to its class quota.
limited/invisible/ambiguous regions do not count. Directions from the same pair
or related events cannot create additional independent families. Duplicate or
reversed pairs, renamed byte-identical content pairs, cross-event source/preview
digests and cross-split family/lineage reuse are rejected. A historical event
contaminates its whole family for fresh-gold counting.

The eight category acquisition targets (four pairs/two events each, default
32 pairs/16 events) remain sampling goals in the parent plan, not automatically
assigned labels. The report exposes observed `phenomena` and exact missing gates.
Do not expand the 40-pair cap to quietly satisfy missing quotas.

No software can authenticate an annotator's humanity, honesty, source ownership,
actual capture time, or the correctness of a self-declared lineage. This tool
strictly validates **declared provenance and byte identity**, not malicious
forgery. Even constructed data satisfying all checks only returns
`quota_ready_pending_human_audit`, never a complete G1 pass. A human curator must
audit source provenance, real independent judgments and acquisition permissions.
Do not promote models or claim product acceptance from this tooling/demo.

## September 28 handler verification supplement

The viewer now marks drafts dirty on `input` as well as `change`, protecting text
still being typed before blur. Source-level tests execute the actual template
script in installed Node with minimal DOM/Blob/URL mocks:

```sh
uv run pytest -q tests/test_human_reference_viewer.py tests/test_human_reference.py
```

Without installed Node, the handler tests explicitly skip; that is not evidence
of verified handlers. No new package or browser dependency is required. The
[dated report](2026-09-28-viewer-contract-report.md) records 31 executed handler
tests, captured Blob → Python merge/validate checks and their limits. Actual
browser layout, event delivery and download remain unverified. Existing local
HTML bundles retain the template version they were generated from; generate a
fresh output name to receive the fix rather than overwriting the old evidence.
