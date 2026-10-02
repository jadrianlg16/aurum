from __future__ import annotations

from aurum.pf import labels


def test_seed_defaults_creates_30_labels():
    """25 expense/transfer labels + 5 income seeds."""
    rows = labels.list_labels("ws1")
    assert len(rows) == 30
    names = {r["name"] for r in rows}
    assert "Comida fuera" in names and "Otros" in names and "Sueldo/Nómina" in names
    # seeding twice must not duplicate
    labels.seed_defaults("ws1")
    assert len(labels.list_labels("ws1")) == 30
    assert {r["kind"] for r in rows} == {"expense", "income", "transfer"}


def test_label_crud():
    created = labels.create_label(
        "ws1", labels.Label(name="Custom", account="Expenses:Custom", tax={"MX": {}, "US": {}})
    )
    assert created["name"] == "Custom"
    assert created["kind"] == "expense" and created["archived"] is False
    updated = labels.update_label(
        "ws1", created["id"], labels.Label(name="Custom2", account="Expenses:Custom", tax={"MX": {}, "US": {}})
    )
    assert updated["name"] == "Custom2"
    labels.delete_label("ws1", created["id"])
    assert created["id"] not in {r["id"] for r in labels.list_labels("ws1")}


def test_match_label_by_alias():
    match = labels.match_label("ws1", "250 tacos comida")
    assert match is not None
    assert match["name"] == "Comida fuera"


def test_router_endpoints(client):
    r = client.get("/api/pf/wsx/labels")
    assert r.status_code == 200
    assert len(r.json()) == 30
    r = client.post("/api/pf/wsx/labels/match", json={"text": "1200 uber trabajo"})
    assert r.status_code == 200
    assert r.json()["label"]["name"] == "Uber/Taxi"
