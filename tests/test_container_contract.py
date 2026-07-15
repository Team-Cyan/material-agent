import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_entrypoint(tmp_path: Path, dry_run_value: str) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    _write_executable(fake_bin / "material-agent", '#!/bin/sh\nprintf "%s\\n" "$*"\n')
    # Contract tests may themselves run in a root CI container. Keep these
    # argument-routing tests on the already-unprivileged entrypoint branch.
    _write_executable(fake_bin / "id", '#!/bin/sh\n[ "$1" = "-u" ] && echo 1000\n')
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "MATERIAL_AGENT_DRY_RUN": dry_run_value,
        "MATERIAL_AGENT_INPUT_DIR": "/photos",
        "MATERIAL_AGENT_CONFIG": "/app/config/config.yaml",
    }
    return subprocess.run(
        ["sh", str(ROOT / "docker" / "entrypoint.sh")],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def _run_root_entrypoint(
    tmp_path: Path,
    *,
    puid: str = "99",
    pgid: str = "100",
    input_dir: str = "/photos",
    work_dir: Path | None = None,
    state_symlink: bool = False,
    cache_symlink: bool = False,
    prepare_runtime: bool = True,
    command_args: tuple[str, ...] = (),
) -> tuple[subprocess.CompletedProcess[str], str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    command_log = tmp_path / "commands.log"
    _write_executable(
        fake_bin / "id",
        "#!/bin/sh\n"
        'if [ "$1" = "-u" ] && [ "$#" -eq 1 ]; then echo 0; '
        'elif [ "$1" = "-g" ]; then echo 1000; else echo 1000; fi\n',
    )
    for name in ("groupmod", "usermod", "chown", "gosu"):
        _write_executable(
            fake_bin / name,
            f'#!/bin/sh\nprintf "{name} %s\\n" "$*" >> "$COMMAND_LOG"\n',
        )
    _write_executable(
        fake_bin / "realpath",
        "#!/bin/sh\nfor value do last=$value; done\nprintf '%s\\n' \"$last\"\n",
    )
    work_dir = work_dir or (tmp_path / "work")
    cache_dir = work_dir / "openvino-cache"
    if prepare_runtime:
        cache_dir.mkdir(parents=True)
        runtime_paths = (
            work_dir / "run.log",
            work_dir / "run.lock",
            cache_dir / "compiled.blob",
        )
        for path in runtime_paths:
            path.write_bytes(b"root-owned")
            path.chmod(0o600)
        state_path = work_dir / "state.db"
        if state_symlink:
            target = tmp_path / "outside-state.db"
            target.write_bytes(b"must-not-be-chowned")
            state_path.symlink_to(target)
        else:
            state_path.write_bytes(b"root-owned")
            state_path.chmod(0o600)
        if cache_symlink:
            target = tmp_path / "outside-cache-target"
            target.write_bytes(b"must-not-be-chowned")
            (cache_dir / "unsafe-link").symlink_to(target)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "COMMAND_LOG": str(command_log),
        "PUID": puid,
        "PGID": pgid,
        "MATERIAL_AGENT_INPUT_DIR": input_dir,
        "MATERIAL_AGENT_CONFIG": "/app/config/config.yaml",
        "MATERIAL_AGENT_WORK_DIR": str(work_dir),
    }
    result = subprocess.run(
        ["sh", str(ROOT / "docker" / "entrypoint.sh"), *command_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    return result, command_log.read_text(encoding="utf-8") if command_log.exists() else ""


def test_entrypoint_accepts_common_true_values_without_failing_open(tmp_path):
    for value in ("true", "TRUE", "1", "yes", "on"):
        result = _run_entrypoint(tmp_path / value.lower(), value)
        assert result.returncode == 0
        assert result.stdout.strip().endswith(
            "run /photos --config /app/config/config.yaml --dry-run"
        )


def test_entrypoint_rejects_unknown_dry_run_value(tmp_path):
    result = _run_entrypoint(tmp_path, "tru")

    assert result.returncode == 64
    assert "Invalid MATERIAL_AGENT_DRY_RUN value" in result.stderr
    assert result.stdout == ""


def test_root_entrypoint_prepares_identity_then_drops_privileges(tmp_path):
    result, command_log = _run_root_entrypoint(tmp_path)

    assert result.returncode == 0
    assert "groupmod -o -g 100 material-agent" in command_log
    assert "usermod -o -u 99 material-agent" in command_log
    assert "usermod -g 100 material-agent" in command_log
    assert f"chown -h 99:100 {tmp_path / 'work'} /home/material-agent" in command_log
    assert f"chown -h 99:100 {tmp_path / 'work' / 'state.db'}" in command_log
    assert f"chown -h 99:100 {tmp_path / 'work' / 'run.log'}" in command_log
    assert f"chown -h 99:100 {tmp_path / 'work' / 'run.lock'}" in command_log
    assert str(tmp_path / "work" / "openvino-cache" / "compiled.blob") in command_log
    assert (
        "gosu material-agent material-agent run /photos "
        "--config /app/config/config.yaml" in command_log
    )
    assert "chown 99:100 /photos" not in command_log


def test_root_entrypoint_rejects_root_puid(tmp_path):
    result, command_log = _run_root_entrypoint(tmp_path, puid="0")

    assert result.returncode == 64
    assert "Invalid PUID value" in result.stderr
    assert command_log == ""


def test_root_entrypoint_refuses_work_dir_inside_photo_source(tmp_path):
    input_dir = tmp_path / "photos"
    result, command_log = _run_root_entrypoint(
        tmp_path,
        input_dir=str(input_dir),
        work_dir=input_dir / ".material-agent",
    )

    assert result.returncode == 64
    assert "must stay outside MATERIAL_AGENT_INPUT_DIR" in result.stderr
    assert "chown" not in command_log


def test_root_entrypoint_uses_explicit_run_input_for_source_protection(tmp_path):
    explicit_input = tmp_path / "explicit-photos"
    result, command_log = _run_root_entrypoint(
        tmp_path,
        work_dir=explicit_input / ".material-agent",
        command_args=("material-agent", "run", str(explicit_input)),
    )

    assert result.returncode == 64
    assert "must stay outside MATERIAL_AGENT_INPUT_DIR" in result.stderr
    assert "chown" not in command_log


def test_root_entrypoint_finds_run_input_after_options_for_source_protection(tmp_path):
    explicit_input = tmp_path / "explicit-photos"
    result, command_log = _run_root_entrypoint(
        tmp_path,
        work_dir=explicit_input / ".material-agent",
        command_args=(
            "material-agent",
            "run",
            "--config",
            "/app/config/config.yaml",
            "--dry-run",
            str(explicit_input),
        ),
    )

    assert result.returncode == 64
    assert "must stay outside MATERIAL_AGENT_INPUT_DIR" in result.stderr
    assert "chown" not in command_log


@pytest.mark.parametrize(
    "command_args",
    [
        ("material-agent", "run", "--conf", "/app/config/config.yaml", "/photos"),
        ("material-agent", "run", "--bogus", "dummy", "/photos"),
        ("material-agent", "run", "--config"),
        ("material-agent", "run", "--"),
    ],
)
def test_root_entrypoint_rejects_malformed_run_options_before_chown(tmp_path, command_args):
    result, command_log = _run_root_entrypoint(
        tmp_path,
        work_dir=tmp_path / "photos" / ".material-agent",
        command_args=command_args,
        prepare_runtime=False,
    )

    assert result.returncode == 64
    assert command_log == ""


@pytest.mark.parametrize(
    "command_args",
    [
        ("material-agent", "reset-ai", "--dir", "/other-photos"),
        ("material-agent", "rewrite-xmp", "--config", "config.yaml", "--dir=/other-photos"),
        ("material-agent", "rescore", "--scene", "people", "--dir", "/other-photos"),
        ("material-agent", "fix-db", "--dir", "/other-photos"),
    ],
)
def test_root_entrypoint_protects_explicit_maintenance_target(tmp_path, command_args):
    target = tmp_path / "other-photos"
    rewritten_args = tuple(
        str(target) if value == "/other-photos" else value.replace("/other-photos", str(target))
        for value in command_args
    )
    result, command_log = _run_root_entrypoint(
        tmp_path,
        input_dir="/photos",
        work_dir=target / ".material-agent",
        command_args=rewritten_args,
        prepare_runtime=False,
    )

    assert result.returncode == 64
    assert "must stay outside MATERIAL_AGENT_INPUT_DIR" in result.stderr
    assert "chown" not in command_log


@pytest.mark.parametrize(
    "command_args",
    [
        ("material-agent", "reset-ai", "--dir"),
        ("material-agent", "reset-ai", "--dir="),
        ("material-agent", "reset-ai", "--dir", "/a", "--dir=/b"),
        ("material-agent", "reset-ai", "--di", "/photos"),
    ],
)
def test_root_entrypoint_rejects_malformed_maintenance_target_before_chown(tmp_path, command_args):
    result, command_log = _run_root_entrypoint(
        tmp_path,
        input_dir="/photos",
        work_dir=tmp_path / "other-photos" / ".material-agent",
        command_args=command_args,
        prepare_runtime=False,
    )

    assert result.returncode == 64
    assert command_log == ""


@pytest.mark.parametrize(
    "command_args",
    [
        ("material-agent", "reset-ai", "--dir", "/other-photos", "--help"),
        ("material-agent", "reset-ai", "--help", "--dir=/other-photos"),
        ("material-agent", "run", "--help", "/other-photos"),
    ],
)
def test_root_entrypoint_help_does_not_bypass_explicit_target_protection(tmp_path, command_args):
    target = tmp_path / "other-photos"
    rewritten_args = tuple(
        str(target) if value == "/other-photos" else value.replace("/other-photos", str(target))
        for value in command_args
    )
    result, command_log = _run_root_entrypoint(
        tmp_path,
        input_dir="/photos",
        work_dir=target / ".material-agent",
        command_args=rewritten_args,
        prepare_runtime=False,
    )

    assert result.returncode == 64
    assert "must stay outside MATERIAL_AGENT_INPUT_DIR" in result.stderr
    assert "chown" not in command_log


def test_root_entrypoint_refuses_root_as_work_dir(tmp_path):
    result, command_log = _run_root_entrypoint(
        tmp_path,
        work_dir=Path("/"),
        prepare_runtime=False,
    )

    assert result.returncode == 64
    assert "must not resolve to /" in result.stderr
    assert "chown" not in command_log


def test_root_entrypoint_refuses_symlinked_runtime_state(tmp_path):
    result, command_log = _run_root_entrypoint(tmp_path, state_symlink=True)

    assert result.returncode == 64
    assert "Runtime state file must not be a symbolic link" in result.stderr
    assert "gosu" not in command_log


def test_root_entrypoint_refuses_symlinks_inside_openvino_cache(tmp_path):
    result, command_log = _run_root_entrypoint(tmp_path, cache_symlink=True)

    assert result.returncode == 64
    assert "OpenVINO cache must not contain symbolic links" in result.stderr
    assert "gosu" not in command_log


def test_entrypoint_has_valid_posix_shell_syntax():
    subprocess.run(
        ["sh", "-n", str(ROOT / "docker" / "entrypoint.sh")],
        check=True,
    )


def test_entrypoint_adds_device_groups_without_chowning_photo_source():
    content = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")

    assert "/dev/dri/renderD* /dev/dri/card*" in content
    assert "stat -c '%g'" in content
    assert 'usermod -a -G "$device_group" "$app_user"' in content
    assert "chown -R" not in content
    assert 'find "$cache_dir" -xdev -exec chown -h' in content
    assert 'chown -h "$puid:$pgid" "$work_dir" /home/material-agent' in content


def test_dockerfiles_bundle_config_and_keep_dependency_layer_stable():
    for name, expected_extra, expected_config in (
        ("Dockerfile.cpu", "--extra cpu", "COPY config.yaml /app/config/config.yaml"),
        (
            "Dockerfile.intel-openvino",
            "--extra intel-openvino",
            "COPY docker/config.intel-openvino.yaml /app/config/config.yaml",
        ),
    ):
        content = (ROOT / name).read_text(encoding="utf-8")
        first_sync = content.index("uv sync --frozen")
        assert expected_config in content
        assert content.index("COPY README.md /app/README.md") > first_sync
        assert expected_extra in content
        assert "--extra quality-models" not in content
        assert "--extra face-models" not in content
        assert "gosu" in content
        assert "passwd" in content
        assert "PUID=1000" in content
        assert "PGID=1000" in content
        assert "useradd --uid 1000" in content


def test_intel_image_baked_config_runs_bundled_openvino_aesthetic_model():
    from material_agent.commands.scoring import load_config

    config = load_config(str(ROOT / "docker" / "config.intel-openvino.yaml"))
    aesthetic = config["local"]["aesthetic"]
    embedding = config["local"]["embedding"]

    assert aesthetic["enabled"] is True
    assert aesthetic["enforce_available"] is True
    assert aesthetic["runtime"] == "openvino"
    assert aesthetic["device"] == "CPU"
    assert aesthetic["fallback_device"] == "CPU"
    assert aesthetic["model_path"].endswith("nima_aesthetic_fp16.tflite")
    assert aesthetic["compiled_cache_dir"] == "/config/openvino-cache"
    assert embedding["enabled"] is False
    assert config["inference"]["runtime"] == "openvino"
    assert config["inference"]["device"] == "CPU"
    assert config["screening"]["enabled"] is False


def test_intel_gpu_top_requires_both_file_and_runtime_perfmon_capability():
    content = (ROOT / "Dockerfile.intel-openvino").read_text(encoding="utf-8")

    assert "libcap2-bin" in content
    assert "setcap cap_perfmon=ep /usr/bin/intel_gpu_top" in content


def test_publish_workflow_gates_mutable_tag_on_quality_and_smoke():
    content = (ROOT / ".github" / "workflows" / "publish-intel-openvino.yml").read_text(
        encoding="utf-8"
    )

    assert "needs: quality" in content
    assert "if: github.ref == 'refs/heads/main'" in content
    assert content.index("packages: write") > content.index("publish:")
    assert "cancel-in-progress: true" in content
    assert "Smoke immutable image" in content
    assert "type=sha,prefix=intel-openvino-" in content
    assert "type=raw,value=intel-openvino" not in content
    assert "steps.build.outputs.digest" in content
    assert "imagetools create" in content
    assert "PUID=12345" in content
    assert '"$IMAGE" material-agent --help' in content
    assert "stat -c '%u:%g'" in content
    assert "uv sync --frozen --group dev --extra intel-openvino" in content
    assert 'ar["requested_device"] == "AUTO:GPU,CPU"' in content
    assert 'not ar["fallback_used"]' in content
    assert 'ar["fallback_used"] and ar["compiled_device"] == "CPU"' in content
    assert 'fr["requested_device"] == "GPU"' in content
    assert 'fr["fallback_used"]' in content
