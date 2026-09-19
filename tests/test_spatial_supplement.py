"""Joint assessment preserves original judgments and reversed panel alignment."""

import copy
import importlib
import json
from pathlib import Path

from tests.test_spatial_reference import row


def test_joint_alignment_and_original_immutability(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    module = importlib.import_module("assess_spatial_supplement")
    old, new = tmp_path / "old", tmp_path / "new"
    snapshots = {}
    for root, categories in [(old, ["object", "gesture"]), (new, ["water", "illumination"])]:
        root.mkdir()
        a = [row("A", i + 1, category=c) for i, c in enumerate(categories)]
        b = [row("B", i + 1, category=c) for i, c in enumerate(reversed(categories))]
        for item in b:
            r = item["regions"][0]
            r["left_box"], r["right_box"] = r["right_box"], r["left_box"]
        inputs = {
            "pairs": [
                {"pair_id": f"{root.name}{i}", "scene_id": f"{root.name}{i}"} for i in range(2)
            ]
        }
        for name, value in [("inputs.json", inputs), ("panel-a.json", a), ("panel-b.json", b)]:
            path = root / name
            path.write_text(json.dumps(value))
            snapshots[path] = path.read_bytes()
    result = module.combined(old, new)
    assert [p["agreed_regions"][0]["category"] for p in result["pairs"]] == [
        "object",
        "gesture",
        "water",
        "illumination",
    ]
    assert all(p.read_bytes() == before for p, before in snapshots.items())
    sample = [row("A")]
    before = copy.deepcopy(sample)
    assert module.renumber(sample + sample, "A")[1]["ids"] == ["A02L", "A02R"]
    assert sample == before
