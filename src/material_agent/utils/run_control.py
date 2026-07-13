from __future__ import annotations

import os
import signal
import threading
from contextlib import contextmanager
from pathlib import Path

from ..app.errors import RunCancelled
from .file_security import secure_private_file


@contextmanager
def exclusive_run_lock(path: str | Path):
    """Hold a non-blocking process lock for one runtime work directory."""

    try:
        import fcntl
    except ImportError as error:  # pragma: no cover - NAS/macOS are POSIX
        raise RuntimeError("material-agent run locking requires a POSIX runtime") from error

    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.is_symlink():
        raise ValueError(f"Unable to open safe run lock {lock_path}: symbolic link")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise ValueError(f"Unable to open safe run lock {lock_path}: {error}") from error
    handle = os.fdopen(descriptor, "r+", encoding="utf-8")
    secure_private_file(lock_path)
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(
                f"Another material-agent run is already active for {lock_path.parent}"
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


@contextmanager
def sigterm_as_cancellation():
    """Translate SIGTERM into a catchable run cancellation on the main thread."""

    if threading.current_thread() is not threading.main_thread() or not hasattr(
        signal, "SIGTERM"
    ):
        yield
        return

    previous_handler = signal.getsignal(signal.SIGTERM)

    def _cancel(_signum, _frame) -> None:
        raise RunCancelled("received SIGTERM")

    signal.signal(signal.SIGTERM, _cancel)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
