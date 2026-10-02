# Research: ask the law, get citations or an honest abstain

**What it does.** Investigación lets you ask in Spanish or English over the ingested law corpus
(`mx-law`, `us-law`, `guidance`). Answers come with **citation cards**: law, article, effective dates,
trust tier, excerpt, link. If the corpus cannot support an answer from a primary or official source, the
assistant **abstains** instead of guessing.

**Trust tiers on every card**: primary law (LISR/LIVA/CFF/RMF, IRC/CFR) › official guidance (SAT
criterios/FAQ, IRS pubs) › professional (Big-4 newsletters: link + short excerpt only) › blog (never the
sole basis).

**Loading the corpus** (empty on a fresh install — ingest what you need):
```
POST /api/research/ingest   multipart file=LISR.pdf  collection=mx-law  law=LISR  jurisdiction=MX
                            trust_tier=primary  effective_from=2026-01-01  url=https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf
GET  /api/research/collections
```
Mexican statutes are split by `Artículo N.` headings and RMF rules by their `x.y.z.w.` numbers so each
chunk carries its article.

**Bulk-loading the standard set** — `scripts/ingest_law.py` fetches/ingests LISR, LIVA, CFF, RMF
2026, IRC Title 26 + Treas. Reg. § 1.1402(a)-1 (via the eCFR API), and Texas Tax Code ch.
151/171 in one shot, with the right `collection`/`law`/`jurisdiction`/`trust_tier`/
`effective_from`/`url` metadata already filled in (see `SOURCES` in the script for the full
registry):
```
uv run python scripts/ingest_law.py                    # fetch everything for real
uv run python scripts/ingest_law.py --source lisr        # just one source
uv run python scripts/ingest_law.py --list                # print the registry, fetch nothing
uv run python scripts/ingest_law.py --offline tests/fixtures/law   # local files instead of a fetch
```
Idempotent by content hash (`aurum.corpus.ingest`'s own dedupe) — re-running it is a no-op unless
a source's text actually changed, in which case the new version auto-links `supersedes` back to
the prior one (same collection + URL). `--offline <dir>` is what tests and CI use;
`tests/fixtures/law/` holds small synthetic fixtures under the exact filenames the real sources
would use.

**Asking**
```
POST /api/research/ask  {"question": "¿Puedo acreditar el IVA de mi laptop en RESICO?", "jurisdiction": "MX", "lang": "es"}
```
The answer is drafted by the local model (Ollama by default; Claude only if `AURUM_CLOUD_OPT_IN=1`) from
the retrieved passages, with a citation-required prompt. If no model is reachable, you still get an
extractive answer built from the passages. Every ask is written to the audit log. Add `"as_of":
"2025-06-01"` to answer using only law in force on that date (chunks are filtered by their
source's `effective_from`/`effective_to`); each citation carries a `related` list of other
articles it cites or is cited by (`GET /api/research/refs?law=&article=` for the full graph).

**Checking research quality** — `POST /api/research/eval` runs `aurum/research/evalset.yaml`
(≥12 ES/EN questions with an expected `{law, article}`) against whatever is currently ingested
and reports precision@1 + abstain counts; see `docs/research-eval.md` for the last recorded run.

**Gotchas**
- Corpus text is data, never instructions: retrieved passages are quoted and isolated before they reach
  a model.
- Embeddings default to `nomic-embed-text`; measure on Spanish statute text and switch to `bge-m3` if
  recall is poor (`AURUM_EMBED_MODEL`). Offline tests use `hash`.
- The default local model (`llama3.1:8b`) sometimes refuses to write tax prose. There is no refusal
  detector, so the refusal text comes back as the answer; the citation cards attached to it are still
  the trusted part (see `docs/modules/research.md`).
- Not advice. Every answer ends with the verify-with-a-licensed-professional line by design.
