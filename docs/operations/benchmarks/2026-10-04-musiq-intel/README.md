# Fixed-shape MUSIQ OpenVINO feasibility on Intel

The existing MUSIQ checkpoint now has a bounded native OpenVINO CPU path without
Torch/PyIQA in the target runtime. This is an isolated conversion/parity diagnostic,
not production integration or admission of a scoring or discard policy.
The earlier [2,048-image Torch comparison](../2026-10-03-public-musiq/README.md)
retains its training-exposure and product-utility limits.

## Frozen route

The unchanged checkpoint SHA256 is
`e95806b9eae5f3814c410f574ba8e552362bd5bc63d758ed5b97860f5d6185aa`.
Select the first sixteen IDs per track after SHA256-of-ID sorting within the
original 2,048 successful predictions. Verify image bytes and reference raw scores
against the original manifest and prediction checksums. This sample establishes
implementation parity; it is not a new quality benchmark.

`scripts/benchmark_musiq_openvino.py` exports the existing eval network with
Torch 2.14.0 and OpenVINO 2026.2.1 as a whole-image static `1×3×384×512` RGB
float32 `[0,1]` graph. It retains normalization, native bicubic interpolation
(`align_corners=False`), SAME/unfold patching, spatial/scale metadata, padding
masks, eval layers and raw linear MOS. Python shape rounding is specialized to
168×224 and 288×384 while retaining native interpolation. The 385 tokens contain
342 valid and 43 padded tokens; the encoder adds CLS. Arbitrary shapes are rejected.

Before conversion, specialized/native preprocessing tokens were exactly equal;
all 32 original/specialized/parent scores matched exactly. TorchScript emits
static-shape and Python 3.14 deprecation warnings; successful export does not
promise dynamic shapes or future Torch support. The [conversion API](https://docs.openvino.ai/2026/api/ie_python_api/_autosummary/openvino.convert_model.html)
supports the installed frontend; [model storage precision](https://docs.openvino.ai/2026/api/ie_python_api/_autosummary/openvino.save_model.html)
is fixed with `compress_to_fp16=False`, separately from the CPU precision hint.
The target checks native execution-device and F32 precision-hint readback;
per-node arithmetic precision is not independently audited.

XML/BIN total 109,156,287 bytes. [Results](results.json) and the
[protocol summary](protocol-summary.json) pin graph hashes and bounds. Complete
protocol SHA256 is `17bbcbde5072d65c5365b18925d0ac5d9d3d039440a7ba3fb6eefc5b8c4e14eb`.
Raw IDs, source images/scores, predictions and graph files stay ignored.

## Gates and measured results

Predeclared bounds: 32 images, two inferences each, 150 MB graph, 900 seconds and
2.5 GB observed RSS. Export has a separate 300-second/2.5 GB subprocess watchdog.
Maximum absolute raw-score error must be `≤0.001`; repeated-output error must
be `≤0.000001`. Neither tolerance changed after observing results. CPU uses
four numerical threads, one stream and requested F32, without alternate fallback.

| Check | Result |
| --- | ---: |
| Local OpenVINO maximum error vs Torch | 0.000080108642578125 |
| Intel OpenVINO maximum error vs Torch | 0.00005340576171875 |
| Intel mean / p95 error | 0.000024020671844482422 / 0.000049209594726562495 |
| Intel maximum repeated-output error | 0 |
| Successful Intel images / native inferences | 32 / 64 |
| Stable pairs with reference gap above 0.002 | 496 / 496 |
| First Intel run-entry time | 8.81 seconds |
| Intel process peak RSS | 447,688,704 bytes |

Tests ran inside reviewed image revision `4296779af6f6badb747d5ba0a337adb0400efcde`.
No target dependencies were installed; the graph uses its existing OpenVINO runtime.
First run reused zero records. Exact-command resume reused all 32 with identical
identity and prediction records; resume is recovery evidence, not throughput.
Timers start after NumPy/OpenVINO imports and include preflight, compile, decode,
two inferences, checks and record writes. The controller's sampled first-run RSS was
449,261,568 bytes. No controlled Torch/Intel speedup or GPU compatibility is claimed.

## Isolation, review and recovery

The authorized homelab controller owns the separate fixed-root wrapper,
36-file/160-MiB approved package, checksum transport, root-owned read-only inputs,
UID/GID 99:100 execution, child limits and audit. Staging partials and atomic
predictions are retained; the previous public corpus is preserved. Outputs/cache/tmp
are separate from inputs and production state. HOME remains unchanged; even a
cached Python temporary directory is overridden and restored. Malformed JSON or
invalid-UTF8 records recompute; unsafe paths and oversized files fail closed.

Independent runner review found the temporary-directory and UTF8 recovery defects;
both were fixed and re-reviewed. Independent wrapper review found no remaining
must-fix issues. Fourteen focused checks, full application tests (1,197 passed,
ten skipped), 80 wrapper checks and lint passed. A separate verifier recomputed
source/record/protocol/graph identities, errors and all 496 applicable order pairs.
First/resume prediction records and identities match. The 40,620-record production
library, configuration and idle API are unchanged; photos remain read-only.
Physical XMP round trips were not tested.

Recovery artifacts remain under ignored `.local/musiq-intel-20261004/` and the
controller's approved plan/receipts. Resume from its checkpoint rather than
re-exporting weights or repeating completed preparation after interruption.

Next expand this same fixed graph to the unchanged 2,048-image quality cohort
on Intel with a separate frozen protocol, resource gate and source-family statistics.
Keep production dependencies lean. Variable-shape/RAW, GPU, product utility and
directed-coverage G1/G2 remain unaccepted; conversion does not admit rejection.
