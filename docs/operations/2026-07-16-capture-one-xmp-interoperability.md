# Capture One XMP Interoperability Contract - 2026-07-16

## Status

This document defines the pre-application contract for using material-agent as
an offline scorer and Capture One as the human culling client.

The XML/RDF and ExifTool portions are locally testable. Capture One readback,
writeback, unknown-field preservation, sidecar case handling, and NAS
permissions remain unverified until an isolated application fixture pass is
completed. Do not promote bidirectional synchronization on the primary photo
library before that pass.

## Product Boundary

The intended workflow is:

```text
material-agent scan/group/score
  -> standard XMP sidecar projection
  -> Capture One Load Metadata
  -> human compare/cull/rate
  -> Capture One Sync Metadata
  -> material-agent imports explicit human overrides
```

Material-agent may assign every rating from zero through five. Five stars is a
valid AI result; it is not reserved for human ratings. Provenance must be
represented separately from the rating value.

Capture One remains responsible for interactive browsing, comparison, culling,
manual ratings, color tags, and edits. Material-agent remains responsible for
the continuous aesthetic score, technical signals, model provenance, grouping,
and AI ranking.

## Evidence Boundary

Capture One's current official documentation says that it:

- reads embedded EXIF, embedded IPTC-IIM, embedded XMP, and `.XMP` sidecars;
- merges a same-name sidecar with metadata in a Session or Catalog;
- loads ratings, color tags, and keywords through the sidecar workflow;
- supports one-way `Load`, two-way `Full Sync`, and manual Load/Sync commands;
- can prefer sidecar metadata over embedded metadata;
- uses one sidecar for files with the same basename but different extensions;
- does not write metadata into the source RAW file;
- supports flat and hierarchical keywords, with hierarchy represented in the
  Lightroom `hierarchicalSubject` bag.

Adobe's XMP Basic schema defines `xmp:Rating` as `-1` or `0..5`, where `-1`
means rejected and `0` means unrated. Material-agent deliberately uses only
integer `0..5`; reject remains a separate decision rather than an XMP rating.

Capture One does not publish a complete guarantee for preserving arbitrary XMP
properties that it does not expose. In particular, preservation of
`xmp:Identifier` during Capture One writeback must be tested, not inferred.

## Sidecar File Contract

### Naming

- The sidecar has the same basename as the image and an `.xmp` or `.XMP`
  extension.
- If either case already exists, update it rather than creating a duplicate.
- The current writer creates lowercase `.xmp`; Capture One documentation uses
  uppercase `.XMP`. Both cases must be tested on the actual SMB/NAS path before
  choosing a Capture One-specific default.
- A RAW and JPEG with the same basename share one sidecar in Capture One. The
  importer must detect this collision and must not assume per-extension rating
  ownership.

### Packet Shape

The material-agent sidecar remains a UTF-8 Adobe XMP packet containing
`x:xmpmeta`, `rdf:RDF`, and one `rdf:Description`. Element-form and
attribute-form scalar properties are semantically equivalent XMP. The current
writer uses element form for new files and ExifTool-compatible updates for
existing files.

### Field Map

| Field | material-agent meaning | Capture One role | Ownership |
| --- | --- | --- | --- |
| `xmp:Rating` | projected AI star rating, `0..5` | visible star rating and filter | AI until an explicit human writeback is detected |
| `dc:subject` | preserved human flat keywords | visible keywords and filters | human/DAM |
| `lr:hierarchicalSubject` | preserved human hierarchy | hierarchical keyword relationship | human/DAM |
| `dc:description[x-default]` | generated review commentary | metadata description/caption candidate | AI scalar; application UI must be verified |
| `photoshop:Instructions` | compact score breakdown | IPTC instructions candidate | AI scalar; application UI must be verified |
| `xmp:Identifier` | deterministic `pj:*` score/rank/group/provenance | no required Capture One UI | material-agent/DB; sidecar preservation unverified |
| `xmp:CreatorTool` | last material-agent writer identity | lifecycle metadata | material-agent when writing |
| `xmp:MetadataDate` | last XMP metadata change | lifecycle metadata | last writer |
| `xmp:ModifyDate` | XMP resource modification time | lifecycle metadata | last writer |
| `xmpMM:DocumentID` | stable new-sidecar document ID | packet identity | preserve after creation |
| `xmpMM:InstanceID` | new-sidecar instance ID | packet identity | update policy pending real round trip |

Material-agent does not write `xmp:Label` or `photoshop:Urgency` for Capture One
color tags. Capture One can synchronize color tags, but their cross-application
mapping is less reliable than rating and is outside the first interoperability
slice.

Material-agent group IDs must not be copied into normal keywords by default.
Doing so would pollute the Capture One keyword library with a high-cardinality
machine taxonomy. Capture One similarity/cull groups are not serialized from
material-agent groups through standard XMP.

## Rating Ownership Protocol

The numeric value alone cannot identify its author. Bidirectional support
therefore requires separate state:

- `ai_star_rating`: the latest material-agent result, including five stars;
- `last_emitted_xmp_rating`: the exact value last written by material-agent;
- `human_star_rating`: an explicit value imported from a Capture One writeback;
- `effective_star_rating`: human value when present, otherwise AI value.

The existing `processed.star_rating` is the AI result and
`xmp_payload_json.rating` records the last emitted scalar. These provide part of
the required provenance but do not yet represent an explicit human override.

On import after Capture One synchronization:

