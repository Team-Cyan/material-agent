# Synthetic Local Benchmark Fixtures

These four images are synthetic assets created with OpenAI's built-in image
generation tool for `material-agent` scoring regression tests on 2026-07-11.
They do not depict a known real person and contain no private source photos.

The set covers:

- a sharp face-positive portrait;
- the same subject and composition with strong global motion blur;
- a severely underexposed indoor scene;
- a generic non-photo software UI screenshot.

The labels in `manifest.yaml` were manually reviewed for the narrow benchmark
properties above. They are not a claim that this small synthetic set represents
production photography. Real-camera RAW and broader scene coverage remain
required for production promotion.

Do not silently replace these images. Increment the manifest version and record
new provenance when the fixture content or labels change.
