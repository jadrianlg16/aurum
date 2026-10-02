"""Ingest: document -> blocks -> chunks -> FTS + embeddings + structure.

Adapted from the ingest module shared with
the author's learning-tutor project (https://github.com/jadrianlg16/learning-tutor), trimmed to what Aurum needs and can run:

* Supported formats: **pdf** (via PyMuPDF, already an aurum dependency), **txt**, **md**,
  **html**. ``python-docx`` and ``python-pptx`` are not installed in this repo, so ``.docx``
  and ``.pptx`` raise :class:`NotImplementedError` with a clear message instead of silently
  failing or half-parsing a zip file as text.
* Material is grouped by ``collection_id``, a free-form string (``"mx-law"``, ``"us-law"``,
  ``"guidance"``, ...), not a closed enum.
* :func:`detect_article` tags each chunk with a Mexican statute heading
  (``Artículo 113-E.``) or an RMF rule number (``2.7.2.4.``) when the chunk's text contains
  one near its start, so search results can be turned into an ``aurum.core.explain.Citation``
  without any extra lookup.

Extraction is per-format and always produces the same two things:

* **blocks** -- ``(locator, text)`` pairs at the format's natural granularity: a PDF page, an
  HTML/Markdown section under one heading, a paragraph of plain text.
* **structure** -- the document's own outline (headings / pages).

Chunking never crosses a locator boundary: blocks are grouped by *identical* locator, then
windowed at ~400 tokens with 60 tokens of overlap. That keeps "page 14" or "Artículo 113-E"
citable at that granularity.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import uuid
from pathlib import Path
from typing import Any

from . import embed as embed_mod
from . import refs as refs_mod
from . import sanitize
from .store import (
    CorpusError,
    CorpusStore,
    collection_sources_dir,
    get_source,
    latest_source_by_url,
    source_by_sha,
    utcnow,
)

TARGET_TOKENS = 400
OVERLAP_TOKENS = 60

#: A PDF page with less text than this is almost certainly a scan or an equation image.
NEEDS_OCR_CHARS = 20

SUPPORTED_KINDS = ("pdf", "md", "txt", "html")

EXT_KIND = {
    ".pdf": "pdf",
    ".md": "md",
    ".markdown": "md",
    ".txt": "txt",
    ".text": "txt",
    ".html": "html",
    ".htm": "html",
}

#: Extensions we deliberately do not support, and why -- so a bad upload fails loudly
#: instead of crashing on a zip file mis-read as text.
UNSUPPORTED_EXT = {
    ".docx": "python-docx is not installed in this repo; DOCX ingest is not available",
    ".pptx": "python-pptx is not installed in this repo; PPTX ingest is not available",
}

Block = tuple[dict[str, Any], str]
Outline = list[dict[str, Any]]


# --- ids and hashes ------------------------------------------------------


def _sid() -> str:
    return f"s_{uuid.uuid4().hex[:12]}"


def _cid(source_id: str, ordinal: int) -> str:
    return f"c_{source_id[2:]}_{ordinal:05d}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def kind_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in UNSUPPORTED_EXT:
        raise NotImplementedError(
            f"{suffix} ingest is not supported: {UNSUPPORTED_EXT[suffix]}. "
            f"Supported kinds: {', '.join(SUPPORTED_KINDS)}."
        )
    kind = EXT_KIND.get(suffix)
    if not kind:
        raise CorpusError(
            f"unsupported file type {suffix!r}; supported: {', '.join(SUPPORTED_KINDS)}"
        )
    return kind


def check_kind(kind: str) -> str:
    if kind not in SUPPORTED_KINDS:
        raise CorpusError(
            f"unknown source kind {kind!r}; expected one of {', '.join(SUPPORTED_KINDS)}"
        )
    return kind


# --- the article / rule-number splitter -----------------------------------

#: Mexican statute headings, e.g. "Artículo 113-E." or "Articulo 27".
_ARTICLE_RE = re.compile(r"Art[ií]culo\s+\d+[A-Za-z\-]*\.?", re.IGNORECASE)

#: RMF (Resolución Miscelánea Fiscal) rule numbers, e.g. "2.7.2.4."
_RMF_RULE_RE = re.compile(r"\b\d+\.\d+\.\d+\.\d+\.?")

#: US-side headings: "§ 1402", "Section 1402", "Sec. 1402", "Chapter 151" — IRC/Treas. Reg.
#: sections and Texas Tax Code chapters all use one of these forms at the head of a section.
_US_SECTION_RE = re.compile(
    r"(?:§\s?[\d.()a-zA-Z\-]+|\bSec(?:tion|\.)?\s+\d+[A-Za-z]*|\bChapter\s+\d+[A-Za-z]*)",
    re.IGNORECASE,
)

#: Only look for a heading near the start of the chunk -- a mid-chunk cross-reference to
#: another article ("see Artículo 27") should not steal the tag.
_HEAD_WINDOW = 120


def detect_article(text: str) -> str | None:
    """Tag a chunk with the statute article or RMF rule number it opens with, if any.

    Simple and regex-based on purpose (see docs/modules/corpus.md): this is a heading
    detector, not a legal parser. It looks only at the first ``_HEAD_WINDOW`` characters so
    a chunk that merely *mentions* another article in passing is not mistagged.
    """

    head = (text or "")[:_HEAD_WINDOW]
    candidates: list[tuple[int, str]] = []
    match = _ARTICLE_RE.search(head)
    if match:
        candidates.append((match.start(), " ".join(match.group(0).split())))
    match = _RMF_RULE_RE.search(head)
    if match:
        candidates.append((match.start(), match.group(0)))
    match = _US_SECTION_RE.search(head)
    if match:
        candidates.append((match.start(), " ".join(match.group(0).split())))
    if not candidates:
        return None
    # Whichever heading the chunk actually opens with wins over one mentioned later
    # (e.g. RMF text that cites "artículo 29 del CFF" in passing after its own rule number).
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


# --- chunking ------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    return sanitize.estimate_tokens(text)


def _window_words(words: list[str], target: int, overlap: int) -> list[list[str]]:
    """Fixed-size word windows with overlap. Word count ~= tokens / 1.3."""

    size = max(1, int(target / 1.3))
    step = max(1, size - int(overlap / 1.3))
    if len(words) <= size:
        return [words]
    windows: list[list[str]] = []
    start = 0
    while start < len(words):
        windows.append(words[start : start + size])
        if start + size >= len(words):
            break
        start += step
    return windows


def chunk_blocks(
    blocks: list[Block],
    *,
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[dict[str, Any]]:
    """Blocks -> chunks. Consecutive blocks merge only when their locators are identical."""

    groups: list[tuple[dict[str, Any], list[str]]] = []
    for locator, text in blocks:
        text = (text or "").strip()
        if not text:
            continue
        key = json.dumps(locator, sort_keys=True)
        if groups and json.dumps(groups[-1][0], sort_keys=True) == key:
            groups[-1][1].append(text)
        else:
            groups.append((locator, [text]))

    chunks: list[dict[str, Any]] = []
    for locator, parts in groups:
        joined = "\n".join(parts)
        for window in _window_words(joined.split(), target_tokens, overlap_tokens):
            piece = " ".join(window).strip()
            if not piece:
                continue
            chunks.append(
                {
                    "locator": locator,
                    "text": piece,
                    "tokens_est": estimate_tokens(piece),
                    "article": detect_article(piece) or "",
                }
            )
    return chunks


# --- extractors ----------------------------------------------------------


def extract_pdf(path: Path) -> tuple[list[Block], Outline, dict[str, Any]]:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - pymupdf is an aurum dependency
        raise CorpusError("PDF ingest needs PyMuPDF (pip install pymupdf)") from exc

    blocks: list[Block] = []
    outline: Outline = []
    needs_ocr: list[int] = []
    with fitz.open(path) as doc:
        for entry in doc.get_toc() or []:
            level, title, page = entry[0], entry[1], entry[2]
            outline.append(
                {
                    "level": max(1, int(level)),
                    "title": str(title).strip(),
                    "locator": {"page": int(page)},
                }
            )
        for index, page in enumerate(doc, start=1):
            text = (page.get_text() or "").strip()
            if len(text) < NEEDS_OCR_CHARS:
                needs_ocr.append(index)
                if not text:
                    continue
            blocks.append(({"page": index}, text))
        page_count = doc.page_count

    if not outline:
        # No embedded TOC: the page sequence is the only outline the document offers.
        outline = [
            {"level": 1, "title": f"Page {locator['page']}", "locator": locator}
            for locator, _ in blocks
        ]
    meta: dict[str, Any] = {"pages": page_count}
    if needs_ocr:
        meta["needs_ocr"] = True
        meta["needs_ocr_pages"] = needs_ocr
    return blocks, outline, meta


_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def extract_markdown(text: str, *, title: str) -> tuple[list[Block], Outline, dict[str, Any]]:
    blocks: list[Block] = []
    outline: Outline = []
    current = "(document)"
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            blocks.append(({"heading": current}, body))
        buffer.clear()

    for line in text.splitlines():
        match = _MD_HEADING.match(line)
        if match:
            flush()
            current = match.group(2).strip()
            outline.append(
                {"level": len(match.group(1)), "title": current, "locator": {"heading": current}}
            )
        else:
            buffer.append(line)
    flush()
    if not outline:
        outline = [{"level": 1, "title": title, "locator": {"heading": "(document)"}}]
    return blocks, outline, {"headings": len(outline)}


def extract_plaintext(text: str, *, title: str) -> tuple[list[Block], Outline, dict[str, Any]]:
    """TXT with no heading syntax: paragraphs are the locator granularity."""

    if _MD_HEADING.search(text):
        return extract_markdown(text, title=title)
    blocks: list[Block] = []
    for index, para in enumerate(re.split(r"\n\s*\n", text), start=1):
        body = para.strip()
        if body:
            blocks.append(({"para": index}, body))
    outline = [{"level": 1, "title": title, "locator": {"heading": "(document)"}}]
    return blocks, outline, {"paragraphs": len(blocks)}


#: Tags whose content should never reach the corpus (scripts/styles), stripped wholesale.
_HTML_STRIP_TAGS = re.compile(r"(?is)<(script|style|noscript)\b.*?</\1>")
_HTML_HEADING_TAG = re.compile(r"(?is)<h([1-6])\b[^>]*>(.*?)</h\1>")
_HTML_BLOCK_BREAK = re.compile(r"(?is)</?(?:p|div|br|li|tr|section|article)\b[^>]*>")
_HTML_TAG = re.compile(r"(?s)<[^>]+>")
_WS = re.compile(r"[ \t]+")


def _html_to_text(fragment: str) -> str:
    text = _HTML_BLOCK_BREAK.sub("\n", fragment)
    text = _HTML_TAG.sub(" ", text)
    text = html_lib.unescape(text)
    text = _WS.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def extract_html(text: str, *, title: str) -> tuple[list[Block], Outline, dict[str, Any]]:
    """A dependency-free HTML extractor: headings become sections, the rest is stripped tags.

    Deliberately simple (regex-based, stdlib ``html.unescape`` for entities) rather than
    pulling in a parser dependency this repo does not already have.
    """

    cleaned = _HTML_STRIP_TAGS.sub("", text)
    matches = list(_HTML_HEADING_TAG.finditer(cleaned))
    blocks: list[Block] = []
    outline: Outline = []

    if not matches:
        body = _html_to_text(cleaned)
        if body:
            blocks.append(({"heading": "(document)"}, body))
        outline = [{"level": 1, "title": title, "locator": {"heading": "(document)"}}]
        return blocks, outline, {"headings": 0}

    # Anything before the first heading is its own leading section.
    lead = _html_to_text(cleaned[: matches[0].start()])
    if lead:
        blocks.append(({"heading": "(document)"}, lead))

    for index, match in enumerate(matches):
        level = int(match.group(1))
        heading_text = _html_to_text(match.group(2)) or f"Section {index + 1}"
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        body = _html_to_text(cleaned[start:end])
        outline.append({"level": level, "title": heading_text, "locator": {"heading": heading_text}})
        if body:
            blocks.append(({"heading": heading_text}, body))

    return blocks, outline, {"headings": len(matches)}


# --- writing -------------------------------------------------------------


def _write_source(
    store: CorpusStore,
    *,
    collection_id: str,
    kind: str,
    title: str,
    path_or_url: str,
    sha256: str,
    meta: dict[str, Any],
    blocks: list[Block],
    outline: Outline,
    embed_model: str | None,
    jurisdiction: str,
    doc_type: str,
    law: str,
    url: str,
    trust_tier: str,
    effective_from: str | None,
    effective_to: str | None,
    supersedes: str | None = None,
) -> dict[str, Any]:
    source_id = _sid()
    chunks = chunk_blocks(blocks)
    flagged = 0
    articles_tagged = 0
    refs_found = 0

    store.execute("BEGIN")
    try:
        store.insert(
            "sources",
            {
                "source_id": source_id,
                "collection_id": collection_id,
                "kind": kind,
                "title": title,
                "path_or_url": path_or_url,
                "sha256": sha256,
                "ingested_at": utcnow(),
                "jurisdiction": jurisdiction,
                "doc_type": doc_type,
                "law": law,
                "url": url,
                "trust_tier": trust_tier,
                "effective_from": effective_from,
                "effective_to": effective_to,
                "meta": json.dumps(meta, ensure_ascii=False),
                "supersedes": supersedes,
            },
        )
        for ordinal, entry in enumerate(outline):
            store.insert(
                "structure",
                {
                    "source_id": source_id,
                    "ordinal": ordinal,
                    "level": int(entry.get("level") or 1),
                    "title": str(entry.get("title") or ""),
                    "locator": json.dumps(entry.get("locator") or {}, sort_keys=True),
                },
            )
        for ordinal, chunk in enumerate(chunks):
            findings = sanitize.scan(chunk["text"])
            if findings:
                flagged += 1
            if chunk.get("article"):
                articles_tagged += 1
            chunk["chunk_id"] = _cid(source_id, ordinal)
            store.insert(
                "chunks",
                {
                    "chunk_id": chunk["chunk_id"],
                    "source_id": source_id,
                    "ordinal": ordinal,
                    "locator": json.dumps(chunk["locator"], sort_keys=True),
                    "text": chunk["text"],
                    "tokens_est": chunk["tokens_est"],
                    "flags": json.dumps(findings, ensure_ascii=False),
                    "article": chunk.get("article") or "",
                    "section": "",
                },
            )
            for ref in refs_mod.detect_refs(chunk["text"], default_law=law):
                refs_found += 1
                store.insert(
                    "corpus_refs",
                    {
                        "ref_id": f"r_{chunk['chunk_id'][2:]}_{refs_found:03d}",
                        "source_chunk_id": chunk["chunk_id"],
                        "law": ref["law"],
                        "article": ref["article"],
                        "kind": ref["kind"],
                    },
                )
        store.execute("COMMIT")
    except Exception:
        store.execute("ROLLBACK")
        raise

    embedded, embed_error = embed_source(store, source_id, model=embed_model)
    result = {
        "status": "ingested",
        "source_id": source_id,
        "collection_id": collection_id,
        "kind": kind,
        "title": title,
        "sha256": sha256,
        "chunks": len(chunks),
        "structure": len(outline),
        "flagged_chunks": flagged,
        "articles_tagged": articles_tagged,
        "refs_found": refs_found,
        "embedded": embedded,
        "meta": meta,
    }
    if embed_error:
        result["embed_error"] = embed_error
    return result


def embed_source(
    store: CorpusStore, source_id: str, *, model: str | None = None
) -> tuple[int, str | None]:
    """Embed every chunk of a source. A failure degrades search to FTS, never blocks ingest."""

    model = model or embed_mod.model_name()
    rows = store.query(
        "SELECT chunk_id, text FROM chunks WHERE source_id = ? ORDER BY ordinal",
        (source_id,),
    )
    if not rows:
        return 0, None
    texts = [str(row["text"]) for row in rows]
    try:
        vectors = embed_mod.embed_texts(texts, model=model)
    except embed_mod.EmbeddingError as exc:
        return 0, str(exc)

    store.execute("BEGIN")
    try:
        for row, vector in zip(rows, vectors, strict=False):
            store.execute(
                "INSERT OR REPLACE INTO embeddings(chunk_id, model, dim, vec) VALUES (?, ?, ?, ?)",
                (str(row["chunk_id"]), model, len(vector), embed_mod.to_blob(vector)),
            )
        store.execute("COMMIT")
    except Exception:
        store.execute("ROLLBACK")
        raise
    return len(rows), None


# --- public entry points -------------------------------------------------


def resolve_path(collection_id: str, path: str, cfg: Any = None) -> Path:
    """Accept an absolute path or one relative to ``AURUM_DATA_DIR/corpus_sources/<collection>/``.

    A relative path may not escape the collection's source directory.
    """

    base = collection_sources_dir(collection_id, cfg)
    base.mkdir(parents=True, exist_ok=True)
    base = base.resolve()
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (base / candidate).resolve()
        if base not in resolved.parents and resolved != base:
            raise CorpusError(f"path {path!r} escapes the collection source directory")
    if not resolved.exists():
        raise CorpusError(f"file not found: {resolved}")
    return resolved


def ingest_file(
    store: CorpusStore,
    collection_id: str,
    path: str | Path,
    *,
    kind: str | None = None,
    title: str | None = None,
    meta: dict[str, Any] | None = None,
    embed_model: str | None = None,
    jurisdiction: str = "",
    doc_type: str = "",
    law: str = "",
    url: str = "",
    trust_tier: str = "primary",
    effective_from: str | None = None,
    effective_to: str | None = None,
    supersedes: str | None = None,
) -> dict[str, Any]:
    resolved = path if isinstance(path, Path) else resolve_path(collection_id, str(path), store.settings)
    resolved = Path(resolved)
    if not resolved.exists():
        raise CorpusError(f"file not found: {resolved}")

    kind = check_kind(kind) if kind else kind_for(resolved)
    digest = sha256_file(resolved)
    existing = source_by_sha(store, collection_id, digest)
    if existing:
        return {
            "status": "duplicate",
            "source_id": existing["source_id"],
            "collection_id": collection_id,
            "kind": existing["kind"],
            "title": existing["title"],
            "sha256": digest,
            "reason": "a source with this sha256 is already ingested for this collection",
        }

    if kind == "pdf":
        blocks, outline, extra = extract_pdf(resolved)
    elif kind == "md":
        blocks, outline, extra = extract_markdown(
            resolved.read_text(encoding="utf-8", errors="replace"), title=resolved.stem
        )
    elif kind == "txt":
        blocks, outline, extra = extract_plaintext(
            resolved.read_text(encoding="utf-8", errors="replace"), title=resolved.stem
        )
    elif kind == "html":
        blocks, outline, extra = extract_html(
            resolved.read_text(encoding="utf-8", errors="replace"), title=resolved.stem
        )
    else:  # pragma: no cover - check_kind/kind_for already restrict this
        raise CorpusError(f"kind {kind!r} is not a supported file kind")

    merged = {**extra, **(meta or {}), "source_bytes": resolved.stat().st_size}
    if supersedes is None and url:
        prior = latest_source_by_url(store, collection_id, url, exclude_sha256=digest)
        supersedes = prior["source_id"] if prior else None
    return _write_source(
        store,
        collection_id=collection_id,
        kind=kind,
        title=title or resolved.stem,
        path_or_url=str(resolved),
        sha256=digest,
        meta=merged,
        blocks=blocks,
        outline=outline,
        embed_model=embed_model,
        jurisdiction=jurisdiction,
        doc_type=doc_type,
        law=law,
        url=url,
        trust_tier=trust_tier,
        effective_from=effective_from,
        effective_to=effective_to,
        supersedes=supersedes,
    )


def ingest_text(
    store: CorpusStore,
    collection_id: str,
    text: str,
    *,
    title: str,
    kind: str = "md",
    path_or_url: str = "",
    meta: dict[str, Any] | None = None,
    embed_model: str | None = None,
    jurisdiction: str = "",
    doc_type: str = "",
    law: str = "",
    url: str = "",
    trust_tier: str = "primary",
    effective_from: str | None = None,
    effective_to: str | None = None,
    supersedes: str | None = None,
) -> dict[str, Any]:
    """In-memory ingest. Used for programmatic loads and by tests."""

    check_kind(kind if kind != "html" else "html")
    digest = sha256_text(text)
    existing = source_by_sha(store, collection_id, digest)
    if existing:
        return {
            "status": "duplicate",
            "source_id": existing["source_id"],
            "collection_id": collection_id,
            "kind": existing["kind"],
            "title": existing["title"],
            "sha256": digest,
            "reason": "a source with this sha256 is already ingested for this collection",
        }
    if kind == "md":
        blocks, outline, extra = extract_markdown(text, title=title)
    elif kind == "html":
        blocks, outline, extra = extract_html(text, title=title)
    else:
        blocks, outline, extra = extract_plaintext(text, title=title)
    if supersedes is None and url:
        prior = latest_source_by_url(store, collection_id, url, exclude_sha256=digest)
        supersedes = prior["source_id"] if prior else None
    return _write_source(
        store,
        collection_id=collection_id,
        kind=kind,
        title=title,
        path_or_url=path_or_url or f"memory:{digest[:12]}",
        sha256=digest,
        meta={**extra, **(meta or {})},
        blocks=blocks,
        outline=outline,
        embed_model=embed_model,
        jurisdiction=jurisdiction,
        doc_type=doc_type,
        law=law,
        url=url,
        trust_tier=trust_tier,
        effective_from=effective_from,
        effective_to=effective_to,
        supersedes=supersedes,
    )


def reindex_source(
    store: CorpusStore, source_id: str, *, model: str | None = None
) -> dict[str, Any]:
    source = get_source(store, source_id)
    if not source:
        raise CorpusError(f"unknown source {source_id!r}")
    embedded, error = embed_source(store, source_id, model=model)
    out = {"source_id": source_id, "embedded": embedded}
    if error:
        out["embed_error"] = error
    return out
