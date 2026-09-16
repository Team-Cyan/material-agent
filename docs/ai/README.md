# AI Workspace

Start at `AGENTS.md`. This directory holds reusable repository guidance; it is an index to select from, not a required reading sequence.

## Choose Context By Task

| Need | Read |
| --- | --- |
| Working rules and verification | `shared-context.md`, once per context |
| Product orientation | `project-overview.md` |
| Module ownership | Relevant contract in `modules/`; `architecture/module-boundaries.md` when ownership is unclear or crosses layers |
| Local runtime or model selection | `inference-runtime.md`, `model-selection.md`, and the relevant local module |
| Isolated local evaluation | `modules/local-benchmark.md` |
| Explicit OMLX comparison work | `harness-workflow.md` and its task-specific route |
| Repeated change pattern | Matching file in `playbooks/` |
| Risk-focused review | Applicable items in `checklists/` or `modules/anti-patterns.md` |
| Task framing or delegation | Optional `prompts/`, `templates/subagent-task.md`, or one relevant `examples/` file |
| Collaboration-doc maintenance | `memory/ai-doc-maintenance-policy.md`; relevant durable decisions in `memory/` |
| External compatibility evidence | Matching file in `reference/` |

## Usage

- Keep AI-facing guidance in English and entrypoint files thin.
- Reuse context already read. Add documents when they resolve a concrete unknown; do not restart the reading sequence after a follow-up or compaction.
- Module contracts and safety invariants remain binding within their scope. Playbooks, examples, and checklist formats are aids, not blanket requirements to create a plan, spawn a worker, run every listed check, or pause for approval.
- Update the owning doc when behavior or safe-edit guidance changes. Keep status in `docs/roadmap.md` and handoff details in `docs/operations/session-handoff.md` only when the task changes or depends on them.
