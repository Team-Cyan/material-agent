# Bounded Adobe Bridge roundtrip review — October 20, 2026

Last updated October 21, 2026; the dated filename and title retain the original review date.

Adobe Bridge 2026 **16.0.3** (installed build **16.0.3.21**) was exercised through its actual File Info UI on
October 19 using fresh disposable public fixtures. The observations below accept
specific read/edit/save/reopen paths. They do not establish a complete format or
cross-application compatibility matrix. Clean case 07 still requires its final
post-writer UI readback before this finite stage can close. Its physical writer
review passed; the October 21 readback remains blocked by a Bridge-specific
native app-binding timeout after the user unlocked the Mac.

## Accepted observations and negative result

| Case | Format | Observed result | Acceptance boundary |
| --- | --- | --- | --- |
| 01 | ARW | Rating 3 → 4; `material-agent:keep` → `material-agent:reject`; saved values visible after reopening. | Bounded Bridge sidecar read/edit/save/reopen. |
| 02 | NEF | Rating 4 → 3; reject → keep; `family` retained after save/reopen. | Bounded selection-keyword edit and user-keyword preservation. |
| 05 | ARW | Rating 4 → 5; reject → keep; `family` and `material-agent:keep-personal` retained after save/reopen. | Exact selection keywords change without treating the similarly prefixed personal keyword as machine-owned. |
| 06 | NEF | Rating 3 → 4; reject → keep; Unicode keywords, foreign field and language alternatives retained. | Historical executor save/reopen observation reconciled by the controller with current file checks; no archived local screenshot or fresh October 20 UI check. |
| 03 | DNG | Read-only File Info shows rating 5, keywords `旅行` and `material-agent:keep`, and the expected description. No thumbnail appears in the grid. | Metadata readback only; no edit/save or preview compatibility acceptance. |
| 04 | JPEG | Read-only File Info shows rating 0 and empty keywords/description, while the adjacent sidecar contains rating -1. A JPEG thumbnail appears. No metadata was saved. | Negative interoperability result: this adjacent sidecar did not supply the displayed metadata in this path. No embedded JPEG write was attempted. |
| 07 clean | NEF | GUI edit changed rating 3 → 4 and keep → reject. The correct production-writer repeat and physical review passed on October 20. The October 21 final readback could not bind to Bridge (`-10005: timeoutReached`). | Do not accept the complete GUI → writer → GUI roundtrip until the last UI result is reviewed. |

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
and source-fixture hash matched before and after. No writer or recovery action
ran. The next action awaits human acknowledgment
of a normal Bridge quit and reopen; no force quit was attempted because an
unsaved dialog could not be inspected. October 19 GUI edits, October 20 writer
review and October 21 access follow-up retain separate dates. A physical writer
receipt alone does not prove what Bridge displays after that write.

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

The review separates the October 19 positive GUI observations from the October
20 physical writer pass and October 21 binding-blocked final UI check. DNG
metadata readback without a thumbnail and JPEG failure to expose adjacent-sidecar metadata remain
explicit limitations. Neither test counts nor XML/ExifTool checks replace the
missing clean 07 post-writer UI result. The October 20 main stage review accepted
physical evidence and the existing GUI observations while retaining the 07 UI
gate. The October 21 access review confirms the Mac is unlocked and records the
Bridge-specific binding timeout. The 06 historical receipt was subsequently reconciled
with current files in a separate final review addendum. It
does not accept the entire stage as passed.

## Evidence and limits

UI observations, physical XMP checks and media-hash receipts are separate
sources of evidence. The controller reconciled the 06 historical receipt and clean 07 physical
writer sequence. Only clean 07 post-writer UI remains unverified. Original fixtures and failed artifacts
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

The existing application CI for `5f7b967e8d8190561f90a6ceefa42bf4a8ed4430`
completed successfully on October 20 (run `39433460536`; 1,592 passed, 45
skipped; quality and publication succeeded). It does not verify Bridge UI
access or close this acceptance gate.

This stage does not verify Capture One, a full RAW/JPEG/DNG matrix, existing
vendor-ID preservation, same-job resume, atomic DB/XMP crash consistency or a
photographic-quality gain. It does not authorize production-library writes.
The independently accepted [recovery-write result](2026-10-15-native-runtime-acceptance.md#isolated-recovery-write--accepted-october-19)
proves its own bounded SQLite restore/new-job reprocessing contract. It neither
substitutes for GUI evidence nor changes G1/G2 coverage gates.

## Finite closeout and follow-up

1. After human acknowledgment that Bridge was normally quit and reopened, finish
   the read-only clean 07 post-writer File Info readback, confirming rating 4
   and the four Unicode keywords plus keep. Close without saving; compare media
   and sidecar hashes afterward. Do not invoke the writer or recovery path again.
   Physical checks own unrelated-field preservation. Main review decides
   acceptance from the complete chain.
2. Close this finite stage with the accepted paths and the JPEG negative result
   explicitly retained. Closing a bounded stage does not certify universal
   cross-application compatibility or require expanding to Capture One.
3. Keep JPEG interoperability as a finite optional follow-up: review an explicit
   opt-in embedded-metadata path, exact disposable fixtures, backup/rollback and
   reader checks before any implementation or write. This stage authorizes no
   JPEG implementation or embedded write.

See the [writer contract](../ai/modules/xmp-writer.md), [current status](2026-09-16-plan-status.md)
and [external acceptance protocol](2026-09-17-external-acceptance-plan.md).
