"""Frozen synthetic-only 2x2 geometry/representation wiring check; never production."""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import sys
import tempfile
import time
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = Path(__file__).with_name("direct_coverage.py")
OBSERVABILITY = Path(__file__).with_name("benchmark_coverage_observability.py")
HISTORICAL_PLAN = ROOT / "docs/operations/benchmarks/2026-09-19-coverage-observability/plan.json"
ACCEPTED_ARMS = ("gray", "rgb_local")


def load_historical(name, path):
    existing = sys.modules.get(name)
    if existing is not None:
        if Path(existing.__file__).resolve() != path.resolve():
            raise RuntimeError(f"historical module resolved from unexpected path: {name}")
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


direct = load_historical("direct_coverage", HISTORICAL)
observability = load_historical("benchmark_coverage_observability", OBSERVABILITY)
Protocol, prepare, relation, select = (
    direct.Protocol,
    direct.prepare,
    direct.relation,
    direct.select,
)
controls = observability.controls


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha_file(path):
    return sha_bytes(path.read_bytes())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fingerprint(value):
    return sha_bytes(canonical(value))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=".representation-", suffix=".tmp", delete=False
    ) as stream:
        temp = Path(stream.name)
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def load_protocol(path):
    plan = json.loads(path.read_text())
    if (
        plan["schema"] != "material-agent.representation-control.v1"
        or not plan["frozen_before_execution"]
    ):
        raise ValueError("not a frozen representation-control protocol")
    if plan["geometry_max_sides"] != [512, 1024] or plan["residual_max_side"] != 512:
        raise ValueError("unexpected resolution matrix")
    if plan["baseline_geometry_max_side"] != 512 or len(plan["cases"]) != 4:
        raise ValueError("unsupported baseline/case count")
    expected_cases = [
        {"id": "identity", "seed": 2049, "side": 1280, "kind": "identity"},
        {"id": "jpeg", "seed": 2049, "side": 1280, "kind": "jpeg"},
        {"id": "small-luminance", "seed": 2049, "side": 1280, "kind": "small_luminance"},
        {"id": "isoluminant-color", "seed": 2049, "side": 1280, "kind": "isoluminant_color"},
    ]
    if plan["cases"] != expected_cases:
        raise ValueError("candidate case IDs, kinds or order differ from frozen list")
    historical = json.loads(HISTORICAL_PLAN.read_text())
    old = historical["protocol"]
    if plan["rgb_local_parameters"] != {key: old[key] for key in plan["rgb_local_parameters"]}:
        raise ValueError("RGB parameters differ from historical frozen plan")
    # The old development plan also contains case metadata; compare only the frozen recipe.
    if any(
        plan["synthetic_preprocess"][key] != historical["development"][key]
        for key in plan["synthetic_preprocess"]
    ):
        raise ValueError("synthetic preview recipe differs from historical plan")
    limits = plan.get("limits")
    bounds = {
        "maximum_cases": (int, 4),
        "maximum_case_seconds_observed": ((int, float), 90),
        "process_rss_limit_bytes_observed": (int, 2_000_000_000),
    }
    if not isinstance(limits, dict) or set(limits) != set(bounds):
        raise ValueError("unexpected resource limit fields")
    for key, (kind, maximum) in bounds.items():
        value = limits[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, kind)
            or not 0 < value <= maximum
            or not math.isfinite(value)
        ):
            raise ValueError(f"invalid resource limit: {key}")
    if limits["maximum_cases"] < len(plan["cases"]):
        raise ValueError("case budget exceeded")
    if plan["quality_inputs"] != {
        "A": {"total": 1.0, "sharpness": 1.0, "exposure": 1.0},
        "B": {"total": 1.0, "sharpness": 1.0, "exposure": 1.0},
    }:
        raise ValueError("quality fixture changed")
    return plan


def preview(rgb, max_side):
    image = Image.fromarray(rgb).convert("RGB")
    image.thumbnail((max_side, max_side))
    return np.asarray(image)


