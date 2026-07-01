# Workflow And Design Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `material-agent run` report partial failures honestly, persist final review rows safely enough for restartability, stabilize compatibility shims under lazy imports, and remove CLI parser drift.

**Architecture:** Keep the existing `shells -> commands -> app -> domain -> adapters` split. Fix the problems at the boundaries instead of refactoring the scoring stack: runtime status should become truthful, processed-state finalization should become a single DB write, compatibility shims should resolve domain symbols lazily, and CLI parser ownership should live in one place.

**Tech Stack:** Python 3.14, `sqlite3`, `argparse`, uv, pytest, ruff

---

### Task 1: Make partial job outcomes explicit in runtime status

**Files:**
- Modify: `src/material_agent/app/dto.py`
- Modify: `src/material_agent/adapters/state/sqlite_runtime.py`
- Modify: `src/material_agent/app/jobs/review_photos.py`
- Modify: `src/material_agent/app/job_executor.py`
- Modify: `src/material_agent/app/review_service.py`
- Test: `tests/test_review_job.py`
- Test: `tests/test_app_services.py`
- Test: `tests/test_runtime_state.py`

- [ ] **Step 1: Write the failing tests for partial-success status**

```python
# tests/test_review_job.py
assert tuple(job_row[:2]) == ("finalize", "finished_with_errors")
assert finished_event == {
    "status": "finished_with_errors",
    "total_files": 2,
    "written_files": 1,
    "error_files": 1,
    "skipped_files": 0,
    "scored_files": 2,
}

# tests/test_app_services.py
assert session_row["status"] == "finished_with_errors"
assert job_row["status"] == "finished_with_errors"

# tests/test_runtime_state.py
repo.update_job(job_id, stage=JobStage.FINALIZE, status=JobStatus.FINISHED_WITH_ERRORS)
repo.update_session(session_id, status=SessionStatus.FINISHED_WITH_ERRORS)
```

- [ ] **Step 2: Run the targeted tests and confirm they fail**

Run:

```bash
uv run pytest \
  tests/test_review_job.py::test_review_job_finished_summary_counts_files_that_reached_scoring \
  tests/test_app_services.py::test_review_run_service_creates_runtime_records_and_runs_executor \
  tests/test_runtime_state.py::test_runtime_repository_sets_finished_at_for_terminal_job_and_session_states \
  -q
```

Expected: failure because `finished_with_errors` does not exist yet and summary payload does not carry status.

- [ ] **Step 3: Add explicit runtime statuses and propagate them**

```python
# src/material_agent/app/dto.py
class SessionStatus(StrEnum):
    OPEN = "open"
    RUNNING = "running"
    FINISHED = "finished"
    FINISHED_WITH_ERRORS = "finished_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    FINISHED_WITH_ERRORS = "finished_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

```python
# src/material_agent/adapters/state/sqlite_runtime.py
return status in {
    SessionStatus.FINISHED.value,
    SessionStatus.FINISHED_WITH_ERRORS.value,
    SessionStatus.FAILED.value,
    SessionStatus.CANCELLED.value,
}
```

```python
# src/material_agent/app/jobs/review_photos.py
final_status = JobStatus.FINISHED_WITH_ERRORS if error_files else JobStatus.FINISHED
summary = {
    "status": final_status.value,
    "total_files": total_files,
    "written_files": written_files,
    "error_files": error_files,
    "skipped_files": skipped_files,
    "scored_files": scored_files,
}
self._update_stage(job_id, JobStage.FINALIZE, final_status, session_id=session_id)
```

```python
# src/material_agent/app/job_executor.py
def run(self, job_id: str, file_paths: list[str]) -> dict:
    return self.review_job.run(job_id, file_paths)
```

```python
# src/material_agent/app/review_service.py
result = executor.run(job_id, pending_files)
session_status = (
    SessionStatus.FINISHED_WITH_ERRORS
    if result["status"] == JobStatus.FINISHED_WITH_ERRORS.value
    else SessionStatus.FINISHED
)
self.session_service.update_session(session_id, status=session_status)
```

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
uv run pytest \
  tests/test_review_job.py \
  tests/test_app_services.py \
  tests/test_runtime_state.py \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/material_agent/app/dto.py \
  src/material_agent/adapters/state/sqlite_runtime.py \
  src/material_agent/app/jobs/review_photos.py \
  src/material_agent/app/job_executor.py \
  src/material_agent/app/review_service.py \
  tests/test_review_job.py \
  tests/test_app_services.py \
  tests/test_runtime_state.py
git commit -m "fix(runtime): surface partial completion explicitly"
```

### Task 2: Persist final processed rows in one write path

**Files:**
- Modify: `src/material_agent/adapters/state/processed_sqlite.py`
- Modify: `src/material_agent/app/review_runtime.py`
- Test: `tests/test_state.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Add regression tests for final commentary persistence**

```python
# tests/test_state.py
repo.mark_done(
    "/tmp/a.ARW",
    total_score=8.2,
    star_rating=4,
    group_boosted=False,
    scores={"exposure": 8.0, "sharpness": 8.0},
    metadata={},
    group_info={"group_id": "group_0001", "group_rank": 1, "group_size": 2},
    scene="people",
    scene_raw="stage singer",
    decision="keep",
    decision_reasons=["top_of_group"],
    commentary_group_issues="Group issue text",
    commentary_shooting="Shooting advice",
    commentary_post="Post advice",
)

