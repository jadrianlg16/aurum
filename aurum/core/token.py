"""API token resolution.

One secret shared by the API bearer check, the MCP HTTP server and the workflows runner::

    resolve_api_token() -> str      # '' when auth is off
    auth_required()     -> bool     # bool(resolve_api_token())
    auth_source()       -> 'env' | 'file' | 'none'

Resolution order: ``AURUM_API_TOKEN`` env → ``{data_dir}/secrets/api_token`` file → auto-generated
file token when the deployment is exposed (``AURUM_BIND`` not loopback) or ``AURUM_REQUIRE_TOKEN=1``
→ ``''`` (loopback, no token: the Host/Origin guard is the only gate).

The generated file is written with ``O_CREAT|O_EXCL`` and mode ``0o600`` (dir ``0o700``) and its
PATH — never its value — is logged once. There is no process-level cache: tests monkeypatch the
environment, and the ``os.stat`` + small read per request is negligible.

CLI: ``python -m aurum.core.token show|rotate|status``.
"""

from __future__ import annotations

import logging
import os
import secrets
import sys
from pathlib import Path

from .config import Settings, settings

log = logging.getLogger("aurum.token")

TOKEN_FILE = "api_token"
_TOKEN_BYTES = 32


def token_path(s: Settings | None = None) -> Path:
    s = s or settings()
    return s.secrets_dir / TOKEN_FILE


def _read_file_token(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_new_token(path: Path) -> str:
    """Create ``path`` exclusively with a fresh token; returns the value. Never overwrites."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:  # Windows / bind mounts: best effort
        pass
    value = secrets.token_urlsafe(_TOKEN_BYTES)
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, (value + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    log.info("api token generated at %s - run: python -m aurum.core.token show", path)
    return value


def _generation_required(s: Settings) -> bool:
    return s.require_token or not s.bind_is_loopback


def resolve_api_token() -> str:
    """The shared secret, or ``''`` when auth is off. See the module docstring for the order."""
    s = settings()
    if s.api_token:
        return s.api_token
    path = token_path(s)
    file_token = _read_file_token(path)
    if file_token:
        return file_token
    if _generation_required(s):
        try:
            return _write_new_token(path)
        except FileExistsError:
            # Another process won the race; read what it wrote.
            return _read_file_token(path)
    return ""


def auth_required() -> bool:
    return bool(resolve_api_token())


def auth_source() -> str:
    s = settings()
    if s.api_token:
        return "env"
    if _read_file_token(token_path(s)) or _generation_required(s):
        return "file"
    return "none"


# ------------------------------------------------------------------------------------------ CLI


def _cli(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        print(f"required={auth_required()} source={auth_source()}")
        return 0
    if cmd == "show":
        token = resolve_api_token()
        if not token:
            print("no token configured (loopback bind, AURUM_REQUIRE_TOKEN unset)", file=sys.stderr)
            return 1
        print(token)
        return 0
    if cmd == "rotate":
        s = settings()
        if s.api_token:
            print("AURUM_API_TOKEN is set in the environment; unset it to rotate the file token", file=sys.stderr)
            return 2
        path = token_path(s)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        _write_new_token(path)
        print(f"rotated: {path}")
        return 0
    print("usage: python -m aurum.core.token show|rotate|status", file=sys.stderr)
    return 64


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(_cli(sys.argv[1:]))
