"""Recurring-commitment detection: deterministic, explainable, no model.

Sources (each read defensively — a missing optional module degrades to "fewer events", never an error):

* the ledger journal (``Expenses:*`` / ``Income:*`` postings),
* ``ingest_bank_lines`` (the ingest module's table),
* ``ingest_cfdi`` recibidos (a supplier invoicing you every month is a bill),
* ``pf_loans`` / ``pf_credit_cards`` → ``loan_payment`` candidates carrying the linked id.

Algorithm

1. **Events.** Every source contributes ``{date, amount>0, description, direction}``. Identical
   (merchant, date, amount) events from two sources are one event — the demo posts each charge to
   both the ledger and the bank table, and a charge must not be counted twice.
2. **Merchant.** ``normalize.normalize(description)`` (see that module for the exact steps).
3. **Amount grouping.** Amounts within **±10 %** of the group mean stay one commitment — this is
   what keeps a price increase (199 → 219, mean 205.67) in a single commitment instead of splitting
   it into two. When the spread is wider the group is split greedily by sorted amount. Utilities
   (``category_hint == "utility"``) are inherently variable and use a ±35 % band with
   ``amount_variable = True``.
4. **Cadence.** Median of the consecutive intervals, mapped through ``cadence.BANDS``.
   ≥2 occurrences are required, ≥3 for weekly.
5. **Confidence.** ``0.34·regularity + 0.33·amount_consistency + 0.33·count_factor`` — every term is
   in the candidate's ``explain``.
6. **Claimed merchants.** A merchant already carried by an *active/trial/paused* commitment is never
   proposed again. A **cancelled** commitment's merchant that keeps charging (≥ ``min_occurrences``
   events after ``ended``) resurfaces as a candidate flagged ``cancelled_still_charging`` carrying
   ``existing_commitment_id``, so the alerts can warn about it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import Amount, q2
from . import cadence as cad
from . import normalize, pf_bridge, store
from .models import Candidate, Commitment, Evidence

AMOUNT_TOLERANCE = Decimal("0.10")
VARIABLE_TOLERANCE = Decimal("0.35")
VARIABLE_HINTS = {"utility"}
LOOKBACK_DAYS = 550  # enough to see two annual renewals


@dataclass(frozen=True)
class Event:
    day: date
    amount: Decimal          # always positive: the magnitude of the movement
    description: str
    direction: str           # "out" | "in"
    source: str              # bank | ledger | cfdi
    currency: str = "MXN"


# --------------------------------------------------------------------------- sources


def _ledger_events(ws_id: str, since: date) -> list[Event]:
    try:
        from ..ledger.base import get_ledger

        txns = get_ledger().journal(ws_id, start=since)
    except Exception:  # noqa: BLE001 — no ledger for this workspace yet
        return []
    out: list[Event] = []
    for t in txns:
        if "voided" in (t.tags or []):
            continue
        desc = t.payee or t.narration or ""
        for p in t.postings:
            if p.amount is None:
                continue
            if p.account.startswith("Expenses:") and p.amount.amount > 0:
                out.append(Event(t.date, p.amount.amount, desc, "out", "ledger", p.amount.currency))
            elif p.account.startswith("Income:") and p.amount.amount < 0:
                out.append(Event(t.date, -p.amount.amount, desc, "in", "ledger", p.amount.currency))
    return out


def _bank_events(ws_id: str, since: date) -> list[Event]:
    conn = store.db()
    try:
        rows = conn.execute(
            "SELECT date, description, amount, currency FROM ingest_bank_lines "
            "WHERE ws_id=? AND date>=? ORDER BY date",
            (ws_id, since.isoformat()),
        ).fetchall()
    except sqlite3.OperationalError:  # pragma: no cover — ingest schema absent
        return []
    out: list[Event] = []
    base = pf_bridge.base_currency(ws_id)
    for r in rows:
        amount = Decimal(str(r["amount"]))
        if amount == 0:
            continue
        out.append(
            Event(
                store.as_date(r["date"]), abs(amount), r["description"],
                "in" if amount > 0 else "out", "bank", r["currency"] or base,
            )
        )
    return out


def _cfdi_events(ws_id: str, since: date) -> list[Event]:
    conn = store.db()
    try:
        rows = conn.execute(
            "SELECT fecha, total, moneda, emisor_rfc, json FROM ingest_cfdi "
            "WHERE ws_id=? AND direction='recibido' AND fecha>=? ORDER BY fecha",
            (ws_id, since.isoformat()),
        ).fetchall()
    except sqlite3.OperationalError:  # pragma: no cover
        return []
    out: list[Event] = []
    base = pf_bridge.base_currency(ws_id)
    for r in rows:
        doc = store.loads(r["json"], {}) or {}
        desc = doc.get("emisor_nombre") or r["emisor_rfc"]
        out.append(
            Event(store.as_date(r["fecha"]), abs(Decimal(str(r["total"]))), str(desc), "out", "cfdi",
                  r["moneda"] or base)
        )
    return out


def collect_events(ws_id: str, since: date) -> list[Event]:
    """All sources, de-duplicated on (merchant, date, amount) — bank evidence wins."""
    ranked = {"bank": 0, "ledger": 1, "cfdi": 2}
    seen: dict[tuple[str, date, Decimal], Event] = {}
    for ev in [*_bank_events(ws_id, since), *_ledger_events(ws_id, since), *_cfdi_events(ws_id, since)]:
        key = (normalize.normalize(ev.description), ev.day, q2(ev.amount))
        current = seen.get(key)
        if current is None or ranked[ev.source] < ranked[current.source]:
            seen[key] = ev
    return sorted(seen.values(), key=lambda e: (e.day, e.description))


# --------------------------------------------------------------------------- grouping


def _split_by_amount(events: list[Event], tolerance: Decimal) -> list[list[Event]]:
    """One group when every amount is within ``tolerance`` of the group mean; else greedy split."""
    if len(events) < 2:
        return [events]
    amounts = [e.amount for e in events]
    mean = sum(amounts, Decimal("0")) / len(amounts)
    if mean > 0 and all(abs(a - mean) <= mean * tolerance for a in amounts):
        return [events]
    groups: list[list[Event]] = []
    for ev in sorted(events, key=lambda e: e.amount):
        placed = False
        for g in groups:
            g_mean = sum((x.amount for x in g), Decimal("0")) / len(g)
            if g_mean > 0 and abs(ev.amount - g_mean) <= g_mean * tolerance:
                g.append(ev)
                placed = True
                break
        if not placed:
            groups.append([ev])
    return [sorted(g, key=lambda e: e.day) for g in groups]


def _confidence(intervals: list[int], amounts: list[Decimal], median: int) -> tuple[float, dict]:
    regularity = 1.0
    if intervals and median:
        worst = max(abs(i - median) for i in intervals)
        regularity = max(0.0, 1.0 - worst / median)
    mean = sum(amounts, Decimal("0")) / len(amounts) if amounts else Decimal("0")
    consistency = 1.0
    if mean > 0:
        worst_amt = max(abs(a - mean) for a in amounts)
        consistency = max(0.0, 1.0 - float(worst_amt / mean))
    count_factor = min(1.0, (len(amounts) - 1) / 3)
    score = 0.34 * regularity + 0.33 * consistency + 0.33 * count_factor
    return round(score, 2), {
        "regularity": round(regularity, 4),
        "amount_consistency": round(consistency, 4),
        "count_factor": round(count_factor, 4),
    }


def _candidate_from_group(
    ws_id: str, merchant: str, group: list[Event], lang: str, today: date, variable: bool,
    info: dict[str, str | None],
) -> tuple[Commitment, list[Evidence], float, Explain] | None:
    dates = [e.day for e in group]
    cadence, interval_days, intervals, median = cad.infer_cadence(dates)
    if len(group) < cad.min_occurrences(cadence):
        return None
    if cadence == "custom" and (median is None or median < 5 or median > 400):
        return None
    amounts = [e.amount for e in group]
    # The most recent amount is what will be charged next, not the average.
    amount = q2(amounts[-1])
    anchor_day, weekday = cad.anchors_from(dates, cadence)
    last_seen = dates[-1]
    next_due = cad.project_next(
        last_seen, cadence, today=today, interval_days=interval_days,
        anchor_day=anchor_day, weekday=weekday, strictly_after=True,
    )
    confidence, terms = _confidence(intervals, amounts, median or 1)
    direction = group[0].direction
    kind = "income" if direction == "in" else (info.get("kind") or "other")
    essential = "needs" if direction == "in" else (info.get("essential") or "wants")
    commitment = Commitment(
        ws_id=ws_id,
        kind=kind,
        name=merchant.title() if merchant.isupper() else merchant,
        merchant_patterns=[merchant],
        amount=Amount(amount=amount, currency=group[-1].currency),
        amount_variable=variable,
        cadence=cadence,
        interval_days=interval_days,
        anchor_day=anchor_day,
        weekday=weekday,
        next_due=next_due,
        account="Assets:Bank",
        essential=essential,
        status="active",
        started=dates[0],
        source="detected",
        confidence=confidence,
        last_seen=last_seen,
        category_hint=info.get("category_hint"),
    )
    explain = Explain(
        summary=i18n_t(
            "organizer.detect.candidate", lang, merchant=merchant, count=len(group),
            intervals=",".join(str(i) for i in intervals), median=median, cadence=cadence,
        )
    )
    explain.add_step("intervals_days", intervals)
    explain.add_step("median_interval", median, formula="median(intervals)")
    explain.add_step(
        "cadence", cadence,
        formula=f"band {cad.NOMINAL_DAYS.get(cadence, interval_days or 0)}d" if cadence != "custom"
        else f"custom every {interval_days}d",
    )
    explain.add_step("amounts", [str(q2(a)) for a in amounts])
    tol = VARIABLE_TOLERANCE if variable else AMOUNT_TOLERANCE
    explain.add_step("amount_tolerance", f"±{tol * 100:.0f}%", formula="|amount − mean| ≤ tol × mean")
    explain.add_step("next_due", next_due.isoformat(), formula=f"{last_seen.isoformat()} + {cadence}")
    for key, value in terms.items():
        explain.add_step(key, value)
    explain.add_step(
        "confidence", confidence,
        formula="0.34·regularity + 0.33·amount_consistency + 0.33·count_factor",
    )
    explain.confidence = confidence
    evidence = [
        Evidence(
            date=e.day, amount=Amount(amount=q2(e.amount), currency=e.currency),
            description=e.description, source=e.source,
        )
        for e in group
    ]
    return commitment, evidence, confidence, explain


# --------------------------------------------------------------------------- pf loans / cards


def _loan_candidates(ws_id: str, lang: str, today: date) -> list[tuple[Commitment, list[Evidence], float, Explain]]:
    out = []
    try:
        from ..pf import credit as pf_credit
    except Exception:  # noqa: BLE001 — pf not present
        return out
    try:
        loans = pf_credit.list_loans(ws_id)
    except Exception:  # noqa: BLE001
        loans = []
    for loan in loans:
        try:
            am = pf_credit.loan_amortization(ws_id, loan["id"])
            payment = Decimal(am["payment"])
        except Exception:  # noqa: BLE001
            continue
        start = store.as_date(loan["start"]) or today
        next_due = cad.project_next(start, "monthly", today=today, anchor_day=start.day)
        explain = Explain(summary=i18n_t("organizer.detect", lang))
        explain.add_step("loan", loan["name"])
        explain.add_step("payment", payment, formula="pf.credit.loan_amortization(principal, rate, months)")
        explain.add_step("next_due", next_due.isoformat(), formula=f"anchor_day={start.day}")
        explain.confidence = 0.95
        out.append((
            Commitment(
                ws_id=ws_id, kind="loan_payment", name=loan["name"],
                merchant_patterns=[normalize.normalize(loan["name"])],
                amount=Amount(amount=q2(payment), currency=loan["currency"]),
                cadence="monthly", anchor_day=start.day, next_due=next_due,
                account=loan["account"], essential="debt", status="active", started=start,
                linked_loan_id=loan["id"], source="detected", confidence=0.95,
                category_hint="loan",
            ),
            [], 0.95, explain,
        ))
    try:
        cards = pf_credit.list_cards(ws_id)
    except Exception:  # noqa: BLE001
        cards = []
    for card in cards:
        due_day = int(card["due_day"])
        next_due = cad.project_next(today, "monthly", today=today, anchor_day=due_day)
        explain = Explain(summary=i18n_t("organizer.detect", lang))
        explain.add_step("card", card["name"])
        explain.add_step("due_day", due_day, formula="pf_credit_cards.due_day")
        explain.add_step("amount_variable", True, formula="the statement balance changes every month")
        explain.confidence = 0.6
        out.append((
            Commitment(
                ws_id=ws_id, kind="loan_payment", name=f"{card['name']} (pago)",
                merchant_patterns=[normalize.normalize(card["name"])],
                amount=Amount(amount=Decimal("0"), currency=card["currency"]),
                amount_variable=True, cadence="monthly", anchor_day=due_day, next_due=next_due,
                account=card["account"], essential="debt", status="active",
                linked_card_id=card["id"], source="detected", confidence=0.6, category_hint="card",
            ),
            [], 0.6, explain,
        ))
    return out


# --------------------------------------------------------------------------- entry point


def detect(ws_id: str, today: date | None = None, lang: str | None = None,
           lookback_days: int = LOOKBACK_DAYS) -> list[Candidate]:
    """Scan every source and persist the open candidates (the wizard resumes from the table)."""
    today = today or date.today()
    lang = lang or ws_lang(ws_id)
    since = today - timedelta(days=lookback_days)
    events = collect_events(ws_id, since)

    by_merchant: dict[tuple[str, str], list[Event]] = {}
    for ev in events:
        merchant = normalize.normalize(ev.description)
        if not merchant:
            continue
        by_merchant.setdefault((merchant, ev.direction), []).append(ev)

    results: list[tuple[Commitment, list[Evidence], float, Explain]] = []
    for (merchant, _direction), group in sorted(by_merchant.items()):
        info = normalize.classify(group[0].description)
        variable = (info.get("category_hint") in VARIABLE_HINTS)
        tolerance = VARIABLE_TOLERANCE if variable else AMOUNT_TOLERANCE
        for sub in _split_by_amount(group, tolerance):
            built = _candidate_from_group(ws_id, merchant, sorted(sub, key=lambda e: e.day),
                                          lang, today, variable, info)
            if built is not None:
                results.append(built)
    results.extend(_loan_candidates(ws_id, lang, today))

    existing_patterns = _claimed_patterns(ws_id)
    cancelled = _cancelled_patterns(ws_id)
    candidates: list[Candidate] = []
    for commitment, evidence, confidence, explain in results:
        if any(p in existing_patterns for p in commitment.merchant_patterns):
            continue
        flags: list[str] = []
        existing_id: str | None = None
        old = next((cancelled[p] for p in commitment.merchant_patterns if p in cancelled), None)
        if old is not None:
            after = [e for e in evidence if old.ended is None or e.date > old.ended]
            if len(after) < cad.min_occurrences(commitment.cadence):
                continue  # cancelled and quiet: stays cancelled
            flags = ["cancelled_still_charging"]
            existing_id = old.id
            evidence = after
        commitment = commitment.model_copy(update={"explain": explain})
        cid = _persist_candidate(ws_id, commitment, evidence, confidence, flags=flags,
                                 existing_commitment_id=existing_id)
        candidates.append(
            Candidate(id=cid, merchant=commitment.merchant_patterns[0], preview=commitment,
                      evidence=evidence, confidence=confidence, status="open", flags=flags,
                      existing_commitment_id=existing_id)
        )
    # A merchant can be persisted twice in one pass (bank group + pf loan/card); the stored row is
    # the merge of both, so return one Candidate per row read back from the table.
    seen_ids: dict[str, Candidate] = {}
    for candidate in candidates:
        seen_ids[candidate.id] = get_candidate(ws_id, candidate.id)
    merged = [c for c in seen_ids.values() if c.status == "open"]
    merged.sort(key=lambda c: (-c.confidence, c.merchant))
    return merged


_LIVE_STATUSES = ("active", "trial", "paused")


def _claimed_patterns(ws_id: str) -> set[str]:
    """Merchants carried by a live (active/trial/paused) commitment — never proposed twice."""
    from . import commitments as cmt

    out: set[str] = set()
    for c in cmt.list_commitments(ws_id):
        if c.status not in _LIVE_STATUSES:
            continue
        out.update(c.merchant_patterns)
        if c.linked_loan_id:
            out.add(f"loan:{c.linked_loan_id}")
        if c.linked_card_id:
            out.add(f"card:{c.linked_card_id}")
    return out


def _cancelled_patterns(ws_id: str) -> dict[str, Commitment]:
    """pattern → the most recently cancelled commitment carrying it."""
    from . import commitments as cmt

    out: dict[str, Commitment] = {}
    for c in cmt.list_commitments(ws_id):
        if c.status != "cancelled":
            continue
        for p in c.merchant_patterns:
            current = out.get(p)
            if current is None or (c.ended or date.min) >= (current.ended or date.min):
                out[p] = c
    return out


def _persist_candidate(ws_id: str, commitment: Commitment, evidence: list[Evidence],
                       confidence: float, flags: list[str] | None = None,
                       existing_commitment_id: str | None = None) -> str:
    conn = store.db()
    merchant = commitment.merchant_patterns[0]
    row = conn.execute(
        "SELECT * FROM organizer_candidates WHERE ws_id=? AND merchant=?", (ws_id, merchant)
    ).fetchone()
    payload = (
        store.dumps(commitment.model_dump(mode="json")),
        store.dumps([e.model_dump(mode="json") for e in evidence]),
        float(confidence),
        store.now(),
    )
    if row is not None:
        # A pf loan/card candidate can land on the same merchant key as a detected bank group
        # (e.g. "CARGO CREDITO AUTOMOTRIZ BBVA" and the pf loan "Crédito auto"). Merge rather than
        # clobber: the pf row is authoritative for the amount and the link, the bank rows keep the
        # evidence and the history dates.
        old = store.loads(row["preview_json"], {}) or {}
        old_evidence = store.loads(row["evidence_json"], []) or []
        merged = commitment.model_dump(mode="json")
        if not evidence and old_evidence:
            evidence_json = store.dumps(old_evidence)
            for field in ("started", "last_seen", "anchor_day", "weekday", "category_hint"):
                if merged.get(field) is None:
                    merged[field] = old.get(field)
            # keep the cadence math from the bank evidence, then the pf steps
            old_explain = old.get("explain") or {}
            if old_explain.get("steps"):
                merged.setdefault("explain", {})
                merged["explain"] = {
                    **old_explain,
                    "steps": [*old_explain["steps"], *(merged.get("explain") or {}).get("steps", [])],
                }
        else:
            evidence_json = payload[1]
        for field in ("linked_loan_id", "linked_card_id", "label_id"):
            merged[field] = merged.get(field) or old.get(field)
        conn.execute(
            "UPDATE organizer_candidates SET preview_json=?, evidence_json=?, confidence=?, "
            "detected_at=?, flags=?, existing_commitment_id=? WHERE id=?",
            (store.dumps(merged), evidence_json, float(confidence), payload[3],
             store.dumps(flags or []), existing_commitment_id, row["id"]),
        )
        if flags:
            # a merchant that resurfaces (cancelled but still charging) reopens its old candidate row
            conn.execute("UPDATE organizer_candidates SET status='open' WHERE id=?", (row["id"],))
        conn.commit()
        return row["id"]
    cid = store.new_id("cand")
    conn.execute(
        "INSERT INTO organizer_candidates (id, ws_id, merchant, preview_json, evidence_json, "
        "confidence, status, detected_at, flags, existing_commitment_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cid, ws_id, merchant, payload[0], payload[1], payload[2], "open", payload[3],
         store.dumps(flags or []), existing_commitment_id),
    )
    conn.commit()
    return cid


def list_candidates(ws_id: str, status: str = "open") -> list[Candidate]:
    conn = store.db()
    rows = conn.execute(
        "SELECT * FROM organizer_candidates WHERE ws_id=? AND status=? ORDER BY confidence DESC, merchant",
        (ws_id, status),
    ).fetchall()
    return [_row_to_candidate(r) for r in rows]


def _row_to_candidate(r) -> Candidate:
    d = dict(r)
    return Candidate(
        id=d["id"], merchant=d["merchant"],
        preview=Commitment.model_validate(store.loads(d["preview_json"], {})),
        evidence=[Evidence.model_validate(e) for e in store.loads(d["evidence_json"], [])],
        confidence=float(d["confidence"]), status=d["status"],
        flags=store.loads(d.get("flags"), []) or [],
        existing_commitment_id=d.get("existing_commitment_id"),
    )


def get_candidate(ws_id: str, candidate_id: str) -> Candidate:
    conn = store.db()
    r = conn.execute(
        "SELECT * FROM organizer_candidates WHERE ws_id=? AND id=?", (ws_id, candidate_id)
    ).fetchone()
    if r is None:
        raise KeyError(candidate_id)
    return _row_to_candidate(r)


def set_candidate_status(ws_id: str, candidate_id: str, status: str) -> None:
    conn = store.db()
    conn.execute(
        "UPDATE organizer_candidates SET status=? WHERE ws_id=? AND id=?", (status, ws_id, candidate_id)
    )
    conn.commit()


def accept(ws_id: str, candidate_id: str, overrides: dict | None = None,
           today: date | None = None) -> Commitment:
    """Turn a candidate into a commitment, seeding its price history from the evidence."""
    from . import commitments as cmt
    from .models import CommitmentIn

    candidate = get_candidate(ws_id, candidate_id)
    data = candidate.preview.model_dump(mode="json")
    data.pop("explain", None)
    data.update(overrides or {})
    body = CommitmentIn.model_validate(
        {k: v for k, v in data.items() if k in CommitmentIn.model_fields}
    )
    created = cmt.create(ws_id, body, today=today)
    for ev in candidate.evidence:
        cmt.record_price(ws_id, created.id, ev.date, ev.amount, source="detected")
    set_candidate_status(ws_id, candidate_id, "accepted")
    return created
