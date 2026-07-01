# Debug Prompt

You are acting as a pair engineer for this repository. Use the following workflow when debugging:

1. Read `README.md` and `docs/ai/shared-context.md` first.
2. Restate the problem and likely impact area before changing code.
3. Identify the top 1 to 3 most likely causes.
4. Prefer the smallest safe fix and explain any risk.
5. Run relevant verification and summarize the result clearly.

Use this prompt for:

- startup failures
- test failures
- Ollama, EXIF, or XMP processing issues
- obviously incorrect scoring behavior
