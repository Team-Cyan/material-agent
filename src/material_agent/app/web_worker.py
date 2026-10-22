"""Private, inherited-lease supervisor for Web scoring subprocesses.

Only this process signals the child it owns. Reconnecting Web managers exchange
private files; they never infer signal authority from a persisted PID.
"""

from __future__ import annotations

from contextlib import suppress

import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def read_private_json(path: Path) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, encoding="utf-8") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError(f"not a regular control file: {path}")
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"invalid control file: {path}")
    return value


def write_private_json(path: Path, value: dict) -> None:
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError(f"not a regular control file: {path}")
    except FileNotFoundError:
        pass
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def lease_busy(path: Path, identity: list[int] | None = None) -> bool:
    """Observe an existing regular lock without creating or changing its data."""
    import fcntl

    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"not a regular lease: {path}")
        if identity is not None and [info.st_dev, info.st_ino] != identity:
            raise ValueError(f"lease identity changed: {path}")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False
    finally:
        # Close only: never LOCK_UN an inherited open-file-description lock.
        os.close(descriptor)


def supervise(spec_path: Path, lease_fd: int, control_fd: int) -> None:
    spec = read_private_json(spec_path)
    receipt_path = spec_path.with_suffix(".receipt")
    cancel_path = spec_path.with_suffix(".cancel")
    token = spec["token"]
    process = None
    receipt = {"token": token, "status": "queued", "pid": None}

    def cancelled() -> bool:
        try:
            return read_private_json(cancel_path).get("token") == token
        except FileNotFoundError:
            return False

    try:
        if cancelled():
            receipt.update(status="cancelled", exit_code=130)
        else:
            process = subprocess.Popen(
                spec["command"],
                cwd=spec["work_dir"],
                env={**os.environ, "MATERIAL_AGENT_WORK_DIR": spec["work_dir"]},
                start_new_session=True,
                pass_fds=(lease_fd,),
            )
            receipt.update(status="running", pid=process.pid)
            write_private_json(receipt_path, receipt)
            while True:
                # No concurrent waiter reaps this child between poll and killpg.
                exit_code = process.poll()
                if exit_code is not None:
                    receipt.update(
                        status="cancelled"
                        if exit_code == 130
                        or (exit_code == -signal.SIGTERM and receipt["status"] == "cancelling")
                        else "finished"
                        if exit_code == 0
                        else "failed",
                        exit_code=exit_code,
                    )
                    break
                if receipt["status"] != "cancelling" and cancelled():
                    receipt["status"] = "cancelling"
                    write_private_json(receipt_path, receipt)
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                time.sleep(0.1)
    except Exception as error:
        if process is not None and process.poll() is None:
            # Keep the lease alive with the child. A failed receipt/cancel read
            # must not turn into a false terminal result or an unsafe replay.
            os.close(control_fd)
            process.wait()
            raise
        receipt.update(status="failed", exit_code=None, error=str(error))
    receipt["finished_at"] = time.time()
    write_private_json(receipt_path, receipt)


if __name__ == "__main__":
    try:
        supervise(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
    finally:
        for descriptor in (int(sys.argv[2]), int(sys.argv[3])):
            with suppress(OSError):
                os.close(descriptor)
