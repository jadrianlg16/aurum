"""The light cross-reference graph: regex-detected mentions of one article/rule in another.

Built once per chunk at ingest time (see ``ingest._write_source``), stored in
``corpus_refs`` (schema_v2.sql). This is a keyword/regex pass, not a legal citation
parser — good enough to answer "what else in the corpus talks about article X" for a
research citation card's ``related`` list and ``GET /api/research/refs``, not to build a
complete statutory cross-reference index.

Patterns:

* MX, law-qualified: ``LISR art. 27``, ``LIVA artículo 5``, ``CFF Art 30-B`` -> law + article.
* MX, bare statute heading: ``Artículo 113-E`` (no law prefix) -> falls back to the chunk's
  own source ``law`` default, since a bare "Artículo N" inside e.g. an LISR document means
  "this law's article N" (this also catches ``ingest.detect_article``'s own heading tag —
  a chunk always at least refers to itself).
* MX, fracción qualifier: ``artículo 27, fracción III`` -> article ``"27 fracción III"``.
* MX, RMF rule number: ``regla 2.7.2.4.`` -> law ``RMF``.
* US: ``26 U.S.C. § 1402``, ``IRC § 911``, ``Treas. Reg. § 1.1402(a)-1``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .store import CorpusStore

#: "LISR art. 27", "LIVA artículo 5", "CFF Art. 30-B" -- law name immediately followed by
#: "art."/"artículo" and a number (with optional letter/dash suffix, e.g. "113-E").
_MX_LAW_ARTICLE = re.compile(
    r"\b(LISR|LIVA|CFF|LIF|LFPIORPI)\s+art(?:[íi]culo|\.)?\s*(\d+[A-Za-z\-]*)",
    re.IGNORECASE,
)

#: Bare "Artículo 113-E" / "Articulo 27" with no law prefix -- caller supplies the fallback law.
_MX_BARE_ARTICLE = re.compile(r"\bArt[ií]culo\s+(\d+[A-Za-z\-]*)\.?", re.IGNORECASE)

#: "artículo 27, fracción III" / "fraccion II" -- a qualifier appended to the article number
#: found immediately before it. Matched separately then merged onto the nearest preceding
#: article mention within a short window.
_MX_FRACCION = re.compile(r"fracci[oó]n\s+([IVXLC]+)", re.IGNORECASE)

#: RMF (Resolución Miscelánea Fiscal) rule numbers, e.g. "regla 2.7.2.4."
_MX_RMF_RULE = re.compile(r"\bregla\s+(\d+\.\d+\.\d+\.\d+)\.?", re.IGNORECASE)

#: US Code, e.g. "26 U.S.C. § 1402" or "26 USC 1402".
_US_CODE = re.compile(r"\b26\s*U\.?S\.?C\.?\s*(?:§|Sec(?:tion|\.)?)?\s*(\d+[A-Za-z]*)")

#: Internal Revenue Code shorthand, e.g. "IRC § 911" or "IRC section 1402".
_IRC = re.compile(r"\bIRC\s*(?:§|[Ss]ection|Sec\.)?\s*(\d+[A-Za-z]*)")

#: Treasury Regulations, e.g. "Treas. Reg. § 1.1402(a)-1".
_TREAS_REG = re.compile(r"\bTreas\.?\s*Reg(?:ulations?|\.)?\s*(?:§|Section)?\s*([\d][\d.()a-zA-Z\-]*)")

_FRACCION_WINDOW = 40  # chars between an article number and a following "fracción N"


def _merge_fracciones(
    text: str, hits: list[tuple[int, int, str, str]]
) -> list[tuple[int, str, str]]:
    """Append a nearby ", fracción N" onto the article mention immediately before it.

    ``hits`` carries each mention's ``(start, end, law, article)`` where ``end`` is the
    position right after the matched article text — the window for a following "fracción
    N" is searched from there, not recomputed from ``len(article)`` (which would be wrong
    whenever the raw matched text differs from the normalized ``article`` string).
    """

    out: list[tuple[int, str, str]] = []
    for start, end, law, article in hits:
        window = text[end : end + _FRACCION_WINDOW]
        match = _MX_FRACCION.search(window)
        if match and window[: match.start()].strip(" ,") == "":
            out.append((start, law, f"{article} fracción {match.group(1).upper()}"))
        else:
            out.append((start, law, article))
    return out


def detect_refs(text: str, *, default_law: str = "") -> list[dict[str, Any]]:
    """Every distinct (law, article) mention in ``text``. Order-stable, de-duplicated.

    ``default_law`` is the ingesting source's own ``law`` field, used as the fallback for a
    bare "Artículo N" mention that names no law of its own.
    """

    text = text or ""
    mx_hits: list[tuple[int, int, str, str]] = []

    for match in _MX_LAW_ARTICLE.finditer(text):
        mx_hits.append((match.start(), match.end(), match.group(1).upper(), match.group(2)))

    # Bare "Artículo N" only counts when it is not immediately preceded by a law name
    # already captured above (avoid double-counting "LISR artículo 27" as both a
    # law-qualified hit and a bare one).
    law_qualified_spans = {m.start() for m in _MX_LAW_ARTICLE.finditer(text)}
    for match in _MX_BARE_ARTICLE.finditer(text):
        # A bare match's span starts at "Artículo"; a law-qualified match's span starts at
        # the law name a few characters earlier, so require no law-qualified hit contains
        # this position.
        if any(0 <= match.start() - qspan < 30 for qspan in law_qualified_spans):
            continue
        mx_hits.append((match.start(), match.end(), (default_law or "").upper(), match.group(1)))

    hits = _merge_fracciones(text, mx_hits)

    for match in _MX_RMF_RULE.finditer(text):
        hits.append((match.start(), "RMF", match.group(1)))

    for match in _US_CODE.finditer(text):
        hits.append((match.start(), "26 U.S.C.", match.group(1)))

    for match in _IRC.finditer(text):
        hits.append((match.start(), "IRC", match.group(1)))

    for match in _TREAS_REG.finditer(text):
        hits.append((match.start(), "Treas. Reg.", match.group(1).rstrip(".")))

    hits.sort(key=lambda item: item[0])
    seen: set[tuple[str, str]] = set()
    refs: list[dict[str, Any]] = []
    for _start, law, article in hits:
        law = law.strip()
        article = article.strip().rstrip(".")
        if not law or not article:
            continue
        key = (law, article)
        if key in seen:
            continue
        seen.add(key)
        refs.append({"law": law, "article": article, "kind": "cites"})
    return refs


# --- graph queries (GET /api/research/refs, citation `related`) -----------

#: Normalizes both sides of a (law, article) comparison: ``chunks.article`` carries the
#: full heading a chunk opens with (e.g. "Artículo 29.", from ``ingest.detect_article``),
#: while ``corpus_refs.article`` carries the bare number/rule a *mention* resolved to
#: (e.g. "29", from this module's own regexes) -- different formats for the same thing, so
#: an exact string match would silently never link. Comparing on the alphanumeric-only,
#: lowercased form makes "Artículo 29." and "29" (or "Chapter 151" and "151") equal.
_NORM = re.compile(r"[^a-z0-9]+")


def _norm(value: str) -> str:
    return _NORM.sub("", (value or "").lower())


def _article_matches(a: str, b: str) -> bool:
    """Substring containment either direction, e.g. "Artículo29" contains "29"."""

    a, b = _norm(a), _norm(b)
    return bool(a) and bool(b) and (a in b or b in a)


def _all_ref_edges(store: CorpusStore) -> list[dict[str, Any]]:
    """Every corpus_refs row joined to the (law, article) of the chunk it was found in."""

    rows = store.query(
        "SELECT r.law AS ref_law, r.article AS ref_article, r.kind AS kind, "
        "s.law AS chunk_law, c.article AS chunk_article "
        "FROM corpus_refs r "
        "JOIN chunks c ON c.chunk_id = r.source_chunk_id "
        "JOIN sources s ON s.source_id = c.source_id"
    )
    return [dict(row) for row in rows]


def cites(store: CorpusStore, law: str, article: str) -> list[dict[str, Any]]:
    """Every (law, article) that chunks belonging to ``law``/``article`` themselves mention."""

    target_law = _norm(law)
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for edge in _all_ref_edges(store):
        if _norm(edge["chunk_law"]) != target_law or not _article_matches(edge["chunk_article"], article):
            continue
        key = (edge["ref_law"], edge["ref_article"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"law": edge["ref_law"], "article": edge["ref_article"], "kind": edge["kind"]})
    out.sort(key=lambda item: (item["law"], item["article"]))
    return out


def cited_by(store: CorpusStore, law: str, article: str) -> list[dict[str, Any]]:
    """Every (law, article) whose chunks mention ``law``/``article`` -- the reverse edge."""

    target_law = _norm(law)
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for edge in _all_ref_edges(store):
        if not edge["chunk_article"]:
            continue
        if _norm(edge["ref_law"]) != target_law or not _article_matches(edge["ref_article"], article):
            continue
        key = (edge["chunk_law"], edge["chunk_article"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"law": edge["chunk_law"], "article": edge["chunk_article"], "kind": edge["kind"]})
    out.sort(key=lambda item: (item["law"], item["article"]))
    return out


def related_for(store: CorpusStore, law: str, article: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """A short, deduplicated ``related`` list for a citation card: cites + cited_by."""

    if not law or not article:
        return []
    combined = cites(store, law, article) + cited_by(store, law, article)
    self_key = (_norm(law), _norm(article))
    seen: set[tuple[str, str]] = {self_key}
    out: list[dict[str, Any]] = []
    for item in combined:
        key = (_norm(item["law"]), _norm(item["article"]))
        if key in seen:
            continue
        seen.add(key)
        out.append({"law": item["law"], "article": item["article"]})
        if len(out) >= limit:
            break
    return out
