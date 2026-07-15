# Unraid OpenVINO NIMA CPU/GPU Matrix

## Decision

Keep the production NIMA profile on `CPU`, batch 1, with up to eight inference
requests. Do not split this stage across CPU and GPU and do not require
`/dev/dri` in the ordinary scoring container.

The target i7-11700T does execute the NIMA graph on `GPU.0`, but the small warm
throughput difference changed direction between repetitions. GPU cold startup
and memory use were consistently higher, so the GPU path does not offer a
stable material benefit for this model and workload.

## Boundary

- image revision: `f89198e73438f516d0d2d158c2a8818cfd45f2ad` for the reported matrix;
- model: bundled NIMA MobileNet/AVA FP16 TFLite, SHA-256
  `a5051a0fcced735682735e3e0fd58ee54c83ed664282a003f52235b3dbcb9320`;
- runtime: OpenVINO 2026.2.1;
- source: 128 RAW files under `/mnt/user/material/photos`, mounted at `/photos`
  read-only;
- state: `/mnt/user/appdata/material-agent/runtime/.material-agent`, mounted at
  `/config` read-write;
- repetitions: one cold plus ten warm passes per device/batch profile in the
  primary run;
- source verification: zero XMP files and zero source-side `.material-agent`
  directories before and after the benchmark.

## Primary Ten-Warm-Pass Matrix

| Device | Batch | Cold seconds | Warm p50 seconds | Warm images/s | Peak warm RSS MiB | Actual execution |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| CPU | 1 | 1.703 | 1.121 | 114.190 | 818.5 | CPU |
| CPU | 4 | 1.288 | 1.156 | 110.705 | 942.5 | CPU |
| CPU | 8 | 1.335 | 1.191 | 107.512 | 1033.9 | CPU |
| GPU.0 | 1 | 4.032 | 1.219 | 105.033 | 1628.6 | GPU.0 |
| GPU.0 | 4 | 2.007 | 1.154 | 110.966 | 1486.6 | GPU.0 |
| GPU.0 | 8 | 1.366 | 1.148 | 111.520 | 1453.2 | GPU.0 |

CPU batch 1 won this run by 2.4% over GPU batch 8. Two shorter five-pass
repetitions put the best GPU batch 4/8 profile roughly 6-7% ahead of CPU batch
1, demonstrating that the small gap is not stable enough to justify a different
production architecture. Every profile reported the requested execution device
and `fallback_used=false`.

## Utilization Sampling

The image includes an `intel_gpu_top` JSON sampler backed by Intel PMU counters.
The first non-privileged run correctly reported that PMU access was denied. A
second isolated DockerMan benchmark added only `CAP_PERFMON`, but the entrypoint
then dropped capabilities while changing to the configured PUID/PGID. The image
contract was therefore tightened so `intel_gpu_top` has the file capability and
the benchmark container must also explicitly opt into the runtime capability.
Neither the production scorer nor the model-management service receives
`CAP_PERFMON`.

The final scoped-PMU run used image revision
`faca64c71709d34bb1d2624e468aff0f89745443`. GPU profiles recorded
`gpu_busy_source=intel_gpu_top`, 3.44-3.64% mean engine busy over the complete
warm measurement windows, and 91.44-100% peak engine busy. CPU profiles returned
no engine-busy samples as expected. In the same run, the best GPU batch-4 warm
profile reached 127.878 images/second versus the best CPU batch-4 profile at
119.115 images/second, but the primary ten-pass run had CPU ahead. The low mean
and high peak show that NIMA inference reaches the iGPU in short bursts and
spends most wall time outside active GPU execution.

OpenVINO execution-device readback, PMU samples, the mapped `/dev/dri` device,
and lower GPU-path process CPU use all independently support that inference was
dispatched to `GPU.0` rather than falling back.

## Operational Result

- CPU batch 1 remains the default in `docker/config.intel-openvino.yaml`;
- the production scorer does not need `/dev/dri` for NIMA;
- the benchmark wrote its JSON report, caches, database, and logs only under
  appdata;
- no XMP or rating was written to the photo share;
- target-specific personal calibration remains disabled until genuine human
  labels and an independent holdout set exist.