row = repo.conn.execute(
    "SELECT status, commentary_group_issues, commentary_shooting, commentary_post "
    "FROM processed WHERE file_path='/tmp/a.ARW'"
).fetchone()
assert tuple(row) == ("done", "Group issue text", "Shooting advice", "Post advice")
```

```python
# tests/test_main.py
row = conn.execute(
    "SELECT commentary_group_issues, commentary_shooting, commentary_post "
    "FROM processed WHERE file_path=?",
    (str(photo_path),),
).fetchone()
assert row[0]
assert row[1]
assert row[2]
```

- [ ] **Step 2: Run the focused persistence tests**

Run:

```bash
uv run pytest tests/test_state.py tests/test_main.py -q
```

Expected: failure because `mark_done()` does not accept commentary fields yet.

- [ ] **Step 3: Fold commentary columns into `mark_done()` and remove the follow-up DB write**

```python
# src/material_agent/adapters/state/processed_sqlite.py
def mark_done(
    self,
    file_path: str,
    total_score: float,
    star_rating: int,
    group_boosted: bool,
    scores: dict,
    metadata: dict,
    group_info: dict,
    scene: str = "other",
    scene_raw: str = "",
    decision: str | None = None,
    decision_reasons: list[str] | None = None,
    screening_prior: float | None = None,
    visible_breakdown: dict | None = None,
    policy_version: str | None = None,
    signals: list[dict] | None = None,
    commentary_group_issues: str = "",
    commentary_shooting: str = "",
    commentary_post: str = "",
):
    payload.update(
        {
            "commentary_group_issues": commentary_group_issues,
            "commentary_shooting": commentary_shooting,
            "commentary_post": commentary_post,
        }
    )
```

```python
# src/material_agent/app/review_runtime.py
commentary_issues, commentary_shooting = split_group_commentary_sections(
    group_commentary,
    output_language=output_language,
)
state.mark_done(
    file_path,
    total_score=total_score,
    star_rating=star,
    group_boosted=boosted,
    scores=scores,
    metadata=meta,
    group_info={"group_id": group_id, "group_rank": rank, "group_size": group_size},
    scene=scene,
    scene_raw=scene_raw,
    decision=decision,
    decision_reasons=decision_reasons,
    screening_prior=score_payload.get("screening_prior"),
    visible_breakdown=visible_breakdown,
    policy_version=score_payload.get("policy_version", "layered-v1"),
    signals=score_payload.get("signals", []),
    commentary_group_issues=commentary_issues,
    commentary_shooting=commentary_shooting,
    commentary_post=post_commentary,
)
```

- [ ] **Step 4: Re-run the focused persistence tests**

Run:

```bash
uv run pytest tests/test_state.py tests/test_main.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/material_agent/adapters/state/processed_sqlite.py \
  src/material_agent/app/review_runtime.py \
  tests/test_state.py \
  tests/test_main.py
git commit -m "fix(state): persist final commentary with done rows"
```

### Task 3: Stabilize compatibility shims under lazy imports

**Files:**
- Modify: `src/material_agent/core/scoring_engine.py`
- Modify: `src/material_agent/core/commentary.py`
- Test: `tests/test_runtime_architecture.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Tighten the shim regression test**

```python
# tests/test_runtime_architecture.py
import importlib
import sys

sys.modules.pop("material_agent.core.scoring_engine", None)
sys.modules.pop("material_agent.domain.scoring_engine", None)

core_module = importlib.import_module("material_agent.core.scoring_engine")
domain_module = importlib.import_module("material_agent.domain.scoring_engine")

assert core_module.ScoreBundle is domain_module.ScoreBundle
assert core_module.decode_raw is domain_module.decode_raw
```

- [ ] **Step 2: Run the shim and lazy-import tests**

Run:

```bash
uv run pytest \
  tests/test_runtime_architecture.py::test_core_modules_remain_compatibility_shims_for_domain_rules \
  tests/test_main.py::test_cli_main_import_does_not_eagerly_import_scoring_stack \
  -q
```

Expected: failure under the current shim implementation when the suite reloads modules in different orders.

- [ ] **Step 3: Replace eager star imports with lazy symbol forwarding**

```python
# src/material_agent/core/scoring_engine.py
from importlib import import_module

_MODULE = "material_agent.domain.scoring_engine"
__all__ = ["RawFrame", "ScoreBundle", "build_score_instructions", "build_xmp_instructions",
           "build_visible_breakdown_instructions", "compute_scores", "decode_raw"]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    return getattr(import_module(_MODULE), name)
```

