import logging
import os
import time
from abc import ABC, abstractmethod
from collections import deque
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

TQDM_NCOLS = 120  # compatibility constant for legacy callers

_DESC_W = 26
_PHASE_BAR_COLUMNS = (
    SpinnerColumn(),
    TextColumn("[bold cyan]{task.description}"),
    BarColumn(bar_width=None),
    TaskProgressColumn(),
    TextColumn("{task.completed}/{task.total}"),
    TimeElapsedColumn(),
    TimeRemainingColumn(),
)


def _pad(s: str, width: int = _DESC_W) -> str:
    if len(s) > width:
        s = s[: width - 1] + "..."
    return f"{s:<{width}}"


def _fmt_eta(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m = int(seconds // 60)
    if m < 60:
        return f"{m}m{int(seconds % 60):02d}s"
    return f"{m // 60}h{m % 60:02d}m"


class ProgressCallback(ABC):
    @abstractmethod
    def on_start(self, total: int): ...

    @abstractmethod
    def on_file_start(self, file_path: str, index: int): ...

    @abstractmethod
    def on_file_done(self, file_path: str, score: float, skipped: bool = False): ...

    @abstractmethod
    def on_error(self, file_path: str, error: Exception): ...

    @abstractmethod
    def on_finish(self): ...

    def on_phase_start(self, desc: str, total: int):
        pass

    def on_phase_advance(self, n: int = 1):
        pass

    def on_score_done(self, file_path: str, score: float):
        pass

    def on_write_done(self, file_path: str, score: float):
        pass


class RichProgress(ProgressCallback):
    def __init__(
        self,
        log_path: str | None = None,
        log_level: str = "info",
        *,
        recent_logs_limit: int = 8,
        console: Console | None = None,
        force_interactive: bool | None = None,
    ):
        self._logger = None
        self._total = 0
        self._ok = 0
        self._err = 0
        self._inflight = 0
        self._score_ts: deque[float] = deque(maxlen=3)
        self._last_pace = "?"
        self._last_eta = "?"
        self._current_file = "-"
        self._phase_name = "idle"
        self._phase_total = 0
        self._phase_completed = 0
        self._recent_logs: deque[str] = deque(maxlen=recent_logs_limit)
        self._bar = None
        self._screen_log_level = logging.INFO

        self._console = console or Console(stderr=True)
        if force_interactive is None:
            force_interactive = bool(getattr(self._console, "is_terminal", False) and not self._console.is_dumb_terminal)
        self._interactive = force_interactive
        self._live: Live | None = None
        self._progress = Progress(*_PHASE_BAR_COLUMNS, console=self._console, expand=True)
        self._phase_task_id: int | None = None

        if log_path:
            handler = logging.FileHandler(log_path, encoding="utf-8")
            os.chmod(log_path, 0o600)
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger = logging.getLogger("material_agent")
            logger.setLevel(logging.DEBUG)
            logger.handlers.clear()
            logger.addHandler(handler)
            self._logger = logger

    def on_start(self, total: int):
        self._total = total
        self._ok = 0
        self._err = 0
        self._inflight = 0
        self._last_pace = "?"
        self._last_eta = "?"
        self._current_file = "-"
        self._phase_name = "scoring"
        self._phase_total = total
        self._phase_completed = 0
        win = max(3, min(100, int(total**0.5))) if total else 3
        self._score_ts = deque(maxlen=win)
        self._reset_progress_task("scoring", total, 0)
        self._log("RUN total=%s" % total)
        self._refresh()

    def on_phase_start(self, desc: str, total: int):
        self._phase_name = desc
        self._phase_total = total
        self._phase_completed = 0
        self._reset_progress_task(desc, total, 0)
        self._refresh()

    def on_phase_advance(self, n: int = 1):
        self._phase_completed = min(self._phase_total, self._phase_completed + n)
        if self._phase_task_id is not None:
            self._progress.update(self._phase_task_id, completed=self._phase_completed)
        self._sync_legacy_bar(self._phase_name, max(self._phase_total, 1), self._phase_completed)
        self._refresh()

    def on_file_start(self, file_path: str, index: int):
        del index
        self._current_file = Path(file_path).name
        self._inflight += 1
        self._phase_name = "scoring"
        self._phase_total = self._total
        self._phase_completed = self._ok + self._err
        self._reset_progress_task("scoring", self._total, self._phase_completed)
        self._log(f"START {file_path}", level="debug")
        self._refresh()

    def on_score_done(self, file_path: str, score: float):
        self._ok += 1
        self._inflight = max(0, self._inflight - 1)
        self._score_ts.append(time.monotonic())
        self._phase_name = "scoring"
        self._phase_total = self._total
        self._phase_completed = self._ok + self._err
        self._reset_progress_task("scoring", self._total, self._phase_completed)
        rate, eta = self._rate_and_eta(self._score_ts, self._phase_completed)
        self._last_pace = f"{rate}/file" if rate != "?" else "?"
        self._last_eta = eta
        self._log(f"SCORED {file_path} score={score:.1f}")
        self._refresh()

    def on_file_done(self, file_path: str, score: float, skipped: bool = False):
        del file_path, score
        if skipped:
            self._inflight = max(0, self._inflight - 1)
            self._phase_name = "scoring"
            self._phase_total = self._total
            self._phase_completed = min(self._total, self._phase_completed + 1)
            self._reset_progress_task("scoring", self._total, self._phase_completed)
            self._refresh()

    def on_error(self, file_path: str, error: Exception):
        self._err += 1
        self._inflight = max(0, self._inflight - 1)
        self._phase_name = "scoring"
        self._phase_total = self._total
        self._phase_completed = self._ok + self._err
        self._reset_progress_task("scoring", self._total, self._phase_completed)
        rate, eta = self._rate_and_eta(self._score_ts, self._phase_completed)
        self._last_pace = f"{rate}/file" if rate != "?" else "?"
        self._last_eta = eta
        self._log(f"ERROR {file_path}: {error}", level="error")
        self._refresh()

    def on_write_done(self, file_path: str, score: float):
        self._log(f"WROTE {file_path} score={score:.1f}")
        self._refresh()

    def on_finish(self):
        self._log(f"FINISH ok={self._ok} err={self._err}", screen=False)
        self._refresh()
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _reset_progress_task(self, description: str, total: int, completed: int) -> None:
        visible_total = max(total, 1)
        if self._phase_task_id is None:
            self._phase_task_id = self._progress.add_task(description, total=visible_total, completed=completed)
        else:
            self._progress.update(self._phase_task_id, description=description, total=visible_total, completed=completed)
        self._sync_legacy_bar(description, visible_total, completed)

    def _log(self, message: str, *, level: str = "info", screen: bool = True) -> None:
        level_no = getattr(logging, level.upper())
        if screen and level_no >= self._screen_log_level:
            self._recent_logs.append(message)
        if self._logger:
            getattr(self._logger, level)(message)
        if not self._interactive and level_no >= self._screen_log_level:
            self._console.print(message)

    def _postfix(self) -> dict[str, Any]:
        postfix: dict[str, Any] = {
            "ok": self._ok,
            "err": self._err,
            "eta": self._last_eta,
        }
        if self._last_pace != "?":
            postfix["pace"] = self._last_pace
        return postfix

    def _sync_legacy_bar(self, description: str, total: int, completed: int) -> None:
        if self._bar is None:
            return
        if hasattr(self._bar, "reset"):
            self._bar.reset(total=total)
        if completed and hasattr(self._bar, "update"):
            self._bar.update(completed)
        if hasattr(self._bar, "set_description_str"):
            self._bar.set_description_str(_pad(description))
        if hasattr(self._bar, "set_postfix"):
            self._bar.set_postfix(**self._postfix())

    def _summary_table(self) -> Table:
        table = Table.grid(expand=True)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_row(
            f"phase: {self._phase_name}",
            f"file: {_pad(self._current_file)}",
            f"ok={self._ok} err={self._err}",
            f"eta={self._last_eta} pace={self._last_pace}",
        )
        return table

    def _log_panel(self) -> Panel:
        lines = list(self._recent_logs) or ["(no logs yet)"]
        return Panel("\n".join(lines), title=f"Recent Logs ({len(lines)})", border_style="blue")

    def _renderable(self) -> Group:
        return Group(
            Panel(self._summary_table(), title="material-agent", border_style="cyan"),
            self._progress,
            self._log_panel(),
        )

    def _refresh(self) -> None:
        if not self._interactive:
            return
        if self._live is None:
            self._live = Live(
                self._renderable(),
                console=self._console,
                refresh_per_second=4,
                transient=False,
            )
            self._live.start()
            return
        self._live.update(self._renderable(), refresh=True)

    def _rate_and_eta(self, ts: deque[float], bar_n: int) -> tuple[str, str]:
        if len(ts) < 2:
            return "?", "?"
        elapsed = ts[-1] - ts[0]
        if elapsed <= 0:
            return "?", "?"
        rate = (len(ts) - 1) / elapsed
        remaining = self._total - bar_n
        eta = _fmt_eta(remaining / rate) if remaining > 0 else "0s"
        secs_per_file = 1.0 / rate
        return f"{secs_per_file:.1f}s", eta


TqdmProgress = RichProgress


__all__ = [
    "ProgressCallback",
    "RichProgress",
    "TQDM_NCOLS",
    "TqdmProgress",
    "_pad",
]
