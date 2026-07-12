import subprocess
from collections.abc import Callable
from pathlib import Path

import yaml

from ..adapters.models.local_runtime import probe_local_runtime
from ..adapters.state.processed_sqlite import SQLiteProcessedRepository
from ..adapters.state.sqlite_runtime import SQLiteRuntimeRepository
from ..app.rescore_service import RescoreService
from ..app.review_runtime import build_review_job_executor as _shared_build_review_job_executor
from ..app.review_service import ReviewRunService
from ..utils.config_validator import normalize_config, validate_config
from ..utils.constants import scene_key_from_display
from ..utils.progress import RichProgress
from ..utils.runtime_paths import ensure_runtime_paths


def load_raw_config(path: str) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def load_config(path: str) -> dict:
    return normalize_config(load_raw_config(path))


def _check_exiftool_version(min_version=(12, 0)):
    try:
        result = subprocess.run(["exiftool", "-ver"], capture_output=True, text=True, timeout=5)
        ver = tuple(int(x) for x in result.stdout.strip().split("."))
        if ver < min_version:
            raise RuntimeError(
                f"exiftool >= {min_version[0]}.{min_version[1]} required, got {'.'.join(map(str, ver))}"
            )
    except FileNotFoundError:
        raise RuntimeError(
            "exiftool not found. Install it on macOS with 'brew install exiftool', "
            "on Windows with 'choco install exiftool', or download the official executable."
        )


def apply_run_overrides(config: dict, args) -> dict:
    config = normalize_config(config)
    config["input_dir"] = args.input_dir
    if getattr(args, "reprocess", False):
        config["reprocess"] = True
    if getattr(args, "scorers", None):
        enabled = set(args.scorers.split(","))
        for name in config["scorers"]:
            config["scorers"][name]["enabled"] = name in enabled
    if getattr(args, "no_visual_merge", False):
        config["grouping"]["visual_similarity"]["enabled"] = False
    return config


def cmd_run(args, config):
    validate_config(config)
    config = apply_run_overrides(config, args)
    _check_exiftool_version()
    _sync_shared_omlx_models_if_needed(config)
    input_dir = Path(args.input_dir)
    runtime_paths = ensure_runtime_paths(input_dir)
    runtime_paths.work_dir.mkdir(parents=True, exist_ok=True)
    runtime_repo = SQLiteRuntimeRepository(runtime_paths.db_path)
    review_service = ReviewRunService(runtime_repo)
    preflight_hook = _build_runtime_probe_preflight_hook(runtime_repo, config)
    with SQLiteProcessedRepository(
        runtime_paths.db_path,
        reprocess=config.get("reprocess", False),
    ) as state:
        base_progress = RichProgress(log_path=str(runtime_paths.log_path), log_level=config.get("log_level", "info"))
        review_service.run(
            input_dir=str(input_dir),
            config=config,
            state=state,
            progress=base_progress,
            dry_run=args.dry_run,
            preflight_hook=preflight_hook,
            build_executor=_build_review_job_executor,
        )


def _sync_shared_omlx_models_if_needed(config: dict) -> None:
    if config.get("backend") != "omlx":
        return
    from ..adapters.models.omlx.instance import is_configured_shared_omlx_runtime
    from ..app.omlx_instance_service import OMLXInstanceService

    if not is_configured_shared_omlx_runtime(config):
        return

    service = OMLXInstanceService()
    summary = service.sync_shared(config)
    status = service.status(config)
    if summary.get("changed") or not status.get("reachable", False):
        summary = service.restart_shared(config)
        active_models = ", ".join(summary.get("active_models", [])) or "(none)"
        print(f"Restarted shared oMLX runtime with active models: {active_models}")
        if summary.get("inactive_models"):
            inactive_models = ", ".join(summary.get("inactive_models", []))
            print(f"Inactive shared desktop models remain installed but unpinned: {inactive_models}")


def _build_review_job_executor(
    *,
    repository: SQLiteRuntimeRepository,
    config: dict,
    state: SQLiteProcessedRepository,
    progress: RichProgress,
    dry_run: bool,
):
    return _shared_build_review_job_executor(
        repository=repository,
        config=config,
        state=state,
        progress=progress,
        dry_run=dry_run,
    )


