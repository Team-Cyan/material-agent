# Model Selection Todo

This note turns the May 2026 model-selection research report into repo-local follow-up work.

## Current Position

- Keep OMLX as the default local runtime path for structured vision scoring on Apple Silicon.
- Keep Ollama as a compatibility and ease-of-use fallback, not the primary optimization target.
- Keep MUSIQ-style fast screening as the technical-quality gate.
- Treat the current VLM path as useful for scene understanding, structured commentary, and explanation.
- Do not assume a larger general VLM is the best primary scorer for culling or burst ranking.

## Short-Term Todo

- Add a model-evaluation plan that compares the current `MUSIQ + VLM` path against `MUSIQ + frozen visual encoder + small ranking head`.
- Define the first benchmark dataset as burst/group examples with human keep/review/reject or pairwise preference labels.
- Track group-level metrics, not only per-image score error:
  - group top-1 agreement
  - pairwise preference accuracy
  - scene-wise calibration
  - reject false-negative rate
- Keep the first pass offline and report-only; do not replace production scoring until it beats the current path on the same fixture set.

## Mid-Term Todo

- Prototype a frozen encoder baseline with DINOv2-S/B or OpenCLIP/SigLIP embeddings.
- Train only a small ranking/regression head first.
- Add auxiliary heads only when useful:
  - scene classification
  - technical quality
  - seven visible scoring dimensions
- Feed accepted human decisions back into a durable local label store before any heavier model training.

## Deferred

- Do not train a full visual backbone from scratch.
- Do not fine-tune a VLM until there is enough image-commentary-label data to justify it.
- Do not make DaVinci/Photomator workflow quality depend on a model swap; solve those through export/XMP workflow bridges separately.
