"""Descarga Masiva client interface — read-only, never signs/transmits filings.

Two implementations of the same `DescargaMasiva` protocol:
  - `FakeSAT`: serves XML fixtures from a directory (`AURUM_SAT_FAKE_DIR`). Used for tests and the demo
    workspace; deterministic, no network.
  - `SatcfdiClient`: wraps `satcfdi`'s Descarga Masiva web-service client with the vault's decrypted
    e.firma. **Not yet verified** — this cannot be exercised without a real e.firma against SAT's production
    endpoint, so treat it as best-effort integration code, not a tested path. If `satcfdi`'s API differs
    from what is wrapped here, `request`/`verify`/`download` raise `NotImplementedError` rather than
    silently doing the wrong thing.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal, Protocol

from .vault import VaultCredentials


class DescargaMasiva(Protocol):
    def request(self, ws_id: str, start: str, end: str, kind: Literal["emitidos", "recibidos"]) -> str: ...
    def verify(self, request_id: str) -> str: ...
    def download(self, package_id: str) -> list[Path]: ...


class FakeSAT:
    """Serves CFDI XML fixtures from a directory instead of calling SAT. Every request immediately
    "completes" and download() returns every .xml file in the fixtures dir (or a kind-specific
    subdirectory `<fixtures_dir>/emitidos` / `<fixtures_dir>/recibidos` if present)."""

    def __init__(self, fixtures_dir: str | Path):
        self.fixtures_dir = Path(fixtures_dir)
        self._requests: dict[str, dict] = {}

    def request(self, ws_id: str, start: str, end: str, kind: Literal["emitidos", "recibidos"]) -> str:
        request_id = f"fake-{uuid.uuid4().hex[:12]}"
        self._requests[request_id] = {"ws_id": ws_id, "start": start, "end": end, "kind": kind}
        return request_id

    def verify(self, request_id: str) -> str:
        if request_id not in self._requests:
            raise KeyError(request_id)
        return "ready"

    def download(self, package_id: str) -> list[Path]:
        meta = self._requests.get(package_id)
        kind_dir = self.fixtures_dir / meta["kind"] if meta else None
        source_dir = kind_dir if kind_dir and kind_dir.is_dir() else self.fixtures_dir
        if not source_dir.exists():
            return []
        return sorted(source_dir.glob("*.xml"))


class SatcfdiClient:
    """Wraps satcfdi's Descarga Masiva client with e.firma credentials from the vault. Not yet verified."""

    def __init__(self, credentials: VaultCredentials, download_dir: str | Path):
        self.credentials = credentials
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        try:
            from satcfdi.descarga_masiva import DescargaMasivaService  # type: ignore
        except ImportError as e:
            raise NotImplementedError(
                "satcfdi does not expose a DescargaMasivaService in this version; "
                "real SAT sync is unimplemented (not yet verified against SAT)"
            ) from e
        self._service_cls = DescargaMasivaService

    def request(self, ws_id: str, start: str, end: str, kind: Literal["emitidos", "recibidos"]) -> str:
        raise NotImplementedError(
            "SatcfdiClient.request is not yet verified: satcfdi's Descarga Masiva API was not exercised "
            "against a real e.firma/SAT endpoint in this environment."
        )

    def verify(self, request_id: str) -> str:
        raise NotImplementedError("SatcfdiClient.verify is not yet verified")

    def download(self, package_id: str) -> list[Path]:
        raise NotImplementedError("SatcfdiClient.download is not yet verified")