def _build_runtime_probe_preflight_hook(
    runtime_repo: SQLiteRuntimeRepository,
    config: dict,
) -> Callable[[str, str], None] | None:
    if config.get("backend") == "local":
        return _build_local_runtime_preflight_hook(runtime_repo, config)
    if config.get("backend") != "omlx":
        return None
    from ..app.omlx_instance_service import OMLXInstanceService

    runtime_cfg = config.get("omlx", {}).get("runtime", {})
    if not bool(runtime_cfg.get("probe_on_run", True)):
        return None

    def _preflight_hook(session_id: str, job_id: str) -> None:
        try:
            summary = OMLXInstanceService().status(config)
            capability_valid = bool(summary.get("capability_valid"))
            event_type = "runtime_probe_passed" if capability_valid else "runtime_probe_failed"
            payload = {
                "backend": config.get("backend"),
                "probe_on_run": bool(runtime_cfg.get("probe_on_run", True)),
                "capability_valid": capability_valid,
                "capability_failure": summary.get("capability_failure"),
                "failure_guidance": summary.get("failure_guidance"),
                "capability_profile": summary.get("capability_profile"),
                "base_url": summary.get("base_url"),
                "instance_root": summary.get("instance_root"),
                "reachable": summary.get("reachable"),
                "runtime_mode": summary.get("runtime_mode"),
                "shared_desktop_running": summary.get("shared_desktop_running"),
                "instance_matches": summary.get("instance_matches"),
                "effective_model_set_matches": summary.get("effective_model_set_matches"),
                "served_models_catalog_superset": summary.get("served_models_catalog_superset"),
            }
            runtime_repo.append_event(
                session_id=session_id,
                job_id=job_id,
                event_type=event_type,
                payload=payload,
            )
            runtime_repo.upsert_artifact(
                job_id=job_id,
                job_file_id=None,
                kind="runtime_probe",
                uri=f"runtime://omlx-probe/{'passed' if capability_valid else 'failed'}",
                metadata=payload,
            )
            if capability_valid:
                return
            failure = summary.get("capability_failure") or {}
            guidance = summary.get("failure_guidance") or (
                "Review the OMLX runtime configuration and restart the dedicated instance."
            )
            summary_text = failure.get("summary") or "OMLX capability requirements are not satisfied."
            code = failure.get("code")
            message = "OMLX runtime probe failed"
            if code:
                message += f" ({code})"
            message += f": {summary_text} {guidance}"
            raise RuntimeError(message)
        except Exception as error:
            if isinstance(error, RuntimeError) and str(error).startswith("OMLX runtime probe failed"):
                raise
            payload = {
                "backend": config.get("backend"),
                "probe_on_run": bool(runtime_cfg.get("probe_on_run", True)),
                "capability_valid": False,
                "capability_failure": {"code": "probe_error", "summary": str(error)},
                "failure_guidance": "Review the OMLX runtime configuration and restart the dedicated instance.",
                "error": str(error),
            }
            runtime_repo.append_event(
                session_id=session_id,
                job_id=job_id,
                event_type="runtime_probe_failed",
                payload=payload,
            )
            runtime_repo.upsert_artifact(
                job_id=job_id,
                job_file_id=None,
                kind="runtime_probe",
                uri="runtime://omlx-probe/failed",
                metadata=payload,
            )
            raise RuntimeError(
                "OMLX runtime probe failed: "
                f"{error}. Review the OMLX runtime configuration and restart the dedicated instance."
            ) from error

    return _preflight_hook


def _build_local_runtime_preflight_hook(
    runtime_repo: SQLiteRuntimeRepository,
    config: dict,
) -> Callable[[str, str], None]:
    def _preflight_hook(session_id: str, job_id: str) -> None:
        try:
            payload = probe_local_runtime(config)
        except Exception as error:  # pragma: no cover - defensive preflight boundary
            payload = {
                "backend": config.get("backend"),
                "runtime": config.get("inference", {}).get("runtime"),
                "enforce_available": bool(
                    config.get("inference", {}).get("enforce_available", False)
                ),
                "heuristic_scoring_active": True,
                "capability_valid": False,
                "capability_failure": {"code": "probe_error", "summary": str(error)},
            }

        capability_valid = bool(payload.get("capability_valid"))
        enforce_available = bool(payload.get("enforce_available", False))
        event_type = "runtime_preflight_passed" if capability_valid else "runtime_preflight_warned"
        runtime = payload.get("runtime") or "unknown"
        status = "passed" if capability_valid else "warned"
        runtime_repo.append_event(
            session_id=session_id,
            job_id=job_id,
            event_type=event_type,
            payload=payload,
        )
        runtime_repo.upsert_artifact(
            job_id=job_id,
            job_file_id=None,
            kind="runtime_preflight",
            uri=f"runtime://local/{runtime}/{status}",
            metadata=payload,
        )
        if capability_valid or not enforce_available:
            return
        failure = payload.get("capability_failure") or {}
        summary = failure.get("summary") or "local runtime preflight failed"
        code = failure.get("code")
        message = "Local runtime preflight failed"
        if code:
            message += f" ({code})"
        message += f": {summary}"
        raise RuntimeError(message)

    return _preflight_hook


def cmd_rescore(args, config):
    config = normalize_config(config)
    scene_keys = [scene_key_from_display(scene) for scene in args.scene] if getattr(args, "scene", None) else None
    with SQLiteProcessedRepository(args.dir) as repository:
        updated = RescoreService(repository).run(
            scene_filters=scene_keys,
            scene_weights=config.get("scene_profiles", {}),
            scoring_config={
                **config.get("scoring", {}),
                "decision_policy": config.get("decision_policy", {}),
                "screening_policy": config.get("screening_policy", {}),
            },
            scorers_config=config.get("scorers", {}),
        )
    print(f"Rejudged {updated} files.")


def configure_run_parser(parser):
    from ..shells.cli.main import configure_run_parser as _configure_run_parser

    return _configure_run_parser(parser)
