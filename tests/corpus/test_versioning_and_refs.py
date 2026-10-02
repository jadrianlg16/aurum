from __future__ import annotations

from aurum.corpus import cite as cite_mod
from aurum.corpus import ingest as ingest_mod
from aurum.corpus import refs as refs_mod
from aurum.corpus.search import search
from aurum.corpus.store import CorpusStore, get_source

OLD_TEXT = "Artículo 1. Tasa anterior del 30% aplicable a los ingresos del ejercicio."
NEW_TEXT = "Artículo 1. Tasa vigente del 35% aplicable a los ingresos del ejercicio."


# --- as-of filtering -----------------------------------------------------


def test_search_as_of_excludes_chunk_not_yet_effective(store: CorpusStore):
    ingest_mod.ingest_text(
        store,
        "mx-law",
        "Artículo 200. Nueva disposición transitoria sobre el régimen fiscal aplicable.",
        title="future rule",
        law="LISR",
        effective_from="2030-01-01",
    )
    results = search(store, "mx-law", "disposición transitoria régimen fiscal", as_of="2026-01-01")
    assert results == []

    results_now = search(store, "mx-law", "disposición transitoria régimen fiscal", as_of="2030-06-01")
    assert results_now


def test_search_as_of_excludes_chunk_no_longer_effective(store: CorpusStore):
    ingest_mod.ingest_text(
        store,
        "mx-law",
        "Artículo 201. Disposición derogada sobre retención bancaria especial única.",
        title="repealed rule",
        law="LISR",
        effective_from="2020-01-01",
        effective_to="2024-12-31",
    )
    assert search(store, "mx-law", "retención bancaria especial única", as_of="2026-01-01") == []
    assert search(store, "mx-law", "retención bancaria especial única", as_of="2022-01-01")


def test_search_without_as_of_ignores_effective_range(store: CorpusStore):
    ingest_mod.ingest_text(
        store,
        "mx-law",
        "Artículo 202. Vigencia futura de una regla sobre plataformas fiscales digitales.",
        title="future rule 2",
        law="LISR",
        effective_from="2099-01-01",
    )
    assert search(store, "mx-law", "vigencia futura regla plataformas fiscales digitales")


def test_cite_or_abstain_honors_as_of(store: CorpusStore):
    ingest_mod.ingest_text(
        store,
        "mx-law",
        "Artículo 203. Tasa especial de retención sobre pagos a residentes en el extranjero.",
        title="future special rate",
        law="LISR",
        effective_from="2030-01-01",
    )
    claim = "tasa especial de retención sobre pagos a residentes en el extranjero"
    assert cite_mod.cite_or_abstain(store, claim, "mx-law", as_of="2026-01-01")["status"] == "abstain"
    assert cite_mod.cite_or_abstain(store, claim, "mx-law", as_of="2031-01-01")["status"] == "cited"


# --- supersedes ------------------------------------------------------------


def test_ingesting_new_version_at_same_url_links_supersedes(store: CorpusStore):
    first = ingest_mod.ingest_text(
        store, "mx-law", OLD_TEXT, title="LISR art 1", law="LISR",
        url="https://diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf", effective_from="2025-01-01",
        effective_to="2025-12-31",
    )
    second = ingest_mod.ingest_text(
        store, "mx-law", NEW_TEXT, title="LISR art 1 (2026)", law="LISR",
        url="https://diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf", effective_from="2026-01-01",
    )
    assert second["status"] == "ingested"
    new_source = get_source(store, second["source_id"])
    assert new_source["supersedes"] == first["source_id"]


def test_explicit_supersedes_is_respected_over_auto_detection(store: CorpusStore):
    first = ingest_mod.ingest_text(store, "mx-law", OLD_TEXT, title="v1", law="LISR", url="https://x/1")
    second = ingest_mod.ingest_text(
        store, "mx-law", NEW_TEXT, title="v2", law="LISR", url="https://x/2", supersedes=first["source_id"]
    )
    assert get_source(store, second["source_id"])["supersedes"] == first["source_id"]


