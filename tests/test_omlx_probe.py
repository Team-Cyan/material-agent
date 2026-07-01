import httpx

from material_agent.adapters.models.omlx.failure_guidance import build_omlx_failure_guidance
from material_agent.adapters.models.omlx.probe import (
    OMLXCapabilityFailure,
    OMLXCapabilityProfile,
    probe_omlx_capabilities,
    validate_omlx_capability,
)


def test_probe_rejects_old_omlx_version():
    profile = OMLXCapabilityProfile(
        reachable=True,
        version="0.2.24",
        structured_outputs=True,
        xgrammar=True,
        served_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        instance_matches=True,
        settings_drift=[],
    )

    valid, reason = validate_omlx_capability(profile, required_version=">=0.3.0")

    assert valid is False
    assert reason is not None
    assert reason.code == "version_too_old"


def test_probe_rejects_unknown_omlx_version_when_required():
    profile = OMLXCapabilityProfile(
        reachable=True,
        version=None,
        structured_outputs=True,
        xgrammar=True,
        served_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        instance_matches=True,
        settings_drift=[],
    )

    valid, reason = validate_omlx_capability(profile, required_version=">=0.3.0")

    assert valid is False
    assert reason is not None
    assert reason.code == "version_unknown"


def test_probe_rejects_missing_structured_outputs():
    profile = OMLXCapabilityProfile(
        reachable=True,
        version="0.3.1",
        structured_outputs=False,
        xgrammar=True,
        served_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        instance_matches=True,
        settings_drift=[],
    )

    valid, reason = validate_omlx_capability(
        profile,
        required_version=">=0.3.0",
        require_structured_outputs=True,
    )

    assert valid is False
    assert reason is not None
    assert reason.code == "structured_outputs_missing"


def test_probe_rejects_unknown_structured_outputs_when_required():
    profile = OMLXCapabilityProfile(
        reachable=True,
        version="0.3.1",
        structured_outputs=None,
        xgrammar=True,
        served_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        instance_matches=True,
        settings_drift=[],
    )

    valid, reason = validate_omlx_capability(
        profile,
        required_version=">=0.3.0",
        require_structured_outputs=True,
    )

    assert valid is False
    assert reason is not None
    assert reason.code == "structured_outputs_unknown"


def test_probe_rejects_unknown_xgrammar_when_required():
    profile = OMLXCapabilityProfile(
        reachable=True,
        version="0.3.1",
        structured_outputs=True,
        xgrammar=None,
        served_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        instance_matches=True,
        settings_drift=[],
    )

    valid, reason = validate_omlx_capability(
        profile,
        required_version=">=0.3.0",
        require_xgrammar=True,
    )

    assert valid is False
    assert reason is not None
    assert reason.code == "xgrammar_unknown"


def test_probe_prefers_instance_mismatch_when_runtime_drift_exists():
    profile = OMLXCapabilityProfile(
        reachable=True,
        version="0.3.2",
        structured_outputs=True,
        xgrammar=False,
        served_models=["Qwen3.5-9B-MLX-4bit"],
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        instance_matches=False,
        settings_drift=["served models do not match linked models"],
    )

    valid, reason = validate_omlx_capability(
        profile,
        required_version=">=0.3.0",
        require_xgrammar=True,
    )

    assert valid is False
    assert reason is not None
    assert reason.code == "instance_mismatch"


def test_probe_can_ignore_instance_mismatch_when_dedicated_instance_enforcement_is_disabled():
    profile = OMLXCapabilityProfile(
        reachable=True,
        version="0.3.2",
        structured_outputs=True,
        xgrammar=True,
        served_models=["Qwen3.5-9B-MLX-4bit"],
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        instance_matches=False,
        settings_drift=["served models do not exactly match linked models"],
    )

    valid, reason = validate_omlx_capability(
        profile,
        required_version=">=0.3.0",
        require_structured_outputs=True,
        require_xgrammar=True,
        require_dedicated_instance=False,
    )

    assert valid is True
    assert reason is None


def test_probe_marks_catalog_superset_as_effective_match_when_linked_models_match_expected(monkeypatch):
    payloads = {
        "http://127.0.0.1:11435/v1/models": {
            "data": [
                {"id": "Qwen3-VL-4B-Instruct-4bit"},
                {"id": "Qwen3-VL-8B-Instruct-4bit"},
                {"id": "gemma-4-e2b-it-4bit"},
            ]
        },
        "http://127.0.0.1:11435/version": {"version": "0.3.4"},
    }

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _fake_get(url, **kwargs):
        payload = payloads.get(url)
        if payload is None:
            raise RuntimeError("missing endpoint")
        return _Response(payload)

    def _fake_post(url, **kwargs):
        request = httpx.Request("POST", url)
        response = httpx.Response(401, request=request, text="missing auth")
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.get", _fake_get)
    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.post", _fake_post)
    profile = probe_omlx_capabilities(
        base_url="http://127.0.0.1:11435",
        headers={},
        linked_models=["Qwen3-VL-4B-Instruct-4bit"],
        expected_models=["Qwen3-VL-4B-Instruct-4bit"],
    )

    assert profile.instance_matches is False
    assert profile.effective_model_set_matches is True
    assert profile.served_models_catalog_superset is True


