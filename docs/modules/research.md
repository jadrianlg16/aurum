# research

Cited legal/tax research over `aurum.corpus`, mounted at `/api/research`. Implements the
"grounded or silent" principle ([ARCHITECTURE.md](../ARCHITECTURE.md#principles)) as an HTTP
endpoint: every answer is either backed by a primary/official-guidance citation or the endpoint
says so and abstains.

## Purpose

- `POST /ask` — pick the corpus collections for the requested jurisdiction, hybrid-search them,
  and either answer with citations or abstain with a reason. Accepts `as_of` (ISO date) to
  answer as of a point in time.
- `POST /ingest` — a thin wrapper over `aurum.corpus.ingest` for uploading a file or fetching a
  URL into a collection, with the metadata (`trust_tier`, `law`, `jurisdiction`, `doc_type`,
  `effective_from`) a citation needs.
- `GET /collections` — per-collection source/chunk counts, so the UI can show what is loaded.
- `GET /refs` — the light cross-reference graph for one `{law, article}`: what it cites and
  what cites it back.
- `POST /eval` — runs `evalset.yaml` against the corpus and scores precision@1 / abstain counts;
  see [research-eval.md](../research-eval.md) for the last recorded run.

## Files

| File | Responsibility |
|---|---|
| `router.py` | The endpoints above. |
| `eval.py` | `run_eval()` — scores `evalset.yaml` questions against the corpus (retrieval only, no LLM call). |
| `evalset.yaml` | ≥12 ES/EN questions with the expected `{law, article}`, one per synthetic law fixture in `tests/fixtures/law/`. |

## `POST /ask`

Request: `{"question": str, "jurisdiction": "MX"|"US"|"both", "lang": "es"|"en", "workspace": str|null, "as_of": str|null}`.

Response: `{"answer": str, "citations": [Citation-shaped dict], "confidence": float, "abstained": bool}`.
Each citation carries `related: [{law, article}]` (the cross-reference graph) alongside
the existing `effective_from`/`effective_to` — the version actually used for that answer.

`as_of` (ISO date, optional) restricts every collection search to chunks whose source's
`effective_from`/`effective_to` covers that date (`aurum.corpus.search.search(..., as_of=)`) —
asking "what did the law say as of 2025-06-01" answers (or abstains) using only law in force on
that date, not whatever is currently in the corpus.

Flow:

1. **Pick collections** — `COLLECTIONS_BY_JURISDICTION`: `MX` -> `["mx-law", "guidance"]`,
   `US` -> `["us-law", "guidance"]`, `both` -> all three.
2. **Hybrid search** each collection via `aurum.corpus.search.search` and merge the hits.
3. **Cite or abstain**: a hit only counts as "supported" once its `support` score (fraction of
   the question's content words present in the chunk — see `aurum.corpus.search.support`) is at
   or above `aurum.corpus.cite.min_score_default()` (`AURUM_CITE_MIN_SCORE`, default 0.5). Of the
   supported hits, only those whose `trust_tier` is `primary` or `official_guidance` can ground an
   asserted answer — a "professional"/"blog" hit alone is not enough, and the endpoint abstains
   even though *something* matched.
4. **Answer text**: when there is at least one trusted, supported citation, the endpoint tries
   `aurum.llm.structured.generate_text` with a citation-required, language-specific prompt
   (`contains_raw_documents=False` — statutes and official guidance are public, not the user's
   private documents). On **any** provider error (`CloudNotAllowed`, an `httpx` error, a
   connection/timeout error, or a bad response) it falls back to an **extractive** answer: a
   plain bullet list quoting each citation's excerpt, with no generation step at all. This is
   what makes the endpoint work with no LLM running (see the offline test fixtures, which point
   `OLLAMA_URL` at a closed port on purpose).
5. Every answer, generated or extractive, gets a not-advice line appended
   (`NOT_ADVICE["es"|"en"]`): verify with a licensed Contador/CPA.
6. `aurum.core.audit.record(workspace, "research.ask", ...)` is always called, whether or not the
   endpoint abstained.

## `POST /ingest`

One route handles both request shapes (file upload and URL) by checking the
`Content-Type` header: `application/json` is parsed as `{"url": ..., "collection": ...}`;
anything else is read as `multipart/form-data` (`file` plus `Form` fields). The collection id is
validated first (`[a-z0-9][a-z0-9_-]{0,63}` or a private `ws:<workspace>`; another workspace's
private collection → 403). A file upload's type is checked before any byte is written; it is then
stored under `<AURUM_DATA_DIR>/corpus_sources/<collection>/` with a server-generated name and
ingested with `aurum.corpus.ingest.ingest_file`. A URL is fetched with
`aurum.core.netguard.fetch_public_url` (public hosts only, size-capped, 20 s timeout, identifying UA;
a blocked or oversized fetch → 400) and ingested with `ingest_text`, tagged `html` or `txt` from the
response's content-type.

## `GET /collections`

`SELECT collection_id, COUNT(DISTINCT source_id), COUNT(chunk_id) ... GROUP BY collection_id`
straight from `aurum.corpus`'s `sources`/`chunks` tables.

## `GET /refs?law=&article=`

Wraps `aurum.corpus.refs.cites`/`cited_by`: `{"law", "article", "cites": [{law,article,kind}],
"cited_by": [{law,article,kind}]}`. `cites` = what chunks tagged with that law/article
themselves mention (built from `aurum.corpus.refs.detect_refs` at ingest time, stored in
`corpus_refs`); `cited_by` is the reverse edge. Comparison is normalized (lowercase,
alphanumeric-only substring match), not exact string equality — see `aurum/corpus/refs.py`.

## `POST /eval`

Runs every question in `evalset.yaml` through the same hybrid-search + trust-tier gate `/ask`
uses (no LLM call — this scores retrieval, not generation) and returns
`{"total", "correct", "abstained", "precision_at_1", "rows": [{id, question, expected, got,
abstained, correct}, ...]}`. `docs/research-eval.md` records the last run (hash backend vs. a
real Ollama `nomic-embed-text` run, when reachable).

## Testing

`tests/research/` runs entirely offline (`AURUM_EMBED_MODEL=hash`, `OLLAMA_URL` pointed at a
closed port with a 1s timeout) so `/ask` always exercises the real extractive fallback rather
than depending on a model being reachable. Covers: abstain on an empty corpus, cite when a
trusted source supports the claim, abstain when only a low-trust source matches, JSON-URL
ingest (with DNS resolution and the fetch transport mocked), and the collections endpoint (`test_research.py`); ingest
hardening — path traversal, validate-before-write, server-side filenames and the SSRF guard
(`test_ingest_hardening.py`); private `ws:{id}` collections (`test_private_collections.py`); and
`as_of`, the refs graph and the eval (`test_as_of_refs_eval.py`).

## Known limitation: local model refusals

A local `llama3.1:8b` (the default `AURUM_LLM_MODEL`) sometimes refuses to write tax prose. In that
case the answer to rely on is the extractive fallback: the cited excerpts, quoted with their
`law`/`article`, with no generation step. The endpoint uses that fallback automatically whenever the
provider call fails (timeout, connection error, bad response, `CloudNotAllowed`) and when Claude
stops with `stop_reason: "refusal"` (`ProviderRefused`). There is no refusal detector for local
models, so a local refusal that comes back as ordinary text is returned as the answer, with the same
trusted citations attached. The citations, not the prose, are what ground the answer.

## Connecting a language-specific question

`lang` only changes which fixed strings (prompt, abstain message, not-advice line) are used —
the corpus itself is not language-partitioned; a Spanish-language statute is still searched by
an English question as long as the content words overlap enough to pass the support threshold.
