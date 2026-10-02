# corpus

Law/guidance material Aurum ingests, searches, and cites against: SQLite FTS5 + embeddings + hybrid
RRF search + cite-or-abstain, shared with the author's learning-tutor project (https://github.com/jadrianlg16/learning-tutor) and
adapted to Aurum's law-citation use case. No vector service — everything lives in one SQLite database. This module is where the
"grounded or silent" principle (cite or abstain; corpus text is data, never instructions) is enforced;
see [ARCHITECTURE.md](../ARCHITECTURE.md#principles).

## Purpose

- Ingest MX/US statute PDFs, RMF (Resolución Miscelánea Fiscal) rules, SAT guidance, and other
  reference material into a searchable, citable store, grouped by a free-form `collection_id`
  (e.g. `"mx-law"`, `"us-law"`, `"guidance"` — not a closed enum).
- Answer "does the corpus support this claim?" with a citation or an explicit abstention —
  never a decorative citation for an unsupported claim.
- Guarantee that ingested document text can never act as an instruction to a model, no matter
  what it says.

## Files

| File | Responsibility |
|---|---|
| `store.py` | SQLite connection, WAL, forward-only migrations, row helpers. DB path: `settings().corpus_db_path`. |
| `schema.sql` | Migration 1: `sources`, `chunks`, `chunks_fts` (FTS5 + triggers), `embeddings`, `structure`. |
| `schema_v2.sql` | Migration 2: `sources.supersedes` (as-of versioning) + `corpus_refs` (the cross-reference graph). |
| `ingest.py` | Format extractors (pdf/md/txt/html), chunking, the article/RMF-rule splitter, embedding on write, `supersedes` auto-detection, `corpus_refs` population. |
| `refs.py` | `detect_refs()` — regex cross-reference detection at ingest; `cites`/`cited_by`/`related_for` — the graph queries behind `GET /api/research/refs` and a citation's `related`. |
| `sanitize.py` | `scan()` flags instruction-like text at ingest; `render_for_context()` is the only supported way to put corpus text in a prompt. |
| `embed.py` | Ollama embeddings, or the offline hash fallback (`AURUM_EMBED_MODEL=hash`). |
| `search.py` | Hybrid search: FTS5 bm25 + cosine, fused with Reciprocal Rank Fusion (RRF); `as_of` filtering. |
| `cite.py` | `cite_or_abstain()` — cite the corpus for a claim, or abstain with a reason; `as_of`; attaches `related` when a store is given. |
| `sources_md.py` | Per-collection `sources.md` (trusted/banned sources, jurisdiction, priority) — a legitimate user-authored instruction file, never mixed with ingested document text. |

Deliberately not part of this module:

- **Source roles** — Aurum grades citations by `trust_tier` instead (see
  `aurum.core.explain.Citation`).
- **Research workflow** — question answering lives in a separate module (`aurum/research`), which
  also exposes the HTTP endpoints.
- **A router** — this module has no FastAPI router of its own; `aurum/research` and other modules call
  these functions directly.

## Schema

`sources` — one row per ingested document. Carries `collection_id`, `kind`
(`pdf`/`md`/`txt`/`html`), and the citation defaults for its chunks: `jurisdiction`, `doc_type`,
`law`, `url`, `trust_tier`, `effective_from`, `effective_to`.

`chunks` — one row per ~400-token window (60-token overlap), never crossing a locator boundary
(a PDF page, an HTML/Markdown heading section, a paragraph). Carries `article` and `section`,
tagged per-chunk by the statute/RMF splitter (`ingest.detect_article`) — this is what lets a
search hit become an `aurum.core.explain.Citation` with **no extra lookup**: join `chunks` to
its `sources` row and every `Citation` field is already there (`law`, `article`, `url`,
`effective_from`, `effective_to`, `trust_tier`, and the best-supporting sentence as `excerpt`).

`chunks_fts` — an external-content FTS5 virtual table over `chunks.text`, kept in sync by
`AFTER INSERT/UPDATE/DELETE` triggers.

`embeddings` — `(chunk_id, model) -> float32 vector blob`, L2-normalised at write time so cosine
similarity is a plain dot product at read time.

`structure` — the document's own outline (headings/pages), for a future sources browser UI.

`sources.supersedes` (migration 2) — the `source_id` of the version this source replaces, same
`collection_id`/`url`. `corpus_refs` (migration 2) — one row per cross-reference mention
detected in a chunk's text: `ref_id`, `source_chunk_id`, `law`, `article`, `kind` (always
`"cites"` today). See `refs.py` above.

