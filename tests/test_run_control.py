import os
import signal

import pytest

from material_agent.app.errors import RunCancelled
from material_agent.utils.run_control import exclusive_run_lock, sigterm_as_cancellation


def test_exclusive_run_lock_rejects_a_second_controller(tmp_path):
    lock_path = tmp_path / "run.lock"

    with exclusive_run_lock(lock_path):
        with pytest.raises(ValueError, match="already active"):
            with exclusive_run_lock(lock_path):
                pass

    assert lock_path.read_text(encoding="utf-8").startswith("pid=")
    assert lock_path.stat().st_mode & 0o777 == 0o600


def test_exclusive_run_lock_rejects_symlink(tmp_path):
    target = tmp_path / "outside"
    target.write_text("preserve", encoding="utf-8")
    lock_path = tmp_path / "run.lock"
    lock_path.symlink_to(target)

    with pytest.raises(ValueError, match="safe run lock"):
        with exclusive_run_lock(lock_path):
            pass

    assert target.read_text(encoding="utf-8") == "preserve"


def test_sigterm_is_translated_to_run_cancellation_and_handler_is_restored():
    previous_handler = signal.getsignal(signal.SIGTERM)

    with pytest.raises(RunCancelled, match="SIGTERM"):
        with sigterm_as_cancellation():
            os.kill(os.getpid(), signal.SIGTERM)

    assert signal.getsignal(signal.SIGTERM) == previous_handler
