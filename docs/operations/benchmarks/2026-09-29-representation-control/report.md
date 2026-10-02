# Controlled representation protocol — synthetic preparation result

Status on 2026-09-29: **runner preparation and four-case synthetic wiring check
complete; labeled quality evaluation is NO-GO until G1/G2 evidence exists.** This
batch did not evaluate a real photo, inspect reserved holdout judgments, tune a
threshold, choose a candidate for promotion, change production behavior or write
photo/XMP metadata. Its purpose is to remove the known geometry/representation
confound before a later, separately gated experiment.

Artifacts: [input/provenance inventory](inventory.md), [frozen protocol](protocol.json),
[compact synthetic results](synthetic-results.json). Full atomic case records and
summary are ignored under `.local/representation-control-20260929-synthetic/`.
The public JSON contains hashes and measurements, not private absolute paths or
image bytes. Historical scripts, reports, datasets and thresholds remain intact.

## Protocol and exact commands

The protocol fixes four directed A→B constructed pairs: `identity`, `jpeg`,
`small_luminance`, `isoluminant_color` (seed 2049, original side 1280). It fixes
synthetic JPEG preview construction, 512/1024 SIFT geometry caps, a **separate
512 residual cap in every cell**, historical gray and RGB-local thresholds,
identical A/B quality inputs, and the unchanged `direct_coverage.select` as a
two-frame diagnostic. Its noise, exposure and subpixel recipe fields are retained
for historical identity checks but those three perturbation kinds were **not
executed** here. Construction labels are symbolic, not human truth.

From the repository root, use a fresh ignored output directory:

```sh
uv run python scripts/benchmark_representation_control.py \
  --protocol docs/operations/benchmarks/2026-09-29-representation-control/protocol.json \
  --output-dir .local/representation-control-20260929-synthetic
```

For an interrupted run, the same directory may resume only with verified case
records. To check completed records without writing or recomputing geometry:

```sh
uv run python scripts/benchmark_representation_control.py \
  --protocol docs/operations/benchmarks/2026-09-29-representation-control/protocol.json \
  --output-dir .local/representation-control-20260929-synthetic \
  --resume --verify-only
```

The first command intentionally refuses a populated directory; use `--resume`
for that state. Each complete case is written via a same-directory temporary
file, `fsync` and atomic replace. A partly computed case has no accepted JSON
and is recomputed; resume operates at **case**, not intra-case, granularity.
Every case record binds the protocol, runner, both read-only historical scripts,
historical plan, Python/OpenCV/NumPy/Pillow/ImageHash versions, generated input
array hashes and exact frozen case ID/kind. It has a complete integrity hash and
a separate semantic hash excluding elapsed/RSS observations. Resume verifies
both hashes and all identities; stale or corrupted cases stop rather than
silently reusing their result. `--verify-only` requires all cases and the matching
summary, returns computed 0/reused 4 and does not write the report.

Observed bounds are 90 seconds per case and 2,000,000,000 bytes process peak
RSS, matching the plan's initial units. An observed overrun is atomically saved
as that case, then processing stops; resume also stops on it. The measurements
are post-call observations, **not an OS-enforced deadline or memory limit**. RSS
is a process peak to date, not per-cell allocation.

## How the four cells are isolated

The runner loads `direct_coverage.py` and `benchmark_coverage_observability.py`
by their exact checked paths. It rejects an already loaded module with the same
name from another location. For each pair and each geometry resolution, it runs
historical `prepare` on source and target once, then historical `relation` once,
intercepting its SIFT homography. Both gray and RGB-local arms use that **same
captured H, feature identity and common gate**. The artifact digest is recorded
once per geometry cell and repeated in both arm records. The frozen candidate,
quality and selector inputs are the same for both arms.

The residual images are independently thumbnail-resized to an actual maximum
side of 512; the output records each source and target width/height. H maps
source geometry pixel centers to target geometry pixel centers. Conversion to
residual coordinates uses, on **each** source/target x/y grid separately,
`x_res = scale * (x_geom + 0.5) - 0.5`; therefore
`H_res = T_target * H_geometry * inverse(T_source)`. An actual Pillow-thumbnail
non-square/unequal-dimension synthetic unit case with a nonidentity perspective H
checks that pure nominal scaling gives a different answer. All four published
matrix inputs happen to be square/equal-sized, so the unequal-shape check is a
separate synthetic protocol test, not four more evaluation cases.