## Key functions

```python
from aurum.corpus.store import open_store
from aurum.corpus import ingest, cite
from aurum.corpus.search import search

store = open_store()

ingest.ingest_file(
    store, "mx-law", "/path/to/lisr.pdf",
    law="LISR", jurisdiction="mx", doc_type="statute",
    url="https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf",
    trust_tier="primary",
)

results = search(store, "mx-law", "retención por plataformas tecnológicas", k=5)

answer = cite.cite_or_abstain(
    store, "las plataformas deben retener ISR mensualmente", "mx-law"
)
# {"status": "cited", "citations": [{"law": "LISR", "article": "Artículo 113-E.", ...}]}
# or {"status": "abstain", "reason": "..."}
```

### The article / RMF-rule splitter

`ingest.detect_article(text)` looks at the first ~120 characters of a chunk (so a chunk that
merely *mentions* another article in passing is not mistagged) for:

- a Mexican statute heading — `Art[ií]culo\s+\d+[A-Za-z\-]*\.?` (e.g. `Artículo 113-E.`)
- an RMF rule number — `\d+\.\d+\.\d+\.\d+` (e.g. `2.7.2.4.`)

It is deliberately simple: a regex heading detector, not a legal parser. When a chunk opens
with neither, `article` is empty and the citation falls back to the source's `law` label alone.
A third pattern, `_US_SECTION_RE`, catches US-side headings a chunk opens with: `§ 1402`,
`Section 1402`, `Sec. 1402`, `Chapter 151` (IRC/Treas. Reg. sections, Texas Tax Code chapters).

### As-of versioning: `supersedes` and `search(..., as_of=)`

`sources.supersedes` (migration 2, `schema_v2.sql`) links a newly-ingested version of the same
law/guidance page to the version it replaces. `ingest.ingest_file`/`ingest_text` auto-detect it:
when the caller passes a `url` and no explicit `supersedes`, the most recent source in that
collection at the same `url` (with different bytes) becomes the new source's `supersedes` —
`aurum.corpus.store.latest_source_by_url` / `source_chain`. An explicit `supersedes=` always
wins over auto-detection.

`search(store, collection_id, query, as_of="2026-01-01")` filters candidates to chunks whose
source's `effective_from`/`effective_to` covers that ISO date (`_within_as_of` in `search.py`;
open bounds are always in force). `cite.cite_or_abstain(..., as_of=...)` and
`POST /api/research/ask`'s `as_of` field both thread through to this. Comparison is plain ISO
string comparison (`"2026-01-01" > "2025-12-31"`), not `datetime` parsing — ISO dates already
sort correctly as strings.

### The cross-reference graph: `refs.py` and `corpus_refs`

