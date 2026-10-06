# Static MUSIQ lifecycle review and quality validity fix

This step completes the next design review after the
[rejected shared-core optimization](benchmarks/2026-10-06-musiq-shared-core/README.md).
It retains the same checkpoint, three original whole-image graphs and explicit
unsupported-input behavior. No new compile, inference, model acquisition or
production scoring run was performed for the lifecycle review.

## Lifecycle feasibility decision

The existing `OpenVinoSession` owns one compiled model. Its compiled-cache
eviction bounds disk entries and bytes; it does not bound resident model memory.
The local client lazily owns one runtime per feature and has no implemented
multi-shape resident graph manager. Evicting graphs between the existing
alternating inputs would introduce recompilation, which must be charged to an
end-to-end measurement. The prior three-whole-graph median compilation cost was
1.240 seconds; it is not a per-switch estimate or a performance guarantee.

A read-only inventory of the original three graphs found:

| Quantity | Bytes |
| --- | ---: |
| Large identical float32 data across 89 groups | 324,519,936 |
| Unique data within those groups | 108,173,312 |
| Duplicate large float32 payload | 216,346,624 |
| Two secondary serialized weight arenas | 217,012,560 |
| 15% of the observed whole-graph median peak RSS | 223,576,473.6 |

All six original XML/BIN size/hash identities remained intact. The inventory
made zero compilation and inference calls. Payload sizes are not measured RSS
savings or a strict allocator/OS-page bound.

Two source-level constraints prevent a simple sharing proposal from establishing
the required value:

- IR numeric Constants are slices retaining the whole original weight buffer.
  A small unshared Constant or an audit array view can retain a secondary arena
  even after large Constants are shared. Releasing it requires a separate,
  explicit detachment and owner-lifetime design. See the pinned
  [OpenVINO 2026.2.1 deserializer](https://raw.githubusercontent.com/openvinotoolkit/openvino/2026.2.1/src/core/xml_util/src/xml_deserialize_util.cpp).
- CPU packed-weight caches belong to individual compiled models. A shared Core
  or Constant pointer does not establish shared packed weights. See
  [CPU compiled-model ownership](https://raw.githubusercontent.com/openvinotoolkit/openvino/2026.2.1/src/plugins/intel_cpu/src/compiled_model.cpp).

The removable serialized payload alone does not establish a credible 15% RSS
improvement. No Constant-interning or naive eviction performance experiment is
selected. The earlier 15% RSS / 10% latency gates and negative result remain
unchanged. A future optional adapter must retain exact shape dispatch, explicit
unavailable results, bounded native-request/model ownership, raw MOS separated
from calibration, and a new reviewed resource contract before execution.

## Confirmed quality validity defect

The continuation review found a concrete defect in `PyIqaQualityAdapter`.
Python `min`/`max` clipping mapped `NaN` to a normalized 10 for higher-better
metrics and 0 for lower-better metrics. Positive infinity could also become a
valid-looking clipped score. An invalid observation could therefore appear as
accepted model evidence rather than unavailable quality data.

The fix validates every configured raw score before signal assembly, including
the native `.item()` value before float coercion. Scores must be finite real
numbers; booleans, strings, complex values and nonscalar arrays are rejected.
Standard and NumPy real scalars remain supported. Configuration bounds and
weights must be finite nonboolean numbers, range width finite and positive,
weights nonnegative and at least one enabled weight positive. Nonfinite
aggregate arithmetic fails explicitly. Finite outliers still clip in their
configured direction; boundary comparisons precede subtraction to avoid
intermediate overflow.

The existing client handles failure as `_quality.status="fallback"` with
`execution.status="unavailable"`; it emits no accepted quality signals or
aggregates. With `enforce_available=true`, the error propagates. Heuristic
dimensions and other valid model blocks retain their existing behavior.
This is evidence validation, not calibration, fusion, provider selection or a
production-policy change. It does not rewrite stored score metadata.

Regression checks cover invalid scalar outputs, invalid configuration, range
and aggregation overflow, valid NumPy values and extreme finite clipping,
native scalar coercion, both client failure modes and strict finite JSON.
Real PyIQA weights/models are not initialized by these tests.
Independent source/client review found no actionable defect. Full checks pass
1,402 tests / ten skipped; 155 focused quality/lifecycle checks and lint pass.

## Continuation

Review and verify the scoped validity fix, then complete its normal push,
exact-revision CI and authorized native release verification. Keep lifecycle
inventory, source hashes and interruption checkpoints in ignored storage.
Retain the existing native baseline and unavailable results; do not broaden
shape support, normalize unsupported previews or introduce the rejected shared
runtime into application defaults. Actual RAW orientation, calibration/product
utility and independent directed-coverage references remain separate gates.
