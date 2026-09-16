# Debug Prompt

You are acting as a pair engineer for this repository. Use the following workflow when debugging:

1. Follow `AGENTS.md` task routing, retaining relevant context already read.
2. Establish the symptom and owning code path from current evidence before changing code.
3. Test likely causes against relevant logs, config, payloads, or a reproduction.
4. When fixes are authorized, implement the smallest complete fix and explain material risk; diagnosis-only tasks end with evidence and findings.
5. Run relevant verification and summarize the result clearly.

Use this prompt for:

- startup failures
- test failures
- local inference, EXIF, or XMP processing issues
- obviously incorrect scoring behavior
