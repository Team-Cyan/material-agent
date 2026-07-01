import json
import subprocess
from pathlib import Path

from ..app.omlx_instance_service import OMLXInstanceService


_OMLX_APP_PATH = Path("/Applications/oMLX.app")


def cmd_setup_omlx(args, config):
    summary = OMLXInstanceService().setup(config)
    print(f"omlx setup complete: {summary['instance_root']}")
    print(f"linked models: {', '.join(summary['linked_models']) or '(none)'}")


def _open_omlx_app() -> None:
    if not _OMLX_APP_PATH.exists():
        raise RuntimeError(f"oMLX.app not found at {_OMLX_APP_PATH}")
    subprocess.run(["open", "-a", str(_OMLX_APP_PATH)], check=True)


def cmd_start_omlx(args, config):
    service = OMLXInstanceService()
    if getattr(args, "dedicated", False):
        summary = service.start(config)
        if summary["started"]:
            print(f"omlx started: pid={summary['pid']} url={summary['base_url']}")
        else:
            print(f"omlx already running: pid={summary['pid']} url={summary['base_url']}")
        if summary.get("served_models"):
            print(f"served models: {', '.join(summary['served_models'])}")
        return

    restart_shared = bool(getattr(args, "restart_shared", False))
    if restart_shared:
        sync_summary = service.restart_shared(config)
        print(f"restarted {_OMLX_APP_PATH} (shared desktop runtime)")
        if sync_summary.get("terminated_pids"):
            terminated = ", ".join(str(pid) for pid in sync_summary["terminated_pids"])
            print(f"terminated shared desktop pids: {terminated}")
    else:
        sync_summary = service.sync_shared(config)
        _open_omlx_app()
        service.wait_until_ready(config)
        print(f"opened {_OMLX_APP_PATH} (shared desktop runtime)")
    print(f"active models: {', '.join(sync_summary['active_models']) or '(none)'}")
    if sync_summary["inactive_models"]:
        print(f"inactive models: {', '.join(sync_summary['inactive_models'])}")
    if sync_summary["changed"] and not restart_shared:
        print("if oMLX.app was already running, run `material-agent omlx-start --restart-shared` to apply the updated active model set")
    print("use --dedicated only when you explicitly want the isolated material-agent runtime")


def cmd_status_omlx(args, config):
    summary = OMLXInstanceService().status(config)
    if getattr(args, "json", False):
        print(json.dumps(summary, ensure_ascii=False))
        return
    profile = summary.get("capability_profile", {})
    print(f"instance_root: {summary['instance_root']}")
    print(f"runtime_mode: {summary.get('runtime_mode')}")
    print(f"reachable: {summary['reachable']}")
    print(f"instance_matches: {summary['instance_matches']}")
    print(f"effective_model_set_matches: {summary.get('effective_model_set_matches')}")
    if summary.get("runtime_mode") == "shared_desktop":
        print(f"shared_desktop_running: {summary.get('shared_desktop_running')}")
        if summary.get("shared_desktop_pids"):
            print(
                "shared_desktop_pids: "
                + ", ".join(str(pid) for pid in summary.get("shared_desktop_pids", []))
            )
    else:
        print(f"pid_alive: {summary['pid_alive']}")
    print(f"active models: {', '.join(summary.get('active_models', [])) or '(none)'}")
    print(f"linked models: {', '.join(summary['linked_models']) or '(none)'}")
    if summary.get("served_models"):
        print(f"served models: {', '.join(summary['served_models'])}")
    if summary.get("served_models_catalog_superset"):
        print("served_models_catalog_superset: true")
        print("note: on shared oMLX desktop runtime, /v1/models may behave like an installed-model catalog instead of the live pinned set")
    version = summary.get("version", profile.get("version"))
    structured_outputs = summary.get("structured_outputs", profile.get("structured_outputs"))
    xgrammar = summary.get("xgrammar", profile.get("xgrammar"))
    settings_drift = summary.get("settings_drift", profile.get("settings_drift", []))
    if version is not None:
        print(f"version: {version}")
    if structured_outputs is not None or "structured_outputs" in profile:
        print(f"structured_outputs: {structured_outputs}")
    if xgrammar is not None or "xgrammar" in profile:
        print(f"xgrammar: {xgrammar}")
    if settings_drift:
        print(f"settings_drift: {'; '.join(settings_drift)}")
    print(f"capability_valid: {summary.get('capability_valid')}")
    if summary.get("capability_failure"):
        print(f"capability_failure: {summary['capability_failure']['code']}")
        print(f"capability_summary: {summary['capability_failure']['summary']}")
    if summary.get("failure_guidance"):
        print(f"guidance: {summary['failure_guidance']}")
    if summary.get("error") and not summary["reachable"]:
        print(f"error: {summary['error']}")
