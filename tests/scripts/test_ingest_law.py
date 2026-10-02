from __future__ import annotations

from pathlib import Path

from aurum.corpus.store import list_sources, open_store
from scripts import ingest_law

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "law"


def test_registry_lists_all_seven_sources():
    ids = {s.id for s in ingest_law.SOURCES}
    assert ids == {
        "lisr", "liva", "cff", "rmf-2026", "irc-title-26", "treas-reg-1402", "tx-tax-code",
    }


def test_every_source_has_a_matching_offline_fixture():
    for source in ingest_law.SOURCES:
        assert (FIXTURES / source.offline_filename).exists(), source.offline_filename


def test_offline_ingest_of_all_sources():
    store = open_store()
    try:
        results = [ingest_law.ingest_offline(store, s, FIXTURES) for s in ingest_law.SOURCES]
    finally:
        store.close()
    assert all(r["status"] == "ingested" for r in results), results
    for source in ingest_law.SOURCES:
        found = [r for r in results if r["id"] == source.id][0]
        assert found["collection_id"] == source.collection


def test_offline_ingest_is_idempotent_by_content_hash():
    store = open_store()
    try:
        first = [ingest_law.ingest_offline(store, s, FIXTURES) for s in ingest_law.SOURCES]
        second = [ingest_law.ingest_offline(store, s, FIXTURES) for s in ingest_law.SOURCES]
    finally:
        store.close()
    assert all(r["status"] == "ingested" for r in first)
    assert all(r["status"] == "duplicate" for r in second)
    for a, b in zip(first, second, strict=True):
        assert a["source_id"] == b["source_id"]


def test_offline_ingest_records_metadata():
    store = open_store()
    try:
        ingest_law.ingest_offline(store, ingest_law.registry_by_id("lisr"), FIXTURES)
        sources = list_sources(store, "mx-law")
    finally:
        store.close()
    lisr = next(s for s in sources if s["law"] == "LISR")
    assert lisr["jurisdiction"] == "MX"
    assert lisr["trust_tier"] == "primary"
    assert lisr["effective_from"] == "2026-01-01"
    assert lisr["url"] == "https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf"


def test_missing_fixture_reports_missing_not_a_crash(tmp_path):
    store = open_store()
    try:
        result = ingest_law.ingest_offline(store, ingest_law.registry_by_id("lisr"), tmp_path)
    finally:
        store.close()
    assert result["status"] == "missing_fixture"


def test_main_offline_cli_exits_zero(capsys):
    code = ingest_law.main(["--offline", str(FIXTURES)])
    assert code == 0
    out = capsys.readouterr().out
    assert "ingested" in out


def test_main_list_flag_prints_registry(capsys):
    code = ingest_law.main(["--list"])
    assert code == 0
    out = capsys.readouterr().out
    assert "lisr" in out


def test_main_unknown_source_id_errors(capsys):
    code = ingest_law.main(["--source", "nonexistent"])
    assert code == 2