```python
# src/material_agent/core/commentary.py
from importlib import import_module

_MODULE = "material_agent.domain.commentary"
__all__ = ["CommentaryGenerator", "build_photo_commentary_context",
           "format_group_commentary", "format_post_commentary",
           "rank_description", "split_group_commentary_sections"]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    return getattr(import_module(_MODULE), name)
```

- [ ] **Step 4: Re-run the shim tests**

Run:

```bash
uv run pytest tests/test_runtime_architecture.py tests/test_main.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/material_agent/core/scoring_engine.py \
  src/material_agent/core/commentary.py \
  tests/test_runtime_architecture.py \
  tests/test_main.py
git commit -m "fix(core): stabilize compatibility shims"
```

### Task 4: Remove `run` parser drift and keep CLI ownership in `shells`

**Files:**
- Modify: `src/material_agent/shells/cli/main.py`
- Modify: `src/material_agent/commands/scoring.py`
- Modify: `src/material_agent/commands/__init__.py`
- Modify: `src/material_agent/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Add a parser ownership regression test**

```python
# tests/test_main.py
from material_agent.shells.cli.main import build_parser

parser = build_parser()
run_parser = next(action for action in parser._subparsers._group_actions if action.dest == "command")

assert run_parser is not None
assert "--dry-run" in parser.format_help()
assert "--no-visual-merge" in parser.format_help()
```

- [ ] **Step 2: Run the CLI tests**

Run:

```bash
uv run pytest tests/test_main.py -q
```

Expected: current tests still pass, but this step gives a clean baseline before collapsing the duplicate parser helper.

- [ ] **Step 3: Make `commands.scoring.configure_run_parser()` a thin forwarder instead of a second definition**

```python
# src/material_agent/commands/scoring.py
def configure_run_parser(parser):
    from ..shells.cli.main import configure_run_parser as _configure_run_parser
    return _configure_run_parser(parser)
```

```python
# src/material_agent/commands/__init__.py
def configure_run_parser(*args, **kwargs):
    from ..shells.cli.main import configure_run_parser as _configure_run_parser
    return _configure_run_parser(*args, **kwargs)
```

```python
# src/material_agent/main.py
def configure_run_parser(*args, **kwargs):
    from .shells.cli.main import configure_run_parser as _configure_run_parser
    return _configure_run_parser(*args, **kwargs)
```

- [ ] **Step 4: Re-run the CLI tests**

Run:

```bash
uv run pytest tests/test_main.py -q
```

Expected: PASS, with only one parser definition remaining as the source of truth.

- [ ] **Step 5: Commit**

```bash
git add src/material_agent/shells/cli/main.py \
  src/material_agent/commands/scoring.py \
  src/material_agent/commands/__init__.py \
  src/material_agent/main.py \
  tests/test_main.py
git commit -m "refactor(cli): remove run parser drift"
```

### Task 5: Update pipeline docs to match the repaired behavior

**Files:**
- Modify: `docs/module-map.md`
- Modify: `docs/ai/modules/review-pipeline.md`

- [ ] **Step 1: Update the human-facing workflow description**

```markdown
## Execution `make run`

8. Write XMP sidecars.
9. Persist the final processed row, including commentary fields, in one DB write.
10. Mark the runtime job/session as `finished_with_errors` when any file failed but the batch continued.
```

- [ ] **Step 2: Update the AI module contract**

```markdown
## Invariants

- cross-run resume is driven by processed-state rows
- a processed row is only `done` after commentary fields are stored
- partial batch success must surface as `finished_with_errors`, not `finished`
```

- [ ] **Step 3: Run a docs smoke check**

Run:

```bash
uv run ruff check .
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/module-map.md docs/ai/modules/review-pipeline.md
git commit -m "docs(pipeline): document repaired runtime semantics"
```

### Final verification

**Files:**
- Modify: none
- Test: `tests/test_review_job.py`
- Test: `tests/test_app_services.py`
- Test: `tests/test_runtime_state.py`
- Test: `tests/test_state.py`
- Test: `tests/test_main.py`
- Test: `tests/test_runtime_architecture.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
uv run pytest \
  tests/test_review_job.py \
  tests/test_app_services.py \
  tests/test_runtime_state.py \
  tests/test_state.py \
  tests/test_main.py \
  tests/test_runtime_architecture.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run the full suite**

Run:

```bash
uv run pytest
```

Expected: PASS with the prior `tests/test_runtime_architecture.py` failure removed.

- [ ] **Step 3: Run lint**

Run:

```bash
uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 4: Commit the verification-only pass if needed**

```bash
git status --short
```

Expected: clean working tree.

## Self-review

1. **Spec coverage:** The plan covers the three concrete review findings from the architecture review: inaccurate batch completion status, processed-state half-done rows, and unstable compatibility shims. It also includes the lower-priority parser drift cleanup and docs sync.
2. **Placeholder scan:** No `TODO`, `TBD`, or “implement later” placeholders remain. Every task includes exact file paths, test commands, and concrete code snippets.
3. **Type consistency:** The plan consistently uses `finished_with_errors` for both `SessionStatus` and `JobStatus`, keeps `processed.status == "done"` as the cross-run completion gate, and keeps parser ownership in `shells/cli/main.py`.
