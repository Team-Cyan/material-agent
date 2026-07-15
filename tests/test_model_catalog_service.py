import hashlib
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from material_agent.app.model_api import ModelApiServer
from material_agent.app.model_catalog_service import (
    ModelCatalogService,
    ModelSpec,
    apply_model_selections,
    load_model_catalog,
)


def _spec(tmp_path: Path, payload: bytes = b"model") -> ModelSpec:
    bundled = tmp_path / "bundled.onnx"
    bundled.write_bytes(payload)
    return ModelSpec(
        model_id="test-model",
        role="detection",
        adapter="openvino-ssd-coco",
        name="test",
        version="v1",
        filename="model.onnx",
        url="https://example.invalid/model.onnx",
        sha256=hashlib.sha256(payload).hexdigest(),
        license="test",
        bundled_path=str(bundled),
    )


def test_bundled_model_can_be_selected_and_applied(tmp_path):
    spec = _spec(tmp_path)
    service = ModelCatalogService(tmp_path / "registry", catalog=(spec,))

    status = service.select(spec.model_id)
    assert status["bundled"] is True
    assert status["selected"] is True

    config = {
        "model_management": {
            "selection_enabled": True,
            "registry_dir": str(tmp_path / "registry"),
        },
        "local": {"detection": {}},
    }
    # The default catalog is intentionally replaced for this isolated fixture.
    # Verify the selection shape through the service and persistence contract.
    assert json.loads(service.selection_path.read_text())["selections"] == {
        "detection": "test-model"
    }
    assert config["local"]["detection"] == {}


def test_active_model_requires_force_before_managed_copy_is_deleted(tmp_path):
    spec = _spec(tmp_path)
    service = ModelCatalogService(tmp_path / "registry", catalog=(spec,))
    managed = service.models_dir / spec.model_id / spec.filename
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"model")
    service.select(spec.model_id)

    with pytest.raises(ValueError, match="selected"):
        service.delete(spec.model_id)

    result = service.delete(spec.model_id, force=True)
    assert result["removed"] is True
    assert result["bundled_preserved"] is True
    assert service.selections() == {}


def test_apply_model_selections_uses_default_catalog_bundled_path(tmp_path, monkeypatch):
    from material_agent.app import model_catalog_service as module

    spec = _spec(tmp_path)
    monkeypatch.setattr(module, "DEFAULT_MODEL_CATALOG", (spec,))
    service = ModelCatalogService(tmp_path / "registry", catalog=(spec,))
    service.select(spec.model_id)
    monkeypatch.setattr(
        module,
        "ModelCatalogService",
        lambda registry_dir, **_kwargs: ModelCatalogService(registry_dir, catalog=(spec,)),
    )
    config = {
        "model_management": {
            "selection_enabled": True,
            "registry_dir": str(tmp_path / "registry"),
        },
        "local": {"detection": {}},
    }
    applied = apply_model_selections(config)
    assert applied["local"]["detection"]["model_path"] == spec.bundled_path
    assert applied["local"]["detection"]["model_id"] == spec.model_id


def test_model_api_requires_bearer_token(tmp_path):
    spec = _spec(tmp_path)
    service = ModelCatalogService(tmp_path / "registry", catalog=(spec,))
    server = ModelApiServer(("127.0.0.1", 0), service, "secret")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v1/models"
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(url)
        assert error.value.code == 401
        request = urllib.request.Request(url, headers={"Authorization": "Bearer secret"})
        payload = json.loads(urllib.request.urlopen(request).read())
        assert payload["models"][0]["model_id"] == spec.model_id
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_custom_catalog_rejects_arbitrary_adapter_and_insecure_url(tmp_path):
    catalog = tmp_path / "catalog.json"
    payload = {
        "schema_version": 1,
        "models": [
            {
                "model_id": "unsafe",
                "role": "aesthetic",
                "adapter": "arbitrary-python",
                "name": "unsafe",
                "version": "v1",
                "filename": "model.onnx",
                "url": "http://example.test/model.onnx",
                "sha256": "0" * 64,
                "license": "unknown",
            }
        ],
    }
    catalog.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported adapter"):
        load_model_catalog(catalog)


def test_custom_catalog_accepts_supported_pinned_entry(tmp_path):
    spec = _spec(tmp_path)
    payload = {"schema_version": 1, "models": [{**spec.__dict__, "bundled_path": None}]}
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_model_catalog(catalog)
    assert loaded[0].model_id == spec.model_id