def test_probe_returns_valid_profile_when_requirements_are_met():
    profile = OMLXCapabilityProfile(
        reachable=True,
        version="0.3.6",
        structured_outputs=True,
        xgrammar=True,
        served_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        instance_matches=True,
        settings_drift=[],
    )

    valid, reason = validate_omlx_capability(
        profile,
        required_version=">=0.3.0",
        require_structured_outputs=True,
        require_xgrammar=True,
    )

    assert valid is True
    assert reason is None


def test_failure_guidance_includes_actionable_steps_for_unreachable_runtime():
    failure = OMLXCapabilityFailure(
        code="omlx_unreachable",
        summary="OMLX API did not respond at the configured base URL.",
    )
    profile = OMLXCapabilityProfile(
        reachable=False,
        version=None,
        structured_outputs=None,
        xgrammar=None,
        served_models=[],
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        instance_matches=False,
        settings_drift=["server was unreachable"],
        error="Connection refused",
    )

    guidance = build_omlx_failure_guidance(
        failure,
        profile,
        base_url="http://127.0.0.1:11435",
        instance_root="/tmp/material-agent-omlx",
    )

    assert "/Applications/oMLX.app" in guidance
    assert "http://127.0.0.1:11435" in guidance
    assert "omlx-start --dedicated" in guidance
    assert "install" in guidance.lower()


def test_probe_uses_version_endpoint_when_admin_endpoints_are_absent(monkeypatch):
    payloads = {
        "http://127.0.0.1:11435/v1/models": {"data": [{"id": "Qwen2.5-VL-7B-Instruct-4bit"}]},
        "http://127.0.0.1:11435/version": {"version": "0.3.4"},
    }

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _fake_get(url, **kwargs):
        payload = payloads.get(url)
        if payload is None:
            raise RuntimeError("missing endpoint")
        return _Response(payload)

    def _fake_post(url, **kwargs):
        request = httpx.Request("POST", url)
        response = httpx.Response(401, request=request, text="missing auth")
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.get", _fake_get)
    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.post", _fake_post)

    profile = probe_omlx_capabilities(
        base_url="http://127.0.0.1:11435",
        headers={},
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
    )

    assert profile.reachable is True
    assert profile.version == "0.3.4"
    assert profile.structured_outputs is None
    assert profile.xgrammar is None


def test_probe_does_not_promote_per_model_capability_flags_to_global_support(monkeypatch):
    payloads = {
        "http://127.0.0.1:11435/v1/models": {
            "data": [
                {
                    "id": "Qwen2.5-VL-7B-Instruct-4bit",
                    "capabilities": {"structured_outputs": True, "xgrammar": True},
                }
            ]
        },
        "http://127.0.0.1:11435/admin/settings": {
            "models": {
                "Qwen2.5-VL-7B-Instruct-4bit": {
                    "structured_outputs": True,
                    "xgrammar": True,
                }
            }
        },
    }

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _fake_get(url, **kwargs):
        payload = payloads.get(url)
        if payload is None:
            raise RuntimeError("missing endpoint")
        return _Response(payload)

    def _fake_post(url, **kwargs):
        request = httpx.Request("POST", url)
        response = httpx.Response(401, request=request, text="missing auth")
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.get", _fake_get)
    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.post", _fake_post)

    profile = probe_omlx_capabilities(
        base_url="http://127.0.0.1:11435",
        headers={},
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
    )

    assert profile.structured_outputs is None
    assert profile.xgrammar is None


