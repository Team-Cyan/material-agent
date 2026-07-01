import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from ..adapters.models.omlx.failure_guidance import build_omlx_failure_guidance
from ..adapters.models.omlx.instance import (
    build_omlx_start_command,
    collect_omlx_runtime_models,
    discover_local_omlx_version,
    discover_omlx_api_key,
    find_omlx_command_prefix,
    is_configured_shared_omlx_runtime,
    is_local_omlx_base_url,
    load_omlx_home_settings,
    load_omlx_home_model_settings,
    sync_omlx_shared_runtime,
    setup_omlx_instance,
)
from ..adapters.models.omlx.probe import probe_omlx_capabilities, validate_omlx_capability


class OMLXInstanceService:
    def __init__(
        self,
        *,
        home_settings_path: Path | None = None,
        home_model_settings_path: Path | None = None,
    ):
        self.home_settings_path = home_settings_path
        self.home_model_settings_path = home_model_settings_path

    def setup(self, config: dict) -> dict:
        return setup_omlx_instance(
            config,
            home_settings_path=self.home_settings_path,
            home_model_settings_path=self.home_model_settings_path,
        )

    def sync_shared(self, config: dict) -> dict:
        self._require_shared_desktop_runtime(config)
        return sync_omlx_shared_runtime(
            config,
            home_settings_path=self.home_settings_path,
            home_model_settings_path=self.home_model_settings_path,
        )

    def restart_shared(self, config: dict) -> dict:
        self._require_shared_desktop_runtime(config)
        summary = self.sync_shared(config)
        terminated_pids = self._shared_desktop_pids(config)
        for pid in terminated_pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                continue
        if terminated_pids:
            self._wait_for_pids_to_exit(terminated_pids)
        subprocess.run(["open", "-a", "/Applications/oMLX.app"], check=True)
        self._wait_until_ready(config)
        return {
            **summary,
            "terminated_pids": terminated_pids,
            "restarted": True,
        }

    def wait_until_ready(self, config: dict, timeout_seconds: float = 30.0) -> dict:
        self._wait_until_ready(config, timeout_seconds=timeout_seconds)
        return self.status(config)

    def status(self, config: dict) -> dict:
        omlx = config.get("omlx", {})
        instance_root = Path(omlx.get("instance_root", "~/.material-agent/omlx")).expanduser()
        model_dir = instance_root / "models"
        cache_dir = instance_root / "cache"
        run_dir = instance_root / "run"
        pid_path = run_dir / "omlx.pid"
        pid = None
        pid_alive = False
        if pid_path.exists():
            try:
                pid = int(pid_path.read_text(encoding="utf-8").strip())
                os.kill(pid, 0)
                pid_alive = True
            except (OSError, ValueError):
                pid_alive = False

        base_url = omlx.get("base_url", "http://127.0.0.1:11435").rstrip("/")
        headers = {}
        api_key = discover_omlx_api_key(
            config,
            home_settings_path=self.home_settings_path,
        )
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        active_models = collect_omlx_runtime_models(config)
        shared_runtime = is_configured_shared_omlx_runtime(
            config,
            home_settings_path=self.home_settings_path,
        )
        if shared_runtime:
            home_settings = load_omlx_home_settings(self.home_settings_path)
            linked_models = sorted(
                str(model).strip()
                for model in home_settings.get("active_models", [])
                if str(model).strip()
            )
            if not linked_models:
                model_settings = load_omlx_home_model_settings(self.home_model_settings_path)
                entries = model_settings.get("models", {}) if isinstance(model_settings, dict) else {}
                linked_models = sorted(
                    model_name
                    for model_name, options in entries.items()
                    if isinstance(options, dict) and bool(options.get("is_pinned", False))
                )
        else:
            linked_models = sorted(path.name for path in model_dir.iterdir()) if model_dir.exists() else []
        shared_desktop_pids = self._shared_desktop_pids(config) if shared_runtime else []
        runtime_cfg = omlx.get("runtime", {})
        profile = probe_omlx_capabilities(
            base_url=base_url,
            headers=headers,
            linked_models=linked_models,
            expected_models=active_models,
            timeout=5.0,
            local_version_fallback=discover_local_omlx_version() if is_local_omlx_base_url(base_url) else None,
        )
        capability_valid, capability_failure = validate_omlx_capability(
            profile,
            required_version=runtime_cfg.get("required_version"),
            require_structured_outputs=bool(runtime_cfg.get("require_structured_outputs", False)),
            require_xgrammar=bool(runtime_cfg.get("require_xgrammar", False)),
            require_dedicated_instance=bool(runtime_cfg.get("enforce_dedicated_instance", True)),
        )
        failure_guidance = build_omlx_failure_guidance(
            capability_failure,
            profile,
            base_url=base_url,
            instance_root=str(instance_root),
        )

        return {
            "instance_root": str(instance_root),
            "model_dir": str(model_dir),
            "cache_dir": str(cache_dir),
            "active_models": active_models,
            "linked_models": linked_models,
            "pid": pid,
            "pid_alive": pid_alive,
            "runtime_mode": "shared_desktop" if shared_runtime else "dedicated",
            "shared_desktop_pids": shared_desktop_pids,
            "shared_desktop_running": bool(shared_desktop_pids) if shared_runtime else False,
            "reachable": profile.reachable,
            "instance_matches": profile.instance_matches,
            "effective_model_set_matches": getattr(
                profile, "effective_model_set_matches", profile.instance_matches
            ),
            "served_models_catalog_superset": getattr(profile, "served_models_catalog_superset", False),
            "served_models": profile.served_models,
            "base_url": base_url,
            "cache_enabled": bool(omlx.get("cache_enabled", True)),
            "error": profile.error,
            "version": profile.version,
            "structured_outputs": profile.structured_outputs,
            "xgrammar": profile.xgrammar,
            "settings_drift": profile.settings_drift,
            "capability_profile": profile.to_dict(),
            "capability_valid": capability_valid,
            "capability_failure": capability_failure.to_dict() if capability_failure else None,
            "failure_guidance": failure_guidance,
        }

    def start(self, config: dict) -> dict:
        summary = self.setup(config)
        status = self.status(config)
        if status["reachable"] and status.get("capability_valid", False):
            return {
                **summary,
                **status,
                "started": False,
                "command": None,
            }
        if status["reachable"] and not status.get("capability_valid", False):
            failure = status.get("capability_failure") or {}
            summary_text = failure.get("summary") or "OMLX capability requirements are not satisfied."
            guidance = status.get("failure_guidance") or "Review the OMLX runtime configuration and restart."
            raise RuntimeError(f"{summary_text} {guidance}")

        omlx_command_prefix = find_omlx_command_prefix()
        instance_root = Path(summary["instance_root"])
        model_dir = Path(summary["model_dir"])
        cache_dir = Path(summary["cache_dir"])
        command = build_omlx_start_command(
            config,
            omlx_command_prefix=omlx_command_prefix,
            instance_root=instance_root,
            model_dir=model_dir,
            cache_dir=cache_dir,
        )

        logs_dir = Path(summary["logs_dir"])
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "omlx.log"
        run_dir = Path(summary["run_dir"])
        run_dir.mkdir(parents=True, exist_ok=True)
        pid_path = run_dir / "omlx.pid"

        with log_path.open("a", encoding="utf-8") as handle:
            process = subprocess.Popen(
                command,
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        pid_path.write_text(f"{process.pid}\n", encoding="utf-8")

        self._wait_until_ready(config)
        return {
            **summary,
            **self.status(config),
            "started": True,
            "command": command,
        }

    def _wait_until_ready(self, config: dict, timeout_seconds: float = 30.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        last_status = None
        while time.monotonic() < deadline:
            status = self.status(config)
            last_status = status
            if status["reachable"] and status.get("capability_valid", False):
                return
            time.sleep(0.5)
        if last_status and last_status["reachable"]:
            failure = last_status.get("capability_failure") or {}
            summary_text = failure.get("summary") or "OMLX instance became reachable but is still invalid."
            guidance = last_status.get("failure_guidance") or "Review the OMLX runtime configuration and restart."
            raise RuntimeError(f"{summary_text} {guidance}")
        raise RuntimeError("OMLX instance did not become ready before timeout")

    def _shared_desktop_pids(self, config: dict) -> list[int]:
        omlx = config.get("omlx", {})
        base_url = str(omlx.get("base_url", "http://127.0.0.1:11435")).rstrip("/")
        if not is_local_omlx_base_url(base_url):
            return []

        parsed = urlparse(base_url)
        port = parsed.port or 11435
        shared_root = str((Path.home() / ".omlx").expanduser())
        app_command = "/Applications/oMLX.app/Contents/MacOS/oMLX"
        server_prefix = "/Applications/oMLX.app/Contents/MacOS/python3 -m omlx.cli serve"
        try:
            result = subprocess.run(
                ["ps", "-ax", "-o", "pid=,command="],
                capture_output=True,
                check=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return []

        pids: list[int] = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            pid_text, command = parts
            try:
                pid = int(pid_text)
            except ValueError:
                continue
            if command == app_command:
                pids.append(pid)
                continue
            if server_prefix in command and f"--base-path {shared_root}" in command and f"--port {port}" in command:
                pids.append(pid)
        return pids

    def _wait_for_pids_to_exit(self, pids: list[int], timeout_seconds: float = 10.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        remaining = set(pids)
        while remaining and time.monotonic() < deadline:
            for pid in list(remaining):
                try:
                    os.kill(pid, 0)
                except OSError:
                    remaining.discard(pid)
            if remaining:
                time.sleep(0.2)
        if remaining:
            joined = ", ".join(str(pid) for pid in sorted(remaining))
            raise RuntimeError(f"Shared oMLX processes did not exit: {joined}")

    def _require_shared_desktop_runtime(self, config: dict) -> None:
        if is_configured_shared_omlx_runtime(config, home_settings_path=self.home_settings_path):
            return
        raise RuntimeError(
            "Shared desktop oMLX management requires a local base_url that matches ~/.omlx settings. "
            "Use --dedicated for the isolated runtime instead."
        )
