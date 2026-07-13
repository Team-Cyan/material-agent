"""Helpers for keeping local runtime state private by default."""

from pathlib import Path


_SQLITE_SIDECAR_SUFFIXES = ("", "-wal", "-shm", "-journal")


def secure_private_file(path: str | Path) -> None:
    """Restrict an existing runtime file to its owning user."""

    target = Path(path)
    try:
        target.chmod(0o600)
    except FileNotFoundError:
        return


def secure_sqlite_files(db_path: str | Path) -> None:
    """Restrict a file-backed SQLite database and its current sidecars."""

    if str(db_path) == ":memory:":
        return
    path = Path(db_path)
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        target = path if not suffix else path.with_name(f"{path.name}{suffix}")
        secure_private_file(target)
