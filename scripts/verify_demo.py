"""End-to-end acceptance checks against a running Aurum API (run after ``docker compose up``).

Drives the real HTTP flows, prints one ``[PASS]`` / ``[FAIL]`` / ``[SKIP]`` line per check and a final
``RESULT:`` line, and exits non-zero when any check fails.

Usage::

    uv run python scripts/verify_demo.py [--api http://localhost:5024/api] [--level N] [--json out.json]
    uv run python scripts/verify_demo.py --level 7 --e2e --mcp http://127.0.0.1:5042/mcp

Levels
------
``--level N`` runs every level up to and including ``N`` (default 1):

1. Core tax flow on ``--ws`` (default ``demo-mx``): health and mounted routers, the RESICO month close
   with its prefill-audit differences and draft PDF, a quick add that is previewed, committed, checked
   on the ledger and then voided again, the personal-finance reads, a research question that must cite
   or abstain, and the law tracker feed.
2. Statements and cross-border: financial statements, the reconcile board (a match that is undone), workspace
   update, localized explanations, goal create/delete, US tax and cross-border on ``demo-us``, holdings,
   FX, credit reports, planning scenarios, research ``as_of`` and cross-references, watch sources.
3. Business KPIs, invoices and an (idempotent) payroll run on ``demo-biz``; insights, the calendar and the
   digest; the report catalog and two rendered reports.
4. Workflows (the built-in month close runs and is recorded) and hardening (``demo_mode`` in health,
   security headers).
5. The money organizer (Mi dinero): summary, commitments, alerts, calendar, forecast, one-line quick add,
   plan, setup status, detection.
6. The manual personal flow on a fresh ``verify-<ts>-<hex4>`` workspace: an account with an opening
   balance, an expense logged, edited and deleted by hand, an income stream, onboarding progress.
7. The full numbered acceptance list (``acceptance_suite()``) on its own throwaway workspace.

Numbered acceptance items (level 7)
-----------------------------------
Every level-7 check name starts with ``acceptance:`` and ends with its item number ``(#N)``; there is one
small ``_item_*`` function per item.

- #1  A throwaway workspace can be created (the protected-workspace guard itself is unit-tested).
- #2  Workspace list order and flags: ``personal`` first and protected, demos flagged ``profile.demo`` and
  listed last, a new workspace unprotected and visible.
- #3  Accounts and liabilities: a card balance is typed positive and stored negative on the ledger
  (``owed`` / ``balance`` / ``balance_signed``); net worth across an expense and a transfer; a negative
  opening balance on a card is a 422; balance adjustment.
- #4  Labels: seeded income labels, the expense account derived server-side, account-name grammar (400),
  a label of the wrong kind (400), archived labels hidden.
- #5  Budgets and void semantics: a 500 expense shows as spent; voiding it removes it from budgets and the
  monthly review, a second delete is a 409, and the ledger still parses cleanly.
- #6  Validate, then write: a rejected request leaves journal and balances untouched; an edit is exactly
  one reversal plus one new transaction; a bulk batch with one invalid item writes nothing.
- #7  The entries envelope: totals over the full filter, disjoint keyset pages, ``limit`` capped at 500,
  ``editable`` / ``non_editable_reason`` on every row.
- #8  Input hygiene: float or text money (422), currency case normalized, invalid tags (400, ledger file
  byte-identical), bad dates and periods (422), duplicate budget (409), unknown goal kind (422), a
  control-character account name (422).
- #9  Budget carry-forward is explicit and idempotent; ``warn`` at 80 %, ``over`` at 100 %; totals and the
  safe-to-spend figure in the status response.
- #10 Goals point at a pf account id; the ledger account and currency are derived server-side; a transfer
  moves progress; an unknown account is a 404.
- #11 Income streams mirror into income commitments (in place on update), pausing removes expected income
  from the forecast, a linked income entry shows in the stream history, ``retained`` excludes
  IVA-Acreditable.
- #12 Commitments: account names, a partial update keeps the other fields, a duplicate is a 409 with
  ``existing_id``, bounds on ``anchor_day`` and calendar ranges (422), review timestamps.
- #13 Mark paid on a fixed amount: one tap creates the entry, a repeat is idempotent, un-marking voids it.
- #14 Mark paid on a variable amount: linking a hand-logged entry; voiding that entry drops the paid status.
- #15 Occurrence history from three months of matched entries; a stale stored ``next_due`` still alerts on
  the effective due date.
- #16 One safe-to-spend figure: balance minus fixed payments due before the next payday, minus remaining
  budgets, minus the buffer; the six explain steps each carry a formula; the forecast drops on the rent
  date.
- #17 Tax rows (calendar items, CFDI/RESICO/DIOT insights) appear only with ``modules.tax`` on; demo-mx has
  one upcoming nudge per commitment.
- #18 Onboarding has fixed step ids and is ``done`` once accounts and first entries are done.
- #19 Shortcuts create ordinary editable entries: quick add previews, then commits (``source: quickadd``);
  a bank CSV imported onto an account creates entries (``source: import``) and a re-import dedupes.
- #20 Backup and export: the per-workspace zip and its ``metadata.json`` counts, ``movimientos.csv`` (BOM,
  ``;`` separator, signed amounts), a full backup that is listed afterwards; downloading ``personal``'s
  zip is an allowed read.
- #21 The health document (no ``data_dir``; auth, bind and schema versions) and a clean ledger at the end.
- #22 Loopback security posture without a token: CORS, Origin and Host checks, workspace-id and path
  validation, and an MCP ``initialize`` (needs ``--mcp`` / ``AURUM_MCP_URL`` or the running compose stack).
- #23 Docker posture, only when ``docker compose ps`` reports the ``api`` and ``web-ui`` services running
  (otherwise a SKIP line with the reason): loopback port bindings, a non-root PID 1, no capabilities, log
  rotation, and how the nginx front door serves ``/plan``, unknown paths and the manifest.
- #24 The seeded demos look the way the seed promises (read-only).
- #25 Idempotency: the workspace list (excluding ``verify-*``) and demo-mx's balances and entry count are
  the same before and after a run, and the throwaway workspace is hidden afterwards. The level-1 quick add
  on demo-mx is voided right after its assertion so the raw balances map comes back identical.
- #26 With ``--e2e``: the headless UI flows (``web-ui/scripts/ui-check.mjs --flows``) against the same
  stack and the throwaway workspace.

Data safety
-----------
Protected workspaces (``personal`` by default; ``AURUM_PROTECTED_WORKSPACES`` extends the list) are never
written. A ``--ws`` that names one is refused with exit code 2 before any HTTP client is constructed
(``guard_protected()``), and the generated throwaway ids go through the same guard. The only requests
that name ``personal`` are two reads in item #20 (does it exist, then its backup zip). Levels 6 and 7
write to throwaway workspaces, which are hidden (``PUT {"hidden": true}``) when the run ends; there is no
delete endpoint.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
from dateutil.relativedelta import relativedelta

FAILS: list[str] = []
RESULTS: list[dict[str, object]] = []

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" - {detail}" if detail else ""))
    RESULTS.append({"name": name, "ok": ok, "detail": detail})
    if not ok:
        FAILS.append(name)


def skip(name: str, reason: str) -> None:
    """A check that cannot run here (missing stack/tool). Printed and recorded, never a PASS or a FAIL."""
    print(f"[SKIP] {name} - {reason}")
    RESULTS.append({"name": name, "ok": None, "detail": reason})


def protected_workspaces() -> set[str]:
    return {x.strip() for x in os.environ.get("AURUM_PROTECTED_WORKSPACES", "personal").split(",") if x.strip()}


def guard_protected(ws: str) -> None:
    """Never touch a protected workspace: hard-refuse before constructing an HTTP client at all — a
    fake ``client_factory`` that raises on any call must never be invoked for a protected ``ws``."""
    if ws in protected_workspaces():
        print(f"refusing to run against protected workspace {ws!r} (AURUM_PROTECTED_WORKSPACES)", file=sys.stderr)
        raise SystemExit(2)


def web_origin(api: str) -> str:
    """``http://host:5024/api`` → ``http://host:5024`` (the nginx front door for items 23/26)."""
    base = api.rstrip("/")
    return base[:-4] if base.endswith("/api") else base


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:5024/api")
    ap.add_argument("--ws", default="demo-mx")
    ap.add_argument("--period", default="2026-08")
    ap.add_argument(
        "--level", type=int, default=1, metavar="N",
        help="run every level up to N (default 1): 1 = core tax flow on demo-mx; 2 adds statements, reconcile, US tax, cross-border, holdings and planning; "
             "3 adds business, insights and reports; 4 adds workflows and hardening; 5 adds the money organizer; "
             "6 adds the manual personal flow on a fresh workspace; 7 adds the full numbered acceptance list "
             "on a throwaway workspace",
    )
    ap.add_argument("--token", default="", help="Bearer token, when AURUM_API_TOKEN is set on the server")
    ap.add_argument("--json", default=None, help="write [{name,ok,detail}] to this file")
    ap.add_argument("--e2e", action="store_true", help="also spawn web-ui/scripts/ui-check.mjs --flows (level 7, item #26)")
    ap.add_argument("--web", default=None, help="web front door for #23/#26 (default: --api without /api)")
    ap.add_argument("--mcp", default=os.environ.get("AURUM_MCP_URL", ""), help="MCP streamable-HTTP URL for #22 (default: AURUM_MCP_URL, else only when the compose stack is up)")
    return ap.parse_args(argv)


def _audit_count(c: httpx.Client, ws: str) -> int:
    rows = c.get("/audit", params={"ws": ws, "limit": 500}).json()
    return len([r for r in rows if not str(r.get("action", "")).startswith("core.backup.")])


def _entries_count(c: httpx.Client, ws: str) -> int | None:
    r = c.get(f"/pf/{ws}/entries", params={"limit": 1})
    body = r.json() if r.status_code == 200 else {}
    return body.get("totals", {}).get("count") if isinstance(body, dict) else None


def _fmt_rows(rows: object) -> str:
    if rows is None:
        return "absent"
    if not isinstance(rows, list):
        return str(rows)
    return "+".join(f"{r.get('amount')} {r.get('currency')}" for r in rows if isinstance(r, dict)) or "[]"


def _all_zero(rows: object) -> bool:
    if not isinstance(rows, list) or not rows:
        return False
    try:
        return all(Decimal(str(r.get("amount"))) == 0 for r in rows)
    except (ArithmeticError, AttributeError, TypeError):
        return False


def balance_diff(before: object, after: object) -> dict[str, str]:
    """Per-account differences between two ``/ledger/{ws}/balances`` maps; ``{}`` when they are identical.

    Item #25 requires demo-mx's balances to be *identical* before and after a run, so the callers decide on
    raw equality of the two maps and only use this to say what moved: ``"1197.00 MXN -> 1447.00 MXN"``
    for an amount, ``"opened at 0.00"`` when an account merely appeared with zero rows (a quickadd that
    auto-opened its expense account and was then voided by a reversal), ``"removed"`` when a key vanished."""
    b = before if isinstance(before, dict) else {}
    a = after if isinstance(after, dict) else {}
    out: dict[str, str] = {}
    for account in sorted(set(b) | set(a)):
        rows_b, rows_a = b.get(account), a.get(account)
        if rows_b == rows_a:
            continue
        if rows_b is None and _all_zero(rows_a):
            out[account] = "opened at 0.00"
        elif rows_a is None:
            out[account] = "removed"
        else:
            out[account] = f"{_fmt_rows(rows_b)} -> {_fmt_rows(rows_a)}"
    return out


