from __future__ import annotations

from pathlib import Path

from .probe import OMLXCapabilityFailure, OMLXCapabilityProfile


def _runtime_log_hint(instance_root: str) -> str | None:
    logs_dir = Path(instance_root) / "logs"
    for name in ("omlx.log", "server.log"):
        path = logs_dir / name
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[-8000:]
        except Exception:
            continue
        if "Failed to initialize GrammarCompiler" in text and "No module named 'torch'" in text:
            return (
                "The local oMLX runtime log shows `Failed to initialize GrammarCompiler: "
                "No module named 'torch'`, so strict grammar support did not come up. "
                "Reinstall oMLX with grammar extras or add the missing grammar dependencies "
                "before restarting the dedicated instance."
            )
    return None


def build_omlx_failure_guidance(
    failure: OMLXCapabilityFailure | None,
    profile: OMLXCapabilityProfile,
    *,
    base_url: str,
    instance_root: str,
) -> str:
    if failure is None:
        return "OMLX capability requirements are satisfied."

    if failure.code == "omlx_unreachable":
        auth_hint = ""
        if profile.error and ("401" in profile.error or "unauthorized" in profile.error.lower()):
            auth_hint = " If the server requires auth, set `omlx.api_key` or let material-agent read it from `~/.omlx/settings.json`."
        return (
            f"OMLX is unreachable at {base_url}. Install oMLX if needed, open `/Applications/oMLX.app`, "
            f"or run `material-agent omlx-start --dedicated` only if you explicitly want the dedicated runtime under {instance_root}."
            f"{auth_hint}"
        )
    if failure.code == "version_too_old":
        return (
            f"Upgrade oMLX to satisfy {failure.details.get('required_version', 'the required version')}. "
            "Older builds may not expose the structured output runtime expected by material-agent."
        )
    if failure.code == "version_unknown":
        return (
            "material-agent could not confirm the running OMLX version. Use oMLX >=0.3.0 and verify that "
            "the runtime exposes `/version` or another diagnostic endpoint that reports the server version."
        )
    if failure.code == "structured_outputs_missing":
        log_hint = _runtime_log_hint(instance_root)
        if log_hint:
            return log_hint
        return (
            "Structured outputs are required for material-agent JSON contracts. Upgrade oMLX to >=0.3.0 "
            "and verify the runtime exposes structured output support for the selected models."
        )
    if failure.code == "structured_outputs_unknown":
        log_hint = _runtime_log_hint(instance_root)
        if log_hint:
            return log_hint
        return (
            "material-agent could not confirm structured output support. Verify the runtime is oMLX >=0.3.0, "
            "then rerun `material-agent omlx-status` and check that `structured_outputs` is reported explicitly."
        )
    if failure.code == "xgrammar_missing":
        log_hint = _runtime_log_hint(instance_root)
        if log_hint:
            return log_hint
        return (
            "xgrammar support is required for strict schema guidance. Reinstall or upgrade oMLX to a build "
            "with xgrammar enabled, then restart the dedicated instance."
        )
    if failure.code == "xgrammar_unknown":
        log_hint = _runtime_log_hint(instance_root)
        if log_hint:
            return log_hint
        return (
            "material-agent could not confirm xgrammar support. Reinstall or upgrade oMLX to a build with "
            "xgrammar enabled, then rerun `material-agent omlx-status`."
        )
    if failure.code == "instance_mismatch":
        return (
            "The reachable server model set does not exactly match the configured models material-agent linked for this "
            "config. Stop the shared server or point omlx.base_url at the dedicated runtime, then rerun "
            "`material-agent omlx-status`."
        )

    details = f" Latest error: {profile.error}." if profile.error else ""
    return f"Review the OMLX runtime configuration and restart oMLX.app or the dedicated runtime.{details}"
