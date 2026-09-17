"""Sequence/selection regressions and experiment contract rejection checks."""

import importlib.util
import json
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image, ImageFilter
import pytest

SPEC = importlib.util.spec_from_file_location(
    "cooking_protocol", Path(__file__).parents[1] / "scripts/cooking_sequence_protocol.py"
)
protocol = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(protocol)


def brightness_records():
    image = Image.fromarray(
        np.random.default_rng(17).integers(0, 128, (128, 128), dtype=np.uint8)
    ).filter(ImageFilter.GaussianBlur(3))
    pixels = np.asarray(image)
    records = []
    for i, factor in enumerate([1, 4, 4.2, 4.4]):
        altered = Image.fromarray(np.clip(pixels.astype(float) * factor, 0, 255).astype("uint8"))
        records.append(
            {
                "id": str(i),
                "seconds": i * 2,
                "hashes": {"phash": imagehash.phash(altered)},
                "score": {"score_total": 8 - i * 2, "decision": "reject"},
                "actions": ["first" if i == 0 else "later"],
                "segments": [i],
            }
        )
    return records


def test_brightness_bridge_keeps_adjacent_chain_and_selects_once():
    records = brightness_records()
    hashes = [r["hashes"]["phash"] for r in records]
    assert all(a - b <= 10 for a, b in zip(hashes, hashes[1:]))
    assert hashes[0] - hashes[-1] > 10
    result = protocol.evaluate_sequence(
        records, {"time_gap_seconds": 10, "hash_threshold": 10}, "phash"
    )
    assert result["group_sizes"] == [4]
    assert result["chain_endpoint_exceedances"] == 1
    assert result["selection"] == {"0": "keep", "1": "reject", "2": "reject", "3": "reject"}
    assert result["lost_actions"] == ["later"]  # Labels measure loss, never split groups.
    assert all(x == "reject" for x in result["quality"].values())
    alone = protocol.evaluate_sequence(
        [records[0], records[-1]], {"time_gap_seconds": 10, "hash_threshold": 10}, "phash"
    )
    assert alone["group_sizes"] == [1, 1]
    assert set(alone["selection"].values()) == {"keep"}
    assert all("meta" not in r["score"] for r in records)  # No metadata leaks between runs.


def test_time_break_still_splits_a_hash_bridge():
    records = brightness_records()
    records[-1]["seconds"] = 20
    result = protocol.evaluate_sequence(
        records, {"time_gap_seconds": 10, "hash_threshold": 10}, "phash"
    )
    assert result["group_sizes"] == [3, 1]
    assert result["selection"]["3"] == "keep"


@pytest.fixture
def contract(tmp_path):
    inputs = {
        "frame_rate": 1,
        "sequences": [{"sequence": "v", "frame_count": 2, "samples": [{"frame": 0}, {"frame": 1}]}],
    }
    manifest = [{"sequence": "v"}]
    paths = {key: tmp_path / f"{key}.json" for key in ["inputs", "manifest", "config"]}
    for key, value in [("inputs", inputs), ("manifest", manifest), ("config", {})]:
        paths[key].write_text(json.dumps(value))
    plan = {
        "schema": "material-agent.cooking-sequence.v1",
        "videos": ["v"],
        "parameters": {
            "variants": ["phash", "equalized_phash", "dhash"],
            "preprocessing": {"preview_max": 1024, "jpeg_quality": 85, "hash_max": 256},
            "hash_threshold": 10,
            "time_gap_seconds": 10,
        },
        "sampling": {"step_seconds": 1, "through_second": 120, "max_frames_per_video": 121},
        "fingerprints": {k: protocol.fingerprint(p) for k, p in paths.items()},
    }
    return plan, inputs, manifest, paths


def test_valid_plan(contract):
    assert protocol.validate_plan(*contract)["hash_threshold"] == 10


@pytest.mark.parametrize("field", ["inputs", "manifest", "config"])
def test_input_drift_rejected(contract, field):
    contract[-1][field].write_text("changed")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        protocol.validate_plan(*contract)


def test_unsupported_variant_rejected(contract):
    contract[0]["parameters"]["variants"].append("unfrozen")
    with pytest.raises(ValueError, match="candidate list"):
        protocol.validate_plan(*contract)


def test_sampling_drift_rejected_even_if_digest_updated(contract):
    plan, inputs, _, paths = contract
    inputs["sequences"][0]["samples"] = [{"frame": 1}]
    paths["inputs"].write_text(json.dumps(inputs))
    plan["fingerprints"]["inputs"] = protocol.fingerprint(paths["inputs"])
    with pytest.raises(ValueError, match="sampling rule"):
        protocol.validate_plan(*contract)
