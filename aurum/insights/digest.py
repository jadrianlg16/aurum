"""Digest text for Telegram/email: a deterministic bullet list, optionally rewritten into one paragraph
by the LLM (never inventing figures -- the model only rephrases the deterministic text already
produced by :mod:`aurum.insights.engine`). Falls back to the deterministic text on ANY provider error,
exactly like :func:`aurum.updater.triage.summarize`, so a digest never blocks on a model being down.
"""

from __future__ import annotations

from .engine import Insight
from .i18n import t

_SEVERITY_MARK = {"urgent": "!!", "warn": "!", "info": "-"}


def deterministic_text(ws_id: str, period: str, insights: list[Insight], lang: str | None = None) -> str:
    if not insights:
        return t("insights.digest.none", lang, period=period)
    counts = {"urgent": 0, "warn": 0, "info": 0}
    for i in insights:
        counts[i.severity] = counts.get(i.severity, 0) + 1
    lines = [
        t("insights.digest.title", lang) + f" ({ws_id}, {period})",
        t("insights.digest.urgent_count", lang, count=counts["urgent"], warn=counts["warn"], info=counts["info"]),
        "",
    ]
    for i in insights:
        mark = _SEVERITY_MARK.get(i.severity, "-")
        due = f" ({i.due_date})" if i.due_date else ""
        lines.append(f"{mark} {i.title}{due}: {i.body}")
    return "\n".join(lines)


def digest_text(ws_id: str, period: str, insights: list[Insight], lang: str | None = None, use_llm: bool = True) -> str:
    """The deterministic digest, optionally polished by the LLM. Always safe to call offline."""
    base = deterministic_text(ws_id, period, insights, lang)
    if not use_llm or not insights:
        return base
    try:
        from ..llm.exceptions import CloudNotAllowed
        from ..llm.structured import generate_text

        lang_name = "Spanish" if (lang or "es").startswith("es") else "English"
        prompt = (
            f"Rewrite the following list of personal-finance notifications as one short, warm paragraph "
            f"in {lang_name}, for a Telegram message. Keep every number and date exactly as given -- do "
            f"not invent or change any figure. Keep it under 80 words.\n\n{base}"
        )
        text, _meta = generate_text(prompt, role="insights_digest", contains_raw_documents=False)
        text = text.strip()
        return text or base
    except (CloudNotAllowed, ImportError, ConnectionError, TimeoutError, OSError, ValueError):
        return base
    except Exception:  # noqa: BLE001 -- a digest must never fail because the LLM stack hiccuped
        return base
