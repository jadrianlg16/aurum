from __future__ import annotations

from aurum.updater import tracker


def test_load_sources_has_required_fields():
    sources = tracker.load_sources()
    ids = {s["id"] for s in sources}
    assert {"dof-daily", "sat-rmf", "nl-periodico-oficial", "irs-irb", "federal-register-title-26"} <= ids
    for source in sources:
        for field in ("id", "name", "jurisdiction", "doc_type", "fetch_method", "cadence", "trust_tier", "url"):
            assert field in source, f"{source.get('id')} missing {field}"


def test_first_fetch_is_baseline_only_no_change():
    fetcher = tracker.FakeFetcher({"sat-rmf": "RMF text v1"})
    result = tracker.run("sat-rmf", fetcher)
    assert result["ran"] == ["sat-rmf"]
    assert result["changed"] == []


def test_second_fetch_with_same_text_is_not_a_change():
    fetcher = tracker.FakeFetcher({"sat-rmf": "RMF text v1"})
    tracker.run("sat-rmf", fetcher)
    result = tracker.run("sat-rmf", fetcher)
    assert result["changed"] == []


def test_changed_text_creates_change_and_reindexes_corpus():
    tracker.run("sat-rmf", tracker.FakeFetcher({"sat-rmf": "RMF texto original sin cambios relevantes."}))
    result = tracker.run(
        "sat-rmf",
        tracker.FakeFetcher(
            {"sat-rmf": "Nueva regla RESICO: la tasa aplicable cambia a 2.5% para plataformas digitales."}
        ),
    )
    assert len(result["changed"]) == 1
    change = result["changed"][0]
    assert change["source_id"] == "sat-rmf"
    assert "RESICO" in change["domains"] or "platform_withholding" in change["domains"]
    assert change["corpus_source_id"]


def test_fake_fetcher_from_dir(tmp_path):
    (tmp_path / "sat-rmf.txt").write_text("contenido de prueba", encoding="utf-8")
    fetcher = tracker.fake_fetcher_from_dir(tmp_path)
    assert fetcher.fetch({"id": "sat-rmf"}) == "contenido de prueba"
    assert fetcher.fetch({"id": "unknown"}) == ""


def test_unknown_source_id_raises():
    import pytest

    with pytest.raises(ValueError):
        tracker.run("nope", tracker.FakeFetcher({}))