def main(argv: list[str] | None = None, client_factory=None) -> int:
    FAILS.clear()
    RESULTS.clear()
    a = parse_args(argv)
    guard_protected(a.ws)

    headers = {"Authorization": f"Bearer {a.token}"} if a.token else {}
    c = client_factory(a.api, headers) if client_factory else httpx.Client(base_url=a.api, timeout=120, headers=headers)

    side_effects_before = None
    if a.level >= 7:
        # Item #25: the acceptance list only reads demo-mx; the level-1 quickadd below is voided right
        # after its assertion so the raw balances map and the entry count come back identical.
        side_effects_before = {
            "audit": _audit_count(c, "demo-mx"),
            "balances": c.get("/ledger/demo-mx/balances").json(),
            "entries": _entries_count(c, "demo-mx"),
        }

    r = c.get("/health")
    check("health", r.status_code == 200 and r.json().get("ok") is True, r.text[:120])
    mounted = c.get("/mounted").json().get("mounted", [])
    check("routers mounted", all(p in mounted for p in ["/api/ledger", "/api/tax", "/api/ingest", "/api/pf", "/api/research", "/api/watch"]), str(mounted))

    r = c.get(f"/workspaces/{a.ws}")
    check("demo workspace exists", r.status_code == 200, r.text[:160])

    # Month close + prefill audit
    r = c.get(f"/tax/mx/resico/{a.ws}/{a.period}")
    ok = r.status_code == 200
    check("month close responds", ok, r.text[:200])
    if ok:
        mc = r.json()
        kinds = {d["kind"] for d in mc.get("diffs", [])}
        check("ISR has explain + citation", bool(mc["isr"]["explain"]["citations"]), json.dumps(mc["isr"]["explain"]["citations"][:1], ensure_ascii=False)[:200])
        for k in ("pue_not_collected", "deposit_without_cfdi", "cash_paid_expense"):
            check(f"diff {k} present", k in kinds, str(sorted(kinds)))
        check("ISR value is decimal string", isinstance(mc["isr"]["value"]["amount"], str) and Decimal(mc["isr"]["value"]["amount"]) >= 0, mc["isr"]["value"]["amount"])
        r2 = c.get(f"/tax/mx/resico/{a.ws}/{a.period}/draft.pdf")
        check("draft PDF/HTML download", r2.status_code == 200 and len(r2.content) > 500, f"{r2.headers.get('content-type')} {len(r2.content)} bytes")

    # Quick add (a shortcut that creates an ordinary editable entry): preview -> commit as a real pf entry on
    # a resolved account -> ledger. No inbox row.
    # The text resolves to the seeded 'Entretenimiento' label (Expenses:Personal:Entertainment), an account
    # the demo-mx seed already posts to: voiding the entry then brings /ledger/demo-mx/balances back to the
    # identical raw map (item #25). 'comida' would auto-open Expenses:Food:DiningOut on a fresh stack and
    # leave a 0.00 row behind, which is not "identical".
    quickadd_text = "250 cinepolis cine"
    before = c.get(f"/ledger/{a.ws}/balances").json()
    inbox_before = c.get(f"/ingest/{a.ws}/inbox").json()
    accounts = c.get(f"/pf/{a.ws}/accounts").json()
    accounts = [x for x in (accounts if isinstance(accounts, list) else accounts.get("accounts", [])) if not x.get("archived")]
    acct_id = next((x["id"] for x in accounts if x.get("type") in ("checking", "cash")), accounts[0]["id"] if accounts else None)
    check("pf accounts exist for quickadd", acct_id is not None, f"{len(accounts)} accounts")
    r = c.post(f"/ingest/{a.ws}/quickadd", json={"text": quickadd_text, "account_id": acct_id})
    check("quickadd previews (no write)", r.status_code == 200 and r.json().get("status") == "preview" and r.json().get("id") is None, r.text[:200])
    r = c.post(f"/ingest/{a.ws}/quickadd", json={"text": quickadd_text, "account_id": acct_id, "commit": True})
    check("quickadd commits a pf entry", r.status_code == 200 and r.json().get("status") == "committed" and r.json().get("id"), r.text[:200])
    if r.status_code == 200 and r.json().get("id"):
        item = r.json()
        after = c.get(f"/ledger/{a.ws}/balances").json()
        postings = item["proposed"]["postings"]
        acct = next((p["account"] for p in postings if p["account"].startswith("Expenses:")), postings[0]["account"])
        b0 = Decimal(next((x["amount"] for x in before.get(acct, []) if x["currency"] == "MXN"), "0"))
        b1 = Decimal(next((x["amount"] for x in after.get(acct, []) if x["currency"] == "MXN"), "0"))
        check("ledger expense balance moved by 250 (persisted)", b1 - b0 == Decimal("250"), f"{acct}: {b0} -> {b1}")
        inbox_after = c.get(f"/ingest/{a.ws}/inbox").json()
        check("quickadd leaves no inbox row", len(inbox_after) == len(inbox_before), f"{len(inbox_before)} -> {len(inbox_after)}")
        # Void it again (a reversal, never a rewrite) so the demo workspace's raw balances map is
        # identical before and after a run — the idempotency proof of item #25.
        r = c.delete(f"/pf/{a.ws}/entries/{item['id']}")
        diff = balance_diff(before, c.get(f"/ledger/{a.ws}/balances").json())
        name = "acceptance: level-1 quickadd on demo-mx voided (#25)" if a.level >= 7 else "quickadd entry voided afterwards"
        check(name, r.status_code == 200 and r.json().get("voided") is True and not diff, f"{r.text[:80]} balances restored={not diff}" + (f" diff={diff}" if diff else ""))

    # Personal finance
    for path in ("accounts", f"budgets/status?period={a.period}", "goals", "credit/cards", f"review/{a.period}", "labels"):
        r = c.get(f"/pf/{a.ws}/{path}")
        check(f"pf {path}", r.status_code == 200, r.text[:120])

    # Research: cite or abstain
    r = c.post("/research/ask", json={"question": "¿Cuál es la tasa de ISR en RESICO para ingresos de 40,000 al mes?", "jurisdiction": "MX", "lang": "es"})
    ok = r.status_code == 200
    check("research ask responds", ok, r.text[:200])
    if ok:
        j = r.json()
        check("research cites or abstains", bool(j.get("citations")) or j.get("abstained") is True, f"abstained={j.get('abstained')} citations={len(j.get('citations', []))}")

    # Law tracker
    r = c.get("/watch/changes")
    check("watch changes", r.status_code == 200 and isinstance(r.json(), list), r.text[:120])

    if a.level >= 2:
        level2_backends(c, a)
    if a.level >= 3:
        level3_business_insights_reports(c, a)
    if a.level >= 4:
        level4_workflows_hardening(c, a)
    if a.level >= 5:
        level5_money_organizer(c, a)
    if a.level >= 6:
        level6_manual_personal_flow(c, a)
    if a.level >= 7:
        acceptance_suite(c, a)

    if side_effects_before is not None:
        audit_diff = _audit_count(c, "demo-mx") - side_effects_before["audit"]
        diff = balance_diff(side_effects_before["balances"], c.get("/ledger/demo-mx/balances").json())
        entries_after = _entries_count(c, "demo-mx")
        entries_same = entries_after == side_effects_before["entries"]
        summary = "none" if not diff and entries_same else "CHANGED"
        print(
            f"SIDE EFFECTS: {summary} (demo-mx balances {'identical' if not diff else f'CHANGED {diff}'}, "
            f"entries {side_effects_before['entries']} -> {entries_after}, audit rows +{audit_diff}), backups +1"
        )

    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(RESULTS, fh, indent=2, ensure_ascii=False)

    print()
    print("RESULT:", "ALL PASS" if not FAILS else f"{len(FAILS)} FAILED -> {FAILS}")
    return 0 if not FAILS else 1


def level2_backends(c: httpx.Client, a) -> None:
    """Level 2: statements, reconcile, US tax, cross-border, holdings, FX, credit reports, planning."""
    ws, period = a.ws, a.period
    # statements / reconcile / workspace PUT / localization
    for typ in ("pnl", "balance", "cashflow"):
        r = c.get(f"/ledger/{ws}/statements/{period}?type={typ}")
        check(f"statement {typ}", r.status_code == 200 and "sections" in r.json() and "explain" in r.json(), r.text[:140])
    r = c.get(f"/ingest/{ws}/reconcile?period={period}")
    ok = r.status_code == 200 and "bank_lines" in r.json()
    check("reconcile board", ok, r.text[:140])
    if ok:
        lines = r.json()["bank_lines"]
        cand = next((ln for ln in lines if ln.get("suggestions")), None)
        if cand:
            sug = cand["suggestions"][0]
            r2 = c.post(f"/ingest/{ws}/reconcile/match", json={"bank_line_id": cand["id"], "txn_id": sug.get("txn_id"), "cfdi_uuid": sug.get("cfdi_uuid")})
            check("reconcile match persists", r2.status_code == 200 and any(
                ln["id"] == cand["id"] and (ln.get("matched_txn_id") or ln.get("cfdi_uuid"))
                for ln in c.get(f"/ingest/{ws}/reconcile?period={period}").json()["bank_lines"]), r2.text[:140])
            c.post(f"/ingest/{ws}/reconcile/unmatch", json={"bank_line_id": cand["id"]})
        else:
            check("reconcile has suggestions", False, "no bank line with suggestions")
    r = c.put(f"/workspaces/{ws}", json={"name": "Demo México (RESICO)", "language": "es"})
    check("workspace PUT", r.status_code == 200, r.text[:120])
    r = c.get(f"/pf/{ws}/budgets/status?period={period}")
    summ = json.dumps(r.json(), ensure_ascii=False)
    check("pf explain localized (es)", r.status_code == 200 and "explain" in summ and " the " not in summ.lower()[:4000], summ[:160])
    r = c.get(f"/pf/{ws}/budgets/status?period={period}&lang=en")
    check("pf explain lang=en override", r.status_code == 200, r.text[:100])
    # goals CRUD round-trip (forms depend on it)
    r = c.post(f"/pf/{ws}/goals", json={"kind": "savings", "name": "verify-goal", "target": "1000", "currency": "MXN", "target_date": "2027-01-31", "account": "Assets:Bank:Nu"})
    ok = r.status_code == 200 and r.json().get("id")
    check("goal create", bool(ok), r.text[:120])
    if ok:
        gid = r.json()["id"]
        r = c.delete(f"/pf/{ws}/goals/{gid}")
        check("goal delete", r.status_code in (200, 204), r.text[:80])
    # US tax + cross-border on demo-us
    r = c.get("/tax/us/demo-us/2026")
    check("us tax year (demo-us)", r.status_code == 200 and "se_tax" in r.json(), r.text[:160])
    r = c.get("/tax/us/demo-us/2026/organizer.pdf")
    check("us organizer pdf", r.status_code == 200 and len(r.content) > 500, f"{r.headers.get('content-type')} {len(r.content)}")
    r = c.get("/crossborder/demo-us/assessment")
    check("crossborder assessment", r.status_code == 200 and "fbar" in r.json() and "residency" in r.json(), r.text[:160])
    # holdings / fx / creditreport
    r = c.get(f"/holdings/{ws}")
    check("holdings positions", r.status_code == 200, r.text[:120])
    r = c.get("/fx/rate?base=USD&quote=MXN")
    check("fx rate", r.status_code in (200, 404, 503), r.text[:120])  # network-optional; must not 500
    r = c.get(f"/creditreport/{ws}")
    check("creditreport list", r.status_code == 200, r.text[:120])
    # plan
    r = c.get(f"/plan/{ws}/scenarios")
    ok = r.status_code == 200
    check("plan catalog", ok, r.text[:120])
    if ok:
        ids = [sc.get("id") for sc in (r.json() if isinstance(r.json(), list) else r.json().get("scenarios", []))]
        check("plan has regime_mx", "regime_mx" in ids, str(ids))
        r = c.post(f"/plan/{ws}/scenarios/regime_mx/run", json={"inputs": {}})
        check("plan regime_mx run", r.status_code == 200 and "results" in r.json() and "explain" in r.json(), r.text[:160])
    # research: point-in-time answers, the cross-reference graph, watch sources
    r = c.post("/research/ask", json={"question": "tasa ISR RESICO", "jurisdiction": "MX", "lang": "es", "as_of": "2026-08-01"})
    check("research as_of accepted", r.status_code == 200, r.text[:120])
    r = c.get("/research/refs?law=LISR&article=113-E")
    check("research refs", r.status_code == 200 and "cites" in r.json(), r.text[:120])
    r = c.get("/watch/sources")
    check("watch sources", r.status_code == 200, r.text[:100])



def level3_business_insights_reports(c: httpx.Client, a) -> None:
    """Level 3: business (demo-biz), insights, reports."""
    ws, period = a.ws, a.period
    r = c.get("/business/demo-biz/kpis?period=2026-08")
    check("business kpis (demo-biz)", r.status_code == 200 and "explain" in json.dumps(r.json()), r.text[:140])
    r = c.get("/business/demo-biz/invoices")
    check("business invoices register", r.status_code == 200, r.text[:120])
    r = c.post("/business/demo-biz/payroll/run", json={"period": "2026-08"})
    check("business payroll run", r.status_code == 200 and "explain" in json.dumps(r.json()), r.text[:160])
    r = c.get(f"/insights/{ws}?period={period}")
    ok = r.status_code == 200 and isinstance(r.json(), list)
    check("insights list", ok, r.text[:140])
    if ok:
        kinds = {i.get("kind") for i in r.json()}
        check("insight: unpaid PUE surfaced", any("pue" in str(k).lower() for k in kinds), str(sorted(map(str, kinds)))[:200])
    r = c.get(f"/insights/{ws}/calendar?from=2026-08-01&to=2026-10-31")
    check("insights calendar", r.status_code == 200, r.text[:120])
    r = c.get(f"/insights/{ws}/digest")
    check("insights digest", r.status_code == 200 and len(r.text) > 20, r.text[:120])
    r = c.get(f"/reports/{ws}")
    check("reports catalog", r.status_code == 200, r.text[:120])
    r = c.get(f"/reports/{ws}/monthly-review?period={period}&format=pdf")
    check("report monthly-review pdf", r.status_code == 200 and r.content[:4] == b"%PDF", f"{r.headers.get('content-type')} {len(r.content)}")
    r = c.get(f"/reports/{ws}/mx-annual?period=2026&format=html")
    check("report mx-annual html has ISR 407.00", r.status_code == 200 and "407.00" in r.text, r.text[:80])

