from pathlib import Path

from material_agent.utils.launcher import build_macos_command_launcher


def main() -> None:
    repo_root = Path.cwd()
    launcher_root = repo_root / "launchers"
    launcher_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        launcher_root / "material-agent.command": build_macos_command_launcher(repo_root),
        launcher_root / "material-agent-dry-run.command": build_macos_command_launcher(repo_root, dry_run=True),
    }
    for output_path, content in outputs.items():
        output_path.write_text(content, encoding="utf-8")
        output_path.chmod(0o755)
        print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
