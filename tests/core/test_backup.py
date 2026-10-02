"""core/backup.py: per-workspace backup.zip/movimientos.csv + full instance backup."""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core import backup
from aurum.core.money import Amount
from aurum.core.workspaces import Workspace, save_workspace
from aurum.organizer import commitments as org_commitments
from aurum.organizer.models import CommitmentIn
from aurum.pf import accounts_admin, budgets, entries, labels


@pytest.fixture
def ws():
    save_workspace(Workspace(id="bws", name="Backup test"))
    return "bws"


@pytest.fixture
def seeded(ws):
    """2 accounts, 3 entries (one with a single split), 1 budget, 1 commitment."""
    checking = accounts_admin.create_account(
        ws, accounts_admin.AccountIn(name="Cheques", type="checking", opening_balance=Amount(amount="10000"))
    )
    accounts_admin.create_account(ws, accounts_admin.AccountIn(name="Efectivo", type="cash"))
    lbls = {lbl["name"]: lbl for lbl in labels.list_labels(ws)}
    comida = lbls["Comida fuera"]
    super_ = lbls["Súper"]

    entries.create_entry(
        ws,
        entries.EntryIn(
            kind="expense", date=date(2026, 9, 1), amount=Amount(amount="250.00"),
            account_id=checking["id"], label_id=comida["id"], payee="Tacos",
        ),
    )
    entries.create_entry(
        ws,
        entries.EntryIn(
            kind="expense", date=date(2026, 9, 2), amount=Amount(amount="500.00"),
            account_id=checking["id"], label_id=super_["id"], payee="Soriana",
        ),
    )
    entries.create_entry(
        ws,
        entries.EntryIn(
            kind="expense", date=date(2026, 9, 3), amount=Amount(amount="300.00"),
            account_id=checking["id"], payee="Mixto",
            splits=[
                entries.SplitIn(label_id=comida["id"], amount=Amount(amount="200.00")),
                entries.SplitIn(label_id=super_["id"], amount=Amount(amount="100.00")),
            ],
        ),
    )
    budgets.create_budget(
        ws, budgets.Budget(label_id=comida["id"], period="2026-09", amount="2000", rollover=False)
    )
    org_commitments.create(
        ws,
        CommitmentIn(kind="rent", name="Renta", amount=Amount(amount="9500"), cadence="monthly", anchor_day=1,
                     account=checking["account"]),
        today=date(2026, 9, 1),
    )
    return ws


def test_workspace_zip_has_the_expected_members(seeded):
    fh = backup.build_workspace_zip(seeded)
    with zipfile.ZipFile(fh) as zf:
        names = set(zf.namelist())
        for expected in ("workspace.json", "main.beancount", "accounts.beancount", "metadata.json", "movimientos.csv"):
            assert expected in names, names
        meta = json.loads(zf.read("metadata.json"))
    assert len(meta["tables"]["pf_entries"]) == 3
    assert len(meta["tables"]["organizer_commitments"]) == 1


def test_csv_starts_with_bom_and_has_the_fixed_header(seeded):
    data = backup.build_movimientos_csv(seeded)
    text = data.decode("utf-8")
    assert data.startswith("﻿".encode())
    lines = text.lstrip("﻿").split("\r\n")
    assert lines[0] == "Fecha;Tipo;Monto;Moneda;Cuenta;Cuenta destino;Categoría;Comercio;Nota;Etiquetas;Origen"
    # 2 plain entries (1 row each) + 1 entry with 2 splits (1 row per split) = 4 data rows
    data_rows = [ln for ln in lines[1:] if ln]
    assert len(data_rows) == 4
    assert any(row.split(";")[2] == "-250.00" for row in data_rows)


def test_csv_split_rows_are_signed_and_tagged_parte_and_sum_to_the_entry(seeded):
    data = backup.build_movimientos_csv(seeded).decode("utf-8")
    split_rows = [ln for ln in data.split("\r\n") if "Mixto" in ln]
    assert len(split_rows) == 2
    amounts = sorted(float(row.split(";")[2]) for row in split_rows)
    assert amounts == [-200.0, -100.0]
    assert all("parte" in row.split(";")[9] for row in split_rows)


def test_backup_zip_excludes_uncommitted_rows_from_another_connection(seeded):
    from aurum.pf import store as pf_store

    conn2 = pf_store.db()
    conn2.execute(
        "INSERT INTO pf_entries (id, ws_id, kind, date, amount, currency, account_id, to_account_id, "
        "label_id, payee, note, tags, splits, source, txn_id, voided, editable, non_editable_reason, "
        "attachment, created_at, updated_at) VALUES ('ghost', ?, 'expense', '2026-09-05', '999.00', 'MXN', "
        "'x', NULL, NULL, 'ghost', NULL, '[]', '[]', 'manual', 'ghost-txn', 0, 1, NULL, NULL, 'x', 'x')",
        (seeded,),
    )
    # deliberately NOT committed
    fh = backup.build_workspace_zip(seeded)
    with zipfile.ZipFile(fh) as zf:
        meta = json.loads(zf.read("metadata.json"))
    ids = {r["id"] for r in meta["tables"]["pf_entries"]}
    assert "ghost" not in ids
    conn2.rollback()
    conn2.close()


def test_backup_keep_prunes_to_newest_n(ws, monkeypatch):
    """Three POSTs a second apart (a real filename resolution of 1s) must leave only the newest 2."""
    import itertools
    from datetime import UTC as _UTC
    from datetime import datetime as _real_datetime
    from datetime import timedelta as _timedelta

    monkeypatch.setenv("AURUM_BACKUP_KEEP", "2")
    base = _real_datetime(2026, 1, 1, tzinfo=_UTC)
    counter = itertools.count()

    class FakeDatetime(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return base + _timedelta(seconds=next(counter))

    monkeypatch.setattr(backup, "datetime", FakeDatetime)
    for _ in range(3):
        backup.create_full_backup()
    files = list((backup.settings().data_dir / "backups").glob("*.zip"))
    assert len(files) == 2


def test_download_backup_rejects_path_traversal():
    client = TestClient(create_app())
    resp = client.get("/api/backups/..%2Fx")
    # The core path guard (docs/SECURITY.md) rejects a decoded ".." segment before any router runs.
    assert resp.status_code == 400
    assert resp.json() == {"error": "bad_path"}


def test_full_backup_route_lists_in_get_backups():
    client = TestClient(create_app())
    resp = client.post("/api/backup")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert re.match(r"^aurum-\d{8}-\d{6}\.zip$", body["name"])
    assert body["sha256"] and body["size"] > 0
    names = {b["name"] for b in client.get("/api/backups").json()}
    assert body["name"] in names


def test_workspace_backup_zip_route_404_for_unknown_ws():
    client = TestClient(create_app())
    resp = client.get("/api/workspaces/does-not-exist/backup.zip")
    assert resp.status_code == 404


def test_workspace_backup_zip_route_streams_a_real_zip(seeded):
    client = TestClient(create_app())
    resp = client.get(f"/api/workspaces/{seeded}/backup.zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment; filename=aurum-bws-" in resp.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert "movimientos.csv" in zf.namelist()


def test_movimientos_csv_route(seeded):
    client = TestClient(create_app())
    resp = client.get(f"/api/workspaces/{seeded}/movimientos.csv")
    assert resp.status_code == 200
    assert resp.content.startswith("﻿".encode())