The common gate admits both historical `geometry_and_photometric_consistency`
and `unexplained_local_change` to residual comparison. Other historical gate
outcomes are shared unchanged between arms, including `different` when target
overlap is below 0.4; residual-grid overlap/observability checks are also shared.
This is an explicit protocol choice. The old observability RGB helper flattened
other historical gate reasons to `unknown`, so this runner does **not** claim
full historical RGB policy parity outside admitted cases. Inside an admitted
512 cell, the gray relation/reason and deterministic residual mean/p95/max-tile
evidence match the old direct-coverage result. The test compares the RGB helper
on a 512 identity control; the entire new RGB policy is not certified identical.
For 1024 geometry, `parity_512_gray` is **null**, because its 512 residual is
deliberately different from the old 1024 end-to-end residual path.

Capturing H currently calls the **full** old `relation`, including its gray
residual, before either new arm runs. This deliberately retains an extra
screening cost to avoid altering the frozen historical function. The per-cell
and per-case elapsed times include that old residual, preparation and both arms;
they are not pure geometry or isolated representation timings. No speedup or
performance admission can be inferred from them.

## Actual synthetic result

The saved summary has **4 cases × 2 geometry resolutions × 2 representation
arms = 16 arm cells**. All four 512-gray cells match the historical relation,
reason and available residual metrics. All eight gray/RGB pairs share their
geometry artifact SHA-256 at their own resolution. All 1024 historical-512
parity fields are null. No observed case exceeded the 90-second / 2,000,000,000-
byte bounds. `--resume --verify-only` checked the saved records with computed 0,
reused 4.

| Constructed case | 512 gray / RGB-local | 1024 gray / RGB-local, residual still 512 | Interpretation limit |
| --- | --- | --- | --- |
| identity | cover / cover | cover / cover | Trivial same-content control. |
| jpeg | cover / cover | cover / cover | Only frozen JPEG-quality contrast. |
| small luminance | cover / cover | cover / cover | The symbolic important 4-pixel change is missed at the fixed residual resolution. This is a known synthetic false cover, not a gate pass. |
| isoluminant color | cover / unknown | cover / unknown | RGB-local detects a chromatic residual missed by gray in this constructed control; it abstains rather than assigning human meaning. |

A separate exact-array isoluminant control in the tests also makes gray pixels
identical while RGB-local returns unknown, exercising actual residual operations
without changing the published four cases. The two-frame selector rejects B
when A→B says cover and keeps B on unknown; this only proves the unchanged
selector wiring. It is not a human-acceptable keeper-set result.

The four case wall times were 0.519–0.633 seconds; process peak RSS to date was
450.6–453.1 MB. Those observations have no same-input performance baseline or
statistical interpretation. No genuine human-label denominator was present.

## Checks, decision and remaining evidence

`uv run pytest -q tests/test_representation_control.py` passed **15** tests after
the semantic-digest repair. They include numeric H mapping from actual unequal
thumbnail dimensions, 512 gray evidence parity, one admitted 512 RGB helper
comparison, constructed chroma separation, one geometry preparation/relation per
pair, full four-case matrix, resume of one missing case, stale result/config
rejection, observed-overrun stop and private-output boundary. The controller
independently ran new plus relevant historical and repository-boundary tests:
**46 passed in 5.57 seconds**, with `make check` passing. After that run, the
mapping test was refined to use actual unequal Pillow-thumbnail dimensions;
the controller reran that test on September 30 (1 passed, 16 deselected) and
confirmed that the runner/protocol hashes still match the saved matrix.

The implementation session hit its account usage limit during report/checkpoint
finalization. Code, atomic case results and report drafts were already saved.
The controller completed the final lint, repository-boundary, public-artifact
hygiene checks and recovery snapshot on September 30. This interruption did not
invalidate or consume new evaluation inputs.

The [inventory](inventory.md) found relevant existing local bytes by path and
size but **zero qualifying fresh human still-photo directed labels**. Minimum G1
shortfalls are 24 pairs/12 independent families overall; each split still needs
six cover and six negative directions across at least three families per class,
plus visible illumination and hand/expression evidence. G2's human-labeled
candidate/selector oracle is likewise pending. Thus the go/no-go result for
**labeled** development/holdout evaluation is **NO-GO**. Previously inspected
RAW bursts, video action labels, model panels and synthetic controls cannot
supply the missing denominator. No candidate was chosen, no threshold changed,
and no reserved real holdout was consumed.
