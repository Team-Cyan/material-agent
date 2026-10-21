# Bounded Adobe Bridge roundtrip review — October 20, 2026

Last updated October 21, 2026; the dated filename and title retain the original review date.

Adobe Bridge 2026 **16.0.3** (installed build **16.0.3.21**) was exercised through its actual File Info UI on
October 19 using fresh disposable public fixtures. The observations below accept
specific read/edit/save/reopen paths. They do not establish a complete format or
cross-application compatibility matrix. The bounded clean case 07 GUI → writer
→ GUI roundtrip was accepted on October 21 after no-save hash reconciliation
and main review. The finite stage is complete within these stated limits.

## Accepted observations and negative result

| Case | Format | Observed result | Acceptance boundary |
| --- | --- | --- | --- |
| 01 | ARW | Rating 3 → 4; `material-agent:keep` → `material-agent:reject`; saved values visible after reopening. | Bounded Bridge sidecar read/edit/save/reopen. |
| 02 | NEF | Rating 4 → 3; reject → keep; `family` retained after save/reopen. | Bounded selection-keyword edit and user-keyword preservation. |
| 05 | ARW | Rating 4 → 5; reject → keep; `family` and `material-agent:keep-personal` retained after save/reopen. | Exact selection keywords change without treating the similarly prefixed personal keyword as machine-owned. |
| 06 | NEF | Rating 3 → 4; reject → keep; Unicode keywords, foreign field and language alternatives retained. | Historical executor save/reopen observation reconciled by the controller with current file checks; no archived local screenshot or fresh October 20 UI check. |
| 03 | DNG | Read-only File Info shows rating 5, keywords `旅行` and `material-agent:keep`, and the expected description. No thumbnail appears in the grid. | Metadata readback only; no edit/save or preview compatibility acceptance. |
| 04 | JPEG | Read-only File Info shows rating 0 and empty keywords/description, while the adjacent sidecar contains rating -1. A JPEG thumbnail appears. No metadata was saved. | Negative interoperability result: this adjacent sidecar did not supply the displayed metadata in this path. No embedded JPEG write was attempted. |
| 07 clean | NEF | GUI edit changed rating 3 → 4 and keep → reject. The correct production-writer repeat and physical review passed on October 20. After the October 21 normal app reopen, File Info showed rating 4, `家族`, `café`, `東京`, `Ω`, `material-agent:keep`, and description `Repeat 家族 café 東京 Ω`; the no-save hash check passed. | Bounded GUI → writer → GUI roundtrip accepted for this exact clean fixture. |

The clean 07 writer repeat requested rating 2 and `pj:decision=keep`. Its committed
projection receipt preserves the existing nonzero rating 4, projects keep,
retains Unicode user keywords and unrelated metadata, and records the correct
`pj:*` identifiers. Its media hash remained unchanged. On October 20, the
controller independently
compared the frozen pre-writer bytes with the new XMP and ExifTool readback:
all 68 non-owned fields matched, rating 4 was preserved, and the four Unicode
keywords plus keep and the two intended `pj:*` identifiers were present. This
is a bounded field comparison, not a general vendor-ID preservation claim.
The October 20 UI attempt recorded the exact inventory error:
`The Mac is locked and automatic unlock could not unlock it. Ask the user to unlock the Mac manually before continuing.`
The user confirmed the Mac unlocked. On October 21, Bridge was still running;
both full app-path and bundle-ID bindings returned
`Computer Use server error -10005: timeoutReached`. Finder's native
accessibility tree worked, and opening the installed Bridge app through Finder
did not restore its binding. No File Info view or metadata was observed. The
target media hash `6c46f9854033e7623ebbb5de8c951df6762ca44f05d45035ccc5cb7e9f4e5692`,
target sidecar hash `3c2e785b08a06df363f6da0fdd9de3ba6059a570200d3c6dc0e00e34f9d0036c`
and source-fixture hash matched before and after that attempt. No writer or
recovery action ran. The October 21 binding timeout was resolved after a human
normal quit/reopen of Bridge; no force quit was used because an unsaved dialog
could not be inspected. These failed access attempts remain historical.

### October 21 post-reopen readback — accepted bounded closeout

The GUI worker opened File Info for the exact clean fixture
`07-writer-repeat-clean.nef`. The private screenshot
`07-writer-repeat-clean-final-ui-readback-20261021-after-reopen.jpg` shows rating 4, keywords
`家族`, `café`, `東京`, `Ω`, and `material-agent:keep`, plus description
`Repeat 家族 café 東京 Ω`. The main reviewer independently inspected that
screenshot. The worker closed File Info with Escape without saving. The
main reviewer recomputed all four pre/post file hashes and 27 fixture/copy
inventory checks; they passed. Target media stayed at
`6c46f9854033e7623ebbb5de8c951df6762ca44f05d45035ccc5cb7e9f4e5692`, target
sidecar at `3c2e785b08a06df363f6da0fdd9de3ba6059a570200d3c6dc0e00e34f9d0036c`,
source fixture media at the same media hash, and source fixture sidecar at
`39ebf5454dc1ea9fd61097395127ad054c31ccbbfa8b3e3814d60d24f601da0f`.
Post-UI ExifTool confirmed rating 4, exact subject/identifier values, and
preserved localized descriptions and unrelated fields. The independent advisory
review also passed with no actionable findings. Writer and recovery were not
replayed.

