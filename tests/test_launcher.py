from pathlib import Path

from material_agent.utils.launcher import build_macos_command_launcher


def test_build_macos_command_launcher_uses_repo_root_and_config_path():
    repo_root = Path("/Users/lancer/projects/material-agent")

    script = build_macos_command_launcher(repo_root)

    assert "REPO_ROOT='/Users/lancer/projects/material-agent'" in script
    assert 'CONFIG_PATH="$REPO_ROOT/config.yaml"' in script
    assert 'uv run material-agent run "$TARGET_DIR" --config "$CONFIG_PATH"' in script
    assert 'read -r -p "Press Enter to close..."' in script


def test_build_macos_command_launcher_supports_dragged_directory_argument():
    script = build_macos_command_launcher(Path("/tmp/material-agent"))

    assert 'TARGET_DIR="${1:-}"' in script
    assert 'if [ -z "$TARGET_DIR" ]; then' in script
    assert 'Please drag a photo folder onto this launcher.' in script
    assert 'if ! OUTPUT=$(uv run material-agent run "$TARGET_DIR" --config "$CONFIG_PATH" 2>&1); then' in script
    assert 'echo "$OUTPUT"' in script


def test_build_macos_command_launcher_supports_dry_run_variant():
    script = build_macos_command_launcher(Path("/tmp/material-agent"), dry_run=True)

    assert 'uv run material-agent run "$TARGET_DIR" --config "$CONFIG_PATH" --dry-run' in script