def capture_geometry(a, b, max_side):
    """Run historical prepare/relation once, sharing its gate and H across both arms."""
    protocol = Protocol(max_side=max_side)
    features = (prepare(a, protocol), prepare(b, protocol))
    captured = {}
    original = cv2.findHomography

    def intercept(*args, **kwargs):
        answer = original(*args, **kwargs)
        captured["H"] = answer[0]
        return answer

    with patch.object(cv2, "findHomography", side_effect=intercept):
        baseline = relation(*features, protocol)
    geometry = {
        "max_side": max_side,
        "source_hw": list(features[0]["gray"].shape),
        "target_hw": list(features[1]["gray"].shape),
        "feature_sha256": [
            fingerprint(
                {
                    "points": sha_bytes(f["points"].tobytes()),
                    "descriptors": None
                    if f["descriptors"] is None
                    else sha_bytes(f["descriptors"].tobytes()),
                    "observable": f["observable"],
                }
            )
            for f in features
        ],
        "common_gate": {"relation": baseline["relation"], "reason": baseline["reason"]},
        "homography": None if captured.get("H") is None else captured["H"].tolist(),
    }
    return protocol, baseline, geometry, fingerprint(geometry)


def map_homography(
    H, source_geometry_hw, target_geometry_hw, source_residual_hw, target_residual_hw
):
    """Convert source-residual pixels to target-residual pixels using both actual shapes."""
    sy, sx = (
        source_residual_hw[0] / source_geometry_hw[0],
        source_residual_hw[1] / source_geometry_hw[1],
    )
    ty, tx = (
        target_residual_hw[0] / target_geometry_hw[0],
        target_residual_hw[1] / target_geometry_hw[1],
    )
    # Pillow's pixel-center resize: x_res = scale * (x_geom + 0.5) - 0.5.
    # Source and target use their own actual width and height ratios.
    source = np.array([[sx, 0.0, (sx - 1) / 2], [0.0, sy, (sy - 1) / 2], [0.0, 0.0, 1.0]])
    target = np.array([[tx, 0.0, (tx - 1) / 2], [0.0, ty, (ty - 1) / 2], [0.0, 0.0, 1.0]])
    return target @ np.asarray(H, dtype=np.float64) @ np.linalg.inv(source)


def common_residual_support(a_gray, b_gray, H, protocol):
    shape = b_gray.shape
    warped = cv2.warpPerspective(a_gray, H, shape[1::-1])
    support = cv2.warpPerspective(np.ones_like(a_gray), H, shape[1::-1], flags=cv2.INTER_NEAREST)
    valid = cv2.erode(support, np.ones((5, 5), np.uint8)).astype(bool)
    overlap = float(valid.mean())
    if overlap < 0.4:
        return None, {"relation": "different", "reason": "target_view_not_covered"}
    if overlap < protocol.min_overlap:
        return None, {"relation": "unknown", "reason": "occlusion_crop_or_parallax"}
    x, y = warped[valid].astype(float), b_gray[valid].astype(float)
    xs, ys = np.percentile(x, [10, 90]), np.percentile(y, [10, 90])
    if xs[1] - xs[0] < protocol.min_dynamic_range:
        return None, {"relation": "unknown", "reason": "unobservable_registered_region"}
    gain = float((ys[1] - ys[0]) / (xs[1] - xs[0]))
    offset = float(np.median(y) - gain * np.median(x))
    if not 0.2 <= gain <= 5:
        return None, {"relation": "unknown", "reason": "extreme_photometric_mapping"}
    return {
        "warped_gray": warped,
        "valid": valid,
        "gain": gain,
        "offset": offset,
        "overlap": overlap,
    }, None