def level4_workflows_hardening(c: httpx.Client, a) -> None:
    """Level 4: workflows, hardening."""
    ws = a.ws
    r = c.get(f"/workflows/{ws}")
    ok = r.status_code == 200
    check("workflows list (built-ins seeded)", ok and any("month-close" in json.dumps(x) for x in (r.json() if isinstance(r.json(), list) else r.json().get("workflows", []))), r.text[:160])
    if ok:
        items = r.json() if isinstance(r.json(), list) else r.json().get("workflows", [])
        wid = next((w.get("id") for w in items if "month-close" in str(w.get("id", "")) or "month-close" in str(w.get("name", ""))), None)
        if wid:
            r = c.post(f"/workflows/{ws}/{wid}/run", json={"params": {"period": a.period}})
            check("workflow month-close-mx run", r.status_code == 200 and str(r.json().get("status", "")).lower() in ("ok", "success", "completed", "done"), r.text[:200])
            r = c.get(f"/workflows/{ws}/{wid}/runs")
            check("workflow runs recorded", r.status_code == 200 and len(r.json() if isinstance(r.json(), list) else r.json().get("runs", [])) >= 1, r.text[:120])
    r = c.get("/workflows/catalog")
    check("workflows catalog", r.status_code == 200, r.text[:100])
    r = c.get("/health")
    check("health reports demo_mode", r.status_code == 200 and "demo_mode" in r.json(), r.text[:160])
    hdrs = c.get("/health").headers
    check("security headers present", hdrs.get("x-content-type-options", "").lower() == "nosniff", str({k: v for k, v in hdrs.items() if k.lower().startswith(("x-", "referrer", "cache"))}))

def level5_money_organizer(c: httpx.Client, a) -> None:
    """Level 5: the Mi dinero money organizer."""
    ws = a.ws
    r = c.get(f"/organizer/{ws}/summary")
    ok = r.status_code == 200
    check("organizer summary", ok and "safe_to_spend" in r.json() and "monthly_committed" in r.json(), r.text[:200])
    r = c.get(f"/organizer/{ws}/commitments")
    ok = r.status_code == 200 and isinstance(r.json(), list)
    check("organizer commitments list", ok, r.text[:120])
    if ok:
        names = [x.get("name", "").lower() for x in r.json()]
        check("organizer demo has >= 8 commitments incl. netflix + loan payment", len(names) >= 8 and any("netflix" in n for n in names) and any(x.get("kind") == "loan_payment" for x in r.json()), str(names)[:200])
    r = c.get(f"/organizer/{ws}/alerts")
    ok = r.status_code == 200
    kinds = {x.get("kind") for x in (r.json() if ok and isinstance(r.json(), list) else [])}
    check("organizer alerts incl. price_increase + trial_ending", ok and {"price_increase", "trial_ending"} <= kinds, str(sorted(map(str, kinds))))
    r = c.get(f"/organizer/{ws}/calendar?from=2026-08-01&to=2026-08-31")
    ok = r.status_code == 200 and "days" in r.json()
    check("organizer calendar", ok, r.text[:140])
    if ok:
        items = [it for d in r.json()["days"] for it in d.get("items", [])]
        check("calendar has paid occurrences (matched to ledger)", any(it.get("status") == "paid" for it in items), str({it.get("status") for it in items}))
    r = c.get(f"/organizer/{ws}/forecast?days=90")
    check("organizer forecast", r.status_code == 200 and len(r.json().get("series", [])) >= 60 and "low_point" in r.json(), r.text[:160])
    r = c.post(f"/organizer/{ws}/quickadd", json={"text": "netflix 219 mensual día 15"})
    j = r.json() if r.status_code == 200 else {}
    j = j.get("preview", j) if isinstance(j, dict) else {}
    check("organizer quickadd parses cadence + day", r.status_code == 200 and j.get("cadence") == "monthly" and j.get("anchor_day") == 15 and str(j.get("amount", {}).get("amount", "")).startswith("219"), r.text[:160])
    r = c.get(f"/organizer/{ws}/plan?period={a.period}")
    check("organizer plan", r.status_code == 200 and "groups" in r.json(), r.text[:140])
    r = c.post(f"/organizer/{ws}/plan/auto", json={"months": 3})
    check("organizer plan/auto", r.status_code == 200, r.text[:140])
    r = c.get(f"/organizer/{ws}/setup/status")
    check("organizer setup status", r.status_code == 200 and "has_commitments" in r.text, r.text[:140])
    r = c.post(f"/organizer/{ws}/detect")
    check("organizer detect runs", r.status_code == 200 and "candidates" in r.json(), r.text[:140])

def level6_manual_personal_flow(c: httpx.Client, a) -> None:
    """Level 6: a person with an empty workspace can set up and log money by hand.
    Runs on a throwaway ``verify-<ts>`` workspace (hidden at the end) so a second run is identical —
    a fixed workspace id would trip the duplicate-account-name guard on the second run."""
    ws = f"verify-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}"
    guard_protected(ws)
    c.post("/workspaces", json={"id": ws, "name": "Verificacion personal", "kind": "personal",
                                "jurisdictions": ["MX"], "base_currency": "MXN", "language": "es"})
    r = c.get(f"/workspaces/{ws}")
    check("fresh workspace exists", r.status_code == 200, r.text[:120])
    check("simple mode is the default", r.status_code == 200 and r.json().get("ui_mode", "simple") == "simple", str(r.json().get("ui_mode")))

    # 1. Add an account by hand, with an opening balance.
    r = c.post(f"/pf/{ws}/accounts", json={"name": "BBVA Cheques", "type": "checking", "institution": "BBVA",
                                           "opening_balance": {"amount": "12400.00", "currency": "MXN"},
                                           "opening_date": "2026-09-01"})
    ok = r.status_code in (200, 201)
    acct_id = r.json().get("id") if ok else None
    check("create an account by hand", ok and bool(acct_id), r.text[:200])
    if not acct_id:
        return
    r = c.get(f"/pf/{ws}/accounts")
    body = json.dumps(r.json(), ensure_ascii=False)
    check("account shows its friendly name and balance", r.status_code == 200 and "BBVA Cheques" in body and "12400" in body, body[:200])

    # 2. Log an expense the way a person would.
    labels = c.get(f"/pf/{ws}/labels").json()
    label_id = (labels[0] if isinstance(labels, list) and labels else {}).get("id")
    r = c.post(f"/pf/{ws}/entries", json={"kind": "expense", "date": "2026-09-07",
                                          "amount": {"amount": "250.00", "currency": "MXN"},
                                          "account_id": acct_id, "label_id": label_id,
                                          "payee": "Tacos El Primo", "note": "comida"})
    ok = r.status_code in (200, 201)
    entry_id = r.json().get("id") if ok else None
    check("log an expense by hand", ok and bool(entry_id), r.text[:200])

    r = c.get(f"/pf/{ws}/entries")
    rows = r.json() if r.status_code == 200 else []
    rows = rows.get("entries", rows) if isinstance(rows, dict) else rows
    check("entries list is human, not postings", r.status_code == 200 and bool(rows) and "postings" not in json.dumps(rows), json.dumps(rows[:1], ensure_ascii=False)[:220])
    if rows:
        row = rows[0]
        check("entry row carries account and category names", bool(row.get("account_name")) and ("label_name" in row), json.dumps(row, ensure_ascii=False)[:200])
        check("expense amount is signed negative", str(row.get("amount", {}).get("amount", "")).startswith("-"), str(row.get("amount")))

    # 3. The balance actually moved in the ledger.
    accts = c.get(f"/pf/{ws}/accounts").json()
    body = json.dumps(accts, ensure_ascii=False)
    check("balance moved after the expense", "12150" in body, body[:200])

    # 4. Edit it, then delete it.
    if entry_id:
        r = c.put(f"/pf/{ws}/entries/{entry_id}", json={"amount": {"amount": "300.00", "currency": "MXN"}, "payee": "Tacos El Primo"})
        check("edit an entry", r.status_code == 200, r.text[:160])
        r = c.delete(f"/pf/{ws}/entries/{entry_id}")
        check("delete an entry", r.status_code in (200, 204), r.text[:160])

    # 5. Income stream, paid twice a month.
    r = c.post(f"/pf/{ws}/income/streams", json={"name": "Nomina", "source_type": "salary",
                                                 "amount": {"amount": "22500.00", "currency": "MXN"},
                                                 "cadence": "semimonthly", "anchor_days": [15, 30],
                                                 "account_id": acct_id})
    ok = r.status_code in (200, 201)
    check("set up an income stream by hand", ok, r.text[:200])
    r = c.get(f"/pf/{ws}/income/streams")
    streams = r.json() if r.status_code == 200 else []
    streams = streams.get("streams", streams) if isinstance(streams, dict) else streams
    check("income stream is listed with its next date", r.status_code == 200 and bool(streams) and bool(streams[0].get("next_expected")), json.dumps(streams[:1], ensure_ascii=False)[:200])
    cm = c.get(f"/organizer/{ws}/commitments").json()
    cm = cm if isinstance(cm, list) else []
    check("income stream reaches the calendar as income", any(x.get("kind") == "income" for x in cm), str([x.get("kind") for x in cm])[:160])

    # 6. Onboarding knows where the user stands.
    r = c.get(f"/pf/{ws}/onboarding")
    check("onboarding reports real progress", r.status_code == 200 and "steps" in r.json(), r.text[:200])

    # Hide the throwaway so the workspace list a person sees is the same before and after a run.
    r = c.put(f"/workspaces/{ws}", json={"hidden": True})
    check("manual-flow throwaway workspace hidden afterwards", r.status_code == 200, r.text[:120])


# --------------------------------------------------------------------------- level 7: numbered acceptance items


def _amt(money: object) -> Decimal:
    """``{"amount": "12.50", ...}`` → Decimal; anything else → Decimal('0')."""
    if isinstance(money, dict):
        try:
            return Decimal(str(money.get("amount", "0")))
        except ArithmeticError:
            return Decimal("0")
    return Decimal("0")


def _body(r: httpx.Response) -> dict:
    try:
        j = r.json()
    except ValueError:
        return {}
    return j if isinstance(j, dict) else {"_": j}


def _list(r: httpx.Response) -> list:
    try:
        j = r.json()
    except ValueError:
        return []
    return j if isinstance(j, list) else []


def _money(amount: str, currency: str = "MXN") -> dict:
    return {"amount": amount, "currency": currency}


def _ledger_amount(balances: dict, account: str, currency: str = "MXN") -> Decimal:
    return Decimal(next((x["amount"] for x in balances.get(account, []) if x["currency"] == currency), "0"))


@dataclass
class _AcceptanceState:
    """Ids the numbered items hand to each other, plus the dates every write is planned around."""

    ws: str
    today: date
    period: str
    prev_period: str
    past: date          # a day in a month no period-sensitive check (#5/#9/#16) looks at
    checking: str = ""
    checking_name: str = ""
    checking_ledger: str = ""
    cash: str = ""
    cash_name: str = ""
    card: str = ""
    card_ledger: str = ""
    savings: str = ""
    labels: dict[str, dict] = field(default_factory=dict)
    entry_500: str = ""
    docker_up: bool = False
    mcp_url: str = ""       # --mcp, else the compose stack's published MCP port, else "" (SKIP)


def _label(c: httpx.Client, st: _AcceptanceState, name: str) -> dict:
    if name not in st.labels:
        for kind in ("expense", "income"):
            for row in _list(c.get(f"/pf/{st.ws}/labels", params={"kind": kind, "include_archived": 1})):
                st.labels.setdefault(row["name"], row)
    return st.labels.get(name, {})


def _accounts(c: httpx.Client, ws: str) -> dict:
    return _body(c.get(f"/pf/{ws}/accounts"))


def _account_row(c: httpx.Client, ws: str, account_id: str) -> dict:
    return _body(c.get(f"/pf/{ws}/accounts/{account_id}"))


def _entries(c: httpx.Client, ws: str, **params: object) -> dict:
    return _body(c.get(f"/pf/{ws}/entries", params=params))


def _all_entries(c: httpx.Client, ws: str, **params: object) -> list[dict]:
    rows: list[dict] = []
    cursor = None
    for _ in range(20):
        page = _entries(c, ws, limit=500, **({"cursor": cursor} if cursor else {}), **params)
        rows.extend(page.get("entries", []))
        cursor = page.get("next_cursor")
        if not cursor:
            break
    return rows


def _post_entry(c: httpx.Client, st: _AcceptanceState, **fields: object) -> httpx.Response:
    body = {"kind": "expense", "date": st.past.isoformat(), "account_id": st.checking}
    body.update(fields)
    return c.post(f"/pf/{st.ws}/entries", json=body)


def _journal(c: httpx.Client, ws: str) -> list[dict]:
    return _list(c.get(f"/ledger/{ws}/journal"))


def _balances(c: httpx.Client, ws: str) -> dict:
    return _body(c.get(f"/ledger/{ws}/balances"))


def _main_beancount(c: httpx.Client, ws: str) -> bytes:
    r = c.get(f"/workspaces/{ws}/backup.zip")
    if r.status_code != 200:
        return b""
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        return z.read("main.beancount") if "main.beancount" in z.namelist() else b""


def _calendar_items(c: httpx.Client, ws: str, start: date, end: date) -> list[dict]:
    cal = _body(c.get(f"/organizer/{ws}/calendar", params={"from": start.isoformat(), "to": end.isoformat()}))
    return [dict(item, day=day.get("date")) for day in cal.get("days", []) for item in day.get("items", [])]


def _commitments(c: httpx.Client, ws: str, **params: object) -> list[dict]:
    return _list(c.get(f"/organizer/{ws}/commitments", params=params))


