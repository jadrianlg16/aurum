"""An in-process, env-gated scheduler for the law/rule tracker.

Off by default: only ``AURUM_WATCH_SCHEDULER=1`` lets ``POST /api/watch/schedule`` actually
start a background thread. With the gate unset, the endpoint still records the requested
config (so the UI/tests can see what *would* run) but never spawns anything — this repo has
no business making network calls on a timer unless the operator opted in explicitly.

Each source's own ``cadence`` (``daily``/``weekly``/``monthly``, from ``sources.yml``) decides
how often it is due; "due" is judged from the most recent ``updater_snapshots`` row for that
source, so a fresh install with no snapshot yet is always due on the first tick.

A single process-wide :class:`Scheduler` instance (``get_scheduler()``) backs the router; tests
exercise ``Scheduler.tick()`` directly with a fake fetcher and a fake "now" rather than waiting
on a real thread.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ..core.config import env_int
from . import tracker

CADENCE_SECONDS: dict[str, int] = {
    "daily": 24 * 3600,
    "weekly": 7 * 24 * 3600,
    "monthly": 30 * 24 * 3600,
}

DEFAULT_POLL_S = 3600


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Scheduler:
    """Not started at import time. ``configure()`` is the only way to start/stop it."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.enabled = False
        self.sources: list[str] | None = None

    def configure(self, enabled: bool, sources: list[str] | None = None) -> None:
        self.sources = sources
        if enabled and not self.enabled:
            self._start()
        elif not enabled and self.enabled:
            self._stop_thread()
        self.enabled = enabled

    def _start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="aurum-watch-scheduler")
        self._thread.start()

    def _stop_thread(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None

    def _loop(self) -> None:
        poll_s = env_int("AURUM_WATCH_POLL_S", DEFAULT_POLL_S)
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - a scheduler tick must never kill the thread
                pass
            self._stop.wait(poll_s)

    def due_sources(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or datetime.now(UTC)
        sources = tracker.load_sources()
        if self.sources is not None:
            sources = [s for s in sources if s["id"] in self.sources]
        due: list[dict[str, Any]] = []
        for source in sources:
            interval = CADENCE_SECONDS.get(source.get("cadence", "weekly"), CADENCE_SECONDS["weekly"])
            last = tracker.last_snapshot(source["id"])
            if last is None:
                due.append(source)
                continue
            elapsed = (now - _parse_iso(last["fetched_at"])).total_seconds()
            if elapsed >= interval:
                due.append(source)
        return due

    def tick(
        self, *, fetcher: tracker.Fetcher | None = None, now: datetime | None = None
    ) -> list[str]:
        """Run every due source once. Returns the list of source ids that ran."""

        fetcher = fetcher or tracker.default_fetcher()
        ran: list[str] = []
        for source in self.due_sources(now=now):
            tracker.run_one(source, fetcher)
            ran.append(source["id"])
        return ran

    def status(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "sources": self.sources, "running": self._thread is not None}


_scheduler = Scheduler()


def get_scheduler() -> Scheduler:
    return _scheduler


def reset_for_tests() -> None:
    """Stop and drop the process-wide scheduler. Test fixtures call this in teardown."""

    global _scheduler
    _scheduler._stop_thread()  # noqa: SLF001 - test-only reset
    _scheduler = Scheduler()


ScheduleFactory = Callable[[], Scheduler]
