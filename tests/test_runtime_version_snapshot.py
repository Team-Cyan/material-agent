"""Version snapshots are lazy and client-scoped; mutable model identity stays live."""

import asyncio
from unittest.mock import Mock

from material_agent.clients import local


class Scorer:
    def __init__(self):
        self.calls = 0

    async def score_images(self, inputs):
        self.calls += 1
        return [{"score": 7, "distribution": [0.1] * 10} for _ in inputs]


def make_client(tmp_path):
    model = tmp_path / "model.tflite"
    if not model.exists():
        model.write_bytes(b"fixture-weights")
    client = local.AsyncLocalClient(
        {"aesthetic": {"model_path": str(model), "runtime": "openvino"}}
    )
    scorer = Scorer()
    client._aesthetic_scorer = lambda: scorer
    return client, scorer, model


def score(client):
    return asyncio.run(client.score_aesthetics([b"in-memory-input"]))[0]


def test_lazy_snapshot_reuses_absence_until_new_client(monkeypatch, tmp_path):
    versions = {
        "openvino": "1",
        "numpy": "2",
        "Pillow": "3",
        "torch": "unknown",
        "transformers": "unknown",
    }
    lookup = Mock(side_effect=lambda name: versions[name])
    monkeypatch.setattr(local, "runtime_version", lookup)
    client, scorer, _ = make_client(tmp_path)
    lookup.assert_not_called()
    assert asyncio.run(client.score_aesthetics([])) == []
    lookup.assert_not_called()
    first = score(client)
    assert lookup.call_count == 5
    versions["torch"] = "4"
    second = score(client)
    assert lookup.call_count == 5
    assert second["result_cache"]["status"] == "hit"
    assert second["result_cache"]["identity"] == first["result_cache"]["identity"]
    assert client._runtime_versions["torch"] == "unknown"
    fresh, _, _ = make_client(tmp_path)
    third = score(fresh)
    assert lookup.call_count == 10
    assert fresh._runtime_versions["torch"] == "4"
    assert third["result_cache"]["identity"] != first["result_cache"]["identity"]
    assert scorer.calls == 1


def test_asset_and_runtime_selection_still_invalidate(monkeypatch, tmp_path):
    lookup = Mock(return_value="fixed-version")
    monkeypatch.setattr(local, "runtime_version", lookup)
    client, scorer, model = make_client(tmp_path)
    keys = [score(client)["result_cache"]["identity"]]
    model.write_bytes(b"changed-model-weights")
    keys.append(score(client)["result_cache"]["identity"])
    client.aesthetic_config["runtime"] = "transformers"
    keys.append(score(client)["result_cache"]["identity"])
    client.inference["runtime"] = "cpu"
    keys.append(score(client)["result_cache"]["identity"])
    assert len(set(keys)) == 4
    assert scorer.calls == 4
    assert lookup.call_count == 5


def test_metadata_unavailable_remains_explicit(monkeypatch):
    from importlib.metadata import PackageNotFoundError
    from material_agent.adapters.models import inference_contract

    lookup = Mock(side_effect=PackageNotFoundError("not-installed"))
    monkeypatch.setattr(inference_contract, "version", lookup)
    assert inference_contract.runtime_version("not-installed") == "unknown"
