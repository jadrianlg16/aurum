"""Reconcile bank lines against ledger transactions and CFDIs.

A bank line is "matched" once ``matched_txn_id`` and/or ``cfdi_uuid`` is set on
``ingest_bank_lines``. Suggestions are heuristic: amount within ±1% and date within ±3 days —
recibidos CFDIs for outflows (negative bank amount), emitidos/REP CFDIs for inflows (positive bank
amount) — plus any ledger transaction touching a bank/cash account within the same tolerance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from ..core.db import connect
from ..core.explain import Explain
from ..core.i18n import t
from ..ledger.base import Transaction, get_ledger

AMOUNT_TOLERANCE_PCT = Decimal("0.01")
DATE_TOLERANCE_DAYS = 3
CASH_PREFIXES = ("Assets:Bank:", "Assets:Cash")

_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass
class Suggestion:
    txn_id: str | None
    cfdi_uuid: str | None
    score: float


def _period_bounds(period: str) -> tuple[date, date]:
    from ..ledger.statements import period_bounds

    return period_bounds(period)


def _score(amount_pct_diff: Decimal, date_diff_days: int) -> float:
    amount_component = max(Decimal("0"), 1 - (amount_pct_diff / AMOUNT_TOLERANCE_PCT))
    date_component = max(Decimal("0"), 1 - (Decimal(date_diff_days) / Decimal(DATE_TOLERANCE_DAYS)))
    return float((amount_component * Decimal("0.6") + date_component * Decimal("0.4")).quantize(Decimal("0.01")))


def _amount_pct_diff(a: Decimal, b: Decimal) -> Decimal:
    base = max(abs(a), abs(b), Decimal("0.01"))
    return abs(a - b) / base


def _cfdi_candidates(ws_id: str, line: dict, start: date, end: date) -> list[Suggestion]:
    conn = connect()
    try:
        direction = "recibido" if Decimal(line["amount"]) < 0 else "emitido"
        rows = conn.execute(
            "SELECT uuid, total, fecha FROM ingest_cfdi WHERE ws_id=? AND direction=? "
            "AND fecha >= ? AND fecha <= ?",
            (ws_id, direction, start.isoformat(), (end + timedelta(days=1)).isoformat()),
        ).fetchall()
    finally:
        conn.close()
    bank_amount = abs(Decimal(line["amount"]))
    bank_date = date.fromisoformat(line["date"])
    out = []
    for row in rows:
        total = Decimal(str(row["total"]))
        pct_diff = _amount_pct_diff(bank_amount, total)
        if pct_diff > AMOUNT_TOLERANCE_PCT:
            continue
        cfdi_date = date.fromisoformat(str(row["fecha"])[:10])
        day_diff = abs((cfdi_date - bank_date).days)
        if day_diff > DATE_TOLERANCE_DAYS:
            continue
        out.append(Suggestion(txn_id=None, cfdi_uuid=row["uuid"], score=_score(pct_diff, day_diff)))
    return out


def _txn_candidates(txns: list[Transaction], line: dict) -> list[Suggestion]:
    bank_amount = Decimal(line["amount"])
    bank_date = date.fromisoformat(line["date"])
    out = []
    for txn in txns:
        for p in txn.postings:
            if p.amount is None or not p.account.startswith(CASH_PREFIXES):
                continue
            pct_diff = _amount_pct_diff(bank_amount, p.amount.amount)
            if pct_diff > AMOUNT_TOLERANCE_PCT:
                continue
            day_diff = abs((txn.date - bank_date).days)
            if day_diff > DATE_TOLERANCE_DAYS:
                continue
            txn_id = txn.links[0] if txn.links else None
            if txn_id is None:
                continue
            out.append(Suggestion(txn_id=txn_id, cfdi_uuid=None, score=_score(pct_diff, day_diff)))
            break
    return out


def suggestions_for(ws_id: str, line: dict, txns: list[Transaction]) -> list[dict]:
    start, end = _period_bounds(line["date"][:7])
    candidates = _txn_candidates(txns, line) + _cfdi_candidates(ws_id, line, start, end)
    candidates.sort(key=lambda s: s.score, reverse=True)
    return [{"txn_id": c.txn_id, "cfdi_uuid": c.cfdi_uuid, "score": c.score} for c in candidates[:5]]


def reconcile_period(ws_id: str, period: str, lang: str | None = None) -> dict:
    if not _PERIOD.match(period):
        raise ValueError("period must be YYYY-MM")
    start, end = _period_bounds(period)
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM ingest_bank_lines WHERE ws_id=? AND date>=? AND date<=? ORDER BY date",
            (ws_id, start.isoformat(), end.isoformat()),
        ).fetchall()
        matched_cfdi_uuids = {
            r["cfdi_uuid"]
            for r in conn.execute(
                "SELECT cfdi_uuid FROM ingest_bank_lines WHERE ws_id=? AND cfdi_uuid IS NOT NULL", (ws_id,)
            ).fetchall()
        }
        all_cfdi_uuids = {
            r["uuid"]
            for r in conn.execute(
                "SELECT uuid FROM ingest_cfdi WHERE ws_id=? AND fecha>=? AND fecha<=?",
                (ws_id, start.isoformat(), (end + timedelta(days=1)).isoformat()),
            ).fetchall()
        }
    finally:
        conn.close()

    txns = get_ledger().journal(ws_id, start=start, end=end)

    bank_lines_out = []
    unmatched_count = 0
    for r in rows:
        line = dict(r)
        already_matched = bool(line.get("matched_txn_id") or line.get("cfdi_uuid"))
        suggestions = [] if already_matched else suggestions_for(ws_id, line, txns)
        if not already_matched:
            unmatched_count += 1
        bank_lines_out.append(
            {
                "id": line["id"],
                "date": line["date"],
                "description": line["description"],
                "amount": {"amount": line["amount"], "currency": line["currency"]},
                "matched_txn_id": line.get("matched_txn_id"),
                "cfdi_uuid": line.get("cfdi_uuid"),
                "suggestions": suggestions,
            }
        )

    unmatched_cfdi = sorted(all_cfdi_uuids - matched_cfdi_uuids)

    explain = Explain(summary=t("ingest.reconcile", lang))
    explain.add_step("bank_lines", len(rows))
    explain.add_step("unmatched_bank", unmatched_count)
    explain.add_step("unmatched_cfdi", len(unmatched_cfdi))

    return {
        "bank_lines": bank_lines_out,
        "unmatched_bank": unmatched_count,
        "unmatched_cfdi": unmatched_cfdi,
        "explain": explain.model_dump(mode="json"),
    }


class MatchNotFound(KeyError):
    pass


def match(ws_id: str, bank_line_id: int, txn_id: str | None = None, cfdi_uuid: str | None = None) -> dict:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM ingest_bank_lines WHERE ws_id=? AND id=?", (ws_id, bank_line_id)
        ).fetchone()
        if row is None:
            raise MatchNotFound(bank_line_id)
        new_txn_id = txn_id if txn_id is not None else row["matched_txn_id"]
        new_cfdi_uuid = cfdi_uuid if cfdi_uuid is not None else row["cfdi_uuid"]
        conn.execute(
            "UPDATE ingest_bank_lines SET matched_txn_id=?, cfdi_uuid=? WHERE ws_id=? AND id=?",
            (new_txn_id, new_cfdi_uuid, ws_id, bank_line_id),
        )
        conn.commit()
        return dict(
            conn.execute("SELECT * FROM ingest_bank_lines WHERE ws_id=? AND id=?", (ws_id, bank_line_id)).fetchone()
        )
    finally:
        conn.close()


def unmatch(ws_id: str, bank_line_id: int) -> dict:
    conn = connect()
    try:
        cur = conn.execute(
            "UPDATE ingest_bank_lines SET matched_txn_id=NULL, cfdi_uuid=NULL WHERE ws_id=? AND id=?",
            (ws_id, bank_line_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise MatchNotFound(bank_line_id)
        return dict(
            conn.execute("SELECT * FROM ingest_bank_lines WHERE ws_id=? AND id=?", (ws_id, bank_line_id)).fetchone()
        )
    finally:
        conn.close()
