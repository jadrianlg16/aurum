"""Seeds the four built-in workflows into a workspace on first ``GET``."""

from __future__ import annotations

from pathlib import Path

from .store import list_defs, save, validate_yaml

_BUILTIN_DIR = Path(__file__).resolve().parent / "builtin"


def builtin_yaml() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(_BUILTIN_DIR.glob("*.yaml"))}


def ensure_seeded(ws: str) -> None:
    existing = {d["id"] for d in list_defs(ws)}
    for workflow_id, raw_yaml in builtin_yaml().items():
        if workflow_id in existing:
            continue
        wf, errors, _ = validate_yaml(raw_yaml)
        if wf is None:  # pragma: no cover - built-ins are hand-verified, this guards drift
            raise ValueError(f"built-in workflow {workflow_id!r} failed validation: {errors}")
        save(ws, wf, raw_yaml)
