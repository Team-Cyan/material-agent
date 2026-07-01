# Playbook: Adjust XMP Output

Use this playbook when the task changes sidecar content, tag preservation behavior, or rewrite flow behavior.

## Read First

- `docs/ai/modules/xmp-writer.md`
- `docs/ai/architecture/module-boundaries.md`
- `src/material_agent/adapters/metadata/exiftool_xmp.py`
- `src/material_agent/app/rewrite_xmp_service.py`

## Typical Scope

- add or change `pj:*` tags
- preserve more user-authored metadata
- change description or instruction formatting
- adjust rewrite behavior from database rows

## When Not To Use

- when the change is actually about ranking or scoring policy
- when the task is only about persistence and no sidecar output changes are required
- when the request is really about commentary generation quality rather than sidecar rendering

## Usual Files

- `src/material_agent/adapters/metadata/exiftool_xmp.py`
- `src/material_agent/app/rewrite_xmp_service.py`
- possibly `src/material_agent/app/review_runtime.py` when upstream assembly changes
- `tests/test_writer.py`

## Checklist

1. Decide whether the change affects:
   - existing XMP update path
   - new XMP creation path
   - rewrite path
2. Preserve non-machine user tags unless the task explicitly says otherwise.
3. Keep generated `pj:*` tags deterministic.
4. If changing text assembly, verify both normal review runs and rewrite flows still agree.
5. Be careful with private helper usage between writer and rewrite service.
6. Keep `dc:description` as `x-default` language alternative and avoid adding Adobe-only XML shortcuts to the new-sidecar path.
7. Prefer explicit ExifTool namespace writes for standard fields such as `XMP-photoshop:Instructions` and `XMP-dc:Description-x-default`.

## Acceptance Checks

- `pytest tests/test_writer.py`
- if processed-state rows are involved: `pytest tests/test_state.py`

## Common Failure Modes

- fixing one write path but forgetting the other
- dropping user keywords during regeneration
- changing description formatting without checking rewrite output
- treating Photomator/Resolve support as proven without a real software matrix run
