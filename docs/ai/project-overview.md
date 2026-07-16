# Project Overview

This file is the primary agent-facing overview for `material-agent`.

## What This Repository Does

`material-agent` is a NAS-first local photo culling and scoring tool.

Its main production path is:

`scan -> group -> local score -> group rank -> write XMP -> persist SQLite state`

The fork intentionally removes Ollama and OMLX from the default design. Legacy copied code may still exist during migration, but new work should target local model runtimes and deterministic fallbacks first.

## Current Direction

- Default backend: `local`
- First accelerated runtime: Intel OpenVINO through native OpenVINO APIs
- Plain ONNX Runtime role: CPU fallback and non-OpenVINO providers
- Required fallback: CPU
- Later runtime tags: NVIDIA CUDA, AMD MIGraphX, native Apple Silicon
- Apple container stance: normal containers should not assume Metal GPU passthrough; prefer native CoreML/MLX/MPS or a host inference service bridge.

## Current AI Documentation Model

This repository uses:

- `AGENTS.md` as a thin repository entrypoint
- `docs/ai/` as the durable AI knowledge base
- `.agents/` as repo-local agent assets and navigation
- `docs/` for human-facing runbooks and architecture guides

## Start Here

For most tasks, read:

1. `docs/ai/project-overview.md`
2. `docs/ai/shared-context.md`
3. `docs/ai/architecture/module-boundaries.md`
4. `docs/ai/inference-runtime.md` for hardware, model runtime, or Docker work
5. `docs/ai/model-selection.md` for local scoring, embedding, and model choice work
6. `docs/ai/icon-design.md` for the current icon geometry, palette, export, and
   validation standard
7. The smallest relevant file under `docs/ai/modules/`

Do not start by reading every historical OMLX plan copied from `material-judge`.

## High-Value Human Docs

- `README.md`
- `docs/roadmap.md`
- `docs/module-map.md`

## Working Defaults

- Keep the primary path free of HTTP model-service dependencies.
- Prefer ONNX-exportable models for scorer and embedding work.
- Prefer the default local model stack in `docs/ai/model-selection.md` unless a
  benchmark shows a candidate is better on fixed sample sets.
- Build provider-specific Docker tags instead of one image with every vendor runtime.
- Keep CPU fallback working before adding accelerator-specific code.
- Prefer small, module-scoped changes.
- Update `docs/ai/inference-runtime.md` when runtime-provider behavior changes.
