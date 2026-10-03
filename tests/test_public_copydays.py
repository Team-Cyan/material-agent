"""Frozen correspondence, portability and recovery checks without native inference."""

import importlib.util
import json
import os
from pathlib import Path
import socket

import pytest


SPEC = importlib.util.spec_from_file_location(
    "copydays_runner", Path(__file__).parents[1] / "scripts/benchmark_public_copydays.py"
)
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)


def native(vector=(1.0, 0.0)):
    return {
        "vector": list(vector),
        "dimensions": len(vector),
        "runtime": "openvino",
        "device": "CPU",
        "requested_device": "CPU",
        "compiled_device": "CPU",
        "fallback_device": "",
        "fallback_used": False,
        "fallback_reason": None,
        "execution_devices": ["CPU"],
        "execution_device_readback": "actual",
        "performance_hint": "THROUGHPUT",
        "batch_size_requested": 1,
        "batch_size_actual": 1,
        "batch_fallback_used": False,
        "infer_requests": 1,
        "execution": {
            "status": "success",
            "execution_devices": ["CPU"],
            "execution_device_readback": "actual",
            "fallback": {"kind": "none"},
            "missing_evidence": [],
            "batch": {"actual": 1, "fallback": False},
            "requests": {"actual": 1},
        },
    }


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    root = tmp_path / "inputs"
    root.mkdir()
    image = root / "copydays-strong.jpg"
    image.write_bytes(b"fixture only; fake adapter")
    digest = r.hash_file(image)
    model = root / "model.onnx"
    model.write_bytes(b"fixture model")
    processor = root / "processor.json"
    processor.write_text("{}")
    monkeypatch.setattr(
        r,
        "model_assets",
        lambda *a: (
            {
                "model/model.onnx": {
                    "sha256": r.hash_file(model),
                    "size_bytes": model.stat().st_size,
                }
            },
            [model, processor],
        ),
    )
    items = [
        {
            "id": f"g{i:03}",
            "path": image.name,
            "track": "copydays",
            "role": "gallery",
            "source_id": f"s{i:03}",
            "sha256": digest,
        }
        for i in range(157)
    ]
    items += [
        {
            "id": f"q{i:03}",
            "path": image.name,
            "track": "copydays",
            "role": "query",
            "source_id": f"s{i % 157:03}",
            "sha256": digest,
        }
        for i in range(229)
    ]
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": r.base.SCHEMA, "items": items}))
    parent_dir = root / "baseline"
    parent_dir.mkdir()
    features = parent_dir / "features"
    features.mkdir()
    config = {
        "limit_per_track": 1024,
        "selection": "sha256-id ascending",
        "quality": "local heuristic default; all learned models disabled",
        "copy": "phash64",
    }
    config_identity = r.digest_json(
        {
            "manifest": r.hash_file(manifest),
            "config": config,
            "code": [r.hash_file(p) for p in r.baseline_sources(root).values()],
            **r.PARENT_RUNTIME,
        }
    )
    inputs = {i["id"]: digest for i in items}
    ids = sorted(inputs)
    parent = {
        "schema_version": r.base.SCHEMA,
        "manifest_sha256": r.hash_file(manifest),
        "config": config,
        "config_identity": config_identity,
        "input_fingerprints": inputs,
        "selected_ids": ids,
        "selected_membership_sha256": r.base.digest(json.dumps(ids).encode()),
        "identity": r.digest_json({"config_identity": config_identity, "inputs": inputs}),
    }
    baseline = parent_dir / "report.json"
    baseline.write_text(json.dumps(parent))
    for item in items:
        record = {
            "id": item["id"],
            "input_sha256": digest,
            "status": "ok",
            "score": 3.0,
            "phash": "0" * 16,
            "scoring_mode": "heuristic",
            "fingerprint": r.base.digest((config_identity + digest).encode()),
        }
        record["record_sha256"] = r.digest_json(record)
        (features / (r.base.digest(item["id"].encode()) + ".json")).write_text(json.dumps(record))
    protocol = root / "protocol.json"
    protocol.write_text(
        json.dumps(r.build_protocol(root, manifest, baseline, model, processor), sort_keys=True)
    )
    monkeypatch.setenv("COPYDAYS_PROTOCOL_SHA256", r.hash_file(protocol))
    monkeypatch.setattr(
        r,
        "runtime_identity",
        lambda: {
            "python": "different-linux-runtime",
            "packages": {"numpy": "different"},
            "source_code_sha256": {},
        },
    )
    return root, manifest, baseline, protocol, model, processor, tmp_path / "output"


def test_parent_cache_is_portable_but_original_runtime_is_frozen(corpus):
    state = r.preflight(*corpus)
    assert state["plan"]["parent_runtime"] == r.PARENT_RUNTIME
    assert state["runtime"]["python"] == "different-linux-runtime"
    assert len(state["items"]) == 386


