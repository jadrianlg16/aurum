"""Heuristic parser for a Buró de Crédito "Reporte de Crédito Especial" PDF.

Real reports vary by layout/version and this is descriptive only (never a filed number, never advice).
The parser looks for labeled fields per account block (``OTORGANTE``/``ACREEDOR`` starts a new block:
``LÍMITE DE CRÉDITO``, ``SALDO``, ``ESTATUS``, ``FECHA DE APERTURA``) and falls back to a generic
"columns separated by 2+ spaces or a pipe" table reader when no labeled blocks are found. Any account
whose required fields could not all be read is still returned, with a warning explaining what is
missing, rather than silently dropped or guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_ACCOUNT_START = re.compile(r"^(OTORGANTE|ACREEDOR)\s*[:\-]?\s*(.*)$", re.IGNORECASE)
_FIELD_PATTERNS: dict[str, re.Pattern] = {
    "type": re.compile(r"^(TIPO DE CUENTA|TIPO DE CR[ÉE]DITO)\s*[:\-]?\s*(.*)$", re.IGNORECASE),
    "limit": re.compile(r"^(L[ÍI]MITE DE CR[ÉE]DITO|CR[ÉE]DITO M[ÁA]XIMO)\s*[:\-]?\s*\$?\s*([\d.,]+)", re.IGNORECASE),
    "balance": re.compile(r"^(SALDO ACTUAL|SALDO)\s*[:\-]?\s*\$?\s*([\d.,]+)", re.IGNORECASE),
    "status": re.compile(r"^(ESTATUS( DE CUENTA)?|ESTADO DE CUENTA)\s*[:\-]?\s*(.*)$", re.IGNORECASE),
    "opened": re.compile(r"^(FECHA DE APERTURA)\s*[:\-]?\s*([\d/\-]+)", re.IGNORECASE),
}
_SCORE_PATTERN = re.compile(r"(SCORE|CALIFICACI[ÓO]N)\s*[:\-]?\s*(\d{3})", re.IGNORECASE)


@dataclass
class ParsedReport:
    accounts: list[dict[str, Any]] = field(default_factory=list)
    score: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


def _clean_amount(raw: str) -> str:
    return raw.replace(",", "").strip()


def _parse_labeled(lines: list[str]) -> list[dict[str, Any]]:
    accounts: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = _ACCOUNT_START.match(line)
        if m:
            if current is not None:
                accounts.append(current)
            current = {"grantor": m.group(2).strip() or None, "type": None, "limit": None,
                       "balance": None, "status": None, "opened": None}
            continue
        if current is None:
            continue
        for field_name, pattern in _FIELD_PATTERNS.items():
            fm = pattern.match(line)
            if fm:
                value = fm.group(fm.lastindex)
                if field_name in ("limit", "balance"):
                    value = _clean_amount(value)
                current[field_name] = value.strip()
                break
    if current is not None:
        accounts.append(current)
    return accounts


def _parse_generic_table(lines: list[str]) -> list[dict[str, Any]]:
    """Fallback: rows with 2+ spaces or ``|`` separating columns; header row picks the column order."""
    rows = [re.split(r"\s{2,}|\|", ln.strip()) for ln in lines if ln.strip()]
    rows = [[c.strip() for c in r if c.strip()] for r in rows if len(r) >= 3]
    if not rows:
        return []
    header = [c.lower() for c in rows[0]]
    key_map = {"otorgante": "grantor", "acreedor": "grantor", "tipo": "type", "limite": "limit",
               "saldo": "balance", "estatus": "status", "apertura": "opened"}
    columns: list[str | None] = []
    for h in header:
        matched = next((v for k, v in key_map.items() if k in h), None)
        columns.append(matched)
    if not any(columns):
        return []
    out = []
    for row in rows[1:]:
        acct: dict[str, Any] = {"grantor": None, "type": None, "limit": None, "balance": None,
                                 "status": None, "opened": None}
        for i, val in enumerate(row):
            if i < len(columns) and columns[i]:
                acct[columns[i]] = _clean_amount(val) if columns[i] in ("limit", "balance") else val
        if acct["grantor"]:
            out.append(acct)
    return out


def parse_text(text: str) -> ParsedReport:
    lines = text.splitlines()
    report = ParsedReport()

    score_match = _SCORE_PATTERN.search(text)
    if score_match:
        report.score = {"value": int(score_match.group(2)), "bureau": "Buró de Crédito"}

    accounts = _parse_labeled(lines)
    if not accounts:
        accounts = _parse_generic_table(lines)
        if accounts:
            report.warnings.append("used generic table fallback; layout did not match known labels")

    if not accounts:
        report.warnings.append("no accounts could be extracted; confidence low")

    for acct in accounts:
        missing = [k for k in ("grantor", "limit", "balance", "status", "opened") if not acct.get(k)]
        if missing:
            report.warnings.append(f"account {acct.get('grantor') or '(unknown)'}: missing {', '.join(missing)}")
        report.accounts.append(acct)

    if report.score is None:
        report.warnings.append("no score found in document")

    return report


class MissingPdfEngine(RuntimeError):
    """Raised only when pymupdf itself cannot be imported (it is a hard project dependency)."""


def parse_pdf_bytes(data: bytes) -> ParsedReport:
    try:
        import fitz  # pymupdf
    except ImportError as e:  # pragma: no cover - pymupdf is a hard project dependency
        raise MissingPdfEngine("pymupdf is required to parse credit report PDFs") from e

    text_parts: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return parse_text("\n".join(text_parts))
