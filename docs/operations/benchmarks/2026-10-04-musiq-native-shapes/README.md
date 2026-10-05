# MUSIQ exact native-shape diagnostic

The actual-input audit found that only the existing 512×384 control fits the
[accepted full-cohort graph](../2026-10-04-musiq-intel-full/README.md). This bounded
step verifies two additional exact shapes with the same checkpoint and native
preprocessing. It adds an experimental runner, without changing production
scoring, selection, dependencies or photo metadata.

## Frozen inputs and semantics

Nine existing public inputs are frozen: six RAW fixtures decoded by the production
`decode_raw` function, an unchanged standard-corpus control, a derived portrait
and a derived oversized input. RAW decoding uses the current preview contract:
prefer embedded previews, maximum edge 1024, focus edge 2048, JPEG quality 85,
and the existing half-size RAW fallback. Every decoded byte identity matches
the preceding read-only inventory.

Supported RGB float32 NCHW shapes are `[1,3,384,512]`, `[1,3,682,1024]` and
`[1,3,1024,682]`. The landscape is an actual public CR3 decoded preview; portrait
is its lossless counterclockwise rotation with an independently computed PyIQA
reference. It does not establish real portrait RAW or EXIF-orientation acceptance.
The other five RAW previews and a lossless 2×2 pixel-tiled oversized input must
return `unsupported_shape`, without selecting a graph or producing a score.

Only the native internal resize dimensions are specialized. Bicubic interpolation,
normalization, original/224/384 scales, SAME padding, hash positions, scale IDs,
masks and original-resolution patch count remain unchanged. Whole token tensors
are exactly equal; both new graphs have 897 tokens, 835 valid and 62 sequence
padding tokens. The control retains 385 tokens. Original Torch references are
saved before tracing; eager score error must be at most 0.00001. Both new exports
have zero eager error and uncompressed FP32 storage. Each graph remains below
150 MB. This is exact bucket support, with no external resizing or dynamic-shape
claim.

## Target execution and recovery

The frozen [protocol summary](protocol-summary.json) records shapes, source/graph
identities and resource gates. The existing Intel native DockerMan image executes
two inferences per supported input using CPU, four threads, one stream and actual
F32 property readback. Raw error must be at most 0.001 and repeat error at most
0.000001. No MOS-quality bootstrap is appropriate for three supported inputs.

An approved fixed homelab wrapper stages 22 allowlisted USTAR files, bounded to
512 MiB, into a separate finalized read-only corpus. Reports/cache/tmp are owned
by UID/GID 99:100; `HOME` is preserved. The external watchdog includes imports,
compilation and native calls: 900 wall seconds, 2.5 GB sampled child RSS,
2500/2510 soft/hard CPU seconds, 12 GiB address space, 128 MiB output files and
1024 open files. Export watchdogs use 300 seconds and 2.5 GB sampled process-group
RSS each. These observations are not complete container memory measurements.

Atomic predictions bind input, protocol, graph, source and runtime identities.
Exact resume recompiles all three graphs for CPU/F32 readback and makes no native
inference calls. Corrupt JSON/UTF8 caches recompute; unknown inputs cannot acquire
a fallback score. Partial predictions remain exportable after interruption;
sources are checked on successful and failed wrapper exits. Inputs, weights,
original references, per-image predictions and private operation receipts remain
ignored on disk.

## Observed result and next boundary

[Aggregate results](results.json) record the native first run and exact resume.
All three supported inputs pass raw parity; all six unsupported inputs produce
no score or graph selection. Maximum raw error is 0.00009155 and repeat error is
zero. First-run entry time is 4.93 seconds and process peak RSS is 1,490,309,120
bytes. These are observations, without a controlled speedup claim.

Independent verification checks references, graph/source/input joins, numerical
errors, unsupported records and exact resume. Local checks pass 1308 tests / ten
skipped, 92 focused runner/helper checks, 232 homelab wrapper checks and lint.
Completed independent source/protocol/package review has no remaining must-fix.
Production library/config snapshots remain equal, with 40,620 indexed/scored
and zero errors; photo inputs remain read-only. Exact resume reuses nine records
with zero native calls and CPU/F32 recompilation; observed time is 3.42 seconds.
Final independent aggregate review passed; its stale plan-summary finding was
fixed. No remaining must-fix finding is known.

This accepts a three-shape diagnostic only. Five actual RAW preview shapes remain
unsupported, and the derived portrait supplies no real orientation evidence.
The next design must address bounded graph lifetime, model storage and explicit
unknown handling before any optional adapter is wired. Product utility and
independent directed-coverage references remain separate acceptance gates;
default-policy promotion, GPU and XMP writes are excluded.
