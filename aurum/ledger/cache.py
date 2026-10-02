"""Process-wide cache of parsed ledgers.

Keyed on the *resolved* ``main.beancount`` path (tests reuse ``ws1`` across temp dirs) and validated
against ``(main mtime_ns, main size, accounts mtime_ns, accounts size)`` — size is part of the key
because Windows mtime resolution is 100 ns and an in-place rewrite of the same length within that
window would otherwise go unnoticed. The store calls ``invalidate()`` inside its write locks after
every append/rewrite, so a reader in the same process never sees a stale parse; an external edit
(another process, an editor) is caught by the stat key. ``AURUM_LEDGER_CACHE=0`` bypasses it.
"""

from __future__ import annotations

import threading
from pathlib import Path

from ..core.config import settings

StatKey = tuple[int, int, int, int]

_lock = threading.Lock()
_entries: dict[str, tuple[StatKey, list, list, dict]] = {}


def enabled() -> bool:
    return settings().ledger_cache


def _key_for(path: Path) -> str:
    return str(path.resolve())


def stat_key(main: Path, accounts: Path) -> StatKey | None:
    try:
        m = main.stat()
    except FileNotFoundError:
        return None
    try:
        a = accounts.stat()
        a_key = (a.st_mtime_ns, a.st_size)
    except FileNotFoundError:
        a_key = (0, 0)
    return (m.st_mtime_ns, m.st_size, *a_key)


def get(main: Path, accounts: Path) -> tuple[list, list, dict] | None:
    """Cached ``(entries, errors, options)`` when the files are unchanged, else ``None``."""
    if not enabled():
        return None
    key = stat_key(main, accounts)
    if key is None:
        return None
    with _lock:
        hit = _entries.get(_key_for(main))
    if hit is None or hit[0] != key:
        return None
    return hit[1], hit[2], hit[3]


def put(main: Path, accounts: Path, key: StatKey, entries: list, errors: list, options: dict) -> None:
    if not enabled():
        return
    with _lock:
        _entries[_key_for(main)] = (key, entries, errors, options)


def invalidate(main: Path) -> None:
    with _lock:
        _entries.pop(_key_for(main), None)


def clear() -> None:
    with _lock:
        _entries.clear()


def size() -> int:
    with _lock:
        return len(_entries)
