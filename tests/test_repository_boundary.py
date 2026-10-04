import re
import subprocess
from pathlib import Path


_TEXT_SUFFIXES = {
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".xml",
    ".yaml",
    ".yml",
}


def _public_text_files() -> list[Path]:
    public = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    return [
        path
        for value in public
        if value
        if (path := Path(value)).suffix.lower() in _TEXT_SUFFIXES
        or path.name in {"AGENTS.md", "Dockerfile", "Makefile"}
    ]


def test_boundary_checks_untracked_public_files_but_excludes_ignored(tmp_path, monkeypatch) -> None:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("private.md\n")
    (tmp_path / "tracked.md").write_text("Public document.\n")
    (tmp_path / "untracked.md").write_text("/Users/" + "lancer")
    (tmp_path / "private.md").write_text("/Users/" + "lancer")
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked.md"], check=True)
    monkeypatch.chdir(tmp_path)
    assert set(_public_text_files()) == {Path("tracked.md"), Path("untracked.md")}
    import pytest

    with pytest.raises(AssertionError, match="untracked.md"):
        test_public_tree_excludes_private_machine_identifiers()


def test_public_tree_excludes_private_machine_identifiers() -> None:
    private_fragments = (
        "/Users/" + "lancer",
        "OM" + "NI",
        "i7-" + "11700T",
        "/mnt/user/material/" + "photos",
    )
    private_ipv4 = re.compile(
        r"(?<!\d)(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
        r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?!\d)"
    )
    violations: list[str] = []
    for path in _public_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for fragment in private_fragments:
            if fragment in text:
                violations.append(f"{path}: private fragment {fragment!r}")
        for match in private_ipv4.finditer(text):
            violations.append(f"{path}: private IPv4 address {match.group()!r}")
    assert not violations, "\n".join(violations)


def test_application_source_excludes_private_controller_capabilities() -> None:
    controller_fragments = (
        "homelab_" + "agent",
        "Docker" + "Man",
        "Compose" + "Man",
        "Router" + "OS",
        "Home " + "Assistant",
        "param" + "iko",
        "ssh_" + "host",
    )
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in Path("src/material_agent").rglob("*.py")
    )
    assert not [fragment for fragment in controller_fragments if fragment in source]
