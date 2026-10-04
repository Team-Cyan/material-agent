# Full frozen MUSIQ Intel diagnostic

This step expands the [accepted 32-image feasibility](../2026-10-04-musiq-intel/README.md)
to the complete unchanged quality cohort. It reuses the exact whole-image graph;
it does not export another graph, acquire weights/packages, fit calibration,
change production scoring/grouping or write photo metadata.

## Protocol and references

The full protocol SHA256 is
`ef9841b0bf34d3f7d63ccf694f8a1d8312c915f95e08cddb0addd15f20315bf2`.
[protocol-summary.json](protocol-summary.json) contains its portable constants,
parent identities and item fingerprint. Exactly 1,024 KonIQ and 1,024 KADID
512×384 images retain their existing labels and diagnostic partitions. KonIQ has
512 development / 512 comparison images. KADID has 530 / 494 images across 40 /
41 disjoint native reference families.

All 2,048 original successful CPU Torch records, heuristic caches and source
checksums were validated before freezing the new protocol. Original raw scores
are read-only numerical references, not a second inference on the target.
The reference cohort and labels were previously inspected. KonIQ uses
KonIQ-trained weights with unaudited training overlap and remains a
training-exposed diagnostic. KADID source-image training overlap is unaudited;
these partitions do not establish independent product acceptance.

The unchanged checkpoint SHA256 is
`e95806b9eae5f3814c410f574ba8e552362bd5bc63d758ed5b97860f5d6185aa`.
The FP32-storage XML/BIN graph is 109,156,287 bytes, with the same hashes as the
32-image feasibility. Input is RGB float32 NCHW `[0,1]`, shape `[1,3,384,512]`;
native internal normalization and original/224/384 scales are already in the
graph. No external resize or calibration is introduced.

## Frozen execution and statistics

`scripts/benchmark_musiq_openvino_full.py` and the immutable parity helper are
bundled together. One native OpenVINO inference per image uses CPU, four threads,
one stream, latency mode and F32 precision-hint readback. The earlier repeat gate
is already accepted; this step additionally tests exact full-cohort resume.
F32 readback is a runtime property, not a per-node arithmetic audit.

The raw-score gate is maximum absolute error at most 0.001 against all frozen
Torch references. Resource bounds are 1,800 wall seconds, 2.5 GB observed child
RSS, 6,500 / 6,510 soft/hard CPU seconds, 12 GiB address space, 128 MiB per output
file and 1,024 open files. An external process-group watchdog bounds native calls.
Observed process RSS does not measure an entire container cgroup.

For each track and all/development/comparison partition, native-target PLCC and
SROCC use exactly the paired candidate/heuristic denominator. The 2,000-draw
paired percentile bootstrap uses seed 20261003 and 95% intervals for
candidate-minus-heuristic correlations. KADID samples complete native reference
families with replacement and preserves member multiplicity. KonIQ samples
image IDs; semantic dependence remains unaudited. Each draw re-ranks its own
scores/targets with average ties. Intervals are conditional on this fixed corpus,
not training-overlap or photographic-utility guarantees.

Incomplete execution, invalid execution readback, asset drift, failed parity or
resource failure invalidates improvement deltas and intervals. This experiment
introduces no new ranking-improvement threshold or production admission rule.

## Isolation and recovery

The homelab controller uses its documented fixed approved-plan wrapper and the
already-deployed native DockerMan image. The immutable package contains 2,053
allowlisted regular files, bounded to 1 GiB: the existing graph, two scripts,
protocol and 2,048 images. Source bytes are root-owned read-only; inference runs
as UID/GID 99:100 with separate owned reports/cache/tmp, preserving `HOME`.
The production photo mount remains read-only.

Each successful prediction and checkpoint is atomic and includes input, protocol,
graph, source and runtime identity. Matching intact records alone may resume;
corrupt JSON/UTF8 records recompute and unsafe paths fail closed. A bounded export
can retrieve completed prediction files even if no final report exists. Protocols,
media, weights, per-image records, private-host receipts and controller snapshots
stay ignored on disk. Only aggregate evidence is published.

An independent verifier uses SciPy correlations and its own paired bootstrap,
checks original reference/cache records and item joins, and checks exact-command
resume without importing the benchmark's numerical algorithms. Wall timings are
observational. Previous Mac Torch timings have different environments and scopes;
this is not a controlled speedup experiment.

## Observed results

The native DockerMan Intel image at `380bbbcf44251bcb69052e53e1d504cce643ab7e` ran all 2,048
predictions successfully with actual CPU/F32 property readback and no fallback.

| Measure | First run |
| --- | --- |
| Maximum raw error | 0.0003051758 |
| Mean / p95 raw error | 0.0000233208 / 0.0000610352 |
| Run-entry elapsed time | 275.15 seconds |
| Process peak RSS | 509,554,688 bytes |
| Wrapper-sampled child peak RSS | 511,033,344 bytes |
| First-run reused predictions | 0 |
| Exact resume reused / new inferences | 2,048 / 0 |

Resume reproduces all records, identity and statistics exactly; its elapsed time
is 28.58 seconds, including validation/compile/statistics. Cached
native-call latency fields describe the first inference, not resume speed.

| Track / partition | Images | MUSIQ SROCC | Heuristic SROCC | Paired delta SROCC 95% interval |
| --- | --- | --- | --- | --- |
| kadid / all | 1024 | 0.5487 | 0.0694 | [0.3935, 0.5610] |
| kadid / development | 530 | 0.5119 | 0.0739 | [0.3334, 0.5467] |
| kadid / comparison | 494 | 0.5964 | 0.0656 | [0.4045, 0.6481] |
| koniq / all | 1024 | 0.8695 | 0.3643 | [0.4525, 0.5578] |
| koniq / development | 512 | 0.8708 | 0.3838 | [0.4129, 0.5604] |
| koniq / comparison | 512 | 0.8672 | 0.3442 | [0.4471, 0.5998] |

[results.json](results.json) preserves every PLCC/SROCC and both interval types.
All draws in these six sets are valid. Independent SciPy calculations reproduce
24 candidate/heuristic correlation fields and six bootstrap sets; original
reference/cache checks and input/partition joins also pass. Maximum association
drift against the original Torch scores is 0.0000076176
for SROCC and 0.0000002366 for PLCC.

The service remains idle with the same library/config snapshots: 40,620 indexed
and scored, zero errors. No production scoring/grouping/XMP policy changed.
Application checks passed 1,230 / ten skipped; 46 focused runner/helper tests,
133 wrapper checks, lint and three repository-boundary checks passed. Completed
independent source review has no remaining mustfix findings.

Next audit the actual scoring input contract and existing real RAW/JPEG previews
against this accepted shape before designing an optional adapter. Freeze any
needed preprocessing/shape contract and separate product-utility/coverage gates.
Do not repeat this cohort, rotate models, implicitly resize inputs or claim
variable-shape/GPU/production acceptance from these standard images.
