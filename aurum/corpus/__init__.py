"""The corpus module: law/guidance material Aurum ingests, searches, and cites against.

Ingest, search, cite, over SQLite FTS5 plus embeddings stored in the same database, no vector
service (shared with the author's learning-tutor project (https://github.com/jadrianlg16/learning-tutor)). Two rules shape every file here:

* **Corpus text is data, never instructions** (``sanitize``). Nothing retrieved reaches a
  model except through ``sanitize.render_for_context``.
* **Grounded or silent** (``cite``). ``cite_or_abstain`` cites the corpus for a claim or says
  it cannot, rather than asserting a claim with a decorative citation.

There is no source-role concept (Aurum's citations are graded by ``trust_tier`` instead), and
question answering lives in the separate ``aurum.research`` module. Material is grouped by a
free-form "collection".
"""

from __future__ import annotations

from .store import CorpusError, CorpusStore, open_store

__all__ = [
    "CorpusError",
    "CorpusStore",
    "open_store",
]
