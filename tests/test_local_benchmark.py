import json
from pathlib import Path

import pytest
import yaml
from PIL import Image
from types import SimpleNamespace

from material_agent.app.local_benchmark_service import (
    SCHEMA_VERSION,
    load_benchmark_manifest,
    run_local_benchmark,
)
from material_agent.shells.cli.main import build_parser


def _write_image(path: Path, value: int, *, pattern: bool = False) -> None:
    image = Image.new("RGB", (32, 32), (value, value, value))
    if pattern:
        pixels = image.load()
        for y in range(32):
            for x in range(32):
                if (x + y) % 2:
                    pixels[x, y] = (min(255, value + 80), max(0, value - 40), value)
    image.save(path, format="JPEG", quality=95)


def _write_manifest(tmp_path: Path) -> Path:
    _write_image(tmp_path / "best.jpg", 120, pattern=True)
    _write_image(tmp_path / "soft.jpg", 110)
    _write_image(tmp_path / "screen.jpg", 250)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "name": "synthetic-baseline",
        "version": 1,
        "items": [
            {
                "id": "best",
                "path": "best.jpg",
                "group": "burst",
                "labels": {"scene": "other", "face_present": True, "reject": False},
            },
            {
                "id": "soft",
                "path": "soft.jpg",
                "group": "burst",
                "labels": {"scene": "other", "face_present": True, "reject": True},
            },
            {
                "id": "screen",
                "path": "screen.jpg",
                "group": "non-photo",
                "labels": {
                    "scene": "other",
                    "face_present": False,
                    "non_photo": True,
                    "reject": True,
                },
            },
        ],
        "preferred_by_group": {"burst": "best"},
        "pairwise_preferences": [
            {"preferred": "best", "other": "soft"},
            {"preferred": "soft", "other": "screen"},
        ],
    }
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return path


def test_load_benchmark_manifest_resolves_images(tmp_path):
    manifest_path = _write_manifest(tmp_path)

    payload, items = load_benchmark_manifest(manifest_path)

    assert payload["name"] == "synthetic-baseline"
    assert [item.item_id for item in items] == ["best", "soft", "screen"]
    assert all(item.path.is_absolute() for item in items)


def test_manifest_rejects_invalid_pairwise_reference(tmp_path):
    manifest_path = _write_manifest(tmp_path)
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["pairwise_preferences"][0]["other"] = "missing"
    manifest_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid item ids"):
        load_benchmark_manifest(manifest_path)


def test_run_local_benchmark_is_isolated_and_reproducible(tmp_path):
    manifest_path = _write_manifest(tmp_path)
    output_dir = tmp_path / "reports"

    json_path, markdown_path, report = run_local_benchmark(
        manifest_path,
        output_dir,
        repeat_count=2,
    )

    assert json_path.is_file()
    assert markdown_path.is_file()
    assert report["metrics"]["deterministic_scores"] is True
    assert report["metrics"]["cold_run_seconds"] >= 0
    assert report["metrics"]["warm_p50_run_seconds"] >= 0
    assert report["metrics"]["item_count"] == 3
    assert report["metrics"]["face_positive_count"] == 2
    assert report["metrics"]["scene_other_rate"]["rate"] == 1.0
    assert report["metrics"]["quality_pairwise_preference"] is None
    assert report["metrics"]["reject_prior_recall"] is None
    assert report["runtime"]["scoring_mode"] == "heuristic"
    assert report["items"][0]["path"] == "best.jpg"
    assert not Path(report["items"][0]["path"]).is_absolute()
    assert not (tmp_path / ".material-agent").exists()
    persisted = json.loads(json_path.read_text(encoding="utf-8"))
    assert persisted["manifest"]["sha256"] == report["manifest"]["sha256"]
    assert persisted["manifest"]["path"] == str(manifest_path)
    assert "Local Heuristic Benchmark Report" in markdown_path.read_text(encoding="utf-8")


def test_cli_exposes_benchmark_local_command():
    parser = build_parser()

    args = parser.parse_args(
        [
            "benchmark-local",
            "--manifest",
            "fixtures.yaml",
            "--output-dir",
            "reports",
        ]
    )

    assert args.command == "benchmark-local"
    assert args.repeat_count == 2
    assert args.config is None
    assert args.quality_reject_threshold == 5.0


def test_run_local_benchmark_decodes_raw_preview(monkeypatch, tmp_path):
    raster = tmp_path / "source.jpg"
    _write_image(raster, 120, pattern=True)
    raw = tmp_path / "source.arw"
    raw.write_bytes(b"raw-placeholder")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "name": "raw-preview",
        "version": 1,
        "items": [{"id": "raw", "path": "source.arw", "group": "single"}],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    jpeg_bytes = raster.read_bytes()

    def fake_decode(path, preview):
        assert path == str(raw)
        assert preview["prefer_embedded"] is True
        return SimpleNamespace(
            jpeg_bytes=jpeg_bytes,
            preview_source="embedded",
            original_size=(7168, 5120),
            preview_size=(1024, 731),
            focus_assessment="preview_proxy",
        )

    monkeypatch.setattr("material_agent.app.local_benchmark_service.decode_raw", fake_decode)
    _, _, report = run_local_benchmark(manifest_path, tmp_path / "reports", repeat_count=1)

    assert report["items"][0]["input_decode"] == {
        "format": "raw_preview",
        "source": "embedded",
        "original_size": [7168, 5120],
        "preview_size": [1024, 731],
        "focus_assessment": "preview_proxy",
    }