def _post_commitment(c: httpx.Client, st: _AcceptanceState, **fields: object) -> httpx.Response:
    body = {"kind": "subscription", "cadence": "monthly", "account_id": st.checking}
    body.update(fields)
    return c.post(f"/organizer/{st.ws}/commitments", json=body)


def _cancel_commitment(c: httpx.Client, ws: str, cid: str) -> None:
    """Soft delete = status cancelled: out of every active-only view and out of the duplicate guard."""
    if cid:
        c.delete(f"/organizer/{ws}/commitments/{cid}")


# --- items -------------------------------------------------------------------------------------


def _item_workspace(c: httpx.Client, ws: str) -> None:
    """#1 (creation; the guard itself is unit-tested) + #2 (ordering and flags)."""
    r = c.post("/workspaces", json={"id": ws, "name": "Verify acceptance", "kind": "personal", "jurisdictions": ["MX"],
                                    "base_currency": "MXN", "language": "es", "ui_mode": "simple"})
    check("acceptance: throwaway workspace created (#1)", r.status_code in (200, 201), r.text[:160])
    wl = _list(c.get("/workspaces"))
    personal_row = next((w for w in wl if w["id"] == "personal"), None)
    if personal_row is not None:
        check("acceptance: personal listed first and protected (#2)", wl[0]["id"] == "personal" and personal_row["protected"] is True, str(wl[:2])[:200])
    else:
        skip("acceptance: personal listed first and protected (#2)", "no 'personal' workspace on this server")
    non_demo = [i for i, w in enumerate(wl) if not w.get("profile", {}).get("demo")]
    demos = [i for i, w in enumerate(wl) if w.get("profile", {}).get("demo")]
    check("acceptance: demos carry profile.demo and come last (#2)", bool(demos) and max(non_demo or [-1]) < min(demos), str([(w["id"], bool(w.get("profile", {}).get("demo"))) for w in wl])[:240])
    mine = next((w for w in wl if w["id"] == ws), None)
    check("acceptance: new workspace unprotected+visible (#2)", bool(mine) and mine["protected"] is False and mine["hidden"] is False, str(mine)[:200])


def _item_accounts(c: httpx.Client, st: _AcceptanceState) -> None:
    """#3 accounts + liabilities: typed positive, stored negative, owed/balance/balance_signed."""
    ws = st.ws
    r = c.post(f"/pf/{ws}/accounts", json={"name": "Cuenta BBVA", "type": "checking", "opening_balance": _money("20000")})
    st.checking, st.checking_name, st.checking_ledger = _body(r).get("id", ""), _body(r).get("name", ""), _body(r).get("account", "")
    r2 = c.post(f"/pf/{ws}/accounts", json={"name": "Efectivo", "type": "cash", "opening_balance": _money("1200")})
    st.cash, st.cash_name = _body(r2).get("id", ""), _body(r2).get("name", "")
    r3 = c.post(f"/pf/{ws}/accounts", json={"name": "Tarjeta", "type": "credit_card", "opening_balance": _money("5000")})
    st.card, st.card_ledger = _body(r3).get("id", ""), _body(r3).get("account", "")
    check("acceptance: checking 20000 / cash 1200 / card 5000 created (#3)", all(x.status_code == 200 for x in (r, r2, r3)) and bool(st.checking and st.cash and st.card), f"{r.status_code} {r2.status_code} {r3.status_code}")
    if not (st.checking and st.cash and st.card):
        return
    ov = _accounts(c, ws)
    card = next((x for x in ov.get("accounts", []) if x["id"] == st.card), {})
    check("acceptance: net_worth 16200.00 after opening balances (#3)", _amt(ov.get("net_worth")) == Decimal("16200.00"), str(ov.get("net_worth")))
    check("acceptance: card row owed/balance 5000.00/balance_signed -5000.00 (#3)", card.get("owed") is True and _amt(card.get("balance")) == Decimal("5000.00") and _amt(card.get("balance_signed")) == Decimal("-5000.00"), json.dumps({k: card.get(k) for k in ("owed", "balance", "balance_signed")}))
    check("acceptance: ledger shows the Liabilities account at -5000 (#3)", _ledger_amount(_balances(c, ws), st.card_ledger) == Decimal("-5000.00"), f"{st.card_ledger}={_ledger_amount(_balances(c, ws), st.card_ledger)}")
    r = _post_entry(c, st, account_id=st.card, amount=_money("300"), payee="Farmacia")
    card = _account_row(c, ws, st.card)
    ov = _accounts(c, ws)
    check("acceptance: expense 300 on the card -> owed 5300.00, net_worth 15900.00 (#3)", r.status_code == 200 and _amt(card.get("balance")) == Decimal("5300.00") and _amt(ov.get("net_worth")) == Decimal("15900.00"), f"owed={card.get('balance')} net_worth={ov.get('net_worth')}")
    r = _post_entry(c, st, kind="transfer", account_id=st.checking, to_account_id=st.card, amount=_money("1000"))
    card = _account_row(c, ws, st.card)
    ov = _accounts(c, ws)
    check("acceptance: transfer 1000 checking->card -> owed 4300.00, net_worth unchanged 15900.00 (#3)", r.status_code == 200 and _amt(card.get("balance")) == Decimal("4300.00") and _amt(ov.get("net_worth")) == Decimal("15900.00"), f"owed={card.get('balance')} net_worth={ov.get('net_worth')}")
    r = c.post(f"/pf/{ws}/accounts", json={"name": "Tarjeta negativa", "type": "credit_card", "opening_balance": _money("-5000")})
    check("acceptance: card with opening_balance -5000 -> 422 (#3)", r.status_code == 422, f"{r.status_code} {r.text[:120]}")
    r = c.post(f"/pf/{ws}/accounts/{st.card}/adjust", json={"balance": _money("4000")})
    check("acceptance: adjust card balance 4000 -> owed 4000.00 (#3)", r.status_code == 200 and _amt(_body(r).get("balance")) == Decimal("4000.00"), str(_body(r).get("balance")))


def _item_labels(c: httpx.Client, st: _AcceptanceState) -> None:
    """#4 labels: seeds, server-derived accounts, grammar, kind mismatch, archive."""
    ws = st.ws
    income = _list(c.get(f"/pf/{ws}/labels", params={"kind": "income"}))
    check("acceptance: labels?kind=income includes Sueldo/Nómina (#4)", any(x["name"] == "Sueldo/Nómina" for x in income), str([x["name"] for x in income])[:200])
    r = c.post(f"/pf/{ws}/labels", json={"name": "Gimnasio", "kind": "expense"})
    gym = _body(r)
    check("acceptance: POST label Gimnasio -> Expenses:Gimnasio, no colon in name (#4)", r.status_code == 200 and gym.get("account") == "Expenses:Gimnasio" and ":" not in gym.get("name", ":"), r.text[:160])
    r = c.post(f"/pf/{ws}/labels", json={"name": "Comida mala", "account": "Expenses:comida"})
    check("acceptance: label with account Expenses:comida -> 400 (#4)", r.status_code == 400, f"{r.status_code} {r.text[:120]}")
    comida = _label(c, st, "Comida fuera")
    r = _post_entry(c, st, kind="income", amount=_money("100"), label_id=comida.get("id"), payee="Mal etiquetado")
    check("acceptance: income entry with an expense label -> 400 (#4)", r.status_code == 400, f"{r.status_code} {r.text[:120]}")
    if gym.get("id"):
        r = c.put(f"/pf/{ws}/labels/{gym['id']}", json={"archived": True})
        visible = [x["id"] for x in _list(c.get(f"/pf/{ws}/labels", params={"kind": "expense"}))]
        check("acceptance: archived label hidden from ?kind=expense (#4)", r.status_code == 200 and gym["id"] not in visible, f"{r.status_code} visible={len(visible)}")


def _item_budget_500(c: httpx.Client, st: _AcceptanceState) -> None:
    """#5 first half: a 2000 budget on 'Comida fuera' this month and a 500 expense against it."""
    ws = st.ws
    comida = _label(c, st, "Comida fuera")
    r = c.post(f"/pf/{ws}/budgets", json={"label_id": comida.get("id"), "period": st.period, "amount": "2000"})
    r2 = _post_entry(c, st, date=st.today.isoformat(), amount=_money("500"), label_id=comida.get("id"), payee="Tacos El Primo")
    st.entry_500 = _body(r2).get("id", "")
    status = _body(c.get(f"/pf/{ws}/budgets/status", params={"period": st.period}))
    row = next((b for b in status.get("budgets", []) if b.get("label_id") == comida.get("id")), {})
    check("acceptance: expense 500 -> budgets/status row spent 500.00 (#5)", r.status_code == 200 and r2.status_code == 200 and _amt(row.get("spent")) == Decimal("500.00"), f"budget={r.status_code} entry={r2.status_code} spent={row.get('spent')}")


def _item_safe_to_spend(c: httpx.Client, st: _AcceptanceState) -> None:
    """#16 one safe-to-spend figure: rent 3000 due before the next payday, budget 2000 with 500 spent, buffer 0."""
    ws = st.ws
    rent_due, pay_due = st.today + timedelta(days=10), st.today + timedelta(days=20)
    rent = _body(_post_commitment(c, st, name="Renta verify", kind="rent", amount=_money("3000"), next_due=rent_due.isoformat()))
    pay = _body(_post_commitment(c, st, name="Pago verify", kind="income", amount=_money("1000"), next_due=pay_due.isoformat()))
    c.put(f"/organizer/{ws}/forecast/buffer", json={"buffer": "0"})
    try:
        balance = _ledger_amount(_balances(c, ws), st.checking_ledger) + _ledger_amount(_balances(c, ws), "Assets:Cash")
        sts = _body(c.get(f"/organizer/{ws}/summary")).get("safe_to_spend", {})
        parts = sts.get("parts", {})
        expected = balance - Decimal("3000") - Decimal("1500")
        check("acceptance: safe_to_spend.amount == B - 3000 - 1500 (#16)", _amt(sts.get("amount")) == expected and _amt(parts.get("balance")) == balance, f"amount={sts.get('amount')} expected={expected} B={balance}")
        check("acceptance: parts fixed_pending 3000.00 / budgets_remaining 1500.00 / buffer 0.00 (#16)", _amt(parts.get("fixed_pending")) == Decimal("3000.00") and _amt(parts.get("budgets_remaining")) == Decimal("1500.00") and _amt(parts.get("buffer")) == Decimal("0.00"), json.dumps(parts))
        check("acceptance: safe_to_spend.until is the payday and currency == base (#16)", sts.get("until") == pay_due.isoformat() and sts.get("currency") == "MXN", f"until={sts.get('until')} currency={sts.get('currency')}")
        steps = sts.get("explain", {}).get("steps", [])
        ids = [s.get("id") for s in steps]
        check("acceptance: explain step ids are exactly the six safe-to-spend ids (#16)", ids == ["liquid_balance", "until", "committed_until", "budgeted_remaining", "buffer", "safe_to_spend"], str(ids))
        # step labels are the ids (the UI humanizes them); every step carries a human-readable formula
        check("acceptance: every explain step carries a human formula (#16)", all(isinstance(s.get("formula"), str) and s["formula"].strip() for s in steps), str([s.get("formula") for s in steps])[:200])
        series = _body(c.get(f"/organizer/{ws}/forecast", params={"days": 30})).get("series", [])
        by_date = {d["date"]: d for d in series}
        day, prev = by_date.get(rent_due.isoformat(), {}), by_date.get((rent_due - timedelta(days=1)).isoformat(), {})
        drop = _amt(prev.get("balance")) - _amt(day.get("balance")) if day and prev else None
        check("acceptance: forecast?days=30 drops by 3000 on the rent date (#16)", drop == Decimal("3000") and _amt(day.get("out")) == Decimal("3000.00"), f"{rent_due}: out={day.get('out')} drop={drop}")
    finally:
        c.put(f"/organizer/{ws}/forecast/buffer", json={"buffer": None})
        _cancel_commitment(c, ws, rent.get("id", ""))
        _cancel_commitment(c, ws, pay.get("id", ""))


def _item_voids(c: httpx.Client, st: _AcceptanceState) -> None:
    """#5 second half (void semantics): a void hides the spend from budgets and review; second delete → 409."""
    ws = st.ws
    comida = _label(c, st, "Comida fuera")
    r = c.delete(f"/pf/{ws}/entries/{st.entry_500}")
    status = _body(c.get(f"/pf/{ws}/budgets/status", params={"period": st.period}))
    row = next((b for b in status.get("budgets", []) if b.get("label_id") == comida.get("id")), {})
    check("acceptance: DELETE entry -> budget spent 0.00 (#5)", r.status_code == 200 and _amt(row.get("spent")) == Decimal("0.00"), f"{r.status_code} spent={row.get('spent')}")
    review = _body(c.get(f"/pf/{ws}/review/{st.period}"))
    check("acceptance: review top_labels [] and expense 0.00 after the void (#5)", review.get("top_labels") == [] and _amt(review.get("expense")) == Decimal("0.00"), f"top_labels={review.get('top_labels')} expense={review.get('expense')}")
    r = c.delete(f"/pf/{ws}/entries/{st.entry_500}")
    check("acceptance: second DELETE -> 409 (#5)", r.status_code == 409, f"{r.status_code} {r.text[:100]}")
    h = _body(c.get(f"/ledger/{ws}/health"))
    check("acceptance: ledger health error_count 0 after the void (#5)", h.get("error_count") == 0, str(h)[:160])


