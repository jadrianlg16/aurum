"""``POST /api/workflows/{ws}/propose``: LLM drafts a workflow YAML from a description.

Never saved or run automatically — the caller gets back ``{yaml, valid, errors, warnings}``
and must ``POST`` the draft through the normal create endpoint themselves. Offline (no
LLM reachable): falls back to keyword-matching the description against the built-in
catalog and returns the closest one, clearly labeled.
"""

from __future__ import annotations

import logging
from typing import Any

from .catalog import build_catalog
from .seed import builtin_yaml
from .store import validate_yaml

logger = logging.getLogger(__name__)

_KEYWORDS: dict[str, set[str]] = {
    "month-close-mx": {"month", "close", "mx", "mexico", "resico", "tax", "monthly"},
    "weekly-review": {"week", "weekly", "review", "budget", "goal", "reconcile"},
    "us-quarterly": {"quarter", "quarterly", "us", "usa", "organizer", "franchise"},
    "law-watch": {"law", "watch", "regulation", "change", "rule", "tracker"},
}


def _keyword_fallback(description: str) -> str:
    words = set(description.lower().split())
    best_id, best_score = "month-close-mx", -1
    for workflow_id, keywords in _KEYWORDS.items():
        score = len(words & keywords)
        if score > best_score:
            best_id, best_score = workflow_id, score
    return builtin_yaml()[best_id]


def _prompt(description: str) -> str:
    catalog = build_catalog()
    lines = "\n".join(f"- {e['method']} {e['path']} -- {e['summary']}" for e in catalog[:80])
    return (
        "Draft an Aurum workflow YAML for this request. "
        "A workflow is: id, name, description, schedule (cron or null), and steps: "
        "[{id, method, path, body?, save_as?, when?}]. Paths may use {{ ws }}, {{ period }}, "
        "{{ params.<key> }}, or {{ steps.<id>.body.<key> }} for templating. "
        "Only use paths from this catalog:\n" + lines + "\n\n"
        f"Request: {description}\n\n"
        "Return ONLY the YAML document, no prose, no code fences."
    )


def propose(ws: str, description: str) -> dict[str, Any]:
    raw_yaml: str
    source = "llm"
    try:
        from ..llm.structured import generate_text

        text, _meta = generate_text(_prompt(description), role="workflows.propose", cache=False)
        raw_yaml = text.strip()
        if raw_yaml.startswith("```"):
            raw_yaml = raw_yaml.strip("`")
            if raw_yaml.lower().startswith("yaml"):
                raw_yaml = raw_yaml[4:]
        raw_yaml = raw_yaml.strip()
    except Exception as e:  # noqa: BLE001 - any LLM failure falls back to the offline path
        logger.info("workflows.propose: LLM unavailable (%s), using keyword fallback", e)
        raw_yaml = _keyword_fallback(description)
        source = "offline-fallback"

    wf, errors, warnings = validate_yaml(raw_yaml)
    if wf is None and source == "llm":
        # give the offline fallback a chance before giving up entirely
        raw_yaml = _keyword_fallback(description)
        source = "offline-fallback"
        wf, errors, warnings = validate_yaml(raw_yaml)

    return {
        "workspace": ws,
        "source": source,
        "yaml": raw_yaml,
        "valid": wf is not None,
        "errors": errors,
        "warnings": warnings,
    }