def gray_residual(shared, target_gray, protocol):
    warped, valid = shared["warped_gray"], shared["valid"]
    residual = np.abs(
        np.clip(warped.astype(float) * shared["gain"] + shared["offset"], 0, 255) - target_gray
    )
    values = residual[valid]
    tiles = []
    for ys0 in np.array_split(np.arange(target_gray.shape[0]), protocol.tile_grid):
        for xs0 in np.array_split(np.arange(target_gray.shape[1]), protocol.tile_grid):
            v = valid[np.ix_(ys0, xs0)]
            tile = residual[np.ix_(ys0, xs0)]
            if v.size and v.mean() >= 0.9:
                tiles.append(float(tile[v].mean()))
    if not tiles:
        return {"relation": "unknown", "reason": "insufficient_residual_support"}
    mean, p95, maximum = float(values.mean()), float(np.percentile(values, 95)), max(tiles)
    relation_value = (
        "cover"
        if (
            mean <= protocol.mean_residual
            and p95 <= protocol.p95_residual
            and maximum <= protocol.tile_residual
        )
        else "unknown"
    )
    return {
        "relation": relation_value,
        "reason": "geometry_and_photometric_consistency"
        if relation_value == "cover"
        else "unexplained_local_change",
        "evidence": {"residual_mean": mean, "residual_p95": p95, "maximum_tile_residual": maximum},
    }


def rgb_local_residual(a_rgb, b_rgb, H, valid, params):
    # Frozen from benchmark_coverage_observability.evaluate_relation, with H and valid supplied.
    x, y = a_rgb.astype(float), b_rgb.astype(float)
    warped = cv2.warpPerspective(x, H, y.shape[1::-1])
    gray_x = cv2.cvtColor(warped.astype(np.float32), cv2.COLOR_RGB2GRAY)
    gray_y = cv2.cvtColor(y.astype(np.float32), cv2.COLOR_RGB2GRAY)
    xx, yy = np.percentile(gray_x[valid], [10, 90]), np.percentile(gray_y[valid], [10, 90])
    gain = (yy[1] - yy[0]) / max(xx[1] - xx[0], 1.0)
    offset = np.median(y[valid], axis=0) - gain * np.median(warped[valid], axis=0)
    corrected = np.clip(warped * gain + offset, 0, 255)
    signed = corrected - y
    centered = signed[valid] - np.median(signed[valid], axis=0)
    mad = 1.4826 * np.median(np.abs(centered), axis=0)
    threshold = np.maximum(params["local_absolute_floor"], params["local_mad_multiplier"] * mad)
    changed = (np.any(np.abs(signed) > threshold, axis=2) & valid).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(changed, 8)
    largest = int(stats[1:, cv2.CC_STAT_AREA].max()) if n > 1 else 0
    smoothed = np.max(
        np.abs(
            cv2.GaussianBlur(corrected, (0, 0), params["smoothing_sigma"])
            - cv2.GaussianBlur(y, (0, 0), params["smoothing_sigma"])
        ),
        axis=2,
    )
    mean, p95 = float(smoothed[valid].mean()), float(np.percentile(smoothed[valid], 95))
    is_change = largest >= params["connected_component_minimum_pixels"]
    is_global = mean > params["global_mean_limit"] or p95 > params["global_p95_limit"]
    return {
        "relation": "unknown" if is_change or is_global else "cover",
        "reason": "localized_unexplained_color_or_luminance"
        if is_change
        else "global_unexplained_residual"
        if is_global
        else "bounded_residual_hypothesis",
        "evidence": {
            "noise_mad_rgb": mad.tolist(),
            "local_threshold_rgb": threshold.tolist(),
            "changed_pixels": int(changed.sum()),
            "largest_component": largest,
            "smoothed_mean": mean,
            "smoothed_p95": p95,
            "gain": float(gain),
        },
    }