def _item_validate_then_write(c: httpx.Client, st: _AcceptanceState) -> None:
    """#6 validate, then write: nothing touches the ledger on a 4xx; an edit is one reversal + one new transaction."""
    ws = st.ws
    entry = _body(_post_entry(c, st, amount=_money("100"), payee="Editable"))
    j0, b0 = _journal(c, ws), _balances(c, ws)
    r = c.put(f"/pf/{ws}/entries/{entry.get('id')}", json={"account_id": "nope"})
    check("acceptance: PUT entry account_id nope -> 404, journal+balances unchanged (#6)", r.status_code == 404 and len(_journal(c, ws)) == len(j0) and _balances(c, ws) == b0, f"{r.status_code} journal={len(j0)}")
    r = c.put(f"/pf/{ws}/entries/{entry.get('id')}", json={"amount": _money("150")})
    j1, b1 = _journal(c, ws), _balances(c, ws)
    new = [t for t in j1 if t not in j0]
    reversal = [t for t in new if "entry-reversal" in t.get("tags", []) and t.get("meta", {}).get("reverses") == entry.get("txn_id")]
    fresh = [t for t in new if not t.get("tags") and t.get("meta", {}).get("pf_entry_id") == entry.get("id")]
    delta = _ledger_amount(b1, "Expenses:Other") - _ledger_amount(b0, "Expenses:Other")
    check("acceptance: valid PUT -> exactly one reversal + one new txn (#6)", r.status_code == 200 and len(new) == 2 and len(reversal) == 1 and len(fresh) == 1, f"{r.status_code} new={len(new)} reversal={len(reversal)} fresh={len(fresh)}")
    check("acceptance: balances reflect only the new amount (#6)", delta == Decimal("50.00"), f"Expenses:Other delta={delta} (100 -> 150)")
    item = {"kind": "expense", "date": st.past.isoformat(), "amount": _money("1"), "account_id": st.checking}
    r = c.post(f"/pf/{ws}/entries/bulk", json={"entries": [item, item, {**item, "account_id": "nope"}]})
    check("acceptance: bulk with item 3 invalid -> 400 and zero txns from the batch (#6)", r.status_code == 400 and len(_journal(c, ws)) == len(j1) and _body(r).get("detail", {}).get("index") == 2, f"{r.status_code} {r.text[:120]} journal={len(_journal(c, ws))}")


def _item_entries_envelope(c: httpx.Client, st: _AcceptanceState) -> None:
    """#7 entries envelope: 120 expenses in one month; totals over the full set; keyset paging; limit cap."""
    ws = st.ws
    month = (st.past - relativedelta(months=1)).replace(day=1)
    rows = [{"kind": "expense", "date": (month + timedelta(days=i % 28)).isoformat(), "amount": _money(f"{(i % 7) + 1}.00"),
             "account_id": st.checking, "payee": f"Gasto {i}"} for i in range(120)]
    expected_out = sum((Decimal(r["amount"]["amount"]) for r in rows), Decimal("0"))
    r = c.post(f"/pf/{ws}/entries/bulk", json={"entries": rows})
    ids = set(_body(r).get("created", []))
    check("acceptance: bulk 120 expenses created (#7)", r.status_code == 200 and len(ids) == 120, f"{r.status_code} created={len(ids)}")
    span = {"from": month.isoformat(), "to": (month + timedelta(days=27)).isoformat()}
    p1 = _entries(c, ws, limit=50, **span)
    check("acceptance: entries?limit=50 -> 50 rows, totals.count 120, totals.out = sum, cursor set (#7)", len(p1.get("entries", [])) == 50 and p1.get("totals", {}).get("count") == 120 and _amt(p1.get("totals", {}).get("out")) == expected_out and bool(p1.get("next_cursor")), f"rows={len(p1.get('entries', []))} totals={p1.get('totals')} expected_out={expected_out}")
    p2 = _entries(c, ws, limit=50, cursor=p1.get("next_cursor", ""), **span)
    p3 = _entries(c, ws, limit=50, cursor=p2.get("next_cursor", ""), **span)
    pages = [{e["id"] for e in p.get("entries", [])} for p in (p1, p2, p3)]
    disjoint = not (pages[0] & pages[1]) and not (pages[1] & pages[2]) and not (pages[0] & pages[2])
    check("acceptance: three pages disjoint covering all 120, last next_cursor null (#7)", disjoint and pages[0] | pages[1] | pages[2] == ids and p3.get("next_cursor") is None, f"sizes={[len(p) for p in pages]} last_cursor={p3.get('next_cursor')}")
    r = c.get(f"/pf/{ws}/entries", params={"limit": 501})
    check("acceptance: entries?limit=501 -> 422 (#7)", r.status_code == 422, f"{r.status_code} {r.text[:100]}")
    check("acceptance: every row carries editable and non_editable_reason (#7)", bool(p1.get("entries")) and all("editable" in e and "non_editable_reason" in e for e in p1.get("entries", [])), str(p1.get("entries", [{}])[0].keys())[:200])


def _item_input_hygiene(c: httpx.Client, st: _AcceptanceState) -> None:
    """#8 input hygiene: floats/text money, currency case, tags, dates, periods, duplicates, enums, control chars."""
    ws = st.ws
    r = _post_entry(c, st, amount={"amount": 12.5, "currency": "MXN"})
    check("acceptance: entry amount 12.5 (float) -> 422 (#8)", r.status_code == 422, f"{r.status_code} {r.text[:100]}")
    r = _post_entry(c, st, amount={"amount": "abc", "currency": "MXN"})
    check("acceptance: entry amount 'abc' -> 422 (#8)", r.status_code == 422, f"{r.status_code} {r.text[:100]}")
    r = _post_entry(c, st, amount={"amount": "10", "currency": "mxn"}, payee="minusculas")
    txn = next((t for t in _journal(c, ws) if _body(r).get("txn_id") in t.get("links", [])), {})
    check("acceptance: currency 'mxn' -> 200 and the ledger line shows MXN (#8)", r.status_code == 200 and bool(txn) and all(p["amount"]["currency"] == "MXN" for p in txn.get("postings", []) if p.get("amount")), f"{r.status_code} postings={[p.get('amount') for p in txn.get('postings', [])]}")
    before = _main_beancount(c, ws)
    r = _post_entry(c, st, amount=_money("10"), tags=["a b"])
    check("acceptance: tags ['a b'] -> 400 with main.beancount byte-identical (#8)", r.status_code == 400 and before and _main_beancount(c, ws) == before, f"{r.status_code} {r.text[:80]} bytes={len(before)}")
    r = c.get(f"/pf/{ws}/entries", params={"from": "abc"})
    check("acceptance: entries?from=abc -> 422 (#8)", r.status_code == 422, f"{r.status_code}")
    r = c.get(f"/pf/{ws}/review/2026-13")
    check("acceptance: review/2026-13 -> 422 (#8)", r.status_code == 422, f"{r.status_code}")
    comida = _label(c, st, "Comida fuera")
    r = c.post(f"/pf/{ws}/budgets", json={"label_id": comida.get("id"), "period": st.period, "amount": "2000"})
    check("acceptance: duplicate budget -> 409 (#8)", r.status_code == 409, f"{r.status_code} {r.text[:80]}")
    r = c.post(f"/pf/{ws}/goals", json={"kind": "foo", "name": "x", "target": "1", "account_id": st.savings or st.checking})
    check("acceptance: goal kind foo -> 422 (#8)", r.status_code == 422, f"{r.status_code}")
    r = c.post(f"/pf/{ws}/accounts", json={"name": "\n", "type": "cash"})
    # the name validator is a pydantic BeforeValidator, so this is body validation (422)
    check("acceptance: account name '\\n' -> 422 (#8)", r.status_code == 422, f"observed {r.status_code} {r.text[:120]}")


def _item_budgets_copy(c: httpx.Client, st: _AcceptanceState) -> None:
    """#9 budgets: explicit carry-forward, idempotent; warn at 80 %, over at 100 %."""
    ws = st.ws
    names = ("Súper", "Transporte/Gasolina", "Ropa")
    created = [c.post(f"/pf/{ws}/budgets", json={"label_id": _label(c, st, n).get("id"), "period": st.prev_period, "amount": "1000"}).status_code for n in names]
    r1 = _body(c.post(f"/pf/{ws}/budgets/copy", json={"from": st.prev_period, "to": st.period}))
    r2 = _body(c.post(f"/pf/{ws}/budgets/copy", json={"from": st.prev_period, "to": st.period}))
    check("acceptance: budgets/copy -> created 3, then created 0 skipped 3 (#9)", created == [200, 200, 200] and r1.get("created") == 3 and r2.get("created") == 0 and r2.get("skipped") == 3, f"prev={created} first={r1} second={r2}")
    status = _body(c.get(f"/pf/{ws}/budgets/status", params={"period": st.period}))
    check("acceptance: status has_previous true, previous_period set (#9)", status.get("has_previous") is True and status.get("previous_period") == st.prev_period, f"has_previous={status.get('has_previous')} previous_period={status.get('previous_period')}")
    ropa = _label(c, st, "Ropa")
    _post_entry(c, st, date=st.today.isoformat(), amount=_money("850"), label_id=ropa.get("id"), payee="Zapatos")
    row = next((b for b in _body(c.get(f"/pf/{ws}/budgets/status", params={"period": st.period})).get("budgets", []) if b.get("label_id") == ropa.get("id")), {})
    check("acceptance: 85 % of a budget -> state warn (#9)", row.get("state") == "warn", f"spent={row.get('spent')} pct={row.get('pct')} state={row.get('state')}")
    _post_entry(c, st, date=st.today.isoformat(), amount=_money("200"), label_id=ropa.get("id"), payee="Camisa")
    status = _body(c.get(f"/pf/{ws}/budgets/status", params={"period": st.period}))
    row = next((b for b in status.get("budgets", []) if b.get("label_id") == ropa.get("id")), {})
    check("acceptance: 105 % of a budget -> state over (#9)", row.get("state") == "over", f"spent={row.get('spent')} pct={row.get('pct')} state={row.get('state')}")
    check("acceptance: status totals present and safe_to_spend still returned (#9)", {"budget", "spent", "remaining"} <= status.get("totals", {}).keys() and "amount" in status.get("safe_to_spend", {}), f"totals={status.get('totals')} safe_to_spend={status.get('safe_to_spend')}")


def _item_goals(c: httpx.Client, st: _AcceptanceState) -> None:
    """#10 goals point at a pf account id; account/currency derived server-side."""
    ws = st.ws
    r = c.post(f"/pf/{ws}/accounts", json={"name": "Ahorro", "type": "savings", "opening_balance": _money("12000")})
    st.savings = _body(r).get("id", "")
    target_date = (st.today + relativedelta(years=1)).isoformat()
    r = c.post(f"/pf/{ws}/goals", json={"kind": "savings", "name": "Viaje", "target": "30000", "target_date": target_date, "account_id": st.savings})
    g = _body(r)
    check("acceptance: goal on account_id -> account derived (Assets:...) + account_name (#10)", r.status_code == 200 and str(g.get("account", "")).startswith("Assets:") and g.get("account_name") == "Ahorro" and g.get("account_id") == st.savings, f"{r.status_code} account={g.get('account')} account_name={g.get('account_name')}")
    row = next((x for x in _list(c.get(f"/pf/{ws}/goals")) if x.get("id") == g.get("id")), {})
    check("acceptance: goal progress 12000.00, pct 40 (#10)", _amt(row.get("progress")) == Decimal("12000.00") and Decimal(str(row.get("pct", "0"))) == Decimal("40"), f"progress={row.get('progress')} pct={row.get('pct')}")
    _post_entry(c, st, kind="transfer", account_id=st.checking, to_account_id=st.savings, amount=_money("2000"))
    row = next((x for x in _list(c.get(f"/pf/{ws}/goals")) if x.get("id") == g.get("id")), {})
    check("acceptance: transfer 2000 -> goal progress 14000.00 (#10)", _amt(row.get("progress")) == Decimal("14000.00"), f"progress={row.get('progress')}")
    r = c.post(f"/pf/{ws}/goals", json={"kind": "savings", "name": "x", "target": "1", "account_id": "nope"})
    check("acceptance: goal with account_id nope -> 404 (#10)", r.status_code == 404, f"{r.status_code} {r.text[:80]}")


