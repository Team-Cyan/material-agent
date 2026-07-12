# Local Model Candidate Benchmark - 2026-07-01

This note records the screening pass for new local model candidates after the
NAS-first runtime pivot. It is a small fixed-sample benchmark, not a final model
evaluation suite.

## Environment

- Host: Apple M4, 16 GB RAM
- Python: 3.14 through `uv run --python 3.14 --isolated`
- Image set: six fixed local images covering cat duplicates, flower-wall
  duplicates, one unrelated cat image, and one screenshot
- IQA input: 512 x 512 previews on CPU
- Embedding input: model processor default or 224 x 224 fallback

## Decision Summary

| Block | Default / preferred | Backup | Not default |
| --- | --- | --- | --- |
| Near-duplicate grouping | DINOv2-small | DINOv3 ViT-S ONNX MHA Q4 | DINOv2-registers, MobileCLIP embeddings, DINOv3 ConvNeXt ONNX |
| Semantic tags | MobileCLIP2-S0 | MobileCLIP-S1, SigLIP2 B/16 or B/32 | MobileCLIP2-S2 for default NAS path |
| Aesthetic / IQA | MUSIQ, NIMA, CLIPIQA+ | CLIPIQA, BRISQUE/NIQE as reject priors | PAQ2PIQ, TOPIQ_NR, CNNIQA, HyperIQA, MANIQA, DBCNN, LIQE, ARNIQA, QualiCLIP+ |
| Subject segmentation | None by default | RMBG-2.0 or BiRefNet as optional offline task | Always-on segmentation in the default batch path |

## Embedding And Grouping

Metrics:

- `same_group_top1`: nearest-neighbor top-1 match among duplicate groups only.
- `screenshot_photo_max`: maximum cosine similarity between the screenshot and
  any photo; lower is better.

| Model | Runtime | Load s | Infer s | Images/s | same_group_top1 | screenshot_photo_max | Result |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| DINOv2-small | Transformers / MPS | 2.062 | 1.551 | 3.87 | 4/4 | 0.0171 | Keep as default grouping model. |
| DINOv2 with registers small | Transformers / MPS | 10.365 | 1.197 | 5.01 | 2/4 | 0.0932 | Not better than DINOv2-small. |
| MobileCLIP2-S0 image embedding | OpenCLIP / MPS | 2.332 | 1.326 | 4.53 | 2/4 | 0.1279 | Keep for semantics, not grouping. |
| MobileCLIP2-S2 image embedding | OpenCLIP / MPS | 17.861 | 1.563 | 3.84 | 2/4 | 0.2567 | No grouping gain over S0. |
| DINOv3 ViT-S Q4 | ONNX Runtime CPU | 0.085 | 1.827 | 3.28 | 2/4 | 0.1582 | Viable ONNX fallback, not default. |
| DINOv3 ViT-S quantized | ONNX Runtime CPU | 0.084 | 1.280 | 4.69 | 2/4 | 0.1272 | Faster than Q4, still weaker grouping. |
| DINOv3 ViT-S MHA Q4 | ONNX Runtime CPU | 0.088 | 1.298 | 4.62 | 3/4 | 0.1551 | Best DINOv3 ONNX variant tested; backup only. |
| DINOv3 ViT-S MHA Q4F16 | ONNX Runtime CPU | 0.110 | 1.395 | 4.30 | 2/4 | 0.1648 | No gain. |
| DINOv3 ConvNeXt Tiny Q4 / quantized | ONNX Runtime CPU | fail | fail | n/a | n/a | n/a | ORT load fails on Loop/If/Concat type inference. |
| DINOv3 ConvNeXt Small Q4 / quantized | ONNX Runtime CPU | fail | fail | n/a | n/a | n/a | Same ORT type-inference failure. |

Conclusion: DINOv3 is worth keeping as an ONNX/OpenVINO candidate, especially
the ViT-S MHA Q4 model, but it does not replace DINOv2-small on this sample set.
The ConvNeXt ONNX exports should be excluded until the ONNX graph or runtime
compatibility issue is resolved.

## Semantic / Scene Tags

Labels used: `screenshot`, `cat`, `flower_wall`, `portrait`, `architecture`,
`food`, `landscape`, `indoor`.

| Model | Runtime | Load s | Infer s | Images/s | Top-1 | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| MobileCLIP2-S0 | OpenCLIP / MPS | 2.189 | 1.386 | 4.33 | 4/6 | Correct for cats and screenshot; flower-wall images drifted to portrait. |
| MobileCLIP2-S2 | OpenCLIP / MPS | 2.727 cached | 1.367 | 4.39 | 4/6 | No practical gain over S0 on this set. |
| SigLIP2 B/32 256 | OpenCLIP / MPS | 25.254 | 1.776 | 3.38 | 4/6 | Correct cats/screenshot, heavier load, no flower-wall gain. |
| SigLIP2 B/16 256 | OpenCLIP / MPS | 23.317 | 1.560 | 3.85 | 4/6 | Same result pattern as B/32. |

