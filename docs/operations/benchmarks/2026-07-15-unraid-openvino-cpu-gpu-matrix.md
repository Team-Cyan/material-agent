# Unraid OpenVINO CPU/GPU Throughput Matrix

Date: 2026-07-15

## Scope

This report selects the deployment default for the bundled quantized DINOv3
ViT-S model on the target Unraid NAS. It uses immutable image
`ghcr.io/team-cyan/material-agent@sha256:3c196d35850f398dc9cc67967cd82ab29e4a4457133c21fffd398e56f59030e8`
from revision `dda680d46fe9114df54c57193c4bc4d6ee8b1bf0`.

Host:

- Unraid 7.2.4, Linux 6.12.54;
- Intel Core i7-11700T with Intel integrated GPU exposed through `/dev/dri`;
- OpenVINO 2026.2.1;
- fixed first 128 RAW files from `/mnt/user/material/photos`;
- 32-preview windows, eight asynchronous requests, `THROUGHPUT` hint;
- grouping, screening, and learned score fusion disabled to isolate the
  maintained heuristic-plus-embedding pipeline.

## Safety Boundary

- The source share was bind-mounted read-only.
- `MATERIAL_AGENT_DRY_RUN=true`.
- Each profile used a fresh appdata directory for SQLite, logs, compiled cache,
  and runtime configuration.
- Every run recorded zero written files and zero errors.
- Final audit: source XMP count 0, source runtime-state directory count 0,
  processed-row count 0.

## 128-RAW Matrix

| Device | Batch | Cold seconds | Cold files/s | Warm seconds | Warm files/s | Warm embedding inference | Actual strategy | Optimal requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| CPU | 1 | 21 | 6.095 | 19 | 6.737 | 2.847 s | single | 8 |
| CPU | 4 | 20 | 6.400 | 19 | 6.737 | 2.803 s | auto_batch | 8 |
| CPU | 8 | 22 | 5.818 | 19 | 6.737 | 2.866 s | auto_batch | 8 |
| GPU.0 | 1 | 265 | 0.483 | 258 | 0.496 | 242.383 s | single | 2 |
| GPU.0 | 4 | 265 | 0.483 | 258 | 0.496 | 242.456 s | auto_batch | 2 |
| GPU.0 | 8 | 264 | 0.485 | 258 | 0.496 | 242.414 s | auto_batch | 2 |

The GPU cold runs reported optimal request counts up to 4; warm runs reported
2. CPU reported 8 consistently. Batch 4/8 used OpenVINO native auto-batch with
the requested batch size and zero fallback. The export could not use fixed
reshape because an internal shape remained dynamic, but auto-batch compatibility
was successful.

## 512-RAW Sustained Run

The selected CPU batch-1 profile processed 512/512 files in 88 seconds:

- end-to-end: 5.818 files/second;
- RAW decode aggregate: 64.712 seconds;
- local heuristic aggregate: 36.488 seconds;
- embedding preprocess: 1.825 seconds;
- embedding inference: 10.616 seconds;
- embedding postprocess: 0.013 seconds;
- compile: 1.452 seconds;
- inference windows: 16;
- actual device: CPU;
- actual requests: 8, optimal requests: 8;
- model embeddings: 512;
- written/error/skipped files: 0/0/0.

Stage aggregates overlap because preview preparation and inference are
concurrent. End-to-end elapsed time is the selection metric.

## Decision

Use CPU, batch 1, `THROUGHPUT`, eight asynchronous requests, and a 32-preview
window as the default for this image and target class. It matches the best CPU
warm throughput without dynamic-shape auto-batch complexity. Keep explicit GPU
and batch 4/8 overrides available for future models and hosts, but do not select
the current iGPU for this DINOv3 graph.
