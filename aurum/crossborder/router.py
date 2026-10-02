"""Cross-border endpoints, mounted at ``/api/crossborder``."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core import audit as audit_log
from ..core.i18n import ws_lang
from ..core.workspaces import WorkspaceNotFound
from . import assessment as assess_mod
from .profile import CrossBorderProfile, load, store

router = APIRouter(tags=["crossborder"])


@router.put("/{ws}/profile")
def put_profile(ws: str, profile: CrossBorderProfile) -> dict:
    try:
        stored = store(ws, profile)
    except WorkspaceNotFound as e:
        raise HTTPException(404, f"no workspace {ws}") from e
    audit_log.record(
        ws,
        "crossborder.profile.put",
        {
            "days_us": profile.days_us,
            "days_mx": profile.days_mx,
            "accounts": len(profile.foreign_accounts),
        },
        {"stored": True},
    )
    return {"workspace": ws, "crossborder": stored.model_dump(mode="json")}


@router.get("/{ws}/profile")
def get_profile(ws: str) -> dict:
    try:
        _, profile = load(ws)
    except WorkspaceNotFound as e:
        raise HTTPException(404, f"no workspace {ws}") from e
    if profile is None:
        raise HTTPException(404, f"workspace {ws} has no cross-border profile — PUT one first")
    return {"workspace": ws, "crossborder": profile.model_dump(mode="json")}


@router.get("/{ws}/assessment")
def assessment(ws: str, lang: str | None = None) -> dict:
    try:
        _, profile = load(ws)
    except WorkspaceNotFound as e:
        raise HTTPException(404, f"no workspace {ws}") from e
    if profile is None:
        raise HTTPException(
            404,
            f"workspace {ws} has no cross-border profile — PUT /api/crossborder/{ws}/profile first",
        )
    payload = assess_mod.assess(ws, profile, lang=ws_lang(ws, lang))
    audit_log.record(
        ws,
        "crossborder.assessment",
        {"days_us": profile.days_us, "days_mx": profile.days_mx},
        {
            "us_resident": payload["residency"]["us"],
            "mx_resident": payload["residency"]["mx"],
            "fbar_required": payload["fbar"]["required"],
            "flags": len(payload["flags"]),
        },
        rule_versions=sorted(
            {
                version
                for section in ("residency", "treaty", "fbar", "feie_vs_ftc")
                for version in payload[section]["explain"].get("rule_versions", [])
            }
        ),
    )
    return payload