Conclusion: MobileCLIP2-S0 remains the semantic default. SigLIP2 is a reasonable
backup when larger OpenCLIP dependencies are acceptable, but it is not better on
the current photo-cleaning labels.

## IQA / Aesthetic / Reject Priors

`screenshot_rank_best1` is the screenshot rank when sorting from best to worst.
For a quality/aesthetic scorer, rank 6/6 is the desired behavior.

| Model | CPU load s | CPU infer s | Images/s | screenshot_rank_best1 | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| BRISQUE | 0.004 | 0.101 | 59.17 | 6/6 | Excellent lightweight non-photo/reject prior. |
| NIQE | 0.041 | 0.154 | 38.91 | 6/6 | Excellent lightweight non-photo/reject prior. |
| NIMA | 1.110 | 0.287 | 20.90 | 6/6 | Fast aesthetic baseline; keep. |
| CLIPIQA | 1.298 | 0.937 | 6.40 | 6/6 | Keep as fallback. |
| CLIPIQA+ | 2.902 | 0.688 | 8.72 | 6/6 | Prefer over plain CLIPIQA when available. |
| MUSIQ | 0.110 cached | 0.730 | 8.22 | 6/6 | Keep as primary NR quality scorer. |
| MUSIQ-SPAQ | 105.994 first load | 1.009 | 5.95 | 6/6 | Works, but no default gain over MUSIQ. |
| CNNIQA | 0.004 | 0.261 | 22.98 | 5/6 | Lightweight but less reliable; not default. |
| PAQ2PIQ | 0.108 cached | 0.206 | 29.09 | 3/6 | Ranks screenshot too high; not default. |
| TOPIQ_NR | 2.493 | 0.821 | 7.31 | 3/6 | Ranks screenshot too high; not default. |
| HyperIQA | 40.714 first load | 18.220 | 0.33 | 6/6 | Too slow/heavy for NAS default. |
| MUSIQ-PAQ2PIQ | timeout | n/a | n/a | n/a | 104 MB weight download timed out; not a default candidate. |
| ARNIQA | timeout | n/a | n/a | n/a | 107 MB weight download timed out; not a default candidate. |
| LIQE / LIQE_mix | not run | n/a | n/a | n/a | Each weight is about 354 MB; too heavy for default. |
| QualiCLIP+ | interrupted | n/a | n/a | n/a | Implementation pulls 390 MB `QualiCLIP.pth`; not default. |
| MANIQA | interrupted | n/a | n/a | n/a | 518 MB checkpoint; not default. |
| DBCNN | interrupted | n/a | n/a | n/a | Pulls VGG16-scale checkpoint; not default. |

Conclusion: use BRISQUE and NIQE as cheap reject priors, not final ranking
signals. Keep MUSIQ + NIMA + CLIPIQA+ as the default IQA/aesthetic model group.
Avoid PAQ2PIQ and TOPIQ_NR as uncalibrated defaults because both scored the
screenshot above real photos in this sample.

## Subject / Saliency Candidates

RMBG-2.0 and BiRefNet remain optional offline tasks rather than default scoring
steps. RMBG-2.0 has useful background-removal behavior, but the Hugging Face
weights are non-commercial, the PyTorch path uses `trust_remote_code`, and the
available model sizes are too large for always-on NAS scoring. Use these only
after the first embedding/IQA path is stable.

## Next Benchmark Work

- Add a checked-in report-only benchmark harness so future candidates run
  against the same sample manifest and metrics.
- Add face-positive, low-light, blurry, burst, screenshot, document-scan, and
  phone-metadata samples.
- Add Intel OpenVINO measurements on the target NAS or a Linux host with
  `/dev/dri` GPU access.
- Calibrate reject priors separately from final aesthetic ranking.

## Primary Sources

- DINOv3: https://github.com/facebookresearch/dinov3
- Hugging Face DINOv3 docs: https://huggingface.co/docs/transformers/en/model_doc/dinov3
- DINOv3 ViT-S ONNX: https://huggingface.co/onnx-community/dinov3-vits16-pretrain-lvd1689m-ONNX
- PyIQA: https://github.com/chaofengc/IQA-PyTorch
- PyIQA weights: https://huggingface.co/chaofengc/IQA-PyTorch-Weights
- OpenCLIP: https://github.com/mlfoundations/open_clip
- MobileCLIP2 OpenCLIP model card: https://huggingface.co/timm/MobileCLIP2-L-14-OpenCLIP
- RMBG-2.0: https://huggingface.co/briaai/RMBG-2.0
- BiRefNet: https://huggingface.co/ZhengPeng7/BiRefNet
