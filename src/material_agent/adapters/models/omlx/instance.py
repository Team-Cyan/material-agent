import json
import plistlib
import shutil
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

_LOCAL_OMLX_HOSTS = {"localhost", "127.0.0.1", "::1"}
_APP_CLI_PATH = "/Applications/oMLX.app/Contents/MacOS/omlx-cli"


def _omlx_config(config: dict) -> dict:
    nested = config.get("omlx")
    if isinstance(nested, dict):
        return nested
    return config


def collect_omlx_runtime_models(config: dict) -> list[str]:
    omlx = _omlx_config(config)
    candidates = [
        omlx.get("fast_vision_model"),
        omlx.get("full_vision_model"),
        omlx.get("commentary_model"),
    ]
    seen: set[str] = set()
    models: list[str] = []
    for model in candidates:
        if not model or model in seen:
            continue
        seen.add(model)
        models.append(model)
    return models


def _load_omlx_settings(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_omlx_home_settings(home_settings_path: Path | None = None) -> dict:
    path = home_settings_path or Path.home() / ".omlx" / "settings.json"
    return _load_omlx_settings(path)


def load_omlx_home_model_settings(home_model_settings_path: Path | None = None) -> dict:
    path = home_model_settings_path or Path.home() / ".omlx" / "model_settings.json"
    return _load_omlx_settings(path)


def _instance_settings_path(config: dict) -> Path:
    return _instance_root(config) / "settings.json"


def _is_local_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    return host in _LOCAL_OMLX_HOSTS


def is_local_omlx_base_url(base_url: str) -> bool:
    return _is_local_base_url(base_url)


def _normalized_local_host(host: str | None) -> str:
    value = (host or "127.0.0.1").strip().lower()
    return "local" if value in _LOCAL_OMLX_HOSTS else value


def is_configured_shared_omlx_runtime(
    config: dict,
    *,
    home_settings_path: Path | None = None,
) -> bool:
    omlx = _omlx_config(config)
    runtime_cfg = omlx.get("runtime", {}) if isinstance(omlx.get("runtime", {}), dict) else {}
    if bool(runtime_cfg.get("enforce_dedicated_instance", False)):
        return False

    base_url = str(omlx.get("base_url", "http://127.0.0.1:11435"))
    if not _is_local_base_url(base_url):
        return False

    base_host, base_port = _parse_base_url(base_url)
    home_settings = load_omlx_home_settings(home_settings_path)
    server_cfg = home_settings.get("server", {}) if isinstance(home_settings, dict) else {}
    server_host = server_cfg.get("host", "127.0.0.1")
    try:
        server_port = int(server_cfg.get("port", 11435))
    except (TypeError, ValueError):
        server_port = 11435
    return _normalized_local_host(base_host) == _normalized_local_host(server_host) and base_port == server_port


def discover_local_omlx_version() -> str | None:
    info_path = Path("/Applications/oMLX.app/Contents/Info.plist")
    if not info_path.exists():
        return None
    try:
        info = plistlib.loads(info_path.read_bytes())
    except Exception:
        return None
    version = info.get("CFBundleShortVersionString") or info.get("CFBundleVersion")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def discover_omlx_api_key(
    config: dict,
    *,
    home_settings_path: Path | None = None,
    instance_settings_path: Path | None = None,
) -> str:
    omlx = _omlx_config(config)
    explicit = str(omlx.get("api_key") or "").strip()
    if explicit:
        return explicit

    base_url = str(omlx.get("base_url", "http://127.0.0.1:11435"))
    if not _is_local_base_url(base_url):
        return ""

    settings_candidates: list[dict] = []
    instance_path = instance_settings_path or _instance_settings_path(config)
    settings_candidates.append(_load_omlx_settings(instance_path))

    settings_candidates.append(load_omlx_home_settings(home_settings_path))

    for settings in settings_candidates:
        auth = settings.get("auth", {}) if isinstance(settings, dict) else {}
        api_key = auth.get("api_key")
        if isinstance(api_key, str) and api_key.strip():
            return api_key.strip()
    return ""


def load_omlx_instance_settings(config: dict, *, instance_settings_path: Path | None = None) -> dict:
    return _load_omlx_settings(instance_settings_path or _instance_settings_path(config))


def load_omlx_discovered_settings(
    config: dict,
    *,
    home_settings_path: Path | None = None,
    instance_settings_path: Path | None = None,
) -> list[dict]:
    discovered: list[dict] = []
    for settings in (
        load_omlx_instance_settings(config, instance_settings_path=instance_settings_path),
        load_omlx_home_settings(home_settings_path),
    ):
        if settings and settings not in discovered:
            discovered.append(settings)
    return discovered


def _instance_root(config: dict) -> Path:
    omlx = _omlx_config(config)
    raw = omlx.get("instance_root", "~/.material-agent/omlx")
    return Path(raw).expanduser()


def _discover_source_model_dirs(config: dict, home_settings_path: Path | None = None) -> list[Path]:
    omlx = _omlx_config(config)
    configured = omlx.get("source_model_dirs")
    if configured:
        return [Path(path).expanduser() for path in configured]

    home_settings = load_omlx_home_settings(home_settings_path)
    model_cfg = home_settings.get("model", {})
    candidates = model_cfg.get("model_dirs") or []
    if model_cfg.get("model_dir"):
        candidates.append(model_cfg["model_dir"])
    if not candidates:
        candidates = ["~/.omlx/models"]
    resolved: list[Path] = []
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path not in resolved:
            resolved.append(path)
    return resolved


def _looks_like_model_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        children = list(path.iterdir())
    except OSError:
        return False
    if not children:
        return True
    return any(not child.is_dir() for child in children)


def _discover_source_model_names(source_dirs: list[Path]) -> list[str]:
    discovered: list[str] = []
    seen: set[str] = set()

    def _remember(path: Path) -> None:
        if path.name not in seen:
            seen.add(path.name)
            discovered.append(path.name)

    for source_dir in source_dirs:
        if not source_dir.exists():
            continue
        try:
            children = list(source_dir.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            if _looks_like_model_dir(child):
                _remember(child)
                continue
            try:
                grandchildren = list(child.iterdir())
            except OSError:
                continue
            for grandchild in grandchildren:
                if grandchild.is_dir() and _looks_like_model_dir(grandchild):
                    _remember(grandchild)
    return discovered


def _find_source_model_dir(model_name: str, source_dirs: list[Path]) -> Path:
    candidates = [model_name]
    basename = Path(model_name).name
    if basename not in candidates:
        candidates.append(basename)
    for source_dir in source_dirs:
        for candidate in candidates:
            direct = source_dir / candidate
            if direct.is_dir():
                return direct
        for child in source_dir.iterdir() if source_dir.exists() else []:
            for candidate in candidates:
                nested = child / candidate
                if nested.is_dir():
                    return nested
    raise FileNotFoundError(f"Cannot find OMLX model directory for {model_name!r} in {source_dirs!r}")


def _parse_base_url(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8000
    return host, port


def _default_model_settings(model_name: str, *, is_default: bool) -> dict:
    return {
        "force_sampling": False,
        "thinking_budget_enabled": False,
        "turboquant_kv_enabled": False,
        "turboquant_kv_bits": 4,
        "specprefill_enabled": False,
        "is_pinned": True,
        "is_default": is_default,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sync_omlx_shared_runtime(
    config: dict,
    *,
    home_settings_path: Path | None = None,
    home_model_settings_path: Path | None = None,
) -> dict:
    settings_path = home_settings_path or Path.home() / ".omlx" / "settings.json"
    model_settings_path = home_model_settings_path or Path.home() / ".omlx" / "model_settings.json"
    existing_settings = load_omlx_home_settings(home_settings_path)
    existing_model_settings = load_omlx_home_model_settings(home_model_settings_path)

    settings = deepcopy(existing_settings) if existing_settings else {"version": "1.0"}
    model_cfg = settings.setdefault("model", {})
    source_dirs = _discover_source_model_dirs(config, home_settings_path)
    if not model_cfg.get("model_dirs"):
        model_cfg["model_dirs"] = [str(path) for path in source_dirs]
    if not model_cfg.get("model_dir") and model_cfg.get("model_dirs"):
        model_cfg["model_dir"] = model_cfg["model_dirs"][0]

    active_models = [Path(model).name for model in collect_omlx_runtime_models(config)]
    settings["active_models"] = active_models
    settings["model_dir_mode"] = _omlx_config(config).get("model_dir_mode", "config_union")

    model_settings = (
        deepcopy(existing_model_settings)
        if existing_model_settings
        else {"version": 1, "models": {}}
    )
    model_settings["version"] = model_settings.get("version", 1)
    model_entries = model_settings.setdefault("models", {})
    active_set = set(active_models)
    tracked_models = sorted(set(model_entries) | active_set | set(_discover_source_model_names(source_dirs)))

    for model_name in tracked_models:
        if model_name in active_set:
            continue
        entry = dict(model_entries.get(model_name) or {})
        entry["is_default"] = False
        entry["is_pinned"] = False
        model_entries[model_name] = entry

    for index, model_name in enumerate(active_models):
        entry = {
            **_default_model_settings(model_name, is_default=index == 0),
            **dict(model_entries.get(model_name) or {}),
        }
        entry["is_default"] = index == 0
        entry["is_pinned"] = True
        entry["force_sampling"] = False
        entry["thinking_budget_enabled"] = False
        entry["specprefill_enabled"] = False
        model_entries[model_name] = entry

    settings_changed = settings != existing_settings
    model_settings_changed = model_settings != existing_model_settings
    if settings_changed:
        _write_json(settings_path, settings)
    if model_settings_changed:
        _write_json(model_settings_path, model_settings)

    inactive_models = sorted(model_name for model_name in model_entries if model_name not in active_set)
    return {
        "settings_path": str(settings_path),
        "model_settings_path": str(model_settings_path),
        "active_models": active_models,
        "inactive_models": inactive_models,
        "settings_changed": settings_changed,
        "model_settings_changed": model_settings_changed,
        "changed": settings_changed or model_settings_changed,
    }


def find_omlx_command_prefix() -> list[str]:
    binary_candidates = [
        shutil.which("omlx"),
        "/opt/homebrew/bin/omlx",
        "/usr/local/bin/omlx",
        _APP_CLI_PATH,
    ]
    for candidate in binary_candidates:
        if candidate and Path(candidate).exists():
            return [candidate]

    raise RuntimeError("omlx executable not found on PATH and oMLX.app launcher was not found")


def setup_omlx_instance(
    config: dict,
    *,
    home_settings_path: Path | None = None,
    home_model_settings_path: Path | None = None,
) -> dict:
    instance_root = _instance_root(config)
    model_dir = instance_root / "models"
    cache_dir = instance_root / "cache"
    logs_dir = instance_root / "logs"
    run_dir = instance_root / "run"
    for directory in (model_dir, cache_dir, logs_dir, run_dir):
        directory.mkdir(parents=True, exist_ok=True)

    active_models = collect_omlx_runtime_models(config)
    source_dirs = _discover_source_model_dirs(config, home_settings_path)

    for existing in list(model_dir.iterdir()):
        if existing.name not in {Path(model).name for model in active_models}:
            if existing.is_symlink() or existing.is_file():
                existing.unlink()
            elif existing.is_dir():
                shutil.rmtree(existing)

    linked_models: list[str] = []
    for model in active_models:
        source_dir = _find_source_model_dir(model, source_dirs)
        target = model_dir / source_dir.name
        if target.exists() or target.is_symlink():
            if target.is_symlink() and target.resolve() == source_dir.resolve():
                linked_models.append(target.name)
                continue
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.symlink_to(source_dir, target_is_directory=True)
        linked_models.append(target.name)

    omlx = _omlx_config(config)
    host, port = _parse_base_url(omlx.get("base_url", "http://127.0.0.1:11435"))
    generated_settings = {
        "server": {"host": host, "port": port},
        "model": {"model_dirs": [str(model_dir)], "model_dir": str(model_dir)},
        "cache": {
            "enabled": bool(omlx.get("cache_enabled", True)),
            "ssd_cache_dir": str(cache_dir),
        },
        "active_models": active_models,
        "model_dir_mode": omlx.get("model_dir_mode", "config_union"),
    }
    _write_json(instance_root / "settings.generated.json", generated_settings)
    _write_json(instance_root / "settings.json", generated_settings)

    model_settings_path = home_model_settings_path or Path.home() / ".omlx" / "model_settings.json"
    if model_settings_path.exists():
        source_model_settings = json.loads(model_settings_path.read_text(encoding="utf-8"))
    else:
        source_model_settings = {"version": 1, "models": {}}
    source_entries = source_model_settings.get("models", {})
    model_settings = {"version": source_model_settings.get("version", 1), "models": {}}
    model_entries = model_settings["models"]
    for index, model in enumerate(active_models):
        model_name = Path(model).name
        model_entries[model_name] = {
            **_default_model_settings(model_name, is_default=index == 0),
            **source_entries.get(model_name, {}),
            "is_default": index == 0,
            "is_pinned": True,
            "force_sampling": False,
            "thinking_budget_enabled": False,
            "specprefill_enabled": False,
        }
    _write_json(instance_root / "model_settings.generated.json", model_settings)
    _write_json(instance_root / "model_settings.json", model_settings)

    return {
        "instance_root": str(instance_root),
        "model_dir": str(model_dir),
        "cache_dir": str(cache_dir),
        "logs_dir": str(logs_dir),
        "run_dir": str(run_dir),
        "active_models": active_models,
        "linked_models": linked_models,
        "cache_enabled": bool(omlx.get("cache_enabled", True)),
        "base_url": omlx.get("base_url", "http://127.0.0.1:11435"),
    }


def build_omlx_start_command(
    config: dict,
    *,
    omlx_command_prefix: list[str],
    instance_root: Path,
    model_dir: Path,
    cache_dir: Path,
) -> list[str]:
    omlx = _omlx_config(config)
    host, port = _parse_base_url(omlx.get("base_url", "http://127.0.0.1:11435"))
    command_prefix = list(omlx_command_prefix)
    if len(command_prefix) == 1 and command_prefix[0] == _APP_CLI_PATH:
        command_prefix = ["/usr/bin/env", "PYTHONNOUSERSITE=1", *command_prefix]
    command = [
        *command_prefix,
        "serve",
        "--base-path",
        str(instance_root),
        "--model-dir",
        str(model_dir),
        "--host",
        host,
        "--port",
        str(port),
    ]
    if omlx.get("cache_enabled", True):
        command.extend(["--paged-ssd-cache-dir", str(cache_dir)])
    api_key = omlx.get("api_key", "")
    if api_key:
        command.extend(["--api-key", api_key])
    return command
