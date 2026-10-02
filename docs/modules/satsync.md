# satsync

Encrypted e.firma vault + SAT Descarga Masiva client interface. Read-only: nothing here signs,
submits, or transmits a filing (e.firma: read, never sign — see
[ARCHITECTURE.md](../ARCHITECTURE.md#principles)).

## Files

- `aurum/satsync/vault.py` — `store(ws, cer_bytes, key_bytes, password, passphrase)` derives a Fernet
  key from the passphrase via `cryptography`'s `Scrypt` (n=2**14, r=8, p=1, random 16-byte salt per
  vault) and encrypts `{cer, key, password}` as one blob at `{DATA_DIR}/vault/{ws}.vault`
  (`salt\ntoken`). `open_vault(ws, passphrase)` decrypts into an in-memory `VaultCredentials` only —
  never written to disk or logged. `status(ws)` returns `{present, stored_at, size_bytes}` only, never
  material. `purge(ws)` deletes the file. Exceptions: `VaultNotFound`, `VaultBadPassphrase`.
- `aurum/satsync/client.py` — `DescargaMasiva` protocol (`request`, `verify`, `download`).
  - `FakeSAT(fixtures_dir)`: serves `.xml` files from `fixtures_dir/<kind>/` (falls back to
    `fixtures_dir/` flat) — deterministic, no network, used by tests and the demo workspace via
    `AURUM_SAT_FAKE_DIR`.
  - `SatcfdiClient(credentials, download_dir)`: intended wrapper around `satcfdi`'s Descarga Masiva
    web-service client. **Not implemented** — the installed `satcfdi` does not expose a
    `descarga_masiva.DescargaMasivaService`, so the constructor raises `NotImplementedError`
    immediately, and `request`/`verify`/`download` raise it too. Treat it as a stub, not working code,
    and re-check `satcfdi`'s current API surface for Descarga Masiva before implementing it.
- `aurum/satsync/schema.sql` — `satsync_jobs` (id, ws_id, kind, start_date, end_date, status,
  request_id, downloaded, error, created_at, updated_at). The vault itself is a file, not a DB row.
- `aurum/satsync/router.py` — mounted at `/api/satsync`.

## Endpoints

| Method & path | Notes |
|---|---|
| `POST /{ws}/vault` | multipart `cer`, `key` files + form `password`, `passphrase`. |
| `GET /{ws}/vault` | status only. |
| `DELETE /{ws}/vault` | purge. |
| `POST /{ws}/sync` | JSON `{start, end, kind, passphrase}`. Uses `FakeSAT` when `AURUM_SAT_FAKE_DIR` is set, else opens the vault and uses `SatcfdiClient` (→ currently always `NotImplementedError` → HTTP 501). Missing vault → 400; wrong passphrase → 401. |
| `GET /{ws}/jobs` | job history for the workspace, newest first. |

## Env

`AURUM_SAT_FAKE_DIR` — fixture directory for `FakeSAT`. When it is unset, `POST /{ws}/sync` goes to the
real client and answers 501 (below).

## Limitations

- **Real SAT Descarga Masiva is not available.** `POST /{ws}/sync` without `AURUM_SAT_FAKE_DIR`
  returns **HTTP 501**, because the installed `satcfdi` lacks the Descarga Masiva service and
  `SatcfdiClient` fails loudly instead of pretending to work.
- **Only the fake SAT is exercised.** Every test and the demo use `FakeSAT`; the real path has never
  run against SAT's production endpoint, and **no real e.firma was ever used** to develop or test this
  module.
- Everything else (vault encryption, `FakeSAT`, job bookkeeping, endpoint shapes) is covered by the
  tests below.

## Tests

`tests/satsync/` — `test_vault.py` (store/open roundtrip, wrong passphrase, status never leaks
material, missing vault, purge), `test_client.py` (`FakeSAT` with a `<kind>/` subdirectory and with a
flat fixtures directory), `test_router.py` (vault store/status/delete via `TestClient`; a full sync via
`FakeSAT`; a sync attempt with no vault returns 400). Run: `uv run pytest -q tests/satsync`.
