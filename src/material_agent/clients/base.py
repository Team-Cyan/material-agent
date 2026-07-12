from ..utils.config_validator import normalize_config
from .protocol import BackendClient


def get_backend_name(config: dict) -> str:
    return normalize_config(config).get("backend", "local")


def get_backend_config(config: dict) -> dict:
    normalized = normalize_config(config)
    return normalized.get(get_backend_name(normalized), {})


def make_client(config: dict) -> BackendClient:
    normalized = normalize_config(config)
    backend = normalized.get("backend", "local")
    backend_config = {
        **normalized.get(backend, {}),
        "output_language": normalized.get("output_language", "zh"),
    }
    if backend == "local":
        from .local import AsyncLocalClient

        backend_config["inference"] = normalized.get("inference", {})
        backend_config["semantic"] = normalized.get("local", {}).get("semantic", {})
        backend_config["quality"] = normalized.get("local", {}).get("quality", {})
        backend_config["embedding"] = normalized.get("local", {}).get("embedding", {})
        backend_config["face"] = normalized.get("local", {}).get("face", {})
        return AsyncLocalClient(backend_config)
    if backend == "omlx":
        from .omlx import AsyncOMLXClient

        return AsyncOMLXClient(backend_config)
    if backend != "ollama":
        raise ValueError(f"unsupported backend: {backend!r}")
    from .ollama import AsyncOllamaClient

    return AsyncOllamaClient(backend_config)


def make_fast_screening_port(config: dict):
    normalized = normalize_config(config)
    screening_cfg = normalized.get("screening", {})
    if not screening_cfg.get("enabled", False):
        return None
    backend = screening_cfg.get("backend", "musiq")
    if backend == "musiq":
        from ..adapters.screening import MusiqFastScreeningAdapter

        return MusiqFastScreeningAdapter(screening_cfg.get("musiq", {}))
    return None