def _item_streams(c: httpx.Client, st: _AcceptanceState) -> None:
    """#11: an income stream mirrors into organizer income commitments (in place on PUT)."""
    ws = st.ws
    r = c.post(f"/pf/{ws}/income/streams", json={"name": "Nómina Acme", "source_type": "salary", "amount": _money("22500"),
                                                 "cadence": "semimonthly", "anchor_days": [15, 30], "account_id": st.checking})
    stream = _body(r)
    sid, created_at = stream.get("id", ""), stream.get("created_at")
    incomes = [x for x in _commitments(c, ws, status="active") if x.get("kind") == "income" and x.get("id") in stream.get("commitment_ids", [])]
    check("acceptance: stream -> 2 income commitments, normalized merchant_patterns, account_name (#11)", r.status_code == 200 and len(incomes) == 2 and all("NOMINA ACME" in x.get("merchant_patterns", []) and x.get("account_name") == st.checking_name for x in incomes), f"{r.status_code} {[(x.get('name'), x.get('merchant_patterns'), x.get('account_name')) for x in incomes]}")
    r = c.put(f"/pf/{ws}/income/streams/{sid}", json={"account_id": "nope"})
    listed = next((x for x in _list(c.get(f"/pf/{ws}/income/streams")) if x.get("id") == sid), {})
    still_active = [x for x in _commitments(c, ws, status="active") if x.get("id") in listed.get("commitment_ids", [])]
    check("acceptance: PUT stream account_id nope -> 404, same created_at, 2 active commitments (#11)", r.status_code == 404 and listed.get("created_at") == created_at and len(still_active) == 2, f"{r.status_code} created_at same={listed.get('created_at') == created_at} active={len(still_active)}")
    r = c.put(f"/pf/{ws}/income/streams/{sid}", json={"active": False})
    mirrored = [x for x in _commitments(c, ws) if x.get("id") in stream.get("commitment_ids", [])]
    series = _body(c.get(f"/organizer/{ws}/forecast", params={"days": 60})).get("series", [])
    income_in = sum((_amt(d.get("in")) for d in series), Decimal("0"))
    check("acceptance: PUT active false -> commitments paused, forecast has no income_expected (#11)", r.status_code == 200 and mirrored and all(x.get("status") == "paused" for x in mirrored) and income_in == 0, f"{r.status_code} statuses={[x.get('status') for x in mirrored]} forecast_in={income_in}")
    fifteenth = next((x for x in mirrored if x.get("anchor_day") == 15), {})
    salary = _label(c, st, "Sueldo/Nómina")
    payday = st.today.replace(day=15) if st.today.day >= 15 else (st.today - relativedelta(months=1)).replace(day=15)
    r = _post_entry(c, st, kind="income", date=payday.isoformat(), amount=_money("22500"), label_id=salary.get("id"), payee="Nómina Acme", commitment_id=fifteenth.get("id"))
    history = _list(c.get(f"/pf/{ws}/income/streams/{sid}/history"))
    hit = [h for h in history if _amt(h.get("received")) == Decimal("22500.00")]
    check("acceptance: income entry 22500 with commitment_id -> history received 22500.00 (#11)", r.status_code == 200 and bool(hit), f"entry={r.status_code} dated={payday} history={json.dumps(history)[:200]}")
    # retained excludes IVA-Acreditable: a raw ledger deposit that also credits IVA-Acreditable.
    iva_month = (st.past - relativedelta(months=2)).replace(day=3)
    r = c.post(f"/ledger/{ws}/transactions", json={"date": iva_month.isoformat(), "payee": "Cliente", "narration": "Factura con IVA", "postings": [
        {"account": st.checking_ledger, "amount": _money("1000")}, {"account": "Assets:Taxes:IVA-Acreditable", "amount": _money("160")},
        {"account": "Income:Other", "amount": _money("-1160")}]})
    month = next((m for m in _body(c.get(f"/pf/{ws}/income", params={"months": 12})).get("months", []) if m.get("month") == iva_month.strftime("%Y-%m")), {})
    check("acceptance: GET /income retained excludes IVA-Acreditable (#11)", r.status_code == 200 and _amt(month.get("gross")) == Decimal("1160.00") and _amt(month.get("retained")) == Decimal("0.00"), f"txn={r.status_code} {iva_month.strftime('%Y-%m')} gross={month.get('gross')} retained={month.get('retained')}")


def _item_commitments(c: httpx.Client, st: _AcceptanceState) -> dict:
    """#12 commitments (bounds, partial update, duplicate guard): returns the Renta row for #13."""
    ws = st.ws
    r = _post_commitment(c, st, name="Renta", kind="rent", amount=_money("3000"), anchor_day=1)
    renta = _body(r)
    check("acceptance: POST Renta -> account_name is the checking name (#12)", r.status_code == 200 and renta.get("account_name") == st.checking_name and renta.get("account_id") == st.checking, f"{r.status_code} account_name={renta.get('account_name')}")
    r = c.put(f"/organizer/{ws}/commitments/{renta.get('id')}", json={"name": "Renta depto"})
    patched = _body(r)
    same = all(patched.get(k) == renta.get(k) for k in ("account_id", "started", "category_hint"))
    check("acceptance: PUT name -> account_id/started/category_hint unchanged (#12)", r.status_code == 200 and patched.get("name") == "Renta depto" and same, f"{r.status_code} {[(k, renta.get(k), patched.get(k)) for k in ('account_id', 'started', 'category_hint')]}")
    r = _post_commitment(c, st, name="Renta", kind="rent", amount=_money("3000"), anchor_day=1)
    detail = _body(r).get("detail", {})
    check("acceptance: duplicate Renta -> 409 with existing_id (#12)", r.status_code == 409 and isinstance(detail, dict) and detail.get("existing_id") == renta.get("id"), f"{r.status_code} {r.text[:120]}")
    r = _post_commitment(c, st, name="Anchor malo", amount=_money("1"), anchor_day=-5)
    check("acceptance: anchor_day -5 -> 422 (#12)", r.status_code == 422, f"{r.status_code}")
    r = c.get(f"/organizer/{ws}/calendar", params={"from": "2026-13-01"})
    check("acceptance: calendar?from=2026-13-01 -> 422 (#12)", r.status_code == 422, f"{r.status_code}")
    r = c.get(f"/organizer/{ws}/calendar", params={"from": "2026-01-01", "to": "2028-02-01"})
    check("acceptance: calendar range > 24 months -> 422 (#12)", r.status_code == 422, f"{r.status_code} {r.text[:80]}")
    r = c.post(f"/organizer/{ws}/commitments/{renta.get('id')}/review")
    check("acceptance: POST review -> reviewed_at set (#12)", r.status_code == 200 and bool(_body(r).get("reviewed_at")), r.text[:80])
    return patched or renta


def _item_mark_paid_fixed(c: httpx.Client, st: _AcceptanceState, renta: dict) -> None:
    """#13 mark paid (fixed amount): one-tap paid creates the entry, repeat is idempotent, un-mark voids it."""
    ws, cid, due = st.ws, renta.get("id", ""), renta.get("next_due", "")
    before = _amt(_account_row(c, ws, st.checking).get("balance"))
    r = c.post(f"/organizer/{ws}/occurrences/mark", json={"commitment_id": cid, "date": due, "status": "paid", "log_entry": True})
    occ, entry_id = _body(r).get("occurrence", {}), _body(r).get("entry_id")
    check("acceptance: mark paid log_entry -> occurrence paid + entry_id (#13)", r.status_code == 200 and occ.get("status") == "paid" and bool(entry_id), r.text[:160])
    rows = _entries(c, ws, commitment_id=cid).get("entries", [])
    row = next((x for x in rows if x.get("id") == entry_id), {})
    check("acceptance: entry payee Renta depto, -3000.00, checking, commitment_id, editable (#13)", row.get("payee") == "Renta depto" and _amt(row.get("amount")) == Decimal("-3000.00") and row.get("account_id") == st.checking and row.get("commitment_id") == cid and row.get("editable") is True, json.dumps({k: row.get(k) for k in ("payee", "amount", "account_name", "commitment_id", "editable")}, ensure_ascii=False))
    after = _amt(_account_row(c, ws, st.checking).get("balance"))
    check("acceptance: checking balance dropped 3000 (#13)", before - after == Decimal("3000"), f"{before} -> {after}")
    r = c.post(f"/organizer/{ws}/occurrences/mark", json={"commitment_id": cid, "date": due, "status": "paid", "log_entry": True})
    count = _entries(c, ws, commitment_id=cid).get("totals", {}).get("count")
    check("acceptance: repeat mark -> same entry_id and still one row (#13)", r.status_code == 200 and _body(r).get("entry_id") == entry_id and count == 1, f"entry_id same={_body(r).get('entry_id') == entry_id} rows={count}")
    r = c.delete(f"/organizer/{ws}/occurrences/mark", params={"commitment_id": cid, "date": due})
    status = next((i.get("status") for i in _calendar_items(c, ws, date.fromisoformat(due), date.fromisoformat(due)) if i.get("id") == cid), None)
    voided = _entries(c, ws, commitment_id=cid).get("totals", {}).get("count") == 0
    check("acceptance: un-mark -> entry voided, calendar back to due/upcoming (#13)", r.status_code == 200 and _body(r).get("voided_entry_id") == entry_id and voided and status in ("due", "upcoming"), f"{r.text[:80]} live_rows_zero={voided} status={status}")


def _item_mark_paid_variable(c: httpx.Client, st: _AcceptanceState) -> None:
    """#14 mark paid (variable amount): linking a hand-logged entry; voiding it must drop the paid status."""
    ws = st.ws
    nf = _body(_post_commitment(c, st, name="Netflix", amount=_money("219"), amount_variable=True, anchor_day=15))
    cid, due = nf.get("id", ""), nf.get("next_due", st.today.isoformat())
    entry = _body(_post_entry(c, st, date=due, amount=_money("219"), payee="Netflix", commitment_id=cid))
    r = c.post(f"/organizer/{ws}/occurrences/mark", json={"commitment_id": cid, "date": due, "status": "paid", "entry_id": entry.get("id")})
    occ = _body(r).get("occurrence", {})
    check("acceptance: mark paid with entry_id -> occurrence.txn_id == entry.txn_id, auto_created false (#14)", r.status_code == 200 and occ.get("txn_id") == entry.get("txn_id") and occ.get("auto_created") is False, r.text[:160])
    r = c.delete(f"/pf/{ws}/entries/{entry.get('id')}")
    status = next((i.get("status") for i in _calendar_items(c, ws, date.fromisoformat(due), date.fromisoformat(due)) if i.get("id") == cid), None)
    check("acceptance: DELETE the linked entry -> occurrence status due/missed/upcoming (#14)", r.status_code == 200 and status in ("due", "missed", "upcoming"), f"delete={r.status_code} observed calendar status={status}")


def _item_history_next_due(c: httpx.Client, st: _AcceptanceState) -> None:
    """#15: three months of matched entries populate history; a stale next_due still alerts."""
    ws = st.ws
    anchor = st.today + timedelta(days=5)
    started = anchor - relativedelta(months=3)
    tel = _body(_post_commitment(c, st, name="Telcel", kind="bill", amount=_money("399"), anchor_day=anchor.day, started=started.isoformat()))
    for i in range(3):
        _post_entry(c, st, date=(started + relativedelta(months=i)).isoformat(), amount=_money("399"), payee="Telcel", commitment_id=tel.get("id"))
    row = _body(c.get(f"/organizer/{ws}/commitments/{tel.get('id')}"))
    paid = [o for o in row.get("occurrences", []) if o.get("status") == "paid"]
    upcoming = [i for i in _calendar_items(c, ws, st.today, st.today + timedelta(days=30)) if i.get("id") == tel.get("id") and i.get("status") in ("upcoming", "due")]
    check("acceptance: commitment started 3 months ago -> >= 3 paid occurrences + 1 upcoming (#15)", len(paid) >= 3 and len(upcoming) == 1 and upcoming[0].get("day") == row.get("next_due"), f"paid={len(paid)} upcoming={[(i.get('day'), i.get('status')) for i in upcoming]} next_due={row.get('next_due')}")
    items = [i for i in _calendar_items(c, ws, started, st.today) if i.get("id") == tel.get("id")]
    check("acceptance: calendar over those 3 months lists 3 items for it (#15)", len(items) == 3 and all(i.get("status") == "paid" for i in items), str([(i.get("day"), i.get("status")) for i in items]))
    old = _body(_post_commitment(c, st, name="Spotify", amount=_money("129"), next_due=(st.today + timedelta(days=3) - relativedelta(months=1)).isoformat()))
    effective = old.get("next_due", "")
    alerts = _list(c.get(f"/organizer/{ws}/alerts"))
    hit = [a for a in alerts if a.get("kind") == "upcoming" and a.get("commitment_id") == old.get("id") and a.get("due") == effective]
    within_week = st.today.isoformat() <= effective <= (st.today + timedelta(days=7)).isoformat()
    check("acceptance: stale stored next_due still yields an upcoming alert for the effective due (#15)", old.get("stored_next_due", "9999") < st.today.isoformat() and within_week and len(hit) == 1, f"stored={old.get('stored_next_due')} effective={effective} alerts={[(a.get('kind'), a.get('due')) for a in alerts if a.get('commitment_id') == old.get('id')]}")