The first 07 attempt used the wrong writer API arguments. Its later correction
reused that polluted copy. Both attempts and their receipts remain preserved and
are excluded from clean acceptance. They cannot be combined with the clean-copy
result to claim an uninterrupted successful roundtrip.

## Review and verification

The controller reviewed the actual writer API call, frozen pre-writer bytes,
committed projection receipt, post-write XML and independent ExifTool readback.
Writer/state verification passed **77 tests**. **27 hash checks** passed; these
verify their recorded file scope, not an unperformed GUI observation. The clean
07 physical comparison preserved all **68 non-owned ExifTool fields**, the media
hash and source fixtures, while applying the intended owned projections.

The review separates the October 19 GUI observations, October 20 physical
writer pass and October 21 post-reopen UI observation. No thumbnail was observed
for DNG in the tested Bridge grid; the DNG result is metadata readback only. The
JPEG result is limited to the tested adjacent-sidecar path. The October 21 main
closeout recomputed the no-save hashes and fixture/copy inventory; post-UI
ExifTool semantics passed. Earlier main and advisory reviews retain their
bounded conclusions; the 06 historical receipt
was separately reconciled with current files. The final advisory review found
no actionable issues. This closes only the finite technical stage.

## Evidence and limits

UI observations, physical XMP checks and media-hash receipts are separate
sources of evidence. The controller reconciled the 06 historical receipt and
clean 07 physical writer sequence. Clean 07's UI values, no-save close, hashes
and metadata semantics are accepted. Original fixtures and failed artifacts
are preserved; private evidence paths and media remain outside the public repo.

| Evidence | SHA256 |
| --- | --- |
| Frozen pre-UI fixture receipt | `30f62678d787212db099b3452bb49d25f7b96b3fbee9a701e8363818531bcd1f` |
| Main UI observations for 01/02/05 | `9f5c2ec194066acfad6f2bc0d554480741cf2fc0050d481da90e8a674e28bc68` |
| Mixed historical receipt containing 03/04 read-only observations and excluded first 07 | `7075ea045165ca82267f622d48eb684530a0b12fc24d17c1b72dea405ecc6b72` |
| Clean 07 immutable physical-result snapshot, before appended self-review | `1197bf7f60d6774efc1a16fc927433c84c8cbedbf627469a99513365f966f2d2` |
| Initial main stage review: physical/existing GUI accepted; final 07 UI blocked and 06 receipt then pending | `c52ad085443ea9ae922ae168cb3135a50e20a2d1e1a25d3c89a3a1b1f7be41fd` |
| Independent advisory stage review, bounded evidence only | `2bf7cc35178c7253df3a2059e003466fd03dc7cb4215a70dd4569806fcb07302` |
| 06 historical GUI observation and current file self-review | `43b04943121449128597c2933d1d110e15ea6de2f68128d272652e42aead892e` |
| Clean 07 result including self-review and exact final-UI lock error | `cb898aaff802b84f694299af66b5d0ed77e0755c5a3dbb21c8bb3d1306b14813` |
| Final main reconciliation: 06 reviewed, only clean 07 UI remains | `92460f67941779c98e71f10a6f767e7bcd5357be16c2cba8ea899572550baa7b` |
| October 21 clean 07 readback attempt; Bridge bindings timed out, hashes unchanged | `f203b5267e3e066290b484fcee4489babab056f3432e09c976eb90bb9b229094` |
| October 21 main access review; Finder worked, Bridge binding still timed out after activation | `dd2fd2b169a886ee9dc94238f381dd6976aaa5145caae0075e28dc9c5b42e7dd` |
| October 21 accepted clean 07 readback and no-save hash receipt | `6c5dcd5d6b1c84f88e0fc97e9a816fb94466b97eed3049b3f1a33c7bff2604d2` |
| October 21 private after-reopen File Info screenshot | `d4a6f54481549a6f33cc14f5f46055420eb8513054919e765b655026e8558233` |
| October 21 main technical closeout review | `c3c64ef56406666b5d18ea27940e7d7bebdf3d8c89077e862398f044d1e2daf8` |

The existing application CI for `2065599` ([run `39608751154`](https://github.com/Team-Cyan/material-agent/actions/runs/39608751154)) completed with
quality and publication success, 1,592 passed and 45 skipped. This is release
context only, not evidence for the Bridge UI or metadata roundtrip; no new CI
result is claimed here.

This stage does not verify Capture One, a full RAW/JPEG/DNG matrix, existing
vendor-ID preservation, same-job resume, atomic DB/XMP crash consistency or a
photographic-quality gain. It does not authorize production-library writes.
The independently accepted [recovery-write result](2026-10-15-native-runtime-acceptance.md#isolated-recovery-write--accepted-october-19)
proves its own bounded SQLite restore/new-job reprocessing contract. It neither
substitutes for GUI evidence nor changes G1/G2 coverage gates.

## Finite closeout and follow-up

The bounded technical stage is complete after GUI worker self-review, main
visual/hash/metadata review and independent advisory review. Preserve the JPEG
negative result and DNG boundary. Optional JPEG interoperability remains backlog:
an explicit opt-in design and separate review would be required before any
implementation or embedded write; this closeout authorizes neither.

See the [writer contract](../ai/modules/xmp-writer.md), [current status](2026-09-16-plan-status.md)
and [external acceptance protocol](2026-09-17-external-acceptance-plan.md).
