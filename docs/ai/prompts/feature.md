# Feature Prompt

You are implementing a new feature in `material-agent`. Follow this workflow:

1. Read `README.md` and `docs/ai/shared-context.md` first.
2. Summarize the requirement, impacted modules, and implementation plan.
3. Preserve the current architecture style and avoid unrelated refactors.
4. If the change affects CLI, config, database schema, or XMP output, check whether docs and tests need updates.
5. Finish with a short summary of changes, verification, and any follow-up suggestions.

Use this prompt for:

- adding a new scoring dimension
- adding a new command
- adjusting config behavior
- improving export or write-back logic
