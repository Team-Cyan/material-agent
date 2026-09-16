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

Follow `AGENTS.md` for task routing and `docs/ai/shared-context.md` for working rules already in scope. Select the owning module and add architecture, runtime, or model-selection context only when the task needs it. Icon work uses `docs/ai/icon-design.md` for geometry, palette, export, and validation.

Roadmap, handoff, and historical OMLX plans are conditional context. Their recorded state needs checking against the current checkout or runtime before it supports a current-state claim.

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

## Public Repository Boundary

This repository owns the application: photo discovery and decoding, scoring,
grouping, SQLite state, XMP behavior, the Web/CLI surfaces, model runtimes, and
generic container deployment contracts.

It must not contain private-machine control capabilities or profiles. In
particular, saved host addresses, credentials, SSH execution, DockerMan or
ComposeMan update orchestration, NAS backup/restore receipts, Home Assistant,
router, and proxy operations belong in a separate private operations
repository. Application documentation may describe the interface expected by
an external operator, but must use generic paths and sanitized evidence.