def evaluate_pair(a, b, geometry_side, residual_side, rgb_params, quality):
    started = time.perf_counter()
    protocol, baseline, geometry, geometry_sha = capture_geometry(a, b, geometry_side)
    a_rgb, b_rgb = preview(a, residual_side), preview(b, residual_side)
    residual_hw = [list(a_rgb.shape[:2]), list(b_rgb.shape[:2])]
    gate_reason = geometry["common_gate"]["reason"]
    H = geometry["homography"]
    mapped = None
    if H is not None:
        mapped = map_homography(H, geometry["source_hw"], geometry["target_hw"], *residual_hw)
    if (
        gate_reason not in ("geometry_and_photometric_consistency", "unexplained_local_change")
        or mapped is None
    ):
        shared_gate = {"relation": baseline["relation"], "reason": gate_reason}
        shared = None
    else:
        a_gray = cv2.cvtColor(a_rgb, cv2.COLOR_RGB2GRAY)
        b_gray = cv2.cvtColor(b_rgb, cv2.COLOR_RGB2GRAY)
        shared, shared_gate = common_residual_support(a_gray, b_gray, mapped, protocol)
    arms = {}
    for arm in ACCEPTED_ARMS:
        if shared_gate is not None:
            result = {**shared_gate, "evidence": {}}
        elif arm == "gray":
            result = gray_residual(shared, b_gray, protocol)
        else:
            result = rgb_local_residual(a_rgb, b_rgb, mapped, shared["valid"], rgb_params)
        edges = {("A", "B"): {"relation": result["relation"]}}
        frames = [{"id": side, "quality": quality[side]} for side in ("A", "B")]
        arms[arm] = {
            **result,
            "geometry_artifact_sha256": geometry_sha,
            "residual_hw": residual_hw,
            "decisions": select(frames, edges, protocol),
        }
    if geometry_side == 512 and (arms["gray"]["relation"], arms["gray"]["reason"]) != (
        baseline["relation"],
        baseline["reason"],
    ):
        raise ValueError("512-gray historical relation parity failed")
    return {
        "geometry": geometry,
        "geometry_artifact_sha256": geometry_sha,
        "mapped_homography": None if mapped is None else mapped.tolist(),
        "baseline_at_geometry": {
            "relation": baseline["relation"],
            "reason": baseline["reason"],
            "residual_evidence": {
                key: baseline["evidence"][key]
                for key in ("residual_mean", "residual_p95", "maximum_tile_residual")
                if key in baseline["evidence"]
            },
        },
        "arms": arms,
        "elapsed_seconds": time.perf_counter() - started,
        "parity_512_gray": None
        if geometry_side != 512
        else (arms["gray"]["relation"], arms["gray"]["reason"])
        == (baseline["relation"], baseline["reason"]),
    }


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value * (1 if sys.platform == "darwin" else 1024))


def identity(protocol_path):
    return {
        "protocol_sha256": sha_file(protocol_path),
        "runner_sha256": sha_file(Path(__file__)),
        "direct_coverage_sha256": sha_file(HISTORICAL),
        "observability_sha256": sha_file(OBSERVABILITY),
        "historical_plan_sha256": sha_file(HISTORICAL_PLAN),
        "runtime": {
            "python": sys.version.split()[0],
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "pillow": Image.__version__,
            "imagehash": importlib.metadata.version("ImageHash"),
        },
    }


def seal(value):
    return {**value, "record_sha256": fingerprint(value)}


def semantic_digest(row):
    matrix = {
        side: {key: value for key, value in result.items() if key != "elapsed_seconds"}
        for side, result in row["geometry_resolutions"].items()
    }
    return fingerprint(
        {key: row[key] for key in ("identity", "input_sha256", "case")}
        | {"geometry_resolutions": matrix}
    )


def verified_record(path, expected):
    row = json.loads(path.read_text())
    check = dict(row)
    claimed = check.pop("record_sha256", None)
    if (
        claimed != fingerprint(check)
        or row.get("identity") != expected["identity"]
        or row.get("input_sha256") != expected["input_sha256"]
        or row.get("case") != expected["case"]
        or row.get("semantic_sha256") != semantic_digest(row)
    ):
        raise ValueError(f"stale or corrupted case result: {path.name}")
    return row