def _item_tax_gating(c: httpx.Client, st: _AcceptanceState) -> None:
    """#17 tax gating: tax rows appear only with modules.tax on; one nudge per commitment on demo-mx."""
    ws = st.ws
    span = (st.today, st.today + relativedelta(months=2))
    tax_kinds = ("cfdi", "resico", "diot")

    def observe() -> tuple[int, list[str]]:
        tax_items = [i for i in _calendar_items(c, ws, *span) if i.get("kind") == "tax"]
        kinds = [i.get("kind", "") for i in _list(c.get(f"/insights/{ws}")) if any(t in str(i.get("kind", "")).lower() for t in tax_kinds)]
        return len(tax_items), kinds

    off = observe()
    check("acceptance: simple workspace -> zero tax calendar items and zero cfdi/resico/diot insights (#17)", off == (0, []), f"tax_items={off[0]} insight_kinds={off[1]}")
    r = c.put(f"/workspaces/{ws}", json={"modules": {"tax": True}})
    on = observe()
    c.put(f"/workspaces/{ws}", json={"modules": {"tax": False}})
    back = observe()
    check("acceptance: modules.tax true -> tax rows appear; revert -> gone (#17)", r.status_code == 200 and on[0] > 0 and back == (0, []), f"on: tax_items={on[0]} insight_kinds={on[1]}; reverted: {back}")
    nudges = [i.get("title") for i in _list(c.get("/insights/demo-mx")) if i.get("kind") == "organizer_upcoming"]
    check("acceptance: insights/demo-mx has exactly one nudge per commitment name (#17)", len(nudges) == len(set(nudges)), f"{len(nudges)} upcoming nudges: {nudges}"[:220])


def _item_onboarding(c: httpx.Client, ws: str, expect_done: bool) -> None:
    """#18 onboarding: fixed step ids; done flips once accounts and first_entries are done."""
    r = c.get(f"/pf/{ws}/onboarding")
    body = _body(r)
    ids = [s.get("id") for s in body.get("steps", [])]
    if not expect_done:
        check("acceptance: onboarding has the four step ids (#18)", r.status_code == 200 and ids == ["accounts", "income", "recurring", "first_entries"] and body.get("done") is False, r.text[:200])
        return
    steps = {s.get("id"): s for s in body.get("steps", [])}
    check("acceptance: onboarding done once accounts and first_entries are done (#18)", body.get("done") is True and steps.get("accounts", {}).get("done") is True and steps.get("first_entries", {}).get("done") is True, str({k: (v.get("done"), v.get("count")) for k, v in steps.items()}))


def _item_quickadd_csv(c: httpx.Client, st: _AcceptanceState) -> None:
    """#19 shortcuts create ordinary editable entries: quickadd previews then commits a pf entry; CSV import
    writes entries and dedupes."""
    ws = st.ws
    first_entries_before = next((s.get("count", 0) for s in _body(c.get(f"/pf/{ws}/onboarding")).get("steps", []) if s.get("id") == "first_entries"), 0)
    r = c.post(f"/ingest/{ws}/quickadd", json={"text": "250 tacos comida", "account_id": st.cash})
    preview = _body(r).get("preview", {})
    check("acceptance: quickadd preview -> label Comida fuera, account_name cash (#19)", r.status_code == 200 and _body(r).get("status") == "preview" and preview.get("label_name") == "Comida fuera" and preview.get("account_name") == st.cash_name, r.text[:200])
    cash_before = _amt(_account_row(c, ws, st.cash).get("balance"))
    r = c.post(f"/ingest/{ws}/quickadd", json={"text": "250 tacos comida", "account_id": st.cash, "commit": True})
    entry = _body(r).get("entry") or {}
    cash_after = _amt(_account_row(c, ws, st.cash).get("balance"))
    check("acceptance: quickadd commit -> entry editable, source quickadd, cash -250 (#19)", r.status_code == 200 and entry.get("editable") is True and entry.get("source") == "quickadd" and cash_before - cash_after == Decimal("250"), f"{r.status_code} editable={entry.get('editable')} source={entry.get('source')} cash {cash_before} -> {cash_after}")
    r = c.post(f"/ingest/{ws}/quickadd", json={"text": "viaje a europa 900", "account_id": st.cash})
    check("acceptance: 'viaje a europa 900' -> label != Ropa (#19)", r.status_code == 200 and _body(r).get("preview", {}).get("label_name") != "Ropa", f"label={_body(r).get('preview', {}).get('label_name')}")
    csv_month = (st.past - relativedelta(months=3)).replace(day=1)
    csv_text = "Fecha,Concepto,Monto\n" + "".join(f"{(csv_month + timedelta(days=i)).isoformat()},OXXO {i},-{10 + i}.00\n" for i in range(10))
    files = {"file": ("verify.csv", csv_text.encode("utf-8"), "text/csv")}
    r = c.post(f"/ingest/{ws}/bank/csv", data={"bank": "verify", "account_id": st.checking}, files=files)
    created = _body(r).get("created", [])
    rows = _entries(c, ws, limit=500, **{"from": csv_month.isoformat(), "to": (csv_month + timedelta(days=9)).isoformat()}).get("entries", [])
    imported = [x for x in rows if x.get("id") in created]
    check("acceptance: bank/csv 10 lines -> created 10 with source import (#19)", r.status_code == 200 and len(created) == 10 and len(imported) == 10 and all(x.get("source") == "import" for x in imported), f"{r.status_code} created={len(created)} listed={len(imported)}")
    balances = _balances(c, ws)
    r = c.post(f"/ingest/{ws}/bank/csv", data={"bank": "verify", "account_id": st.checking}, files={"file": ("verify.csv", csv_text.encode("utf-8"), "text/csv")})
    check("acceptance: re-import -> skipped_duplicates 10 and balances unchanged (#19)", r.status_code == 200 and _body(r).get("skipped_duplicates") == 10 and _body(r).get("created") == [] and _balances(c, ws) == balances, f"{r.status_code} {r.text[:120]}")
    first_entries_after = next((s.get("count", 0) for s in _body(c.get(f"/pf/{ws}/onboarding")).get("steps", []) if s.get("id") == "first_entries"), 0)
    check("acceptance: onboarding first_entries counts the quickadd row, not the import (#19)", first_entries_after == first_entries_before + 1, f"{first_entries_before} -> {first_entries_after}")


def _item_backup_export(c: httpx.Client, st: _AcceptanceState) -> None:
    """#20 backups: per-workspace zip + CSV export, full backup listed, personal backup is a read."""
    ws = st.ws
    r = c.get(f"/workspaces/{ws}/backup.zip")
    names: list[str] = []
    metadata: dict = {}
    if r.status_code == 200 and r.headers.get("content-type") == "application/zip":
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            names = z.namelist()
            metadata = json.loads(z.read("metadata.json")) if "metadata.json" in names else {}
    wanted = {"workspace.json", "main.beancount", "accounts.beancount", "metadata.json", "movimientos.csv"}
    check("acceptance: backup.zip 200 application/zip with the five names (#20)", wanted <= set(names), f"{r.status_code} {r.headers.get('content-type')} {names}")
    tables = metadata.get("tables", {})
    md_entries = [e for e in tables.get("pf_entries", []) if not e.get("voided")]
    md_ids = {e.get("id") for e in md_entries}
    listed = _all_entries(c, ws)
    foreign = [e for e in listed if e.get("id") not in md_ids]
    totals_count = _entries(c, ws, limit=1).get("totals", {}).get("count")
    check("acceptance: metadata pf_entries (non-voided) == entries totals.count minus foreign ledger rows (#20)", bool(md_entries) and totals_count == len(md_entries) + len(foreign) and all(e.get("editable") is False for e in foreign), f"metadata={len(md_entries)} totals.count={totals_count} foreign={len(foreign)}")
    check("acceptance: metadata organizer_commitments count matches (#20)", len(tables.get("organizer_commitments", [])) == len(_commitments(c, ws)) > 0, f"metadata={len(tables.get('organizer_commitments', []))} api={len(_commitments(c, ws))}")
    r = c.get(f"/workspaces/{ws}/movimientos.csv")
    lines = r.content.decode("utf-8-sig").splitlines() if r.status_code == 200 else []
    header = "Fecha;Tipo;Monto;Moneda;Cuenta;Cuenta destino;Categoría;Comercio;Nota;Etiquetas;Origen"
    signed = [ln.split(";")[2] for ln in lines[1:]]
    check("acceptance: movimientos.csv BOM, ';' header, header+N rows, signed amounts (#20)", r.status_code == 200 and r.content[:3] == b"\xef\xbb\xbf" and lines[:1] == [header] and len(lines) == 1 + (totals_count or -1) and all(s.startswith("-") or Decimal(s) > 0 for s in signed), f"{r.status_code} rows={len(lines) - 1} expected={totals_count} sample={lines[1:2]}")
    r = c.post("/backup")
    ok = r.status_code == 200 and {"path", "size", "sha256"} <= _body(r).keys()
    check("acceptance: POST /backup returns path/size/sha256 (#20)", ok, r.text[:160])
    if ok:
        names_listed = {b["name"] for b in _list(c.get("/backups"))}
        check("acceptance: GET /backups lists the new backup (#20)", _body(r).get("name") in names_listed, str(sorted(names_listed))[:200])
    if c.get("/workspaces/personal").status_code == 200:
        r = c.get("/workspaces/personal/backup.zip")
        check("acceptance: GET personal/backup.zip is an allowed read (#20)", r.status_code == 200, str(r.status_code))
    else:
        skip("acceptance: GET personal/backup.zip (#20)", "no 'personal' workspace on this server")


def _item_health(c: httpx.Client) -> None:
    """#21 first half: the health document (no data_dir; auth, bind and schema versions)."""
    h = _body(c.get("/health"))
    check("acceptance: health has no data_dir (#21)", "data_dir" not in h, str(h)[:160])
    check("acceptance: health auth {required false, source none}, bind 127.0.0.1 (#21)", h.get("auth") == {"required": False, "source": "none"} and h.get("bind") == "127.0.0.1", f"auth={h.get('auth')} bind={h.get('bind')}")
    check("acceptance: health.schema includes pf and organizer versions (#21)", isinstance(h.get("schema"), dict) and {"pf", "organizer"} <= h.get("schema", {}).keys(), str(h.get("schema")))


def _item_ledger_health_end(c: httpx.Client, ws: str) -> None:
    """#21 second half: the ledger file parses cleanly after the whole flow."""
    h = _body(c.get(f"/ledger/{ws}/health"))
    check("acceptance: ledger health error_count 0 at the end of the flow (#21)", h.get("error_count") == 0 and h.get("txns", 0) > 100, str(h)[:200])


def _item_security_smoke(c: httpx.Client, a: argparse.Namespace, st: _AcceptanceState) -> None:
    """#22 loopback posture without a token — CORS, Origin, Host, ws ids, paths, MCP."""
    ws = st.ws
    r = c.get("/workspaces", headers={"Origin": "https://evil.example"})
    cors = [k for k in r.headers if k.lower() == "access-control-allow-origin"]
    check("acceptance: GET with Origin evil prints no access-control-allow-origin (#22)", r.status_code == 200 and not cors, f"{r.status_code} cors_headers={cors}")
    r = c.post(f"/pf/{ws}/labels", headers={"Origin": "https://evil.example"}, json={"name": "x", "kind": "expense"})
    check("acceptance: POST with Origin evil -> 403 origin_not_allowed (#22)", r.status_code == 403 and _body(r).get("error") == "origin_not_allowed", f"{r.status_code} {r.text[:80]}")
    r = c.get("/workspaces", headers={"Host": "attacker.example"})
    check("acceptance: Host attacker.example -> 403 host_not_allowed (#22)", r.status_code == 403 and _body(r).get("error") == "host_not_allowed", f"{r.status_code} {r.text[:80]}")
    r = c.get("/pf/A_B/accounts")
    check("acceptance: /pf/A_B/accounts -> 400 invalid_workspace_id (#22)", r.status_code == 400 and _body(r).get("error") == "invalid_workspace_id", f"{r.status_code} {r.text[:80]}")
    r = c.get("/pf/..%2F..%2Fx/accounts")
    # Against the API itself the traversal is refused with 400 bad_path. Through the nginx front door
    # (5024) the path is normalized to /x/accounts before it is proxied, so the request never reaches
    # the API and nginx answers its own (non-JSON) 404: the traversal is refused either way.
    api_refused = r.status_code == 400 and _body(r).get("error") == "bad_path"
    front_door_404 = r.status_code == 404 and "json" not in r.headers.get("content-type", "").lower()
    how = "api 400 bad_path" if api_refused else "front door normalized it away (404, not the API)" if front_door_404 else "NOT refused"
    check("acceptance: /pf/..%2F..%2Fx/accounts -> 400 bad_path (api) or a non-API 404 (front door) (#22)", api_refused or front_door_404, f"{r.status_code} {r.headers.get('content-type', '')} {how} {r.text[:60]!r}")
    r = c.get("/health")
    check("acceptance: /health still 200 (#22)", r.status_code == 200, str(r.status_code))
    mcp = st.mcp_url or a.mcp
    if not mcp:
        skip("acceptance: MCP initialize -> 200 (#22)", "pass --mcp http://127.0.0.1:5042/mcp (or run the compose stack, whose published MCP port is read from `docker compose port api 5042`)")
        return
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "verify", "version": "1"}}}
    try:
        r = httpx.post(mcp, json=init, headers={"Accept": "application/json, text/event-stream"}, timeout=30)
        check("acceptance: MCP initialize -> 200 (#22)", r.status_code == 200 and "serverInfo" in r.text, f"{mcp} {r.status_code} {r.text[:80]}")
    except httpx.HTTPError as e:
        check("acceptance: MCP initialize -> 200 (#22)", False, f"{mcp}: {e}")


# --- docker posture (#23), optional --------------------------------------------------------------


