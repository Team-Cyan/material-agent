"""Combine immutable original and supplemental panels without relabeling."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from assess_spatial_reference import assess, validate_panel


def renumber(rows, panel):
    result = copy.deepcopy(rows)
    for i, row in enumerate(result):
        mapping = {
            old: f"{panel}{i + 1:02}{side}" for old, side in zip(row["ids"], "LR", strict=True)
        }
        row["ids"] = [mapping[old] for old in row["ids"]]
        for relation in row["directed_relations"]:
            for key in ("source", "target"):
                relation[key] = mapping[relation[key]]
    return result


def combined(original, supplement):
    def read(root, name):
        return json.loads((root / name).read_text())

    oi, si = read(original, "inputs.json"), read(supplement, "inputs.json")
    oa, ob = read(original, "panel-a.json"), read(original, "panel-b.json")
    sa, sb = read(supplement, "panel-a.json"), read(supplement, "panel-b.json")
    for rows, panel, count in [
        (oa, "A", len(oi["pairs"])),
        (ob, "B", len(oi["pairs"])),
        (sa, "A", len(si["pairs"])),
        (sb, "B", len(si["pairs"])),
    ]:
        validate_panel(rows, panel, count)
    # B is globally reverse ordered, with each pair's left/right already reversed.
    result = assess(
        {"pairs": oi["pairs"] + si["pairs"]}, renumber(oa + sa, "A"), renumber(sb + ob, "B")
    )
    result["provenance"] = (
        "Original labels unchanged; neutral IDs only remapped in memory. A=original+supplement; B=supplement+original; each B set is reverse ordered. U01 excluded."
    )
    result["fingerprints"] = {
        f"{label}/{name}": hashlib.sha256((root / name).read_bytes()).hexdigest()
        for label, root in [("original", original), ("supplement", supplement)]
        for name in ["inputs.json", "panel-a.json", "panel-b.json"]
    }
    for path in [Path(__file__), Path(__file__).with_name("assess_spatial_reference.py")]:
        result["fingerprints"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output must be new")
    base = Path("docs/operations/benchmarks")
    result = combined(base / "2026-09-19-spatial-reference", base / "2026-09-19-spatial-supplement")
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result["summary"]))
