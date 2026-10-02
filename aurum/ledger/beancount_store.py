"""Beancount v3 implementation of ``LedgerStore``.

Layout per workspace, under ``{DATA_DIR}/workspaces/{ws}/``::

    accounts.beancount   # option header + one `open` directive per account
    main.beancount       # include of accounts.beancount + appended transactions

Accounts are opened automatically the first time they are used. The open directive is dated at the
first use; if a later append carries an *earlier* date, the existing open is rewritten backwards so
the file always loads without errors. ``2000-01-01`` is the floor used for template/opening accounts.

Every write is guarded by a per-workspace re-entrant thread lock *and* an on-disk lock file, so two
processes (API + `python -m aurum.demo`) cannot interleave appends.

Write hardening: every write re-validates the model (defeats ``model_construct``
/ ``model_copy`` bypasses), renders the transaction and parses the text back — exactly one clean
``Transaction`` or ``LedgerRenderError`` and nothing is written; amounts render through ``q2``;
``replace_txn`` (the one in-place rewrite, used by PUT/void) lives here under the same locks; reads go
through ``aurum.ledger.cache`` keyed on the files' stat.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from beancount import loader
from beancount.core import data as bc_data
from beancount.parser import parser as bc_parser

from ..core.config import WS_ID_RE, InvalidWorkspaceId, settings
from ..core.money import Amount, q2
from . import cache as ledger_cache
from .base import Posting, Transaction, validate_account

log = logging.getLogger("aurum.ledger")

EPOCH = date(2000, 1, 1)


class LedgerRenderError(ValueError):
    """The rendered transaction did not parse back as exactly one clean Beancount transaction; nothing written."""


class TxnNotFound(LookupError):
    """``replace_txn`` found no block carrying ``^txn_id`` (router maps → 404)."""


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Beancount lexer: a meta key is at least two characters (found by the round-trip property test).
_META_KEY = re.compile(r"^[a-z][a-zA-Z0-9_-]+$")
_INTERNAL_META = {"filename", "lineno", "__tolerances__", "__automatic__", "__residual__"}

_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def _ws_lock(key: str) -> threading.RLock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _locks[key] = lock
        return lock


class _FileLock:
    """Cross-platform advisory lock: exclusive-create a ``.lock`` file, retry, always release."""

    def __init__(self, path: Path, timeout: float = 10.0) -> None:
        self.path = path
        self.timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> _FileLock:
        deadline = time.monotonic() + self.timeout
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.monotonic() > deadline:
                    # A stale lock from a crashed process must not wedge the app forever.
                    try:
                        self.path.unlink()
                    except OSError:
                        raise TimeoutError(f"could not acquire ledger lock {self.path}") from None
                time.sleep(0.02)

    def __exit__(self, *exc: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.path.unlink()
        except OSError:
            pass


def _fmt_amount(amount: Amount) -> str:
    return f"{q2(amount.amount)} {amount.currency}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def template_path(name: str = "mx_resico_pf") -> Path:
    return TEMPLATES_DIR / f"{name}.beancount"


def _revalidate(txn: Transaction) -> Transaction:
    """Run every validator again: callers may hand us ``model_construct``/``model_copy(update=)`` objects
    that skipped them (raises ``pydantic.ValidationError`` → 400 via the API handler)."""
    return Transaction.model_validate(txn.model_dump())


def _quantized_postings(txn: Transaction) -> list[Posting]:
    """Postings with explicit amounts quantized to cents (HALF_UP) *before* the balancing leg is
    computed, so the rendered lines always sum to zero per currency."""
    quantized = txn.model_copy(
        update={
            "postings": [
                p.model_copy(update={"amount": p.amount.quantized()}) if p.amount is not None else p
                for p in txn.postings
            ]
        }
    )
    return quantized.balanced()


def _replace_txn_block(path: Path, txn_id: str, new_text: str) -> None:
    """Rewrite the transaction block whose header carries ``^txn_id`` in ``path`` (caller holds the locks)."""
    text = path.read_text(encoding="utf-8")
    blocks = text.split("\n\n")
    replaced = False
    out = []
    for block in blocks:
        header = block.splitlines()[0] if block.strip() else ""
        if f"^{txn_id}" in header.split():
            out.append(new_text.rstrip("\n"))
            replaced = True
        else:
            out.append(block)
    if not replaced:
        raise TxnNotFound(txn_id)
    rendered = "\n\n".join(b for b in out if b.strip() != "") + "\n"
    path.write_text(rendered, encoding="utf-8")


class BeancountLedger:
    """``LedgerStore`` on plain-text Beancount files. One directory per workspace."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else None

    # ---------------------------------------------------------------- paths

    def workspace_dir(self, ws_id: str) -> Path:
        if not WS_ID_RE.match(ws_id or ""):
            raise InvalidWorkspaceId(ws_id)
        root = self._data_dir or settings().workspaces_dir.parent
        return root / "workspaces" / ws_id

    def main_path(self, ws_id: str) -> Path:
        return self.workspace_dir(ws_id) / "main.beancount"

    def accounts_path(self, ws_id: str) -> Path:
        return self.workspace_dir(ws_id) / "accounts.beancount"

    def _lock_path(self, ws_id: str) -> Path:
        return self.workspace_dir(ws_id) / "ledger.lock"

    # ------------------------------------------------------------ bootstrap

    def ensure_files(self, ws_id: str, currency: str = "MXN") -> None:
        d = self.workspace_dir(ws_id)
        d.mkdir(parents=True, exist_ok=True)
        accounts = self.accounts_path(ws_id)
        if not accounts.exists():
            accounts.write_text(
                f'option "operating_currency" "{currency}"\n\n; Accounts are opened automatically on first use.\n',
                encoding="utf-8",
            )
        main = self.main_path(ws_id)
        if not main.exists():
            main.write_text(
                f'; Aurum ledger for workspace {ws_id}. The ledger is the truth.\ninclude "accounts.beancount"\n\n',
                encoding="utf-8",
            )

    def apply_template(self, ws_id: str, name: str = "mx_resico_pf", currency: str = "MXN") -> list[str]:
        """Open every account in a chart-of-accounts template. Idempotent."""
        path = template_path(name)
        if not path.exists():
            raise FileNotFoundError(f"no chart-of-accounts template named {name!r}")
        accounts = [
            line.split()[2]
            for line in path.read_text(encoding="utf-8").splitlines()
            if len(line.split()) >= 3 and line.split()[1] == "open"
        ]
        with _ws_lock(str(self.main_path(ws_id))), _FileLock(self._lock_path(ws_id)):
            self.ensure_files(ws_id, currency)
            self._open_accounts(ws_id, {a: EPOCH for a in accounts}, currency)
        return accounts

    # --------------------------------------------------------------- writes

    def _existing_opens(self, ws_id: str) -> dict[str, date]:
        out: dict[str, date] = {}
        text = self.accounts_path(ws_id).read_text(encoding="utf-8") if self.accounts_path(ws_id).exists() else ""
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "open":
                try:
                    out[parts[2]] = date.fromisoformat(parts[0])
                except ValueError:
                    continue
        return out

    def _open_accounts(self, ws_id: str, wanted: dict[str, date], currency: str) -> None:
        """Ensure every account in ``wanted`` is open, no later than the requested date.

        Callers hold ``_ws_lock`` + ``_FileLock``; every account is validated before it is rendered."""
        for account in wanted:
            validate_account(account)
        existing = self._existing_opens(ws_id)
        changed = {a: d for a, d in wanted.items() if a not in existing or d < existing[a]}
        if not changed:
            return
        merged = dict(existing)
        merged.update(changed)
        header = f'option "operating_currency" "{currency}"\n\n; Accounts are opened automatically on first use.\n'
        lines = [f"{d.isoformat()} open {a}" for a, d in sorted(merged.items())]
        self.accounts_path(ws_id).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
        ledger_cache.invalidate(self.main_path(ws_id))

    def _render(self, txn: Transaction, txn_id: str) -> str:
        payee = f'"{_escape(txn.payee)}" ' if txn.payee else ""
        narration = f'"{_escape(txn.narration or "")}"'
        tags = "".join(f" #{t}" for t in txn.tags)
        links = {txn_id, *txn.links}
        link_str = "".join(f" ^{link}" for link in sorted(links))
        head = f"{txn.date.isoformat()} * {payee}{narration}{tags}{link_str}"
        lines = [head]
        for key, value in sorted(txn.meta.items()):
            if not _META_KEY.match(key):
                continue
            lines.append(f'  {key}: "{_escape(str(value))}"')
        for p in _quantized_postings(txn):
            assert p.amount is not None
            lines.append(f"  {p.account:<40} {_fmt_amount(p.amount)}")
        return "\n".join(lines) + "\n\n"

    def _render_checked(self, txn: Transaction, txn_id: str) -> str:
        """Render, then parse the text back: exactly one ``Transaction`` and zero parser errors, else
        ``LedgerRenderError`` (an injected ``option``/``plugin`` line yields extra entries + errors)."""
        rendered = self._render(txn, txn_id)
        entries, errors, _options = bc_parser.parse_string(rendered)
        txns = [e for e in entries if isinstance(e, bc_data.Transaction)]
        if errors or len(entries) != 1 or len(txns) != 1:
            first = errors[0].message if errors else f"{len(entries)} entries"
            raise LedgerRenderError(f"transaction does not render to one clean Beancount entry: {first}")
        return rendered

    def append(self, ws_id: str, txn: Transaction) -> str:
        txn = _revalidate(txn)
        txn_id = txn.links[0] if txn.links else f"txn-{uuid.uuid4().hex[:12]}"
        postings = _quantized_postings(txn)
        currency = next((p.amount.currency for p in postings if p.amount), "MXN")
        rendered = self._render_checked(txn, txn_id)
        main = self.main_path(ws_id)
        with _ws_lock(str(main)), _FileLock(self._lock_path(ws_id)):
            self.ensure_files(ws_id, currency)
            self._open_accounts(ws_id, {p.account: txn.date for p in postings}, currency)
            with main.open("a", encoding="utf-8") as fh:
                fh.write(rendered)
            ledger_cache.invalidate(main)
        return txn_id

    def replace_txn(self, ws_id: str, txn_id: str, txn: Transaction) -> None:
        """Rewrite the block whose header carries ``^txn_id`` with ``txn`` (same link kept). The only
        in-place rewrite of ``main.beancount``; runs under the same locks as ``append``."""
        txn = _revalidate(txn)
        new_txn = txn.model_copy(update={"links": sorted({txn_id, *txn.links})})
        postings = _quantized_postings(new_txn)
        currency = next((p.amount.currency for p in postings if p.amount), "MXN")
        rendered = self._render_checked(new_txn, txn_id)
        main = self.main_path(ws_id)
        with _ws_lock(str(main)), _FileLock(self._lock_path(ws_id)):
            if not main.exists():
                raise TxnNotFound(txn_id)
            _replace_txn_block(main, txn_id, rendered)
            self._open_accounts(ws_id, {p.account: new_txn.date for p in postings}, currency)
            ledger_cache.invalidate(main)

    # ---------------------------------------------------------------- reads

    def load(self, ws_id: str) -> tuple[list, list]:
        """Load the workspace ledger; returns (entries, errors). Missing files load as empty.

        Served from ``aurum.ledger.cache`` while the files' stat key is unchanged."""
        path = self.main_path(ws_id)
        if not path.exists():
            return [], []
        accounts = self.accounts_path(ws_id)
        hit = ledger_cache.get(path, accounts)
        if hit is not None:
            return hit[0], hit[1]
        key = ledger_cache.stat_key(path, accounts)
        entries, errors, options = loader.load_file(str(path))
        if errors:
            first = errors[0]
            source = getattr(first, "source", None) or {}
            log.warning(
                "ledger %s loaded with %d error(s); first at line %s: %s",
                ws_id, len(errors), source.get("lineno", "?"), getattr(first, "message", first),
            )
        if key is not None:
            ledger_cache.put(path, accounts, key, entries, errors, options)
        return entries, errors

    def health(self, ws_id: str) -> dict:
        """``{"txns": n, "errors": [{"lineno", "message"}][:20], "error_count": k}`` (GET /ledger/{ws}/health)."""
        entries, errors = self.load(ws_id)
        return {
            "txns": sum(1 for e in entries if isinstance(e, bc_data.Transaction)),
            "errors": [
                {
                    "lineno": (getattr(e, "source", None) or {}).get("lineno"),
                    "message": str(getattr(e, "message", e)),
                }
                for e in errors[:20]
            ],
            "error_count": len(errors),
        }

    def _to_txn(self, entry: bc_data.Transaction) -> Transaction:
        meta = {k: str(v) for k, v in (entry.meta or {}).items() if k not in _INTERNAL_META}
        return Transaction(
            date=entry.date,
            payee=entry.payee,
            narration=entry.narration or "",
            postings=[
                Posting(
                    account=p.account,
                    amount=Amount(amount=p.units.number, currency=p.units.currency)
                    if p.units is not None and p.units.number is not None
                    else None,
                )
                for p in entry.postings
            ],
            tags=sorted(entry.tags or ()),
            links=sorted(entry.links or ()),
            meta=meta,
        )

    def journal(
        self,
        ws_id: str,
        start: date | None = None,
        end: date | None = None,
        account_prefix: str | None = None,
    ) -> list[Transaction]:
        entries, _ = self.load(ws_id)
        out: list[Transaction] = []
        for e in entries:
            if not isinstance(e, bc_data.Transaction):
                continue
            if start and e.date < start:
                continue
            if end and e.date > end:
                continue
            if account_prefix and not any(p.account.startswith(account_prefix) for p in e.postings):
                continue
            out.append(self._to_txn(e))
        return sorted(out, key=lambda t: t.date)

    def balances(self, ws_id: str, as_of: date | None = None) -> dict[str, list[Amount]]:
        entries, _ = self.load(ws_id)
        totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        for e in entries:
            if not isinstance(e, bc_data.Transaction):
                continue
            if as_of and e.date > as_of:
                continue
            for p in e.postings:
                if p.units is None or p.units.number is None:
                    continue
                totals[p.account][p.units.currency] += p.units.number
        return {
            acct: [Amount(amount=v, currency=c) for c, v in sorted(cur.items())]
            for acct, cur in sorted(totals.items())
        }

    def query(self, ws_id: str, bql: str) -> list[dict]:
        import beanquery

        path = self.main_path(ws_id)
        if not path.exists():
            return []
        conn = beanquery.connect("beancount:" + str(path))
        cursor = conn.execute(bql)
        columns = [c[0] for c in cursor.description]
        return [{col: _jsonable(val) for col, val in zip(columns, row, strict=False)} for row in cursor.fetchall()]

    def accounts(self, ws_id: str) -> list[str]:
        entries, _ = self.load(ws_id)
        found = {e.account for e in entries if isinstance(e, bc_data.Open)}
        for e in entries:
            if isinstance(e, bc_data.Transaction):
                found.update(p.account for p in e.postings)
        return sorted(found)


def _jsonable(value: object) -> object:
    # Inventory subclasses dict in Beancount v3; render it the way bean-query prints it.
    if type(value).__name__ in {"Inventory", "Position", "Amount"}:
        return str(value)
    if isinstance(value, Decimal | date):
        return str(value)
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)