def test_probe_uses_active_structured_request_when_metadata_endpoints_are_missing(monkeypatch):
    payloads = {
        "http://127.0.0.1:11435/v1/models": {"data": [{"id": "Qwen2.5-VL-7B-Instruct-4bit"}]},
    }

    class _Response:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _fake_get(url, **kwargs):
        payload = payloads.get(url)
        if payload is None:
            raise RuntimeError("missing endpoint")
        return _Response(payload)

    def _fake_post(url, **kwargs):
        assert url == "http://127.0.0.1:11435/v1/chat/completions"
        return _Response(
            {
                "choices": [
                    {
                        "message": {
                            "parsed": {"status": "ok"},
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.get", _fake_get)
    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.post", _fake_post)

    profile = probe_omlx_capabilities(
        base_url="http://127.0.0.1:11435",
        headers={},
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
        local_version_fallback="0.3.0",
    )

    assert profile.version == "0.3.0"
    assert profile.structured_outputs is True
    assert profile.xgrammar is True
    assert profile.active_structured_probe is True
    assert profile.active_structured_probe_error is None


def test_probe_marks_active_structured_request_as_failed_when_runtime_returns_prose(monkeypatch):
    payloads = {
        "http://127.0.0.1:11435/v1/models": {"data": [{"id": "Qwen2.5-VL-7B-Instruct-4bit"}]},
    }

    class _Response:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _fake_get(url, **kwargs):
        payload = payloads.get(url)
        if payload is None:
            raise RuntimeError("missing endpoint")
        return _Response(payload)

    def _fake_post(url, **kwargs):
        assert url == "http://127.0.0.1:11435/v1/chat/completions"
        return _Response(
            {
                "choices": [
                    {
                        "message": {
                            "content": "This is prose, not JSON.",
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.get", _fake_get)
    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.post", _fake_post)

    profile = probe_omlx_capabilities(
        base_url="http://127.0.0.1:11435",
        headers={},
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
    )

    assert profile.structured_outputs is False
    assert profile.xgrammar is False
    assert profile.active_structured_probe is False
    assert "strict JSON object" in (profile.active_structured_probe_error or "")


def test_probe_leaves_unknown_capability_values_as_unknown(monkeypatch):
    payloads = {
        "http://127.0.0.1:11435/v1/models": {"data": [{"id": "Qwen2.5-VL-7B-Instruct-4bit"}]},
        "http://127.0.0.1:11435/admin/settings": {
            "capabilities": {
                "structured_outputs": "maybe",
                "xgrammar": "auto",
            }
        },
    }

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _fake_get(url, **kwargs):
        payload = payloads.get(url)
        if payload is None:
            raise RuntimeError("missing endpoint")
        return _Response(payload)

    def _fake_post(url, **kwargs):
        request = httpx.Request("POST", url)
        response = httpx.Response(401, request=request, text="missing auth")
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.get", _fake_get)
    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.post", _fake_post)

    profile = probe_omlx_capabilities(
        base_url="http://127.0.0.1:11435",
        headers={},
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
    )

    assert profile.structured_outputs is None
    assert profile.xgrammar is None


def test_probe_parses_explicit_global_capabilities_from_mixed_string_and_bool_shapes(monkeypatch):
    payloads = {
        "http://127.0.0.1:11435/v1/models": {"data": [{"id": "Qwen2.5-VL-7B-Instruct-4bit"}]},
        "http://127.0.0.1:11435/admin/settings": {
            "server": {
                "capabilities": {
                    "structured_outputs": "enabled",
                    "xgrammar": False,
                }
            }
        },
    }

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _fake_get(url, **kwargs):
        payload = payloads.get(url)
        if payload is None:
            raise RuntimeError("missing endpoint")
        return _Response(payload)

    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.get", _fake_get)

    profile = probe_omlx_capabilities(
        base_url="http://127.0.0.1:11435",
        headers={},
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
    )

    assert profile.structured_outputs is True
    assert profile.xgrammar is False


def test_probe_marks_extra_served_models_as_instance_mismatch(monkeypatch):
    payloads = {
        "http://127.0.0.1:11435/v1/models": {
            "data": [
                {"id": "Qwen2.5-VL-7B-Instruct-4bit"},
                {"id": "Qwen3.5-9B-MLX-4bit"},
            ]
        },
        "http://127.0.0.1:11435/version": {"version": "0.3.7"},
        "http://127.0.0.1:11435/admin/settings": {
            "capabilities": {
                "structured_outputs": True,
                "xgrammar": True,
            }
        },
    }

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _fake_get(url, **kwargs):
        payload = payloads.get(url)
        if payload is None:
            raise RuntimeError("missing endpoint")
        return _Response(payload)

    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.get", _fake_get)

    profile = probe_omlx_capabilities(
        base_url="http://127.0.0.1:11435",
        headers={},
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
    )

    assert profile.instance_matches is False
    assert "served models include models outside the linked set" in profile.settings_drift


def test_probe_prefers_server_level_version_over_nested_model_version(monkeypatch):
    payloads = {
        "http://127.0.0.1:11435/v1/models": {
            "version": "0.3.5",
            "data": [{"id": "Qwen2.5-VL-7B-Instruct-4bit", "version": "9.9.9"}],
        },
        "http://127.0.0.1:11435/admin/settings": {
            "models": {"Qwen2.5-VL-7B-Instruct-4bit": {"version": "8.8.8"}},
            "server": {"version": "0.3.6"},
        },
        "http://127.0.0.1:11435/version": {"version": "0.3.7"},
    }

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _fake_get(url, **kwargs):
        payload = payloads.get(url)
        if payload is None:
            raise RuntimeError("missing endpoint")
        return _Response(payload)

    monkeypatch.setattr("material_agent.adapters.models.omlx.probe.httpx.get", _fake_get)

    profile = probe_omlx_capabilities(
        base_url="http://127.0.0.1:11435",
        headers={},
        linked_models=["Qwen2.5-VL-7B-Instruct-4bit"],
        expected_models=["mlx-community/Qwen2.5-VL-7B-Instruct-4bit"],
    )

    assert profile.version == "0.3.7"
