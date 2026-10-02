"""Workspaces: one JSON file per workspace under {DATA_DIR}/workspaces/{id}/workspace.json."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .config import WS_ID_RE, env, settings

_ID = WS_ID_RE


def protected_workspace_ids() -> set[str]:
    """Workspace ids that migrations and scripts must never write to: ``AURUM_PROTECTED_WORKSPACES``
    (default ``personal``, comma-separated) union every workspace whose ``workspace.json`` says
    ``protected: true``. Reads files only — never the sqlite metadata db — so it works even from a
    migration function or before the metadata db exists."""
    ids = {x.strip() for x in env("AURUM_PROTECTED_WORKSPACES", "personal").split(",") if x.strip()}
    root = settings().workspaces_dir
    if root.exists():
        for p in root.glob("*/workspace.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("protected") is True:
                ids.add(p.parent.name)
    return ids


class Modules(BaseModel):
    """Advanced-only modules, all hidden by default. A UI preference only —
    nothing on the server refuses a hidden module's endpoint."""

    tax: bool = False
    business: bool = False
    research: bool = False
    watch: bool = False
    workflows: bool = False
    reports: bool = False
    crossborder: bool = False
    holdings: bool = False


class Workspace(BaseModel):
    id: str
    name: str
    kind: Literal["personal", "business", "advisory"] = "personal"
    jurisdictions: list[Literal["MX", "US"]] = Field(default_factory=lambda: ["MX"])
    base_currency: str = "MXN"
    language: Literal["es", "en"] = "es"
    profile: dict[str, Any] = Field(default_factory=dict)
    ui_mode: Literal["simple", "advanced"] = "simple"
    modules: Modules = Field(default_factory=Modules)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    protected: bool = False
    hidden: bool = False

    @model_validator(mode="after")
    def _force_protected(self) -> Workspace:
        """``id`` env-protected (default: ``personal``) is always protected, no matter what the caller
        or the stored file say. Rejecting an explicit attempt to unset it is the
        router's job (it can return a 400 with a message); this validator only guarantees the invariant
        holds for every ``Workspace`` instance in memory."""
        if self.id in protected_workspace_ids():
            self.protected = True
        return self

    def masked(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        prof = dict(data.get("profile") or {})
        for key in ("rfc", "curp", "ssn", "ein"):
            if key in prof and isinstance(prof[key], str) and len(prof[key]) > 4:
                prof[key] = "*" * (len(prof[key]) - 4) + prof[key][-4:]
        data["profile"] = prof
        return data


class WorkspaceNotFound(KeyError):
    pass


def _path(ws_id: str):
    return settings().workspace_dir(ws_id) / "workspace.json"


def list_workspaces() -> list[Workspace]:
    root = settings().workspaces_dir
    if not root.exists():
        return []
    out: list[Workspace] = []
    for p in sorted(root.glob("*/workspace.json")):
        out.append(Workspace.model_validate_json(p.read_text(encoding="utf-8")))
    return out


def get_workspace(ws_id: str) -> Workspace:
    p = _path(ws_id)
    if not p.exists():
        raise WorkspaceNotFound(ws_id)
    return Workspace.model_validate_json(p.read_text(encoding="utf-8"))


def save_workspace(ws: Workspace) -> Workspace:
    if not _ID.match(ws.id):
        raise ValueError("workspace id must be lowercase letters, digits, hyphens (2-41 chars)")
    d = settings().workspace_dir(ws.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "docs").mkdir(exist_ok=True)
    _path(ws.id).write_text(json.dumps(ws.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
    return ws


def ensure_workspace(ws_id: str, **defaults: Any) -> Workspace:
    try:
        return get_workspace(ws_id)
    except WorkspaceNotFound:
        return save_workspace(Workspace(id=ws_id, name=defaults.pop("name", ws_id), **defaults))


def ordered_workspaces(include_hidden: bool = False) -> list[Workspace]:
    """``GET /api/workspaces`` order: personal, non-demo workspaces first
    (oldest ``created_at`` first), then other non-demo workspaces, then every demo (``profile.demo``)
    last. Hidden workspaces are omitted unless ``include_hidden``. ``list_workspaces()`` itself stays
    unordered/unfiltered — this is the only place that applies the rule."""

    def is_demo(w: Workspace) -> bool:
        return bool(w.profile.get("demo"))

    all_ws = list_workspaces()
    personal = sorted(
        (w for w in all_ws if w.kind == "personal" and not is_demo(w)), key=lambda w: w.created_at
    )
    other = [w for w in all_ws if w.kind != "personal" and not is_demo(w)]
    demos = [w for w in all_ws if is_demo(w)]
    ordered = personal + other + demos
    if not include_hidden:
        ordered = [w for w in ordered if not w.hidden]
    return ordered


def module_on(ws_id: str, name: str) -> bool:
    """True when an advanced module is visible for a workspace: ``ui_mode == "advanced"`` or the
    matching ``modules`` flag is on. Unknown workspace or unknown module name → False. Server-side
    gating helper for things like calendar tax items."""
    try:
        ws = get_workspace(ws_id)
    except (WorkspaceNotFound, ValueError):
        return False
    if ws.ui_mode == "advanced":
        return True
    return bool(getattr(ws.modules, name, False))
