# Viewer handler contract verification — 2026-09-28

Status: source-level handler tests and a minimal unsaved-input fix are complete.
**Actual browser layout, event delivery and download acceptance remain
unverified.** This supplements the September 27 report without rewriting its
historical results. G1 remains `reference_insufficient`; no human reference
labels or production acceptance were obtained.

## Problem and fix

Previously the viewer marked a form dirty only on `change`. Typing into
`reason`, `qualityReason` or `description` and immediately leaving before blur
could leave the draft unprotected. A handler test dispatched **only `input`**
and then `beforeunload`; all three fields failed to call `preventDefault()` and
left `returnValue` unset. No synthetic blur or change event concealed the issue.

The sole viewer change adds `input` alongside the existing `change` listener
for selects, inputs and textareas. The same dirty state now protects navigation,
export and the unload handler while text is still being entered. These checks
verify the handler's calls and state; they do not demonstrate that a particular
browser displays an unload prompt.

## Test method and scope

`tests/human_reference_viewer_harness.mjs` reads the actual
`scripts/human_reference_viewer.html`, extracts its one inline script, substitutes
the synthetic payload and executes that script using installed Node's `vm`.
It does not copy the viewer handlers into tests or merely search source strings.

The harness provides only the dependencies exercised by these handlers:

- Element IDs/tags from the real template, form values, listeners, child boxes
  and direct dispatch of the requested events. No event bubbling, automatic
  blur/change, HTML engine, layout or image decoding is simulated.
- Explicit image rectangles for coordinate calculations and a fixed advancing
  clock for deterministic annotation timestamp ordering. Real event timing and
  browser pixel geometry are outside this test.
- Node's `Blob`, a mock object-token/anchor sink and a queued timer callback.
  Tests inspect the actual Blob text created by the export handler. Clicking the
  mock anchor neither navigates nor downloads anything. Captured Blob content
  is **handler unit output**, not browser download evidence.

No browser, HTTP server, CDP, alternate page URL, network access or browser
security-policy workaround was used. Reading the local template as program
source is the only access to it. The previous `file://` browser rejection still
applies. Testing was already authorized; the browser policy remains the separate
limit on actual browser acceptance.

`tests/test_human_reference_viewer.py` runs the harness as a bounded Node
subprocess, using the existing synthetic Python fixtures and validator. Node
v25.8.2 was already installed; no dependency was added or downloaded. If Node
is absent, these 31 tests explicitly skip with
`Installed Node is required for template handler unit tests`. Such a skip means
handler verification was not performed; it is not equivalent to this run's pass.
This run had **31 executed handler tests and zero skips**.

## Verified behavior

| Case | Observed handler result |
| --- | --- |
| Empty form / empty export | Save reports incomplete judgments; export creates no Blob |
| Input without blur/change in all three text fields | Unload handler calls `preventDefault()` and sets `returnValue`; unsaved navigation and export are blocked |
| Existing select/checkbox `change` path | Still marks the draft dirty |
| Completed save/export | Exact bundle/pair identity, required record shape, preview hashes, timestamps, separate judgments and JSON Blob MIME type |
| Image rect scaled by 2, reverse drag, out-of-bounds coordinates | Stable normalized `[0.25, 0.25, 0.75, 0.75]` boxes, correct side/overlay percentages and clamping |
| Orphan pointer-up, pointer cancellation, zero-area drag | No spurious region; a subsequent valid drag succeeds |
| Missing region fields or whitespace-only description | Rejected without adding a region |
| Negative A → B with only an important A region | Rejected until an important target-B region is supplied |
| Quality preference differs from directed coverage | Quality, coverage and unknown quality remain independent in the exported record |
| Saved pair revisit after another pair | Restores judgments and regions, retains both pair records without state leaking into the second pair |
| Blob output → existing Python `merge`/`validate` | Valid schema and source/preview bytes; original manifest unchanged; synthetic source remains excluded from human quota |

The fixture source events remain `synthetic`, even though the viewer's normal
record format declares `origin: new_human`. Executing a handler with test inputs
does not create a human judgment. The round-trip validator reports zero eligible
human pairs and `reference_insufficient`.

## Commands and actual results

| Check | Result |
| --- | --- |
| Before fix: `uv run pytest -q tests/test_human_reference_viewer.py -k input_before_blur --tb=short` | 3 failed, 28 deselected; expected dirty-state regression reproduced after harness setup |
| After fix: `uv run pytest -q tests/test_human_reference_viewer.py --tb=short` | 31 passed in 1.79 seconds |
| `uv run pytest -q tests/test_human_reference_viewer.py tests/test_human_reference.py tests/test_repository_boundary.py` | 81 passed in 1.93 seconds: 31 new + 48 existing + 2 boundary |
| `make check` | `All checks passed!` |
| `node --check tests/human_reference_viewer_harness.mjs` | Exit 0 |
| `git diff --check` | Exit 0 |
| Explicit owned-file whitespace/private-boundary scan | Five files passed; includes untracked tests/report not covered by tracked-file enumeration |

Controller review independently reran the same 81 tests with `uv run --no-sync`
(81 passed in 1.87 seconds), `make check` and the Node harness syntax check.

## Changed files and recovery

- `scripts/human_reference_viewer.html`: input dirty listener only.
- `tests/human_reference_viewer_harness.mjs`: minimal source-handler runtime mocks.
- `tests/test_human_reference_viewer.py`: executed handler/validator contracts.
- This dated report and an appended README validation note.

The existing demo HTML predates the template fix and is intentionally preserved.
The coordinating task generated a fresh artifact from the updated template at
`.local/reference-tooling-demo/viewer-2026-09-28.html`, without browser navigation;
that artifact alone is not evidence of browser acceptance. No source
photos, Python production/tools code, schema, graph files, plans, status ledger,
locks or historical reports were changed by this follow-up. No commit, push or
deployment occurred.

Recovery is recorded atomically at
`.local/task-handoffs/culling-2026-09-27/human-reference.md`, including the red
regression, minimal fix and passing checks. The remaining browser acceptance
and fresh human-label dependencies are unchanged; no G1/G2 or product gate is
closed by these tests.
