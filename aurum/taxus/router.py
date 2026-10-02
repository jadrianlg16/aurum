"""US tax endpoints, mounted at ``/api/tax/us``."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from ..core import audit as audit_log
from ..rules.us import constants_2026 as K
from . import organizer_pdf, service

router = APIRouter(tags=["tax-us"])

MIN_YEAR, MAX_YEAR = 2000, 2100


def _year(year: int) -> int:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise HTTPException(400, f"year must be between {MIN_YEAR} and {MAX_YEAR}")
    return year


@router.get("/constants")
def constants() -> dict:
    """Every year-effective US constant with its citation and whether it was verified in a source."""
    rows = K.table()
    return {
        "year": K.YEAR,
        "constants": rows,
        "verified": sum(1 for r in rows if r["verified"]),
        "unverified": [r["key"] for r in rows if not r["verified"]],
    }


@router.get("/{ws}/{year}")
def annual(ws: str, year: int, lang: str | None = None) -> dict:
    payload = service.annual(ws, _year(year), lang=lang)
    if payload.get("applicable"):
        audit_log.record(
            ws,
            "tax.us.annual",
            {"year": year},
            {
                "schedule_c_net": payload["schedule_c"]["net"],
                "se_tax": payload["se_tax"]["value"],
                "income_tax": payload["income_tax"]["value"],
                "quarterly_each": payload["quarterly"]["amount_each"],
            },
            rule_versions=sorted(
                {
                    version
                    for section in ("schedule_c", "se_tax", "income_tax", "quarterly")
                    for version in payload[section]["explain"].get("rule_versions", [])
                }
            ),
        )
    return payload


@router.get("/{ws}/{year}/organizer.pdf")
def organizer(ws: str, year: int, lang: str | None = None) -> Response:
    payload = service.annual(ws, _year(year), lang=lang)
    return Response(
        content=organizer_pdf.render(payload),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="aurum-{ws}-{year}-US-organizer-DRAFT.pdf"'},
    )


@router.get("/{ws}/{year}/tx-franchise")
def tx_franchise(ws: str, year: int, lang: str | None = None) -> dict:
    payload = service.tx_franchise(ws, _year(year), lang=lang)
    if payload.get("applicable"):
        audit_log.record(
            ws,
            "tax.us.tx_franchise",
            {"year": year},
            {"no_tax_due": payload["no_tax_due"], "tax": payload["tax"]},
            rule_versions=payload["explain"].get("rule_versions", []),
        )
    return payload
