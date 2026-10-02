"""In-process cron scheduler for workflows, gated by ``AURUM_WORKFLOWS_SCHEDULER=1`` (off
by default) -- mirrors the pattern in :mod:`aurum.updater.scheduler` (a process-wide
instance, ``configure()``/``tick()``, never started at import time)."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Any

from . import runner, store
from .cron import parse

logger = logging.getLogger(__name__)

DEFAULT_POLL_S = 60


class Scheduler:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.enabled = False
        self._last_tick_minute: str | None = None

    def configure(self, enabled: bool) -> None:
        if enabled and not self.enabled:
            self._start()
        elif not enabled and self.enabled:
            self._stop_thread()
        self.enabled = enabled

    def _start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="aurum-workflows-scheduler")
        self._thread.start()

    def _stop_thread(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - a scheduler tick must never kill the thread
                logger.exception("workflows scheduler tick failed")
            self._stop.wait(DEFAULT_POLL_S)

    def tick(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Run every workflow whose cron schedule matches ``now`` (minute resolution;
        de-duplicated so the same minute never runs twice even on a sub-minute poll)."""
        now = now or datetime.now(UTC)
        minute_key = now.strftime("%Y-%m-%dT%H:%M")
        if minute_key == self._last_tick_minute:
            return []
        self._last_tick_minute = minute_key

        ran: list[dict[str, Any]] = []
        for entry in store.all_scheduled():
            try:
                schedule = parse(entry["schedule"])
            except Exception:  # noqa: BLE001 - a bad cron string never crashes the loop
                continue
            if schedule.matches(now):
                result = runner.run(entry["workspace"], entry["id"])
                ran.append({"workspace": entry["workspace"], "id": entry["id"], "run_id": result["id"]})
        return ran

    def status(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "running": self._thread is not None}


_scheduler = Scheduler()


def get_scheduler() -> Scheduler:
    return _scheduler


def reset_for_tests() -> None:
    global _scheduler
    _scheduler._stop_thread()  # noqa: SLF001 - test-only reset
    _scheduler = Scheduler()
