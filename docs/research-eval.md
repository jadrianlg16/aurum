# Research eval results

`POST /api/research/eval` runs `aurum/research/evalset.yaml` (15 ES/EN questions across
MX and US collections) against the corpus and scores **precision@1**: does the top *trusted*
citation land on the question's expected `{law, article}`? It also counts abstentions —
questions where no trusted citation cleared the `support` threshold at all (the "grounded or
silent" principle: an ungrounded question must abstain, not guess).

This measures retrieval, not generation — no LLM is called by `/eval`.

## How to run it

Corpus: `scripts/ingest_law.py --offline tests/fixtures/law` (the 7 synthetic law/guidance
fixtures — LISR, LIVA, CFF, RMF, IRC Title 26, Treas. Reg. § 1.1402(a)-1, Texas Tax Code
ch. 151/171).

```
export AURUM_DATA_DIR=<tmp> AURUM_EMBED_MODEL=<hash|nomic-embed-text> [OLLAMA_URL=http://localhost:11434]
uv run python scripts/ingest_law.py --offline tests/fixtures/law
uv run python -c "from aurum.corpus.store import open_store; from aurum.research import eval as eval_mod; \
  store = open_store(); print(eval_mod.run_eval(store)); store.close()"
```

The result is deterministic: every ingest mints random source ids, so ranking ties are broken
by where a chunk came from (path or URL, then its position in the source) rather than by id.
Before that tie-break existed, repeated offline runs gave 6, 7 or 8 correct answers out of 15.

## Results

| Backend | Date | Runs | total | correct | abstained | precision@1 |
|---|---|---|---|---|---|---|
| `AURUM_EMBED_MODEL=hash` (offline, no network) | 2026-10-02 | 5 fresh ingests, identical results | 15 | 7 | 5 | **0.467** |
| `AURUM_EMBED_MODEL=nomic-embed-text` via local Ollama | 2026-09-06 | 1 (before the tie-break change; not re-run since) | 15 | 10 | 5 | 0.667 |

The same 5 questions abstain under both backends: every English-language question asked
against a Spanish-only MX-law fixture (`mx-*-en` ids). This is not a bug in either
embedding backend — `cite_or_abstain`'s trust gate thresholds on **lexical word-overlap
support** (`aurum.corpus.search.support`), which is language-specific by construction. A
semantic embedding (`nomic-embed-text`) still ranked the right chunk first for 4 of the 5 in
the 2026-09-06 run (checked by hand), but the lexical support score stays near zero because the
question and the corpus text share almost no words. Two ways to close this without weakening
"grounded or silent": (1) translate or duplicate the MX-law fixtures into an EN paraphrase
collection, or (2) let `support` optionally blend in the semantic similarity score when the
embedding backend is not the offline hash. Neither is implemented; it is a known limitation.

The corpus here is tiny (7 sources, about 20 chunks) and entirely synthetic, so these numbers
describe *this fixture set*, not the corpus's general accuracy. Re-run after a real
`scripts/ingest_law.py` (online) ingest for a number that means something operationally.

## Not yet measured

- Precision@1 on the real (non-synthetic) LISR/LIVA/CFF/RMF/IRC/Texas Tax Code text.
- The `nomic-embed-text` row with the deterministic tie-break.
