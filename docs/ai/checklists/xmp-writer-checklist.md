# Checklist: XMP Writer Changes

Use this checklist before finalizing a change in sidecar writing or rewrite behavior.

## Scope Check

- Is the change about sidecar output, tag preservation, or rewrite behavior?
- Did it stay mostly inside the writer or rewrite service?

## Behavior Check

- Are non-machine user keywords still preserved?
- Do existing-file update and new-file creation paths still produce aligned output?
- If text formatting changed, do normal review runs and rewrite runs still agree?
- Are generated `pj:*` tags deterministic for the same payload?
- Does `dc:description` stay an `x-default` language alternative for both new and existing sidecars?
- Do new sidecars include creator/lifecycle metadata (`CreatorTool`, `MetadataDate`, `ModifyDate`, `DocumentID`, `InstanceID`)?
- Do existing sidecar updates use explicit namespaces for `photoshop:Instructions` and `dc:Description-x-default`?

## Contract Check

- Did the change avoid leaking more writer internals into rewrite code?
- If a new tag was added, is it safe for downstream consumers and human readers?
- If a new compatibility field was added, is the preservation/update policy explicit?

## Verification Check

- Run `pytest tests/test_writer.py`
- If processed rows are involved, also run `pytest tests/test_state.py`

## Docs Check

- Update `docs/ai/modules/xmp-writer.md` if writer boundaries or risks changed
- Update the XMP playbook if this becomes a repeated pattern
