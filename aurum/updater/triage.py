"""Domain tagging and cautious proposal-drafting for a detected law/guidance change.

Regex/keyword tagging on purpose — this is a triage step for a human, not a legal
parser. A proposal is only ever ``status="proposed"``; nothing in this module (or
anywhere in the updater) writes to ``aurum/rules``.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from ..core.db import connect
from ..llm.exceptions import CloudNotAllowed
from ..llm.structured import generate_text

#: Domain -> keywords/phrases (lowercased, Spanish+English) that flag a change as
#: touching that domain. Order does not matter; a change can carry several domains.
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "RESICO": ["resico", "régimen simplificado de confianza", "regimen simplificado de confianza"],
    "IVA": ["iva", "impuesto al valor agregado", "value added tax"],
    "ISN": ["isn", "impuesto sobre nóminas", "impuesto sobre nominas", "payroll tax"],
    "platform_withholding": [
        "plataformas tecnológicas",
        "plataformas digitales",
        "30-b",
        "retención de plataformas",
        "digital platform withholding",
    ],
    "CFDI": ["cfdi", "comprobante fiscal digital", "catálogo", "catalogo"],
    "standard_deduction": ["standard deduction", "deducción estándar"],
    "franchise_tax": ["franchise tax", "texas franchise"],
    "se_tax": ["self-employment tax", "self employment tax", "schedule se", "impuesto de autoempleo"],
    "sales_tax": ["sales and use tax", "sales tax", "use tax", "impuesto sobre ventas"],
    "fbar": ["fbar", "foreign bank and financial accounts", "fincen 114"],
    "feie": ["foreign earned income exclusion", "form 2555", "exclusión de ingresos del extranjero"],
}

#: A percentage ("30%") or a currency amount ("$1,500.00") near a domain keyword is
#: the signal that a *rate or threshold*, not just prose, may have changed.
_RATE_OR_AMOUNT = re.compile(r"\d+(?:\.\d+)?\s?%|\$\s?[\d,]+(?:\.\d+)?")


def detect_domains(text: str) -> list[str]:
    lowered = (text or "").lower()
    return [domain for domain, keywords in DOMAIN_KEYWORDS.items() if any(k in lowered for k in keywords)]


def _fallback_summary(source: dict[str, Any], text: str, domains: list[str]) -> str:
    head = " ".join((text or "").split())[:220]
    tag = f" (domains: {', '.join(domains)})" if domains else ""
    return f"Change detected in {source['name']}{tag}: {head}"


def summarize(source: dict[str, Any], text: str, domains: list[str]) -> str:
    """One-line summary of what changed. Tries the LLM; falls back to a plain excerpt
    on ANY provider error so the tracker never blocks on a model being unavailable."""

    prompt = (
        "In one sentence, summarize what this regulatory text changes or announces. "
        f"Relevant domains so far: {', '.join(domains) or 'unknown'}.\n\n{(text or '')[:3000]}"
    )
    try:
        summary, _meta = generate_text(prompt, role="updater_triage", contains_raw_documents=False)
        summary = summary.strip()
        return summary or _fallback_summary(source, text, domains)
    except (CloudNotAllowed, httpx.HTTPError, ConnectionError, TimeoutError, OSError, ValueError):
        return _fallback_summary(source, text, domains)


def propose_from_change(change_id: str, text: str, domains: list[str]) -> list[dict[str, Any]]:
    """Draft (never apply) a proposal per domain when a rate/threshold appears near it.

    Status is always ``"proposed"`` — a human reviews and accepts/rejects elsewhere.
    """
    if not domains:
        return []
    matches = _RATE_OR_AMOUNT.findall(text or "")
    if not matches:
        return []

    proposals: list[dict[str, Any]] = []
    conn = connect()
    try:
        for domain in domains:
            new_value = matches[0]
            proposal_id = f"prop_{uuid.uuid4().hex[:12]}"
            row = {
                "id": proposal_id,
                "change_id": change_id,
                "rule_id": f"mx.{domain.lower()}",
                "field": "rate_or_threshold",
                "old_value": None,
                "new_value": new_value,
                "status": "proposed",
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            conn.execute(
                "INSERT INTO updater_proposals "
                "(id, change_id, rule_id, field, old_value, new_value, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["id"],
                    row["change_id"],
                    row["rule_id"],
                    row["field"],
                    row["old_value"],
                    row["new_value"],
                    row["status"],
                    row["created_at"],
                ),
            )
            proposals.append(row)
        conn.commit()
    finally:
        conn.close()
    return proposals
