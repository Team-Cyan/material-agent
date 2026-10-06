# MUSIQ shared-token-core diagnostic

This experiment tests whether three exact native preprocessing graphs can share
one bounded token core without changing the existing checkpoint, native tokens
or raw scores. It is an isolated resource and numerical diagnostic. It does not
admit a production adapter, additional shapes or a selection policy.

## Frozen comparison

The unchanged [native-shape baseline](../2026-10-04-musiq-native-shapes/README.md)
supplies nine public inputs, three original CPU references and three whole-image
graphs. Control, landscape and derived portrait have exact supported shapes;
the other six inputs produce no graph, score or fallback. The derived portrait
does not establish actual portrait RAW/EXIF acceptance.

Variant A compiles the three existing whole-image graphs. Variant B compiles
three static preprocessing graphs and one shared core with token length bounded
to 385–897; dispatch admits only lengths 385 and 897. Both use CPU, float32,
four threads and one stream, with actual execution-property readback. There is
no prediction cache or compiled disk cache.

Three pairs run in fresh processes in this order: A1, B1, B2, A2, A3, B3. Each
process performs two warm and ten measured cycles of control, landscape,
portrait, control: 48 logical scores and 40 measured timings. B timings include
preprocessing, a real contiguous token copy and shared-core inference. Inputs
are prepared before timing. Timing is observational; RSS is process high-water
memory, not total container usage or a leak proof.

The fixed gates are:

| Gate | Bound |
| --- | --- |
| Eager native preprocessing tokens | Exact full tensor equality |
| Eager split-core raw error | At most 0.00001 |
| Target token HSE, scale and mask | Exact equality |
| Target token pixels | Maximum absolute error 0.000001, relative tolerance zero |
| All target raw scores | Maximum absolute error 0.001 |
| Repeat raw score range | At most 0.000001 |
| Four B graphs, eight XML/BIN files combined | At most 150,000,000 bytes |
| B package | At most 160,000,000 bytes |
| Export | 300 seconds and 2,500,000,000 sampled process-group RSS bytes |
| Each target process | 900 seconds and 2,500,000,000 child RSS bytes |
| Median B/A peak RSS | At most 0.85 |
| Median B/A warm median latency | At most 1.10 |

All six complete rounds, numerical gates and storage gates are required before
resource admission. A partial or failed round cannot establish an improvement.

## Original conversion result

The original conversion exported four FP32 graphs totaling 109,369,614 bytes
and a 140,390,400-byte package. Eager tokens matched exactly for all three
shapes, and split eager raw scores matched their original references.

The first target whole-graph round passed 48 raw scores and 40 measured timings,
with maximum raw error 0.0000915527 and zero repeat range. The first shared round
failed `preprocess token pixel parity failed` on the control token check. Token
metadata passed; shared-core scoring and performance measurement had not begun.
The original failure did not record the maximum pixel difference, so the cause
and its magnitude are not established. The remaining performance rounds were
stopped. This attempt is **not admitted**.

## Isolated correction design

The correction uses a new source/schema/package identity and a separate target
namespace. Original artifacts remain intact. All six paired processes must run
again under the corrected source; the original A1 cannot be reused.

Only the two strictly matched cubic resize nodes per preprocessing graph may
change. Native Torch eager preprocessing and the shared core's eval submodules,
weights, shapes and token semantics remain unchanged. Export retraces the same
core; this is not a promise to reuse an earlier IR file byte for byte.
The proposed lowering derives fixed per-axis float32 weights by applying the
original CPU rank-4 bicubic interpolation to unit bases, with a singleton
orthogonal axis, `align_corners=False` and `antialias=False`. Sparse horizontal
then vertical Gather, Multiply and sequential Add operations use at most four
exact nonzero coefficients per output position. Coefficients do not depend on
photos, labels or model scores. No coefficient pruning, normalization, clipping
or tolerance changes are permitted. Shape, node attributes, output consumers
and names are checked; nearest HSE and padding/masks remain unchanged.