def _run(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def compose_services_up(ps_output: str) -> set[str]:
    """Names of running services from ``docker compose ps --format json`` (one object per line or a list)."""
    text = ps_output.strip()
    if not text:
        return set()
    rows: list[dict] = []
    try:
        parsed = json.loads(text)
        rows = parsed if isinstance(parsed, list) else [parsed]
    except ValueError:
        for line in text.splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return {str(r.get("Service", "")) for r in rows if isinstance(r, dict) and str(r.get("State", "")).lower() == "running"}


def cap_eff_is_empty(status_text: str) -> bool:
    for line in status_text.splitlines():
        if line.startswith("CapEff:"):
            return int(line.split(":", 1)[1].strip() or "1", 16) == 0
    return False


def proc_uid(status_text: str) -> int | None:
    """Real uid of the process from its ``/proc/<pid>/status`` (``Uid:\\treal\\teffective\\tsaved\\tfs``).

    PID 1 is what the container runs as: ``Dockerfile.api`` has no ``USER`` line on purpose (the
    entrypoint drops to ``aurum`` with setpriv after fixing /data), so ``docker compose exec … id -u``
    spawns a *new* root process and says 0 while the API itself runs as 10001."""
    for line in status_text.splitlines():
        if line.startswith("Uid:"):
            fields = line.split(":", 1)[1].split()
            return int(fields[0]) if fields and fields[0].isdigit() else None
    return None


def expected_published_ports(env: dict[str, str] | None = None) -> tuple[str, str]:
    """``(web-ui, mcp)`` host bindings the compose file publishes: loopback on ``AURUM_PORT`` /
    ``AURUM_MCP_HOST_PORT`` (defaults 5024 / 5042, the values item #23 expects). The host is always
    127.0.0.1 — that is the posture being checked, so a stack started with ``AURUM_BIND=0.0.0.0``
    fails here on purpose."""
    env = os.environ if env is None else env
    return f"127.0.0.1:{env.get('AURUM_PORT', '5024')}", f"127.0.0.1:{env.get('AURUM_MCP_HOST_PORT', '5042')}"


def docker_stack_up(repo: Path, run=_run) -> bool:
    if shutil.which("docker") is None:
        return False
    code, out = run(["docker", "compose", "ps", "--format", "json"], cwd=repo)
    return code == 0 and {"api", "web-ui"} <= compose_services_up(out)


def compose_mcp_url(repo: Path, run=_run) -> str:
    """``http://<host:port>/mcp`` from ``docker compose port api 5042`` (empty when compose has no answer)."""
    code, out = run(["docker", "compose", "port", "api", "5042"], cwd=repo)
    binding = out.strip().splitlines()[0].strip() if code == 0 and out.strip() else ""
    return f"http://{binding}/mcp" if re.fullmatch(r"[\w.:\[\]-]+:\d+", binding) else ""


def _item_docker_posture(a: argparse.Namespace, st: _AcceptanceState, repo: Path, run=_run) -> None:
    """#23: only meaningful against the compose stack; SKIP otherwise."""
    if not st.docker_up:
        skip("acceptance: docker posture (#23)", "docker compose ps does not report the aurum stack (api + web-ui) running")
        return
    web = (a.web or web_origin(a.api)).rstrip("/")
    _, ui_port = run(["docker", "compose", "port", "web-ui", "8080"], cwd=repo)
    _, mcp_port = run(["docker", "compose", "port", "api", "5042"], cwd=repo)
    want_web, want_mcp = expected_published_ports()
    check("acceptance: docker port shows loopback web-ui and mcp bindings (AURUM_PORT/AURUM_MCP_HOST_PORT, default 127.0.0.1:5024 / :5042) (#23)", ui_port.strip() == want_web and mcp_port.strip() == want_mcp, f"web-ui={ui_port.strip()} (want {want_web}) api={mcp_port.strip()} (want {want_mcp})")
    _, status = run(["docker", "compose", "exec", "-T", "api", "cat", "/proc/1/status"], cwd=repo)
    uid = proc_uid(status)
    check("acceptance: api container PID 1 runs as uid != 0 (/proc/1/status; exec id -u would say 0, no USER line) (#23)", uid is not None and uid != 0, f"Uid={uid}")
    check("acceptance: CapEff 0 (#23)", cap_eff_is_empty(status), next((ln for ln in status.splitlines() if ln.startswith("CapEff")), status[:80]))
    _, config = run(["docker", "compose", "config"], cwd=repo)
    check("acceptance: compose config shows json-file 10m x 3 (#23)", "json-file" in config and "10m" in config and '"3"' in config, str([ln.strip() for ln in config.splitlines() if "max-" in ln or "json-file" in ln])[:200])
    try:
        r = httpx.get(f"{web}/plan", follow_redirects=False, timeout=30)
        # nginx serves $uri/index.html directly (200, no redirect round-trip); a 301 is acceptable only
        # with a relative Location (absolute_redirect off / port_in_redirect off), never the container's :8080.
        loc = r.headers.get("location") or ""
        served = r.status_code == 200 and "text/html" in r.headers.get("content-type", "")
        redirected = r.status_code == 301 and loc in ("/plan/", f"{web}/plan/")
        check("acceptance: slash-less /plan -> 200 served directly, or 301 to relative /plan/ (never :8080) (#23)", served or redirected, f"{r.status_code} content-type={r.headers.get('content-type')} location={loc or None}")
        r = httpx.get(f"{web}/nope/", timeout=30)
        check("acceptance: /nope/ -> 404 (#23)", r.status_code == 404, str(r.status_code))
        r = httpx.get(f"{web}/manifest.webmanifest", timeout=30)
        check("acceptance: /manifest.webmanifest -> 200 application/manifest+json (#23)", r.status_code == 200 and r.headers.get("content-type", "").startswith("application/manifest+json"), f"{r.status_code} {r.headers.get('content-type')}")
    except httpx.HTTPError as e:
        check("acceptance: web front door reachable for #23 (#23)", False, f"{web}: {e}")


def _item_demos(c: httpx.Client) -> None:
    """#24: the seeded demos (read-only) look the way the seed promises."""
    onb = _body(c.get("/pf/demo-personal/onboarding"))
    check("acceptance: demo-personal onboarding done (#24)", onb.get("done") is True, str({s.get('id'): s.get('done') for s in onb.get('steps', [])}))
    accts = _accounts(c, "demo-personal").get("accounts", [])
    check("acceptance: demo-personal >= 4 accounts incl. one owed card (#24)", len(accts) >= 4 and any(x.get("owed") and x.get("type") == "credit_card" for x in accts), str([(x.get("name"), x.get("owed")) for x in accts])[:200])
    rows = _entries(c, "demo-personal", limit=100).get("entries", [])
    check("acceptance: demo-personal entries all editable, >= 1 commitment_id (#24)", bool(rows) and all(x.get("editable") is True for x in rows) and any(x.get("commitment_id") for x in rows), f"rows={len(rows)} linked={sum(1 for x in rows if x.get('commitment_id'))}")
    sts = _body(c.get("/organizer/demo-personal/summary")).get("safe_to_spend", {})
    alerts = _list(c.get("/organizer/demo-personal/alerts"))
    check("acceptance: demo-personal safe_to_spend > 0 and no missed alert (#24)", _amt(sts.get("amount")) > 0 and not any(x.get("kind") == "missed_payment" for x in alerts), f"safe_to_spend={sts.get('amount')} alerts={[x.get('kind') for x in alerts]}")
    streams = _list(c.get("/pf/demo-personal/income/streams"))
    cmts = [x for x in _commitments(c, "demo-personal") if x.get("kind") != "income"]
    check("acceptance: seeding twice does not duplicate streams/commitments (#24)", len(streams) == 1 and len(cmts) == 4, f"streams={len(streams)} non-income commitments={len(cmts)} (seed declares 1 / 4; --refresh runs on every boot)")
    ov = _accounts(c, "demo-mx")
    bal = _balances(c, "demo-mx")
    total = sum((Decimal(x["amount"]) for k, v in bal.items() if k.startswith(("Assets:", "Liabilities:")) for x in v if x["currency"] == "MXN"), Decimal("0"))
    check("acceptance: demo-mx lists 3 pf accounts and net_worth == sum(Assets)+sum(Liabilities) (#24)", len(ov.get("accounts", [])) == 3 and _amt(ov.get("net_worth")) == total, f"accounts={len(ov.get('accounts', []))} net_worth={ov.get('net_worth')} ledger_sum={total}")
    goals = _list(c.get("/pf/demo-mx/goals"))
    check("acceptance: demo-mx goals progress > 0 (#24)", bool(goals) and all(_amt(g.get("progress")) > 0 for g in goals), str([(g.get("name"), g.get("progress")) for g in goals])[:200])


def _item_e2e(a: argparse.Namespace, ws: str, repo: Path) -> None:
    """#26: spawn the headless UI flows against the same stack (never against ``personal``)."""
    script = repo / "web-ui" / "scripts" / "ui-check.mjs"
    node = shutil.which("node")
    if not a.e2e:
        return
    if node is None or not script.exists():
        skip("acceptance: --e2e ui-check flows (#26)", f"node={node} script_exists={script.exists()}")
        return
    env = {**os.environ, "WS": ws, "BASE_URL": (a.web or web_origin(a.api)).rstrip("/")}
    try:
        p = subprocess.run([node, str(script), "--flows"], cwd=repo / "web-ui", env=env, capture_output=True, text=True, timeout=1800, check=False)
        tail = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()[-3:]
        check("acceptance: --e2e ui-check --flows exit 0 (#26)", p.returncode == 0, f"exit={p.returncode} {' | '.join(tail)[:300]}")
    except (OSError, subprocess.TimeoutExpired) as e:
        check("acceptance: --e2e ui-check --flows exit 0 (#26)", False, str(e))


def acceptance_suite(c: httpx.Client, a: argparse.Namespace, repo: Path | None = None) -> None:
    """Level 7: the numbered acceptance items (see the module docstring) on a throwaway workspace. One
    helper per numbered item; #23 runs only against the compose stack and #26 only with ``--e2e``.
    demo-mx and demo-personal are read, never written (the level-1 quickadd on demo-mx is voided in
    ``main()``)."""
    today = date.today()
    ws = f"verify-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}"
    guard_protected(ws)
    repo = repo or Path(__file__).resolve().parents[1]
    st = _AcceptanceState(ws=ws, today=today, period=today.strftime("%Y-%m"),
                          prev_period=(today - relativedelta(months=1)).strftime("%Y-%m"),
                          past=(today - relativedelta(months=5)).replace(day=10))

    before_ids = sorted(w["id"] for w in _list(c.get("/workspaces")) if not w["id"].startswith("verify-"))
    before_demo_mx = (_balances(c, "demo-mx"), _entries_count(c, "demo-mx"))
    st.docker_up = docker_stack_up(repo)
    st.mcp_url = a.mcp or (compose_mcp_url(repo) if st.docker_up else "")

    try:
        _item_workspace(c, ws)
        _item_health(c)
        _item_onboarding(c, ws, expect_done=False)
        _item_accounts(c, st)
        if not (st.checking and st.cash and st.card):
            check("acceptance: accounts available for the rest of the flow (#3)", False, "account creation failed; later items not run")
            return
        _item_labels(c, st)
        _item_budget_500(c, st)
        _item_safe_to_spend(c, st)
        _item_voids(c, st)
        _item_validate_then_write(c, st)
        _item_entries_envelope(c, st)
        _item_goals(c, st)
        _item_input_hygiene(c, st)
        _item_budgets_copy(c, st)
        _item_streams(c, st)
        renta = _item_commitments(c, st)
        _item_mark_paid_fixed(c, st, renta)
        _item_mark_paid_variable(c, st)
        _item_history_next_due(c, st)
        _item_tax_gating(c, st)
        _item_onboarding(c, ws, expect_done=True)
        _item_quickadd_csv(c, st)
        _item_backup_export(c, st)
        _item_security_smoke(c, a, st)
        _item_docker_posture(a, st, repo)
        _item_demos(c)
        _item_ledger_health_end(c, ws)
        _item_e2e(a, ws, repo)

        # #25 — the read side is stable while we're the only writer here
        again = sorted(w["id"] for w in _list(c.get("/workspaces")) if not w["id"].startswith("verify-"))
        check("acceptance: workspace list (excl. verify-*) unchanged by this run (#25)", before_ids == again, f"{before_ids} vs {again}" if before_ids != again else str(again))
        after_demo_mx = (_balances(c, "demo-mx"), _entries_count(c, "demo-mx"))
        diff = balance_diff(before_demo_mx[0], after_demo_mx[0])
        check("acceptance: demo-mx balances and entry count untouched by this run (#25)", before_demo_mx == after_demo_mx, f"entries {before_demo_mx[1]} -> {after_demo_mx[1]}" + (f" balances diff={diff}" if diff else ", balances identical"))
    finally:
        c.put(f"/workspaces/{ws}", json={"hidden": True})
        omitted = ws not in {w["id"] for w in _list(c.get("/workspaces"))}
        included = ws in {w["id"] for w in _list(c.get("/workspaces?include_hidden=1"))}
        check("acceptance: throwaway workspace hidden afterwards (#25)", omitted and included, f"omitted={omitted} included={included}")


if __name__ == "__main__":
    sys.exit(main())
