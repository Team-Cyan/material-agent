from pathlib import Path


def build_macos_command_launcher(repo_root: Path, *, dry_run: bool = False) -> str:
    root = repo_root.resolve()
    escaped_root = str(root).replace("'", "'\"'\"'")
    dry_run_flag = " --dry-run" if dry_run else ""
    cli_cmd = 'uv run material-agent run "$TARGET_DIR" --config "$CONFIG_PATH"'
    return f"""#!/bin/bash
set -euo pipefail

REPO_ROOT='{escaped_root}'
CONFIG_PATH="$REPO_ROOT/config.yaml"
TARGET_DIR="${{1:-}}"

if [ -z "$TARGET_DIR" ]; then
  osascript -e 'display dialog "Please drag a photo folder onto this launcher." buttons {{"OK"}} default button "OK"'
  exit 1
fi

if [ ! -d "$TARGET_DIR" ]; then
  osascript -e 'display dialog "Target is not a folder." buttons {{"OK"}} default button "OK"'
  exit 1
fi

cd "$REPO_ROOT"
if ! OUTPUT=$({cli_cmd}{dry_run_flag} 2>&1); then
  echo "$OUTPUT"
  echo
  read -r -p "Press Enter to close..."
  exit 1
fi

echo "$OUTPUT"
echo
read -r -p "Press Enter to close..."
"""
