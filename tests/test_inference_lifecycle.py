"""No media files are created: images remain in memory, models/cache use tmp_path."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
import json
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from material_agent.adapters.models.inference_contract import (
    ModelDeclaration,
    ResultCache,
    asset_identity,
)
from material_agent.adapters.models.openvino_embedding import _OpenVinoRuntime
from material_agent.adapters.models.openvino_nima_aesthetic import _OpenVinoNimaRuntime
from material_agent.adapters.models.openvino_session import OpenVinoSession, compiled_cache
from material_agent.app.jobs.review_photos import _aggregate_timings
from material_agent.clients.local import AsyncLocalClient


def declaration():
    return ModelDeclaration.create(
        "fixture",
        "1",
        {"state": "available", "digest": "a"},
        {"revision": "1", "dtype": "float32"},
        "1",
    )


def identity_model(tmp_path):
    onnx = pytest.importorskip("onnx")
    helper = onnx.helper

    def port(name):
        return helper.make_tensor_value_info(name, onnx.TensorProto.FLOAT, [1, 3, 2, 2])

    model = helper.make_model(
        helper.make_graph(
            [helper.make_node("Identity", ["input"], ["output"])],
            "fixture",
            [port("input")],
            [port("output")],
        ),
        opset_imports=[helper.make_opsetid("", 13)],
    )
    path = tmp_path / "identity.onnx"
    onnx.save(model, path)
    (tmp_path / "preprocessor_config.json").write_text(
        json.dumps({"size": {"height": 2, "width": 2}, "do_normalize": False}), encoding="utf-8"
    )
    return path


def runtime(tmp_path, **kwargs):
    pytest.importorskip("openvino")
    path = identity_model(tmp_path)
    return _OpenVinoRuntime(
        model_path=str(path),
        processor_path=str(tmp_path),
        device="CPU",
        fallback_device="CPU",
        compiled_cache_dir=str(tmp_path / "cache"),
        **kwargs,
    )


def test_declaration_revisions_partition_identity():
    first = declaration()
    assert (
        len(
            {
                first.key,
                replace(first, revision="2").key,
                replace(first, preprocessing_json='{"revision":"2"}').key,
                replace(first, assets_json='{"digest":"b"}').key,
                replace(first, output_revision="2").key,
            }
        )
        == 5
    )


def test_real_batch_order_partial_and_concurrent_runs(tmp_path):
    session = runtime(tmp_path, batch_size=4, infer_requests=2)
    images = [Image.new("RGB", (2, 2), (value, 20, 30)) for value in (5, 99, 5, 201, 17)]
    expected = []
    for image in images:
        tensor = session.processor(image).reshape(-1)
        expected.append(tensor / np.linalg.norm(tensor))
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(session.embed_many, [images, images]))
    for result in outputs:
        np.testing.assert_allclose(result, expected, atol=1e-4, rtol=1e-3)
    assert session.last_run_timing["batch_count"] == 2
    assert session.last_run_timing["image_count"] == 5
    assert session.execution_record()["execution_devices"] == ["CPU"]


def test_real_compiled_identity_changes_with_preprocessing_and_batch(tmp_path):
    first = runtime(tmp_path, batch_size=1)
    second = _OpenVinoRuntime(
        model_path=str(tmp_path / "identity.onnx"),
        processor_path=str(tmp_path),
        device="CPU",
        fallback_device="CPU",
        compiled_cache_dir=str(tmp_path / "cache"),
        batch_size=2,
    )
    assert first.compiled_cache_identity != second.compiled_cache_identity
    config = tmp_path / "preprocessor_config.json"
    config.write_text(json.dumps({"size": {"height": 2, "width": 2}, "do_rescale": False}))
    third = _OpenVinoRuntime(
        model_path=str(tmp_path / "identity.onnx"),
        processor_path=str(tmp_path),
        device="CPU",
        fallback_device="CPU",
        compiled_cache_dir=str(tmp_path / "cache"),
    )
    assert first.compiled_cache_identity != third.compiled_cache_identity
    assert first.compile_event_id != third.compile_event_id


def test_compiled_cache_only_prunes_owned_entries_and_handles_oversize(tmp_path):
    unmanaged = tmp_path / "existing.blob"
    unmanaged.write_bytes(b"keep")
    with compiled_cache(tmp_path, "a" * 64, max_entries=1, max_bytes=10) as directory:
        (directory / "blob").write_bytes(b"one")
    with compiled_cache(tmp_path, "b" * 64, max_entries=1, max_bytes=10) as directory:
        (directory / "blob").write_bytes(b"two")
    assert not (directory.parent / ("a" * 64)).exists()
    assert unmanaged.read_bytes() == b"keep"
    with compiled_cache(tmp_path, "c" * 64, max_entries=1, max_bytes=1) as oversized:
        (oversized / "blob").write_bytes(b"oversize")
    assert not oversized.exists()


def test_unavailable_assets_have_no_fabricated_digest(tmp_path):
    assert asset_identity(tmp_path / "missing.onnx") == {"state": "missing", "digest": None}
    path = tmp_path / "bad.onnx"
    path.write_bytes(b"not an ONNX graph")
    assert asset_identity(path)["digest"] is None
    with pytest.raises(RuntimeError, match="assets unavailable"):
        OpenVinoSession(
            model_path=path,
            declaration=replace(declaration(), assets_json='{"state":"missing","digest":null}'),
            device="CPU",
            fallback_device="CPU",
            compiled_cache_dir=tmp_path / "cache",
        )


def test_result_cache_deep_copies_and_evicts():
    cache = ResultCache(1)
    value = {"distribution": [0.1], "execution": {"status": "success"}}
    cache.put("first", value)
    value["distribution"][0] = 9
    copied = cache.get("first")
    copied["execution"]["status"] = "changed"
    assert cache.get("first")["distribution"] == [0.1]
    assert cache.get("first")["execution"]["status"] == "success"
    cache.put("second", {})
    assert cache.get("first") is None


def test_client_cache_revision_cannot_reuse_previous_output():
    class Scorer:
        result_cache_revision = "fixture"
        calls = 0

        async def score_images(self, inputs):
            self.calls += 1
            return [{"score": 7, "distribution": [0.1] * 10} for _ in inputs]

    client = AsyncLocalClient({"aesthetic": {"enabled": True, "cache_revision": "one"}})
    scorer = Scorer()
    client._aesthetic = scorer
    client._aesthetic_scorer = lambda: scorer
    output = BytesIO()
    Image.new("RGB", (2, 2)).save(output, format="JPEG")
    payload = output.getvalue()
    first = asyncio.run(client.score_aesthetics([payload, payload]))
    second = asyncio.run(client.score_aesthetics([payload]))
    assert scorer.calls == 1
    assert second[0]["result_cache"]["status"] == "hit"
    client.aesthetic_config["cache_revision"] = "two"
    third = asyncio.run(client.score_aesthetics([payload]))
    assert scorer.calls == 2
    assert first[0]["result_cache"]["identity"] != third[0]["result_cache"]["identity"]


def test_compile_timing_sums_models_but_not_repeated_runs():
    class Evidence:
        def list_artifact_metadata(self, **kwargs):
            def record(compile_id, run_id, duration):
                return {
                    "compile_event_id": compile_id,
                    "inference_run_id": run_id,
                    "timing": {"compile_seconds": duration, "inference_seconds": 0.1},
                }

            return [
                {"meta": {"aesthetic": record("a", "a1", 2), "embedding": record("b", "b1", 3)}},
                {"meta": {"aesthetic": record("a", "a2", 2), "embedding": record("b", "b1", 3)}},
            ]

    result = _aggregate_timings(Evidence(), [], job_id="fixture")
    assert result["model_compile_seconds"] == 5
    assert result["model_inference_seconds"] == 0.3
    assert result["model_runs"] == 3


def test_nima_preprocessing_and_output_parity_without_files():
    session = object.__new__(_OpenVinoNimaRuntime)
    session.np = np
    spec = {"color": "RGB", "resize": [224, 224], "resample": 2, "divisor": 127.5, "offset": -1.0}
    session.declaration = ModelDeclaration.create("nima", "1", {}, spec, "1")
    image = Image.new("RGB", (17, 23), (30, 80, 150))
    expected = np.expand_dims(
        np.asarray(image.resize((224, 224), Image.Resampling.BILINEAR), dtype=np.float32) / 127.5
        - 1.0,
        0,
    )
    np.testing.assert_array_equal(session._preprocess(image), expected)
    assert session._normalize([np.eye(10, dtype=np.float32)])[6] == (7.0, np.eye(10)[6].tolist())
    with pytest.raises(RuntimeError):
        session._normalize([np.zeros((1, 10), dtype=np.float32)])


def test_callback_order_and_missing_outputs_are_checked():
    session = object.__new__(OpenVinoSession)
    session.np = np
    session.input_batch_size = 1
    session.infer_requests = 2
    session.compile_seconds = 0.0
    session.declaration = declaration()
    session.compiled = SimpleNamespace(input=lambda _: SimpleNamespace(get_any_name=lambda: "x"))

    class Queue:
        def __init__(self, *args):
            self.inputs = []

        def set_callback(self, callback):
            self.callback = callback

        def start_async(self, inputs, userdata):
            self.inputs.append((inputs["x"], userdata))

        def wait_all(self):
            for tensor, index in reversed(self.inputs):
                self.callback(SimpleNamespace(output_tensors=[SimpleNamespace(data=tensor)]), index)

    session.ov = SimpleNamespace(AsyncInferQueue=Queue)

    def preprocess(n):
        return np.full((1, 1, 1, 1), n, dtype=np.float32)

    def normalize(arrays):
        return arrays[0].reshape(-1).tolist()

    assert session._run([9, 1, 7], preprocess, normalize) == [9, 1, 7]
    with pytest.raises(RuntimeError, match="batch count"):
        session._run([1], preprocess, lambda arrays: [])
    with pytest.raises(RuntimeError, match="nonfinite"):
        session._run([float("nan")], preprocess, normalize)


def test_sqlite_accepts_execution_record_without_schema_migration(tmp_path):
    from material_agent.utils.state import State

    state = State(str(tmp_path))
    try:
        state.mark_scored(
            "fixture-item",
            total_score=7.0,
            scores={},
            metadata={
                "aesthetic": {
                    "execution": {
                        "schema": "local-inference-v1",
                        "status": "success",
                        "model_identity": "fixture",
                    }
                }
            },
        )
        restored = state.get_scored("fixture-item")
        assert restored["meta"]["aesthetic"]["execution"]["model_identity"] == "fixture"
        # Simulate an existing version-1 JSON row without new execution facts.
        state.conn.execute(
            "UPDATE processed SET score_metadata_json = ?", ('{"aesthetic":{"score":7}}',)
        )
        state.conn.commit()
        assert state.get_scored("fixture-item")["meta"]["aesthetic"] == {"score": 7}
    finally:
        state.close()


def test_non_onnx_asset_and_processor_changes_are_detected(tmp_path):
    from material_agent.adapters.models.inference_contract import AssetSnapshot

    path = tmp_path / "nima.tflite"
    path.write_bytes(b"weights-v1")
    snapshot = AssetSnapshot(path)
    first = snapshot.current()
    assert first["state"] == "available"
    path.write_bytes(b"weights-v2")
    assert snapshot.current()["digest"] != first["digest"]


def test_client_declared_preprocessing_changes_result_key(monkeypatch):
    class Scorer:
        result_cache_revision = "fixture"
        calls = 0

        async def score_images(self, inputs):
            self.calls += 1
            return [{"score": 7, "distribution": [0.1] * 10} for _ in inputs]

    scorer = Scorer()
    client = AsyncLocalClient({"aesthetic": {"enabled": True}})
    client._aesthetic = scorer
    client._aesthetic_scorer = lambda: scorer
    first = asyncio.run(client.score_aesthetics([b"synthetic-input"]))
    monkeypatch.setattr(
        "material_agent.clients.local.preprocessing_spec", lambda *args: {"revision": "changed"}
    )
    second = asyncio.run(client.score_aesthetics([b"synthetic-input"]))
    assert scorer.calls == 2
    assert first[0]["result_cache"]["identity"] != second[0]["result_cache"]["identity"]


def test_asset_snapshot_recovers_when_missing_companion_is_installed(tmp_path):
    from material_agent.adapters.models.inference_contract import AssetSnapshot
    model = tmp_path / 'model.xml'
    model.write_text('<net/>')
    snapshot = AssetSnapshot(model)
    assert snapshot.current()['state'] == 'missing_companion'
    model.with_suffix('.bin').write_bytes(b'weights')
    assert snapshot.current()['state'] == 'available'