Merged edge coefficients and float32 fusion/accumulation can still change
rounding. Mathematical separability is not proof of numerical equivalence.
Before photo checks, all six fixed structural probes—constant, impulse, ramp,
alternating sign, edge and corner—must match complete original native token
references for each of the three buckets. These 18 diagnostic preprocessing
calls are separate from B's three photo token checks and 48 scoring calls.
The lossless ZIP-LZMA reference archive has exactly 18 float32 arrays, fixed names and
native shapes, at most 4,000,000 compressed bytes, 200,000,000 expanded bytes and
16 MiB per entry. Headers and bounds are checked before loading without pickle.
An initial default-DEFLATE archive exceeded the 4 MB bound before numerical
validation. Lossless repacking preserved all 18 decoded arrays byte for byte
and produced 2,658,871 bytes; probe values and all gates remain unchanged.

## Corrected target result

All six fresh target rounds passed the original numerical gates: 288 logical
raw scores, 240 measured timings, 54 structural token checks and nine photo
token checks. Maximum structural pixel error was 0.0000001788; maximum photo
pixel error was 0.0000002384. Metadata matched exactly. Maximum raw score error
was 0.0000915527 and every repeat range was zero. Six unsupported inputs remained
without a graph, score or fallback in each round.

| Three-round median | Whole graphs A | Shared core B |
| --- | ---: | ---: |
| Process peak RSS, bytes | 1,490,509,824 | 1,020,039,168 |
| Warm median latency, ms | 203.284 | 281.089 |
| Total graph storage, bytes | 327,472,811 | 109,636,947 |

B reduces median peak RSS by **31.56%**, but increases the warm latency statistic
by **38.27%**. Its RSS ratio 0.6844 passes the 0.85 bound; its latency ratio
1.3827 fails the 1.10 bound. The 143,339,520-byte package and graph storage pass.
The overall result is **optimization not accepted**. Do not promote this shared
runtime into an adapter or redefine the metric after seeing these measurements.
The original core XML/BIN bytes also match the corrected export exactly.

See [machine-readable results](results.json) for frozen identities, per-round
values and gate outcomes. The independent verifier and separate controller
recomputation agree. Full tests pass 1,338 / ten skipped; 131 controller wrapper
checks and lint pass. Independent wrapper review completed. The source reviewer
reported no actionable defect before reaching quota; the controller reviewed
the final checkpoint/provenance and lossless-codec deltas. A completed final
independent source review is not claimed.

The target image was the previously verified release, as pinned in results.
Production library/config snapshots remained equal, with idle state, 40,620
indexed/scored records and zero errors. No production policy or metadata writes
occurred. Publication and native deployment of the reviewed code are separate
release steps, not additional benchmark evidence.

Next design a bounded lifecycle for the retained static whole-graph baseline
and explicit unsupported-input results before any optional adapter. Freeze a
new resource contract before another inference run; retain these negative
measurements and do not repeat the completed quality cohort or download another
model. Actual RAW orientation and photographic utility remain separate gates.

## Recovery and ownership

`scripts/benchmark_musiq_shared_core.py` owns the scientific runner; the homelab
controller owns fixed transport, approved plans, native target preflight and
the external watchdog. Source/model/input/protocol hashes are frozen before
execution. Source trees are read-only, inference is unprivileged and reports use
separate writable directories. Production photos are read-only.

Ignored experiment directories retain source snapshots, protocol/package
identities, native references, export receipts, per-round logs, partial call
counters and atomic checkpoints. A nonempty round output is exported and
reviewed rather than overwritten. Completed evidence survives session or quota
interruption. No production photo/XMP or default-policy changes are authorized
by this experiment.

Verification uses `tests/test_musiq_shared_core.py`, the native/helper checks,
repository boundary checks and a separate numerical report verifier. Current
execution status is recorded in the [task ledger](../../2026-09-16-plan-status.md).
