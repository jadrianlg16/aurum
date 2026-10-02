"""The one place the organizer touches pf and the ledger.

Everything pf-related is imported **lazily inside functions** (``pf.streams`` imports
``organizer.commitments`` at module level, so a module-level import here would be a cycle) and every
difference between pf schema/API versions is absorbed here with ``model_fields`` / ``has_column`` /
``.get()`` checks:

* ``pf.entries.EntryIn`` may or may not carry ``commitment_id`` (pf v3);
* ``pf_entries.commitment_id`` may not exist yet — reads/stamps are guarded by ``has_column``;
* ``pf.entries.get_entry`` exposes neither ``txn_id`` nor ``voided``/timestamps, so :func:`pf_entry_row`
  reads the row directly (same precedent as ``summary.has_bank_lines`` reading ``ingest_bank_lines``);
* ``pf.budgets.budget_status`` rows carry ``effective`` (budget plus carried rollover); older rows carry
  only ``budget``.

Ledger reads go through ``pf.ledger_view.live_txns`` (void semantics: no reversals, no reversed originals, no
``#voided``) and fall back to the same filter over ``get_ledger().journal`` when that module is absent.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from typing import Any

from ..core.money import Amount
from . import store

REVERSAL_TAGS = frozenset({"entry-reversal", "voided-reversal"})
VOIDED_TAGS = frozenset({"voided"})


# --------------------------------------------------------------------------- workspace


def base_currency(ws_id: str) -> str:
    """``Workspace.base_currency``; ``MXN`` when the workspace file does not exist (bare tests)."""
    try:
        from ..core.workspaces import WorkspaceNotFound, get_workspace
    except Exception:  # noqa: BLE001
        return "MXN"
    try:
        return get_workspace(ws_id).base_currency or "MXN"
    except (WorkspaceNotFound, ValueError, OSError):
        return "MXN"


def module_on(ws_id: str, name: str) -> bool:
    try:
        from ..core.workspaces import module_on as _module_on
    except Exception:  # noqa: BLE001
        return False
    return _module_on(ws_id, name)


# --------------------------------------------------------------------------- ledger (void-aware)


def _fallback_live_txns(ws_id: str, start: date | None, end: date | None) -> list:
    try:
        from ..ledger.base import get_ledger

        journal = get_ledger().journal(ws_id)
    except Exception:  # noqa: BLE001 — no ledger yet
        return []
    reversed_ids: set[str] = set()
    for txn in journal:
        if set(txn.tags or []) & REVERSAL_TAGS:
            target = (txn.meta or {}).get("reverses") or ""
            if target:
                reversed_ids.add(target)
    out = []
    for txn in journal:
        tags = set(txn.tags or [])
        if tags & REVERSAL_TAGS or tags & VOIDED_TAGS:
            continue
        if any(link in reversed_ids for link in (txn.links or [])):
            continue
        if start and txn.date < start:
            continue
        if end and txn.date > end:
            continue
        out.append(txn)
    return out


def live_txns(ws_id: str, start: date | None = None, end: date | None = None) -> list:
    """Live ledger transactions in ``[start, end]`` — ONE journal parse per call. Callers that build
    several commitments share the result through ``txns=``."""
    try:
        from ..pf import ledger_view
    except Exception:  # noqa: BLE001
        return _fallback_live_txns(ws_id, start, end)
    try:
        # Unbounded read = a single parse (a bounded one parses twice for the reversal pairing).
        txns = ledger_view.live_txns(ws_id)
    except Exception:  # noqa: BLE001 — workspace without a ledger file
        return []
    if start is None and end is None:
        return txns
    return [t for t in txns if (start is None or t.date >= start) and (end is None or t.date <= end)]


def savings_accounts(ws_id: str) -> frozenset[str]:
    """Ledger paths of the pf accounts typed ``savings``. They live under ``Assets:Bank:`` next to
    checking, but money put aside is not money to spend, so the Disponible leaves them out."""
    try:
        rows = store.db().execute(
            "SELECT account FROM pf_accounts WHERE ws_id=? AND type='savings'", (ws_id,)
        ).fetchall()
    except sqlite3.Error:
        return frozenset()
    return frozenset(r["account"] for r in rows)


def liquid_balance(ws_id: str, prefixes: tuple[str, ...], as_of: date | None = None,
                   exclude: frozenset[str] = frozenset()) -> Decimal:
    try:
        from ..ledger.base import get_ledger

        balances = get_ledger().balances(ws_id, as_of=as_of)
    except Exception:  # noqa: BLE001
        return Decimal("0")
    total = Decimal("0")
    for account, amounts in balances.items():
        if account.startswith(prefixes) and account not in exclude:
            total += sum((a.amount for a in amounts), Decimal("0"))
    return total


# --------------------------------------------------------------------------- pf accounts


def accounts_index(ws_id: str) -> dict[str, dict[str, Any]]:
    """Every pf account of the workspace (archived included) keyed by id AND by ledger account name:
    ``{"acc-…": {id, name, account, archived}, "Assets:Bank:Bbva": {…}}``. One query per request;
    rows are the raw ``pf_accounts`` columns (no balance computation — that would parse the ledger
    once per account)."""
    conn = store.db()
    try:
        rows = conn.execute(
            "SELECT id, name, account, archived FROM pf_accounts WHERE ws_id=? ORDER BY archived, type, name",
            (ws_id,),
        ).fetchall()
    except sqlite3.OperationalError:  # pragma: no cover — pf schema absent
        return {}
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        row = {"id": r["id"], "name": r["name"], "account": r["account"], "archived": bool(r["archived"])}
        out[row["id"]] = row
        # active rows win the reverse (ledger account → id) lookup
        if row["account"] not in out or (out[row["account"]]["archived"] and not row["archived"]):
            out[row["account"]] = row
    return out


def get_account(ws_id: str, account_id: str) -> dict[str, Any]:
    """``pf.accounts_admin.get_account`` (KeyError when unknown)."""
    from ..pf import accounts_admin

    return accounts_admin.get_account(ws_id, account_id)


def resolve_account(ws_id: str, account_id: str | None, account: str | None) -> tuple[str | None, str]:
    """→ ``(account_id, ledger_account)``. ``account_id`` wins (KeyError when unknown), else a ledger
    name is reverse-looked-up for its pf id, else the legacy default ``Assets:Bank``."""
    if account_id:
        row = get_account(ws_id, account_id)
        return row["id"], row["account"]
    if account:
        hit = accounts_index(ws_id).get(account)
        return (hit["id"] if hit else None), account
    return None, "Assets:Bank"


# --------------------------------------------------------------------------- pf entries


def has_commitment_column() -> bool:
    from ..core.db import has_column

    try:
        return has_column(store.db(), "pf_entries", "commitment_id")
    except sqlite3.OperationalError:  # pragma: no cover
        return False


def pf_entry_row(ws_id: str, entry_id: str) -> dict[str, Any] | None:
    """Raw ``pf_entries`` columns the organizer needs (``txn_id``, ``voided``, timestamps, optional
    ``commitment_id``); ``None`` when the row does not exist."""
    conn = store.db()
    cols = "id, txn_id, voided, source, created_at, updated_at, kind, amount, currency, date, account_id"
    if has_commitment_column():
        cols += ", commitment_id"
    try:
        row = conn.execute(f"SELECT {cols} FROM pf_entries WHERE ws_id=? AND id=?", (ws_id, entry_id)).fetchone()
    except sqlite3.OperationalError:  # pragma: no cover
        return None
    if row is None:
        return None
    d = dict(row)
    d["voided"] = bool(d["voided"])
    d.setdefault("commitment_id", None)
    return d


def pf_entry_by_txn(ws_id: str, txn_id: str) -> dict[str, Any] | None:
    """The non-voided pf entry that owns ``txn_id`` (a matched ledger transaction), if any."""
    conn = store.db()
    try:
        row = conn.execute(
            "SELECT id, txn_id, voided, created_at, updated_at FROM pf_entries "
            "WHERE ws_id=? AND txn_id=? AND voided=0 LIMIT 1",
            (ws_id, txn_id),
        ).fetchone()
    except sqlite3.OperationalError:  # pragma: no cover
        return None
    return dict(row) if row else None


def linked_entries(ws_id: str, commitment_id: str, start: date, end: date) -> list[dict[str, Any]]:
    """Non-voided pf entries stamped with ``commitment_id`` dated in ``[start, end]`` — empty until pf
    v3 adds the column."""
    if not has_commitment_column():
        return []
    conn = store.db()
    rows = conn.execute(
        "SELECT id, txn_id, date, amount, currency FROM pf_entries "
        "WHERE ws_id=? AND commitment_id=? AND voided=0 AND date>=? AND date<=? ORDER BY date",
        (ws_id, commitment_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    return [dict(r) for r in rows]


def stamp_commitment(ws_id: str, entry_id: str, commitment_id: str) -> bool:
    """Write ``pf_entries.commitment_id`` when the column exists and the row has none yet."""
    if not has_commitment_column():
        return False
    conn = store.db()
    cur = conn.execute(
        "UPDATE pf_entries SET commitment_id=? WHERE ws_id=? AND id=? AND commitment_id IS NULL",
        (commitment_id, ws_id, entry_id),
    )
    conn.commit()
    return cur.rowcount > 0


def create_pf_entry(
    ws_id: str,
    *,
    kind: str,
    when: date,
    amount: Amount,
    account_id: str,
    label_id: str | None,
    payee: str,
    commitment_id: str,
) -> dict[str, Any]:
    """``pf.entries.create_entry`` with ``source='organizer'``, tag ``pago-fijo`` and — when
    ``EntryIn`` has the field — ``commitment_id``. Returns the raw row (see :func:`pf_entry_row`).
    Raises pf's own ``KeyError`` (unknown account/label) and ``ValueError`` (rejected entry)."""
    from ..pf import entries as pf_entries

    payload: dict[str, Any] = {
        "kind": kind,
        "date": when,
        "amount": amount,
        "account_id": account_id,
        "label_id": label_id,
        "payee": payee,
        "tags": ["pago-fijo"],
        "source": "organizer",
    }
    if "commitment_id" in pf_entries.EntryIn.model_fields:
        payload["commitment_id"] = commitment_id
    created = pf_entries.create_entry(ws_id, pf_entries.EntryIn(**payload))
    stamp_commitment(ws_id, created["id"], commitment_id)
    row = pf_entry_row(ws_id, created["id"])
    assert row is not None
    return row