1. Read the current sidecar rating and the last material-agent payload.
2. If the current rating differs from the last emitted rating, record it as a
   human override and preserve it on future AI runs.
3. If the values are equal, there is no observable override. Keep the rating
   usable, but do not silently treat it as a new human training label.
4. Continue computing and storing a new AI rating even when the effective XMP
   rating is human-owned.
5. Replace a human override only through an explicit operator action.

Comparing values prevents accidental overwrite but cannot prove that a human
reviewed an image and independently selected the same rating. Training-label
ingestion therefore needs an explicit confirmation/import action rather than
using every synchronized XMP rating automatically.

## Capture One Synchronization Phases

### Phase 1: AI to Capture One

- Generate sidecars in an isolated fixture directory.
- In Capture One, use `Auto Sync Sidecar XMP: None` plus manual `Load Metadata`,
  or use `Load` for one-way automatic import.
- Enable `Prefer Sidecar XMP over Embedded Metadata` for the fixture if the RAW
  already contains a conflicting embedded rating.
- Confirm ratings `0..5`, keywords, descriptions, and UTF-8 text.

This phase is safe for evaluating material-agent output because Capture One
does not update sidecars in `Load` mode.

### Phase 2: Capture One to Material-Agent

- Change selected ratings in Capture One, including a transition to and from
  five stars.
- Use manual `Sync Metadata` on only the fixture images.
- Snapshot the sidecar before and after synchronization.
- Import changed ratings only after the ownership classifier exists.

Do not enable library-wide `Full Sync` for this phase. It is two-way, can create
or update sidecars, and Capture One warns that it can reduce performance on a
large collection.

### Phase 3: Controlled Bidirectional Operation

Promote only after the fixture matrix proves field preservation and the
material-agent import/preservation path exists. At that point, manual sync is
still preferred for clear transaction boundaries. `Full Sync` may be evaluated
later, but it is not required for the product workflow.

## Capture One Fixture Matrix

Use copied images and sidecars only. Include at least one RAW format used in the
real library and one RAW+JPEG basename pair.

| Case | Material-agent setup | Capture One action | Required evidence |
| --- | --- | --- | --- |
| Rating range | sidecars with `0,1,2,3,4,5` | Load Metadata | exact visible rating for every file |
| Five-star writeback | AI rating `5` | change to `2`, Sync Metadata | sidecar becomes `2`; DB still retains AI `5` |
| Upgrade to five | AI rating `3` | change to `5`, Sync Metadata | human `5` is detected and preserved |
| Unknown fields | `pj:*` in `xmp:Identifier` | Sync Metadata | determine whether identifiers survive byte/semantic diff |
| Flat keywords | existing `dc:subject` | Load, edit rating, Sync | keywords remain intact |
| Hierarchy | existing `lr:hierarchicalSubject` | Load, edit rating, Sync | hierarchy remains usable and serialized |
| Text | Chinese description/instructions | Load and Sync | UTF-8 survives; visible Capture One fields identified |
| Extension case | one `.xmp`, one `.XMP` | Load Metadata | both are discovered on the mounted NAS path |
| Basename collision | `IMG_1.ARW`, `IMG_1.JPG`, one XMP | Load Metadata | shared-rating behavior matches official documentation |
| Permissions | container-created sidecar | Load then Sync | Capture One can read; write behavior and resulting uid/gid/ACL recorded |
| Atomic replacement | replace sidecar while Catalog is open | manual reload | no partial read; updated rating is recognized |

For every case capture:

- source and sidecar SHA-256 before and after;
- `stat` mode, owner, group, size, and modification time;
- ExifTool JSON for Rating, Label, Urgency, Subject,
  HierarchicalSubject, Identifier, Description, Instructions, CreatorTool,
  MetadataDate, ModifyDate, DocumentID, and InstanceID;
- Capture One version, Session or Catalog mode, sync preference, and sidecar
  preference;
- a semantic field diff rather than relying only on a byte diff.

## Implementation Sequence After The Fixture Pass

1. Add a read-only Capture One round-trip inspection command that snapshots and
   compares the field set above.
2. Add explicit AI/effective/human rating ownership to persisted state.
3. Add a dry-run human-rating import report showing detected conflicts before
   any DB or XMP mutation.
4. Preserve human-owned ratings in normal review and rewrite flows while still
   updating machine identifiers and AI scores in SQLite.
5. Add explicit operator actions for accepting synchronized ratings as human
   aesthetic labels and for clearing a human override.
6. Re-run the fixture matrix, then separately authorize primary-library XMP
   promotion.

## Sources

- Capture One, Metadata in XMP sidecar files:
  https://support.captureone.com/hc/en-us/articles/360002544898-Metadata-in-XMP-sidecar-files
- Capture One, Preferences/Settings Image tab:
  https://support.captureone.com/hc/en-us/articles/360002484457-Capture-One-Preferences-Settings-Image-tab
- Capture One, Pairing RAW and JPG files:
  https://support.captureone.com/hc/en-us/articles/30110560619165-Pairing-RAW-and-JPG-files-in-Capture-One
- Capture One, Keywords overview:
  https://support.captureone.com/hc/en-us/articles/360002544178-Keywords-overview
- Capture One, Rearranging keywords:
  https://support.captureone.com/hc/en-us/articles/360002544358-Rearranging-keywords
- Capture One, Managing metadata:
  https://support.captureone.com/hc/en-us/articles/360002544738-Managing-metadata
- Adobe, XMP Basic namespace:
  https://developer.adobe.com/xmp/docs/xmp-namespaces/xmp/