def test_protocol_approval_and_complete_cohort_are_required(corpus, monkeypatch):
    monkeypatch.delenv("COPYDAYS_PROTOCOL_SHA256")
    with pytest.raises(ValueError, match="controller-reviewed"):
        r.preflight(*corpus)
    protocol = corpus[3]
    data = json.loads(protocol.read_text())
    data["items"].pop()
    protocol.write_text(json.dumps(data))
    monkeypatch.setenv("COPYDAYS_PROTOCOL_SHA256", r.hash_file(protocol))
    with pytest.raises(ValueError, match="frozen full cohort"):
        r.preflight(*corpus)


def test_parent_feature_corruption_and_source_drift_fail_closed(corpus):
    feature = next((corpus[2].parent / "features").glob("*.json"))
    data = json.loads(feature.read_text())
    data["phash"] = "f" * 16
    feature.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        r.preflight(*corpus)


def test_output_cannot_overlap_inputs_or_symlink(corpus, tmp_path):
    with pytest.raises(ValueError, match="overlaps"):
        r.preflight(*corpus[:-1], corpus[2].parent)
    link = tmp_path / "alias"
    link.symlink_to(corpus[0], target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        r.preflight(*corpus[:-1], link / "output")


@pytest.mark.parametrize(
    "change",
    [
        {"fallback_used": True},
        {"execution_devices": []},
        {"execution_device_readback": "unknown"},
        {"vector": [float("nan"), 0.0]},
        {"vector": [0.0, 0.0]},
        {"vector": [2.0, 0.0]},
        {"dimensions": 3},
    ],
)
def test_missing_execution_or_invalid_vector_cannot_score(change):
    record = native()
    record.update(change)
    with pytest.raises(ValueError):
        r.validate_prediction(record)


def test_exact_ties_follow_gallery_id_and_native_source_rank():
    items = [
        {"id": "a", "role": "gallery", "source_id": "s1"},
        {"id": "b", "role": "gallery", "source_id": "s2"},
        {"id": "q", "role": "query", "source_id": "s2"},
    ]
    records = {i["id"]: {"vector": [1.0, 0.0], "phash": "0" * 16} for i in items}
    for cosine in [False, True]:
        metrics, rows = r.retrieval(items, records, cosine=cosine)
        assert metrics["top1"] == 0 and metrics["mrr"] == 0.5
        assert metrics["tied_first_queries"] == 1 and rows[0]["rank"] == 2


def test_bootstrap_pairs_whole_source_families():
    baseline = [
        {"id": str(i), "source_id": source, "top1": 0, "reciprocal_rank": 0.5}
        for i, source in enumerate(["a", "a", "b"])
    ]
    candidate = [{**x, "top1": 1, "reciprocal_rank": 1.0} for x in baseline]
    result = r.paired_bootstrap(candidate, baseline)
    assert result["top1"]["ci95"] == [1.0, 1.0]
    assert result["mrr"]["ci95"] == [0.5, 0.5]
    with pytest.raises(ValueError, match="paired query"):
        r.paired_bootstrap(candidate[::-1], baseline)


def test_offline_guard_and_experiment_paths_preserve_home(tmp_path):
    before = os.environ.get("HOME")
    with r.offline_guard(), r.isolated_homes(tmp_path):
        assert os.environ.get("HOME") == before
        assert Path(os.environ["TMPDIR"]).is_relative_to(tmp_path)
        with pytest.raises(RuntimeError, match="network"):
            socket.getaddrinfo("example.com", 443)
    assert os.environ.get("HOME") == before


def test_complete_run_resume_and_corrupt_record_recovery(corpus, monkeypatch):
    calls = []

    class Adapter:
        def __init__(self, config):
            pass

        async def embed_image(self, data):
            calls.append(data)
            return native()

    monkeypatch.setattr(r.embedding, "OpenVinoEmbeddingAdapter", Adapter)
    first = r.run(*corpus)
    assert first["status"] == "complete" and first["successful"] == len(calls) == 386
    second = r.run(*corpus)
    assert second["cache_reused"] == 386 and len(calls) == 386
    assert (
        second["identity"] == first["identity"]
        and second["semantic_digest"] == first["semantic_digest"]
    )
    cache = next((corpus[-1] / "predictions").glob("*.json"))
    data = json.loads(cache.read_text())
    data["vector"] = [0.0, 1.0]
    cache.write_text(json.dumps(data))
    recovered = r.run(*corpus)
    assert recovered["cache_reused"] == 385 and len(calls) == 387


def test_native_failure_never_becomes_valid_delta(corpus, monkeypatch):
    class Adapter:
        def __init__(self, config):
            pass

        async def embed_image(self, data):
            raise RuntimeError("model unavailable")

    monkeypatch.setattr(r.embedding, "OpenVinoEmbeddingAdapter", Adapter)
    report = r.run(*corpus)
    assert report["status"] == "incomplete" and report["failure_count"] == 8
    assert report["comparison"] is None and report["valid_delta_and_ci"] is False