def void_pf_entry(ws_id: str, entry_id: str) -> dict[str, Any]:
    """``pf.entries.delete_entry`` — raises ValueError (already voided), PermissionError (not editable)
    or KeyError (unknown) exactly as pf does; the router maps them to 409/403/404."""
    from ..pf import entries as pf_entries

    return pf_entries.delete_entry(ws_id, entry_id)


# --------------------------------------------------------------------------- pf budgets / labels


def budget_rows(ws_id: str, period: str) -> list[dict[str, Any]]:
    """``pf.budgets.budget_status(ws, period)['budgets']`` normalized to ``{label_id, effective:Decimal,
    spent:Decimal}`` (``effective`` falls back to ``budget`` when a row has no carry-forward field)."""
    try:
        from ..pf import budgets as pf_budgets
    except Exception:  # noqa: BLE001
        return []
    try:
        status = pf_budgets.budget_status(ws_id, period)
    except Exception:  # noqa: BLE001 — no budgets/labels yet
        return []
    out = []
    for row in status.get("budgets", []):
        effective = row.get("effective") or row.get("budget") or {"amount": "0"}
        spent = row.get("spent") or {"amount": "0"}
        out.append({
            "label_id": row.get("label_id"),
            "label_name": row.get("label_name"),
            "effective": Decimal(str(effective["amount"])),
            "spent": Decimal(str(spent["amount"])),
        })
    return out


def labels_index(ws_id: str) -> dict[str, dict[str, Any]]:
    try:
        from ..pf import labels as pf_labels

        return {lbl["id"]: lbl for lbl in pf_labels.list_labels(ws_id)}
    except Exception:  # noqa: BLE001
        return {}
