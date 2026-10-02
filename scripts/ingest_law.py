"""Ingest the standard set of law/guidance sources into ``aurum.corpus``.

Two modes:

* **online** (default): fetches each registered source's URL and ingests the result.
* **``--offline <dir>``**: ingests local files from ``<dir>`` instead of fetching anything —
  every source's ``offline_filename`` names the file expected in that directory. This is the
  path tests and CI use; ``tests/fixtures/law/`` holds small synthetic fixtures with the same
  filenames as the real sources so ``--offline tests/fixtures/law`` exercises the exact same
  registry and metadata as a real run, with no network.

Idempotent: ``aurum.corpus.ingest`` dedupes by ``(collection_id, sha256)`` — re-running this
script (online or offline) on unchanged content is a no-op (``status: "duplicate"``); changed
content ingests as a new version, auto-linked via ``supersedes`` (same collection + URL).

Usage::

    uv run python scripts/ingest_law.py --offline tests/fixtures/law
    uv run python scripts/ingest_law.py                       # fetch everything, real network
    uv run python scripts/ingest_law.py --source lisr          # just one source, real network
    uv run python scripts/ingest_law.py --list                 # print the registry and exit
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


@dataclass(frozen=True)
class LawSource:
    id: str
    law: str
    jurisdiction: str  # "MX" | "US"
    collection: str  # aurum.corpus collection_id
    doc_type: str  # "statute" | "guidance"
    trust_tier: str
    effective_from: str
    url: str
    fetch: str  # "pdf" | "html" | "ecfr" | "txt"
    offline_filename: str
    title: str


#: The source registry. URLs point at the Cámara de Diputados' published PDF for each MX
#: statute, SAT's RMF landing page, the eCFR versioner API for IRC Title 26, and the Texas
#: Legislature's statutes site for the Tax Code chapters used elsewhere in Aurum (US tax
#: module: franchise tax ch. 171, sales/use tax ch. 151).
SOURCES: list[LawSource] = [
    LawSource(
        id="lisr",
        law="LISR",
        jurisdiction="MX",
        collection="mx-law",
        doc_type="statute",
        trust_tier="primary",
        effective_from="2026-01-01",
        url="https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf",
        fetch="pdf",
        offline_filename="lisr.txt",
        title="Ley del Impuesto Sobre la Renta (LISR)",
    ),
    LawSource(
        id="liva",
        law="LIVA",
        jurisdiction="MX",
        collection="mx-law",
        doc_type="statute",
        trust_tier="primary",
        effective_from="2026-01-01",
        url="https://www.diputados.gob.mx/LeyesBiblio/pdf/LIVA.pdf",
        fetch="pdf",
        offline_filename="liva.txt",
        title="Ley del Impuesto al Valor Agregado (LIVA)",
    ),
    LawSource(
        id="cff",
        law="CFF",
        jurisdiction="MX",
        collection="mx-law",
        doc_type="statute",
        trust_tier="primary",
        effective_from="2026-01-01",
        url="https://www.diputados.gob.mx/LeyesBiblio/pdf/CFF.pdf",
        fetch="pdf",
        offline_filename="cff.txt",
        title="Código Fiscal de la Federación (CFF)",
    ),
    LawSource(
        id="rmf-2026",
        law="RMF",
        jurisdiction="MX",
        collection="guidance",
        doc_type="guidance",
        trust_tier="official_guidance",
        effective_from="2026-01-01",
        url="https://www.sat.gob.mx/normatividad/15224/normatividad-de-resolucion-miscelanea-fiscal",
        fetch="html",
        offline_filename="rmf.txt",
        title="Resolución Miscelánea Fiscal (RMF) 2026",
    ),
    LawSource(
        id="irc-title-26",
        law="IRC",
        jurisdiction="US",
        collection="us-law",
        doc_type="statute",
        trust_tier="primary",
        effective_from="2026-01-01",
        # eCFR versioner "full text" endpoint (Title 26, Part 1 -- self-employment and FEIE
        # regulations). See docs/modules/updater.md for the versioner API shape.
        # {date} is resolved at fetch time via the eCFR titles endpoint (see resolve_ecfr_url):
        # the versioner "full text" endpoint has no "current" alias, only a real ISO date.
        url="https://www.ecfr.gov/api/versioner/v1/full/{date}/title-26.xml?part=1",
        fetch="ecfr",
        offline_filename="irc_title26.txt",
        title="Internal Revenue Code, Title 26 (via eCFR)",
    ),
    LawSource(
        id="treas-reg-1402",
        law="Treas. Reg.",
        jurisdiction="US",
        collection="us-law",
        doc_type="statute",
        trust_tier="primary",
        effective_from="2026-01-01",
        url="https://www.ecfr.gov/api/versioner/v1/full/{date}/title-26.xml?part=1&section=1.1402(a)-1",
        fetch="ecfr",
        offline_filename="treas_reg.txt",
        title="Treasury Regulations § 1.1402(a)-1",
    ),
    LawSource(
        id="tx-tax-code",
        law="Texas Tax Code",
        jurisdiction="US",
        collection="us-law",
        doc_type="statute",
        trust_tier="primary",
        effective_from="2026-01-01",
        url="https://statutes.capitol.texas.gov/Docs/TX/htm/TX.171.htm",
        fetch="html",
        offline_filename="tx_tax_code.txt",
        title="Texas Tax Code, Chapters 151 & 171",
    ),
]


def registry_by_id(source_id: str) -> LawSource | None:
    for source in SOURCES:
        if source.id == source_id:
            return source
    return None


# --- fetchers --------------------------------------------------------------


class FetchError(Exception):
    """Any expected failure talking to a real source (network, HTTP status, empty body)."""


_ECFR_TITLES_URL = "https://www.ecfr.gov/api/versioner/v1/titles.json"


def resolve_ecfr_date(client: Any, title: str = "26") -> str:
    """The eCFR versioner "full text" endpoint takes a real ISO date, not "current" — look
    one up from the titles endpoint (``up_to_date_as_of``) so this never hardcodes a date
    that goes stale."""

    resp = client.get(_ECFR_TITLES_URL, timeout=30.0)
    resp.raise_for_status()
    for entry in resp.json().get("titles", []):
        if str(entry.get("number")) == title:
            return str(entry["up_to_date_as_of"])
    raise FetchError(f"eCFR titles.json did not list title {title}")


def fetch_online(source: LawSource) -> tuple[bytes, str]:
    """Returns ``(raw_bytes, content_kind)`` where ``content_kind`` is a corpus ``kind``."""

    import httpx

    headers = {"User-Agent": "aurum-ingest-law/0.1 (self-hosted personal finance tool)"}
    url = source.url
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
            if source.fetch == "ecfr" and "{date}" in url:
                url = url.format(date=resolve_ecfr_date(client))
            resp = client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise FetchError(f"{source.id}: could not fetch {url}: {exc}") from exc

    if source.fetch == "pdf":
        return resp.content, "pdf"
    if source.fetch == "ecfr":
        # eCFR's "full" endpoint returns XML; treat it as HTML for extraction purposes --
        # ingest.extract_html's regex tag-stripper is tolerant of XML tags too.
        return resp.content, "html"
    if source.fetch == "html":
        return resp.content, "html"
    return resp.content, "txt"  # pragma: no cover - no registered source uses "txt" fetch


# --- ingest ------------------------------------------------------------


def ingest_offline(store: Any, source: LawSource, directory: Path) -> dict[str, Any]:
    from aurum.corpus import ingest as ingest_mod
    from aurum.corpus.store import CorpusError

    path = directory / source.offline_filename
    if not path.exists():
        return {"id": source.id, "status": "missing_fixture", "path": str(path)}
    try:
        return {
            "id": source.id,
            **ingest_mod.ingest_file(
                store,
                source.collection,
                path,
                kind="txt",
                title=source.title,
                jurisdiction=source.jurisdiction,
                doc_type=source.doc_type,
                law=source.law,
                url=source.url,
                trust_tier=source.trust_tier,
                effective_from=source.effective_from,
            ),
        }
    except (CorpusError, NotImplementedError) as exc:
        return {"id": source.id, "status": "error", "error": str(exc)}


def ingest_online(store: Any, source: LawSource) -> dict[str, Any]:
    import tempfile

    from aurum.corpus import ingest as ingest_mod
    from aurum.corpus.store import CorpusError

    try:
        raw, kind = fetch_online(source)
    except FetchError as exc:
        return {"id": source.id, "status": "fetch_error", "error": str(exc)}

    if not raw:
        return {"id": source.id, "status": "fetch_error", "error": "empty response body"}

    try:
        if kind == "pdf":
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
                handle.write(raw)
                tmp_path = Path(handle.name)
            try:
                result = ingest_mod.ingest_file(
                    store,
                    source.collection,
                    tmp_path,
                    kind="pdf",
                    title=source.title,
                    jurisdiction=source.jurisdiction,
                    doc_type=source.doc_type,
                    law=source.law,
                    url=source.url,
                    trust_tier=source.trust_tier,
                    effective_from=source.effective_from,
                )
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            text = raw.decode("utf-8", errors="replace")
            result = ingest_mod.ingest_text(
                store,
                source.collection,
                text,
                title=source.title,
                kind=kind,
                path_or_url=source.url,
                jurisdiction=source.jurisdiction,
                doc_type=source.doc_type,
                law=source.law,
                url=source.url,
                trust_tier=source.trust_tier,
                effective_from=source.effective_from,
            )
    except (CorpusError, NotImplementedError) as exc:
        return {"id": source.id, "status": "error", "error": str(exc)}
    return {"id": source.id, **result}


# --- CLI ---------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        metavar="DIR",
        help="ingest from local files in DIR instead of fetching (see <id>.offline_filename)",
    )
    parser.add_argument("--source", help="only ingest this source id (default: all)")
    parser.add_argument("--list", action="store_true", help="print the registry as JSON and exit")
    args = parser.parse_args(argv)

    if args.list:
        print(json.dumps([s.__dict__ for s in SOURCES], indent=2, ensure_ascii=False))
        return 0

    sources = SOURCES
    if args.source:
        one = registry_by_id(args.source)
        if not one:
            print(f"unknown source id {args.source!r}; use --list to see the registry", file=sys.stderr)
            return 2
        sources = [one]

    from aurum.corpus.store import open_store

    store = open_store()
    results: list[dict[str, Any]] = []
    try:
        for source in sources:
            if args.offline:
                result = ingest_offline(store, source, Path(args.offline))
            else:
                result = ingest_online(store, source)
            results.append(result)
            status = result.get("status", "?")
            print(f"[{status}] {source.id} ({source.law}, {source.jurisdiction})")
    finally:
        store.close()

    print(json.dumps(results, indent=2, ensure_ascii=False))
    failed = [r for r in results if r.get("status") in ("error", "fetch_error", "missing_fixture")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