def test_reingesting_identical_bytes_at_same_url_is_still_a_duplicate(store: CorpusStore):
    first = ingest_mod.ingest_text(store, "mx-law", OLD_TEXT, title="v1", law="LISR", url="https://y/1")
    again = ingest_mod.ingest_text(store, "mx-law", OLD_TEXT, title="v1 again", law="LISR", url="https://y/1")
    assert again["status"] == "duplicate"
    assert again["source_id"] == first["source_id"]


# --- corpus_refs graph -----------------------------------------------------


def test_detect_refs_law_qualified_mx():
    refs = refs_mod.detect_refs("Conforme a lo dispuesto por LIVA art. 5, el acreditamiento procede.")
    assert {"law": "LIVA", "article": "5", "kind": "cites"} in refs


def test_detect_refs_bare_article_falls_back_to_default_law():
    refs = refs_mod.detect_refs("Artículo 27, fracción III de esta disposición.", default_law="LISR")
    assert any(r["law"] == "LISR" and "27" in r["article"] and "III" in r["article"] for r in refs)


def test_detect_refs_rmf_rule():
    refs = refs_mod.detect_refs("Para los efectos de la regla 2.7.2.4. deberá observarse lo siguiente.")
    assert {"law": "RMF", "article": "2.7.2.4", "kind": "cites"} in refs


def test_detect_refs_us_patterns():
    text = "See 26 U.S.C. § 1402 and IRC § 911, as well as Treas. Reg. § 1.1402(a)-1."
    refs = refs_mod.detect_refs(text)
    laws = {(r["law"], r["article"]) for r in refs}
    assert ("26 U.S.C.", "1402") in laws
    assert ("IRC", "911") in laws
    assert ("Treas. Reg.", "1.1402(a)-1") in laws


def test_detect_refs_no_false_positive_on_plain_text():
    assert refs_mod.detect_refs("This paragraph mentions nothing citable at all.") == []


def test_ingest_populates_corpus_refs_table(store: CorpusStore):
    ingest_mod.ingest_text(
        store,
        "mx-law",
        "Artículo 29. Los contribuyentes observarán la regla 2.7.2.4. de la RMF vigente.",
        title="CFF 29",
        law="CFF",
    )
    rows = store.query("SELECT * FROM corpus_refs")
    assert any(dict(r)["law"] == "RMF" and dict(r)["article"] == "2.7.2.4" for r in rows)


def test_refs_cites_and_cited_by(store: CorpusStore):
    ingest_mod.ingest_text(
        store, "mx-law",
        "Artículo 29. Los contribuyentes observarán la regla 2.7.2.4. de la RMF vigente.",
        title="CFF 29", law="CFF",
    )
    ingest_mod.ingest_text(
        store, "guidance",
        "2.7.2.4. Para los efectos del artículo 29 del CFF, se aplicará este procedimiento.",
        title="RMF rule", law="RMF",
    )
    cites = refs_mod.cites(store, "CFF", "29.")
    assert any(c["law"] == "RMF" and c["article"] == "2.7.2.4" for c in cites)

    cited_by = refs_mod.cited_by(store, "RMF", "2.7.2.4")
    assert any(c["law"] == "CFF" for c in cited_by)


def test_related_for_dedupes_and_excludes_self(store: CorpusStore):
    ingest_mod.ingest_text(
        store, "mx-law",
        "Artículo 29. Los contribuyentes observarán la regla 2.7.2.4. de la RMF vigente, "
        "conforme a la regla 2.7.2.4.",
        title="CFF 29", law="CFF",
    )
    related = refs_mod.related_for(store, "CFF", "29.")
    keys = [(r["law"], r["article"]) for r in related]
    assert ("CFF", "29.") not in keys
    assert len(keys) == len(set(keys))


def test_to_citation_includes_related_when_store_given(store: CorpusStore):
    ingest_mod.ingest_text(
        store, "mx-law",
        "Artículo 29. Los contribuyentes observarán la regla 2.7.2.4. de la RMF vigente.",
        title="CFF 29", law="CFF", url="https://x/cff29",
    )
    result = cite_mod.cite_or_abstain(store, "los contribuyentes observarán la regla", "mx-law")
    assert result["status"] == "cited"
    citation = result["citations"][0]
    assert "related" in citation
    assert any(r["law"] == "RMF" for r in citation["related"])
