"""The deny-list of paths a workflow step may never call.

A workflow orchestrates read/compute/report calls against the API; it must never be
able to exfiltrate the encrypted e.firma vault or delete a workspace. Both checks are
on the *rendered* path (after ``{{ }}`` substitution) and the method.
"""

from __future__ import annotations

import posixpath
import re
from urllib.parse import urlsplit

# (method pattern or None for "any", path regex) — matched against the NORMALIZED, lower-cased path
_DENY: list[tuple[str | None, re.Pattern[str]]] = [
    (None, re.compile(r"^/satsync/[^/]+/vault(/.*)?$")),
    ("POST", re.compile(r"^/satsync/[^/]+/sync(/.*)?$")),
    ("DELETE", re.compile(r"^/workspaces(/.*)?$")),
]

DENY_DESCRIPTIONS = [
    "GET/POST/PUT/DELETE /satsync/{ws}/vault* -- e.firma vault is read-never-exfiltrate",
    "POST /satsync/{ws}/sync* -- a workflow never triggers a Descarga Masiva job",
    "DELETE /workspaces* -- workflows must never delete a workspace",
]

_API_PREFIX = re.compile(r"^/api(?=/|$)", re.IGNORECASE)


def normalize_api_path(path: str) -> str:
    """Canonical route path for the deny check and for dispatch: query/fragment stripped,
    leading ``/`` ensured, ``posixpath.normpath`` (collapses ``//``, ``.``, ``..``), one leading
    ``/api`` segment removed case-insensitively. Case of the remainder is preserved (``is_denied``
    lower-cases for matching; the runner dispatches the case-preserved path)."""
    raw = urlsplit(path or "").path
    if not raw.startswith("/"):
        raw = "/" + raw
    norm = posixpath.normpath(raw)
    if not norm.startswith("/"):
        norm = "/" + norm
    norm = _API_PREFIX.sub("", norm, count=1) or "/"
    return norm if norm.startswith("/") else "/" + norm


def is_denied(method: str, path: str) -> bool:
    normalized = normalize_api_path(path).lower()
    for deny_method, pattern in _DENY:
        if deny_method is not None and deny_method != method.upper():
            continue
        if pattern.match(normalized):
            return True
    return False
