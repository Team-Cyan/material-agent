import logging
import multiprocessing
import os
import tempfile

from material_agent.utils.progress import RichProgress, TqdmProgress


def test_logger_handler_not_duplicated_on_reinit():
    """Re-instantiating TqdmProgress with a log path must not accumulate handlers."""
    with tempfile.TemporaryDirectory() as d:
        log_path = os.path.join(d, "test.log")
        TqdmProgress(log_path=log_path)
        TqdmProgress(log_path=log_path)
        TqdmProgress(log_path=log_path)
        logger = logging.getLogger("material_agent")
        assert len(logger.handlers) == 1


def test_progress_respects_info_log_level():
    with tempfile.TemporaryDirectory() as d:
        log_path = os.path.join(d, "info.log")
        progress = TqdmProgress(log_path=log_path, log_level="info")
        progress._bar = _FakeBar()
        progress.on_start(1)
        progress.on_file_start("/tmp/example.ARW", 0)
        content = open(log_path, encoding="utf-8").read()
        assert "INFO RUN total=1" in content
        assert "DEBUG START /tmp/example.ARW" in content


def test_progress_respects_debug_log_level():
    with tempfile.TemporaryDirectory() as d:
        log_path = os.path.join(d, "debug.log")
        progress = TqdmProgress(log_path=log_path, log_level="debug")
        progress._bar = _FakeBar()
        progress.on_start(1)
        content = open(log_path, encoding="utf-8").read()
        assert "INFO RUN total=1" in content


class _FakeBar:
    def __init__(self):
        self.n = 0
        self.last_postfix = {}
        self.desc = ""

    def reset(self, total):
        self.total = total
        self.n = 0

    def set_description_str(self, desc):
        self.desc = desc

    def set_postfix(self, **kwargs):
        self.last_postfix = kwargs

    def update(self, n):
        self.n += n

    def close(self):
        pass


def test_progress_shows_running_work_before_first_completion():
    progress = TqdmProgress()
    progress._bar = _FakeBar()

    progress.on_start(3)
    progress.on_file_start("/tmp/example.ARW", 0)
    assert "run" not in progress._bar.last_postfix

    progress.on_score_done("/tmp/example.ARW", 7.5)
    assert "run" not in progress._bar.last_postfix
    assert progress._bar.last_postfix["ok"] == 1
    assert "score" not in progress._bar.last_postfix


def test_progress_logs_run_score_write_and_finish():
    with tempfile.TemporaryDirectory() as d:
        log_path = os.path.join(d, "test.log")
        progress = TqdmProgress(log_path=log_path)
        progress._bar = _FakeBar()

        progress.on_start(2)
        progress.on_file_start("/tmp/example.ARW", 0)
        progress.on_score_done("/tmp/example.ARW", 7.5)
        progress.on_write_done("/tmp/example.ARW", 7.5)
        progress.on_finish()

        content = open(log_path, encoding="utf-8").read()
        assert "RUN total=2" in content
        assert "DEBUG START /tmp/example.ARW" in content
        assert "SCORED /tmp/example.ARW score=7.5" in content
        assert "WROTE /tmp/example.ARW score=7.5" in content
        assert "FINISH ok=1 err=0" in content


def test_progress_bar_avoids_multiprocessing_lock(monkeypatch):
    def fail_rlock(*args, **kwargs):
        raise AssertionError("multiprocessing RLock should not be called")

    monkeypatch.setattr(multiprocessing, "RLock", fail_rlock)
    progress = TqdmProgress()
    progress.on_start(1)
    progress.on_finish()


def test_progress_resets_scoring_total_after_grouping_phase():
    progress = TqdmProgress()
    progress._bar = _FakeBar()

    progress.on_start(10)
    progress.on_phase_start("grouping", 4)
    progress.on_phase_advance(4)
    assert progress._bar.total == 4
    assert progress._bar.n == 4

    progress.on_file_start("/tmp/example.ARW", 0)

    assert progress._bar.total == 10
    assert progress._bar.n == 0
    assert "run" not in progress._bar.last_postfix


def test_progress_keeps_latest_eta_visible_while_next_file_is_running(monkeypatch):
    progress = TqdmProgress()
    progress._bar = _FakeBar()

    progress.on_start(10)
    progress.on_file_start("/tmp/a.ARW", 0)
    progress.on_score_done("/tmp/a.ARW", 7.5)

    monkeypatch.setattr(progress, "_rate_and_eta", lambda ts, bar_n: ("12.0s", "9m00s"))
    progress.on_file_start("/tmp/b.ARW", 1)
    progress.on_score_done("/tmp/b.ARW", 7.0)
    progress.on_file_start("/tmp/c.ARW", 2)

    assert progress._bar.last_postfix["pace"] == "12.0s/file"
    assert progress._bar.last_postfix["eta"] == "9m00s"


def test_rich_progress_keeps_recent_log_window_and_full_log_file():
    with tempfile.TemporaryDirectory() as d:
        log_path = os.path.join(d, "rich.log")
        progress = RichProgress(log_path=log_path, recent_logs_limit=2)

        progress.on_start(2)
        progress.on_file_start("/tmp/a.ARW", 0)
        progress.on_score_done("/tmp/a.ARW", 7.5)
        progress.on_write_done("/tmp/a.ARW", 7.5)
        progress.on_finish()

        assert list(progress._recent_logs) == [
            "SCORED /tmp/a.ARW score=7.5",
            "WROTE /tmp/a.ARW score=7.5",
        ]

        content = open(log_path, encoding="utf-8").read()
        assert "RUN total=2" in content
        assert "DEBUG START /tmp/a.ARW" in content
        assert "SCORED /tmp/a.ARW score=7.5" in content
        assert "WROTE /tmp/a.ARW score=7.5" in content


def test_rich_progress_hides_debug_events_from_screen_logs_but_keeps_file_logs():
    with tempfile.TemporaryDirectory() as d:
        log_path = os.path.join(d, "rich.log")
        progress = RichProgress(log_path=log_path, recent_logs_limit=4)

        progress.on_start(1)
        progress.on_file_start("/tmp/a.ARW", 0)
        progress.on_score_done("/tmp/a.ARW", 7.5)

        assert list(progress._recent_logs) == [
            "RUN total=1",
            "SCORED /tmp/a.ARW score=7.5",
        ]

        content = open(log_path, encoding="utf-8").read()
        assert "DEBUG START /tmp/a.ARW" in content
        assert "INFO RUN total=1" in content
        assert "INFO SCORED /tmp/a.ARW score=7.5" in content


def test_rich_progress_tracks_phase_and_scoring_state():
    progress = RichProgress(recent_logs_limit=2)

    progress.on_start(10)
    progress.on_phase_start("grouping", 4)
    progress.on_phase_advance(4)

    assert progress._phase_name == "grouping"
    assert progress._phase_total == 4
    assert progress._phase_completed == 4

    progress.on_file_start("/tmp/example.ARW", 0)

    assert progress._phase_name == "scoring"
    assert progress._total == 10
    assert progress._ok == 0
    assert progress._inflight == 1