`refs.detect_refs(text, default_law=...)` regex-scans a chunk's text for mentions of other
articles/rules — MX law-qualified (`LIVA art. 5`), MX bare (`Artículo 27` falls back to
`default_law`, the ingesting source's own `law`), MX fracción qualifiers (`artículo 27,
fracción III`), RMF rule numbers (`regla 2.7.2.4.`), and US (`26 U.S.C. § 1402`, `IRC § 911`,
`Treas. Reg. § 1.1402(a)-1`). `ingest._write_source` runs it on every chunk at ingest time and
writes one `corpus_refs` row per distinct mention.

`refs.cites(store, law, article)` / `refs.cited_by(store, law, article)` answer "what does this
article mention" / "what mentions this article" by joining `corpus_refs` back to the chunk it
was found in. Comparison is normalized (lowercase, alphanumeric-only, substring containment
either direction) rather than exact string equality — `chunks.article` carries the full heading
a chunk opens with (`"Artículo 29."`, from `detect_article`) while `corpus_refs.article` carries
the bare number a *mention* resolved to (`"29"`); an exact match would never link the two.
`refs.related_for(store, law, article)` is the deduplicated, self-excluding short list used for
a citation's `related` field. `cite.to_citation(chunk, claim, store=...)` attaches it when a
store is given; `GET /api/research/refs?law=&article=` exposes `cites`/`cited_by` directly.

### Offline embeddings

`AURUM_EMBED_MODEL=hash` (the literal string `"hash"`, checked by
`embed.is_offline_backend()`) switches to a deterministic hashed-bag-of-words embedding —
signed hashing into `AURUM_EMBED_DIM` (default 256) dimensions, sub-linear term weighting,
L2-normalised. No network, no dependency beyond the standard library. Every test in
`tests/corpus/` runs with this backend (`tests/corpus/conftest.py`). Any other value (default
`nomic-embed-text`, from `settings().embed_model`) calls Ollama at `settings().ollama_url`.

### Sanitize: corpus text is data, never instructions

`sanitize.scan(text)` is a high-recall, low-precision line/segment classifier: it flags text
that reads like an instruction to a model (`"ignore previous instructions"`, role-override
phrasing, tool-call syntax, exfiltration attempts, etc.). A flag never edits or drops stored
text — it only changes how the segment is rendered. `sanitize.render_for_context(chunks)` is
the *only* supported way to put retrieved chunks in front of a model: every chunk is wrapped in
a `<<<SOURCE ...>>>` / `<<<END SOURCE>>>` block under a fixed preamble stating the content is
quoted data, and every flagged segment is additionally rewritten as
`[QUOTED INSTRUCTION-LIKE TEXT ...]` so it reads as a quotation, not a directive.

## Env vars

| Var | Default | Meaning |
|---|---|---|
| `AURUM_DATA_DIR` | `./data` | Corpus db lives at `<data_dir>/corpus.db`; uploaded sources at `<data_dir>/corpus_sources/<collection_id>/`. |
| `AURUM_EMBED_MODEL` | `nomic-embed-text` | Set to `hash` for the offline fallback. |
| `AURUM_EMBED_DIM` | `256` | Dimension of the offline hash embedding (ignored for Ollama). |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama base URL when not using the hash backend. |
| `AURUM_CITE_MIN_SCORE` | `0.5` | `cite_or_abstain`'s support threshold (fraction of the claim's content words that must appear in the cited chunk). |

## Worked example: ingesting an LISR/LIVA/RMF PDF

```python
from aurum.core.config import settings
from aurum.corpus.store import open_store
from aurum.corpus.ingest import ingest_file
from aurum.corpus.cite import cite_or_abstain

store = open_store()

# 1. Ingest a statute PDF into the "mx-law" collection, tagging it with citation defaults.
result = ingest_file(
    store,
    "mx-law",
    "lisr-2026.pdf",  # resolved under AURUM_DATA_DIR/corpus_sources/mx-law/ if relative
    law="LISR",
    jurisdiction="mx",
    doc_type="statute",
    url="https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf",
    trust_tier="primary",
    effective_from="2026-01-01",
)
# {"status": "ingested", "chunks": 340, "articles_tagged": 118, "embedded": 340, ...}

# 2. Ingest an RMF rule as plain text (no PDF needed for a short rule).
from aurum.corpus.ingest import ingest_text
ingest_text(
    store, "mx-law",
    "2.7.2.4. Para los efectos del artículo 29 del CFF, ...",
    title="RMF 2026 regla 2.7.2.4",
    kind="txt",
    law="RMF",
    jurisdiction="mx",
    trust_tier="official_guidance",
)

# 3. Cite or abstain for a claim the rest of Aurum wants to assert.
answer = cite_or_abstain(
    store,
    "los ingresos por plataformas tecnológicas se retienen mensualmente",
    "mx-law",
)
if answer["status"] == "cited":
    citation = answer["citations"][0]
    # citation maps directly onto aurum.core.explain.Citation:
    # {"law": "LISR", "article": "Artículo 113-E.", "url": "...", "trust_tier": "primary",
    #  "effective_from": "2026-01-01", "excerpt": "..."}
else:
    print("abstained:", answer["reason"])
```

## Supported ingest formats

Only `pdf` (via PyMuPDF, already an aurum dependency), `txt`, `md`, and `html`. `.docx` and
`.pptx` raise `NotImplementedError` naming the missing dependency (`python-docx` /
`python-pptx` are not installed in this repo) rather than failing silently or half-parsing a
zip file as text.
