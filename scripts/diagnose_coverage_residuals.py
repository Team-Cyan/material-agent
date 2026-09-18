"""Read-only attribution of frozen coverage failures; does not propose decisions."""

import argparse
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image
from material_agent.domain.scoring_engine import decode_raw
from direct_coverage import Protocol, prepare, relation
from benchmark_direct_coverage import encode, synthetic


def moments(values):
    return {
        "mean": float(values.mean()),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
        "max": float(values.max()),
    }


def residual_diagnostics(a, b, p):
    source, target = prepare(a, p), prepare(b, p)
    captured = {}
    original = cv2.findHomography

    def capture(*args, **kwargs):
        result = original(*args, **kwargs)
        captured["transform"] = result[0]
        return result

    with patch.object(cv2, "findHomography", side_effect=capture):
        edge = relation(source, target, p)
    result = {"baseline": edge}
    if "transform" not in captured or captured["transform"] is None:
        return result
    transform = captured["transform"]
    x, y = source["gray"], target["gray"]
    shape = y.shape[::-1]
    support = cv2.warpPerspective(np.ones_like(x), transform, shape, flags=cv2.INTER_NEAREST)
    valid = cv2.erode(support, np.ones((5, 5), np.uint8)).astype(bool)
    warped = cv2.warpPerspective(x, transform, shape).astype(float)
    y = y.astype(float)
    qx, qy = np.percentile(warped[valid], [10, 90]), np.percentile(y[valid], [10, 90])
    gain = (qy[1] - qy[0]) / max(qx[1] - qx[0], 1.0)
    offset = np.median(y[valid]) - gain * np.median(warped[valid])
    aligned = np.clip(warped * gain + offset, 0, 255)
    residual = np.abs(aligned - y)
    result["affine_residual"] = moments(residual[valid])
    # Diagnostic edge stratification, not a content-classification threshold.
    gx = cv2.Sobel(y, cv2.CV_64F, 1, 0, ksize=3) / 8
    gy = cv2.Sobel(y, cv2.CV_64F, 0, 1, ksize=3) / 8
    grad = np.hypot(gx, gy)
    cut = np.percentile(grad[valid], 75)
    high = valid & (grad >= cut)
    flat = valid & (grad < cut)
    result["gradient_strata"] = {
        "top_quartile_mean": float(residual[high].mean()),
        "other_mean": float(residual[flat].mean()),
        "top_quartile_error_mass_fraction": float(
            residual[high].sum() / max(residual[valid].sum(), 1e-12)
        ),
    }
    result["blur_sensitivity"] = {
        str(sigma): moments(
            np.abs(cv2.GaussianBlur(aligned, (0, 0), sigma) - cv2.GaussianBlur(y, (0, 0), sigma))[
                valid
            ]
        )
        for sigma in [0.5, 1.0, 2.0]
    }
    # A distribution-only diagnostic can absorb true changes; it NEVER authorizes cover.
    qs = np.linspace(0, 100, 101)
    xx = np.percentile(warped[valid], qs)
    yy = np.percentile(y[valid], qs)
    unique, ix = np.unique(xx, return_index=True)
    nonlinear = np.interp(warped, unique, yy[ix])
    result["quantile_mapping_residual"] = moments(np.abs(nonlinear - y)[valid])
    result["local_evidence"] = {}
    for threshold in [6, 12, 24]:
        mask = ((residual > threshold) & valid).astype(np.uint8)
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        result["local_evidence"][str(threshold)] = {
            "pixels": int(mask.sum()),
            "largest_component": int(stats[1:, cv2.CC_STAT_AREA].max()) if n > 1 else 0,
        }
    # Report worst local region in normalized coordinates; no derived image file.
    yy0, xx0 = np.unravel_index(int(residual.argmax()), residual.shape)
    result["peak_residual_location_fraction"] = [
        float(xx0 / residual.shape[1]),
        float(yy0 / residual.shape[0]),
    ]
    result["transform"] = transform.tolist()
    return result


def image_array(decoded):
    return np.asarray(Image.open(io.BytesIO(decoded.jpeg_bytes)).convert("RGB"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output must be new")
    cv2.setNumThreads(1)
    p = Protocol()
    config = json.loads(
        Path("docs/operations/benchmarks/2026-09-17-hdrplus-holdout/config.json").read_text()
    )
    manifest = json.loads(
        Path("docs/operations/benchmarks/2026-09-18-direct-coverage/inputs.json").read_text()
    )
    results = {}
    source_hashes = {}
    for case in manifest["cases"]:
        if case["id"] not in ["fresh-hdr-1", "fresh-hdr-2", "exposure-bracket"]:
            continue
        root = Path(
            ".local/direct-coverage/holdout"
            if case["root"] == "holdout"
            else ".local/exposure-brackets"
        )
        items = sorted(case["frames"], key=lambda f: f["seconds"])[:2]
        arrays = []
        for item in items:
            path = root / item["file"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == item["sha256"]
            source_hashes[path] = digest
            arrays.append(image_array(decode_raw(str(path), config["preview"])))
        results[case["id"]] = residual_diagnostics(*arrays, p)
    for kind in ["identity", "exposure", "noise", "expression"]:
        a, b = synthetic(kind)
        results["synthetic-" + kind + "-arrays"] = residual_diagnostics(a, b, p)
        results["synthetic-" + kind + "-jpeg"] = residual_diagnostics(
            image_array(encode(a)), image_array(encode(b)), p
        )
    # Exact equal-luminance colors expose information discarded by grayscale.
    a, b = synthetic("identity")
    a[144:160, 144:160] = [200, 0, 0]
    b[144:160, 144:160] = [0, 102, 0]
    ga = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
    gb = cv2.cvtColor(b, cv2.COLOR_RGB2GRAY)
    results["isoluminant-color"] = {
        "gray_absolute_max": int(np.abs(ga.astype(int) - gb.astype(int)).max()),
        "rgb_absolute_max": int(np.abs(a.astype(int) - b.astype(int)).max()),
        "diagnostics": residual_diagnostics(a, b, p),
    }
    # Same tiny patch, progressively less observable at the original 512 cap.
    results["resolution-loss"] = []
    for side in [320, 640, 1280]:
        a = cv2.resize(synthetic("identity")[0], (side, side))
        b = a.copy()
        b[side // 2 : side // 2 + 4, side // 2 : side // 2 + 4] = 60
        aa = prepare(a, p)["gray"]
        bb = prepare(b, p)["gray"]
        diff = np.abs(aa.astype(float) - bb.astype(float))
        results["resolution-loss"].append(
            {
                "input_side": side,
                "prepared_shape": list(aa.shape),
                "nonzero_pixels": int((diff > 0).sum()),
                "maximum_difference": float(diff.max()),
                "sum_difference": float(diff.sum()),
            }
        )
    assert all(
        hashlib.sha256(path.read_bytes()).hexdigest() == digest
        for path, digest in source_hashes.items()
    )
    payload = {
        "schema": "material-agent.coverage-attribution.v1",
        "no_threshold_changes": True,
        "no_selection_changes": True,
        "sources_unchanged": True,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
