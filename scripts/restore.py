"""Restore a full-instance backup produced by ``POST /api/backup``.

Always restores into a **new**, empty directory — never the live data dir, never in place — and refuses
outright while the API might still be writing to that data dir. This is read-only with respect to the
running instance: it never touches ``AURUM_DATA_DIR``.

Usage::

    uv run python scripts/restore.py <zip> --into <new-empty-dir> [--api http://localhost:5024]

Exit codes: ``2`` the ``--into`` directory already exists and is non-empty; ``3`` the API answered at
``--api`` (any HTTP status counts as "up" — refuse to restore near a live instance); ``4`` a file's
sha256 does not match ``manifest.json``; ``0`` success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import zipfile
from pathlib import Path

import httpx

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _api_is_up(api_url: str) -> bool:
    """Any HTTP response (2xx-5xx) means the server is up and answering — a connection error means
    down. We refuse to restore near a live instance either way an error would be ambiguous."""
    try:
        httpx.get(f"{api_url.rstrip('/')}/api/health", timeout=3)
        return True
    except httpx.RequestError:
        return False


def restore(zip_path: Path, into: Path, api_url: str) -> int:
    if into.exists() and any(into.iterdir()):
        print(f"refusing to restore: {into} already exists and is not empty", file=sys.stderr)
        return 2

    if _api_is_up(api_url):
        print(f"refusing to restore: the API at {api_url} is answering — stop it first", file=sys.stderr)
        return 3

    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        mismatches: list[str] = []
        for relpath, expected_sha in manifest.get("files", {}).items():
            actual_sha = _sha256_bytes(zf.read(relpath))
            if actual_sha != expected_sha:
                mismatches.append(f"{relpath}: expected {expected_sha}, got {actual_sha}")
        if mismatches:
            print("sha256 mismatch, refusing to restore:", file=sys.stderr)
            for m in mismatches:
                print(f"  {m}", file=sys.stderr)
            return 4

        into.mkdir(parents=True, exist_ok=True)
        zf.extractall(into)

    print(f"restored into {into}")
    print(f"backup version {manifest.get('version')}, created_at {manifest.get('created_at')}")

    db_path = into / "aurum.db"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        try:
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            ]
            print("table counts:")
            for t in tables:
                (count,) = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()  # noqa: S608 — t is our own PRAGMA-discovered identifier
                print(f"  {t}: {count}")
        finally:
            conn.close()

    ws_root = into / "workspaces"
    workspaces: list[str] = []
    if ws_root.exists():
        for p in sorted(ws_root.glob("*/workspace.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                workspaces.append(str(data.get("id", p.parent.name)))
            except (OSError, ValueError):
                workspaces.append(p.parent.name)
    print(f"workspaces ({len(workspaces)}): {', '.join(workspaces)}")

    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("zip", type=Path, help="backup zip produced by POST /api/backup")
    ap.add_argument("--into", required=True, type=Path, help="new, empty directory to restore into")
    ap.add_argument("--api", default=os.environ.get("AURUM_API_URL", "http://localhost:5024"))
    args = ap.parse_args(argv)
    return restore(args.zip, args.into, args.api)


if __name__ == "__main__":
    raise SystemExit(main())
