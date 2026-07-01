import logging
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger("material_agent")
_LEGACY_DB_NAME = "material-agent.db"
_SQLITE_SIDECAR_SUFFIXES = ("", "-wal", "-shm", "-journal")


@dataclass(frozen=True)
class RuntimePaths:
    work_dir: Path
    db_path: Path
    log_path: Path


def build_runtime_paths(input_dir: str | Path) -> RuntimePaths:
    input_path = Path(input_dir)
    work_dir = input_path / ".material-agent"
    return RuntimePaths(
        work_dir=work_dir,
        db_path=work_dir / "state.db",
        log_path=work_dir / "run.log",
    )


def _path_with_suffix(path: Path, suffix: str) -> Path:
    return path if not suffix else path.with_name(f"{path.name}{suffix}")


def _migrate_legacy_runtime_db(legacy_db_path: Path, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        source = _path_with_suffix(legacy_db_path, suffix)
        target = _path_with_suffix(db_path, suffix)
        if not source.exists():
            continue
        target.unlink(missing_ok=True)
        source.replace(target)
    _log.info("Migrated legacy runtime DB from %s to %s", legacy_db_path, db_path)


def ensure_runtime_paths(input_dir: str | Path) -> RuntimePaths:
    input_path = Path(input_dir)
    paths = build_runtime_paths(input_path)
    legacy_db_path = input_path / _LEGACY_DB_NAME

    if paths.db_path.exists():
        return paths
    if legacy_db_path.exists():
        _migrate_legacy_runtime_db(legacy_db_path, paths.db_path)
    return paths