def run(protocol_path, output_dir, resume=False, verify_only=False):
    protocol_path = protocol_path.resolve()
    output_dir = output_dir.resolve()
    if protocol_path.is_relative_to(output_dir):
        raise ValueError("protocol must be outside the output directory")
    if not output_dir.is_relative_to(ROOT / ".local") or not output_dir.name.startswith(
        "representation-control-"
    ):
        raise ValueError("output must be a fresh .local/representation-control-* directory")
    plan = load_protocol(protocol_path)
    run_id = identity(protocol_path)
    cv2.setNumThreads(1)
    if verify_only and not resume:
        raise ValueError("--verify-only requires --resume")
    if not output_dir.exists():
        if resume:
            raise ValueError("resume directory does not exist")
        output_dir.mkdir(parents=True)
    elif not resume and any(output_dir.iterdir()):
        raise ValueError("output directory is not new/empty; use --resume for verified records")
    rows, computed, reused = [], 0, 0
    for case in plan["cases"]:
        a, b = controls(case["seed"], case["side"], case["kind"], plan["synthetic_preprocess"])
        input_sha = [sha_bytes(array.tobytes()) for array in (a, b)]
        expected = {"identity": run_id, "input_sha256": input_sha, "case": case}
        path = output_dir / f"{case['id']}.json"
        if path.exists():
            if not resume:
                raise ValueError(f"refusing to overwrite {path.name}")
            row = verified_record(path, expected)
            reused += 1
        else:
            if verify_only:
                raise ValueError(f"missing case result: {path.name}")
            started = time.perf_counter()
            matrix = {
                str(side): evaluate_pair(
                    a,
                    b,
                    side,
                    plan["residual_max_side"],
                    plan["rgb_local_parameters"],
                    plan["quality_inputs"],
                )
                for side in plan["geometry_max_sides"]
            }
            elapsed = time.perf_counter() - started
            peak = peak_rss_bytes()
            limit = plan["limits"]
            value = {
                **expected,
                "case": case,
                "geometry_resolutions": matrix,
                "case_seconds": elapsed,
                "process_peak_rss_bytes_observed": peak,
                "resource_overrun_observed": elapsed > limit["maximum_case_seconds_observed"]
                or peak > limit["process_rss_limit_bytes_observed"],
                "human_label_status": "none; construction-only synthetic control",
            }
            row = seal({**value, "semantic_sha256": semantic_digest(value)})
            atomic_json(path, row)
            computed += 1
        if row["resource_overrun_observed"]:
            raise ValueError(f"observed resource bound exceeded in {case['id']}; case saved, stop")
        rows.append(row)
    summary_data = {
        "schema": plan["schema"],
        "identity": run_id,
        "case_digests": {r["case"]["id"]: r["record_sha256"] for r in rows},
        "case_semantic_digests": {r["case"]["id"]: r["semantic_sha256"] for r in rows},
        "cases": len(rows),
        "matrix_arms": len(rows) * 4,
        "all_512_gray_parity": all(
            r["geometry_resolutions"]["512"]["parity_512_gray"] for r in rows
        ),
        "all_arm_geometry_shared": all(
            all(
                part["arms"]["gray"]["geometry_artifact_sha256"]
                == part["arms"]["rgb_local"]["geometry_artifact_sha256"]
                for part in r["geometry_resolutions"].values()
            )
            for r in rows
        ),
        "resource_overruns_observed": sum(r["resource_overrun_observed"] for r in rows),
        "quality_gate": "not_applicable_synthetic_only",
    }
    summary_path = output_dir / "summary.json"
    if verify_only:
        if not summary_path.exists() or json.loads(summary_path.read_text()) != summary_data:
            raise ValueError("stale or missing summary")
    else:
        atomic_json(summary_path, summary_data)
    return {**summary_data, "computed": computed, "reused": reused, "output_dir": str(output_dir)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.protocol, args.output_dir, args.resume, args.verify_only), indent=2))


if __name__ == "__main__":
    main()
