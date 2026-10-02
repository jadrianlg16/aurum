"""Two-layer labels ("categorías"): a friendly user label maps to a ledger account leaf + a tax treatment
per jurisdiction. A default MX personal set (25 expense/
transfer + 5 income = 30) is seeded per workspace on first access, idempotently by name. Tax flags are set
conservatively; anything not settled law is documented `(verify)` in docs/modules/pf.md.

Every label carries ``kind`` (``expense`` | ``income`` | ``transfer`` — the last one is the
backfilled ``Assets:`` labels, hidden from pickers) and ``archived``. ``POST /labels {name, kind, parent?}``
derives the ledger account server-side (``Expenses:<Slug>`` / ``Income:<Slug>``, ``<parent.account>:<Slug>``
under a parent, numeric suffix on collision) and validates it against the Beancount grammar; advanced
callers may still send ``account`` explicitly. Deleting a label that any live entry or split references is
refused (``LabelInUse`` → 409).

``pf_labels`` columns: ``id, ws_id, name, aliases (JSON list[str]), account, icon, tax (JSON), sort,
kind, archived``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..ledger.base import validate_account
from . import store

LabelKind = Literal["expense", "income", "transfer"]

router = APIRouter()


def _mx(isr_deductible: bool, iva_creditable: bool, requires_cfdi: bool, personal_deduction: bool) -> dict:
    return {
        "isr_deductible": isr_deductible,
        "iva_creditable": iva_creditable,
        "requires_cfdi": requires_cfdi,
        "personal_deduction": personal_deduction,
    }


def _us(schedule_c: bool, itemized: bool) -> dict:
    return {"schedule_c": schedule_c, "itemized": itemized}


# (name, account, icon, aliases, MX tax, US tax)
# MX personal_deduction = art. 151 LISR "deducciones personales" (anual). isr_deductible here means
# "deductible as a business expense against RESICO/Schedule-C income" — most personal-life categories
# are False; a handful are plausibly business expenses for a freelancer and marked accordingly.
_DEFAULT_MX_PERSONAL: list[tuple[str, str, str, list[str], dict, dict]] = [
    ("Comida fuera", "Expenses:Food:DiningOut", "🍽️", ["restaurante", "comida"],
     _mx(False, False, False, False), _us(False, False)),
    ("Súper", "Expenses:Food:Groceries", "🛒", ["super", "supermercado", "abarrotes"],
     _mx(False, False, False, False), _us(False, False)),
    ("Renta/Hipoteca", "Expenses:Housing:RentMortgage", "🏠", ["renta", "hipoteca", "infonavit"],
     _mx(False, False, False, False), _us(False, False)),
    ("Servicios (luz/agua/gas)", "Expenses:Housing:Utilities", "💡", ["luz", "agua", "gas", "cfe"],
     _mx(False, True, True, False), _us(False, False)),
    ("Internet/Teléfono", "Expenses:Housing:Internet", "📶", ["internet", "telefono", "celular"],
     _mx(True, True, True, False), _us(False, False)),  # (verify) home-office proration for freelancers
    ("Transporte/Gasolina", "Expenses:Transport:Fuel", "⛽", ["gasolina", "transporte"],
     _mx(True, True, True, False), _us(False, False)),  # (verify) business-use portion only
    ("Uber/Taxi", "Expenses:Transport:Rideshare", "🚕", ["uber", "taxi", "didi"],
     _mx(False, False, True, False), _us(False, False)),
    ("Salud/Médico", "Expenses:Health:Medical", "🩺", ["medico", "doctor", "consulta", "salud"],
     _mx(False, False, True, True), _us(False, True)),  # (verify) 7.5% AGI floor for US itemized
    ("Medicinas", "Expenses:Health:Medicine", "💊", ["medicina", "farmacia"],
     _mx(False, False, True, True), _us(False, True)),  # (verify) MX requires pago electrónico + factura
    ("Educación/Colegiaturas", "Expenses:Education:Tuition", "🎓", ["colegiatura", "escuela", "educacion"],
     _mx(False, False, True, True), _us(False, False)),  # (verify) MX cap by school level, no public school
    ("Software/Suscripciones", "Expenses:Work:Software", "💻", ["software", "suscripcion", "saas"],
     _mx(True, True, True, False), _us(True, False)),
    ("Equipo de trabajo", "Expenses:Work:Equipment", "🖥️", ["equipo", "laptop", "herramienta"],
     _mx(True, True, True, False), _us(True, False)),
    ("Ropa", "Expenses:Personal:Clothing", "👕", ["ropa", "zapatos"],
     _mx(False, False, False, False), _us(False, False)),
    ("Entretenimiento", "Expenses:Personal:Entertainment", "🎬", ["cine", "streaming", "entretenimiento"],
     _mx(False, False, False, False), _us(False, False)),
    ("Viajes", "Expenses:Personal:Travel", "✈️", ["viaje", "vacaciones", "hotel", "vuelo"],
     _mx(False, False, False, False), _us(False, False)),
    ("Seguros", "Expenses:Insurance", "🛡️", ["seguro"],
     _mx(False, False, True, True), _us(False, False)),  # (verify) only seguro de gastos médicos qualifies
    ("Mascotas", "Expenses:Personal:Pets", "🐾", ["mascota", "veterinario"],
     _mx(False, False, False, False), _us(False, False)),
    ("Regalos", "Expenses:Personal:Gifts", "🎁", ["regalo"],
     _mx(False, False, False, False), _us(False, False)),
    ("Impuestos", "Expenses:Taxes", "🧾", ["impuesto", "isr", "iva"],
     _mx(False, False, False, False), _us(False, False)),
    ("Comisiones bancarias", "Expenses:Fees:Bank", "🏦", ["comision", "banco"],
     _mx(True, False, False, False), _us(False, False)),  # (verify) deductible when tied to business account
    ("Ahorro/Inversión", "Assets:Investments:General", "💰", ["ahorro", "inversion", "afore", "ppr"],
     _mx(False, False, False, False), _us(False, False)),  # (verify) PPR/Afore contributions: see PPR label note
    ("Transferencia", "Assets:Transfers", "🔁", ["transferencia", "traspaso"],
     _mx(False, False, False, False), _us(False, False)),
    ("Ingreso freelance", "Income:Freelance", "🧑‍💻", ["freelance", "honorarios", "factura"],
     _mx(False, False, False, False), _us(True, False)),
    ("Ingreso plataforma", "Income:Platform", "📱", ["plataforma", "uber eats", "didi food"],
     _mx(False, False, False, False), _us(True, False)),
    ("Otros", "Expenses:Other", "❔", ["otro", "varios"],
     _mx(False, False, False, False), _us(False, False)),
]



# income seeds: (name, account, icon, aliases)
_DEFAULT_INCOME: list[tuple[str, str, str, list[str]]] = [
    ("Sueldo/Nómina", "Income:Salary", "💼", ["sueldo", "nomina", "nómina", "salario", "quincena"]),
    ("Renta cobrada", "Income:Rent", "🏘️", ["renta cobrada", "alquiler"]),
    ("Intereses", "Income:Interest", "📈", ["intereses", "rendimiento"]),
    ("Dividendos", "Income:Dividends", "💹", ["dividendo", "dividendos"]),
    ("Otros ingresos", "Income:Other", "➕", ["otro ingreso", "otros ingresos"]),
]


def kind_for_account(account: str) -> str:
    if account.startswith("Income:"):
        return "income"
    if account.startswith("Expenses:"):
        return "expense"
    return "transfer"


class Label(BaseModel):
    """Full write shape (``organizer/organize.py`` builds it with only the original fields — ``kind``,
    ``archived`` and ``parent`` are optional)."""

    id: str = ""
    ws_id: str = ""
    name: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list)
    account: str | None = None
    icon: str | None = None
    tax: dict[str, Any] = Field(default_factory=dict)
    sort: int = 0
    kind: LabelKind | None = None
    archived: bool = False
    parent: str | None = None  # input only: parent label id


class LabelPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    icon: str | None = None
    aliases: list[str] | None = None
    archived: bool | None = None
    tax: dict[str, Any] | None = None
    sort: int | None = None


class LabelInUse(Exception):
    """A non-voided entry (or split) still references the label → 409."""


def _row(r) -> dict:
    d = store.row_to_dict(r)
    d["aliases"] = store.loads(d.get("aliases"), [])
    d["tax"] = store.loads(d.get("tax"), {})
    d["archived"] = bool(d.get("archived", 0))
    d["kind"] = d.get("kind") or kind_for_account(d["account"])
    return d


def _existing_names(conn, ws_id: str) -> set[str]:
    return {r["name"] for r in conn.execute("SELECT name FROM pf_labels WHERE ws_id=?", (ws_id,)).fetchall()}


def seed_defaults(ws_id: str) -> None:
    """Idempotent by name: a workspace that already has the 25 original labels gains only the income seeds."""
    conn = store.db()
    names = _existing_names(conn, ws_id)
    (max_sort,) = conn.execute("SELECT COALESCE(MAX(sort), -1) FROM pf_labels WHERE ws_id=?", (ws_id,)).fetchone()
    sort = int(max_sort) + 1
    added = False
    for name, account, icon, aliases, mx, us in _DEFAULT_MX_PERSONAL:
        if name in names:
            continue
        conn.execute(
            "INSERT INTO pf_labels (id, ws_id, name, aliases, account, icon, tax, sort, kind, archived) "
            "VALUES (?,?,?,?,?,?,?,?,?,0)",
            (store.new_id("lbl"), ws_id, name, store.dumps(aliases), account, icon,
             store.dumps({"MX": mx, "US": us}), sort, kind_for_account(account)),
        )
        sort += 1
        added = True
    for name, account, icon, aliases in _DEFAULT_INCOME:
        if name in names:
            continue
        conn.execute(
            "INSERT INTO pf_labels (id, ws_id, name, aliases, account, icon, tax, sort, kind, archived) "
            "VALUES (?,?,?,?,?,?,?,?,?,0)",
            (store.new_id("lbl"), ws_id, name, store.dumps(aliases), account, icon,
             store.dumps({"MX": _mx(False, False, False, False), "US": _us(False, False)}), sort, "income"),
        )
        sort += 1
        added = True
    if added:
        conn.commit()


def list_labels(ws_id: str, kind: str | None = None, include_archived: bool = False) -> list[dict]:
    seed_defaults(ws_id)
    conn = store.db()
    sql = "SELECT * FROM pf_labels WHERE ws_id=?"
    args: list[object] = [ws_id]
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if not include_archived:
        sql += " AND archived=0"
    sql += " ORDER BY sort, name"
    return [_row(r) for r in conn.execute(sql, args).fetchall()]


def get_label(ws_id: str, label_id: str) -> dict:
    conn = store.db()
    row = conn.execute("SELECT * FROM pf_labels WHERE ws_id=? AND id=?", (ws_id, label_id)).fetchone()
    if row is None:
        raise KeyError(label_id)
    return _row(row)


def _slug(name: str) -> str:
    from .accounts_admin import slugify

    return slugify(name)


def derive_account(ws_id: str, kind: str, name: str, parent: dict | None = None) -> str:
    """``Expenses:<Slug>`` / ``Income:<Slug>`` (or ``<parent.account>:<Slug>``), numeric suffix when another
    label already owns that account. Pure function of (existing labels, kind, name, parent)."""
    conn = store.db()
    existing = {r["account"] for r in conn.execute("SELECT account FROM pf_labels WHERE ws_id=?", (ws_id,)).fetchall()}
    if parent is not None:
        base = f"{parent['account']}:{_slug(name)}"
    else:
        root = "Income" if kind == "income" else "Expenses"
        base = f"{root}:{_slug(name)}"
    candidate = base
    n = 2
    while candidate in existing:
        candidate = f"{base}{n}"
        n += 1
    return candidate


def _resolve_account_and_kind(ws_id: str, label: Label) -> tuple[str, str]:
    parent = None
    if label.parent:
        parent = get_label(ws_id, label.parent)  # KeyError → 404
    if label.account:
        account = validate_account(label.account.strip())
        kind = label.kind or kind_for_account(account)
        if kind != kind_for_account(account):
            raise ValueError(f"account {account} is not a {kind} account")
        return account, kind
    kind = label.kind or (parent["kind"] if parent else None)
    if kind not in ("expense", "income"):
        raise ValueError("kind must be 'expense' or 'income' (or send an explicit account)")
    if parent is not None and parent["kind"] != kind:
        raise ValueError("parent label has a different kind")
    return validate_account(derive_account(ws_id, kind, label.name, parent)), kind


def create_label(ws_id: str, label: Label) -> dict:
    seed_defaults(ws_id)
    account, kind = _resolve_account_and_kind(ws_id, label)
    conn = store.db()
    label_id = store.new_id("lbl")
    (max_sort,) = conn.execute("SELECT COALESCE(MAX(sort), -1) FROM pf_labels WHERE ws_id=?", (ws_id,)).fetchone()
    conn.execute(
        "INSERT INTO pf_labels (id, ws_id, name, aliases, account, icon, tax, sort, kind, archived) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (label_id, ws_id, label.name.strip(), store.dumps(label.aliases), account, label.icon,
         store.dumps(label.tax), label.sort or max_sort + 1, kind, int(label.archived)),
    )
    conn.commit()
    return get_label(ws_id, label_id)


def update_label(ws_id: str, label_id: str, label: Label | LabelPatch) -> dict:
    existing = get_label(ws_id, label_id)
    if isinstance(label, LabelPatch):
        changed = label.model_dump(exclude_unset=True)
        merged = {**existing, **{k: v for k, v in changed.items() if v is not None or k == "icon"}}
        account, kind = existing["account"], existing["kind"]
    else:
        merged = {
            "name": label.name, "aliases": label.aliases, "icon": label.icon, "tax": label.tax,
            "sort": label.sort, "archived": label.archived,
        }
        if label.account and label.account != existing["account"]:
            account = validate_account(label.account.strip())
            kind = label.kind or kind_for_account(account)
            if kind != kind_for_account(account):
                raise ValueError(f"account {account} is not a {kind} account")
        else:
            account, kind = existing["account"], label.kind or existing["kind"]
    conn = store.db()
    conn.execute(
        "UPDATE pf_labels SET name=?, aliases=?, account=?, icon=?, tax=?, sort=?, kind=?, archived=? "
        "WHERE ws_id=? AND id=?",
        (str(merged["name"]).strip(), store.dumps(merged["aliases"]), account, merged.get("icon"),
         store.dumps(merged.get("tax") or {}), int(merged.get("sort") or 0), kind, int(bool(merged.get("archived"))),
         ws_id, label_id),
    )
    conn.commit()
    return get_label(ws_id, label_id)


def label_in_use(ws_id: str, label_id: str) -> bool:
    conn = store.db()
    row = conn.execute(
        "SELECT 1 FROM pf_entries WHERE ws_id=? AND voided=0 AND (label_id=? OR splits LIKE ?) LIMIT 1",
        (ws_id, label_id, f'%"label_id": "{label_id}"%'),
    ).fetchone()
    return row is not None


def delete_label(ws_id: str, label_id: str) -> None:
    get_label(ws_id, label_id)
    if label_in_use(ws_id, label_id):
        raise LabelInUse(f"label {label_id} is used by entries; archive it instead")
    conn = store.db()
    cur = conn.execute("DELETE FROM pf_labels WHERE ws_id=? AND id=?", (ws_id, label_id))
    conn.commit()
    if cur.rowcount == 0:
        raise KeyError(label_id)


# --------------------------------------------------------------------------- matching


def _fold(text: str) -> str:
    """Lowercase, accents stripped, non-alphanumerics → spaces (whole-word matching over this)."""
    norm = unicodedata.normalize("NFKD", text or "")
    norm = "".join(c for c in norm if not unicodedata.combining(c)).lower()
    return " " + re.sub(r"[^a-z0-9ñ]+", " ", norm).strip() + " "


def match_label(ws_id: str, text: str, kind: str | None = None) -> dict | None:
    """Best label by whole-word, accent-insensitive name/alias match (``viaje a europa`` never → ``Ropa``).
    Longest matching candidate wins; ties keep the first label by sort order."""
    haystack = _fold(text)
    best: dict | None = None
    best_score = 0
    for lbl in list_labels(ws_id, kind=kind):
        candidates = [lbl["name"], *lbl["aliases"]]
        for cand in candidates:
            needle = _fold(cand)
            if needle.strip() and needle in haystack:
                score = len(needle.strip())
                if score > best_score:
                    best_score = score
                    best = lbl
    return best


# --- router -----------------------------------------------------------------------------------


class MatchRequest(BaseModel):
    text: str


@router.get("/{ws}/labels")
def api_list_labels(
    ws: str,
    kind: Literal["expense", "income", "transfer"] | None = Query(default=None),
    include_archived: bool = False,
) -> list[dict]:
    return list_labels(ws, kind=kind, include_archived=include_archived)


@router.post("/{ws}/labels")
def api_create_label(ws: str, label: Label) -> dict:
    try:
        return create_label(ws, label)
    except KeyError as e:
        raise HTTPException(404, f"parent label {label.parent} not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/{ws}/labels/{label_id}")
def api_update_label(ws: str, label_id: str, label: LabelPatch) -> dict:
    try:
        return update_label(ws, label_id, label)
    except KeyError as e:
        raise HTTPException(404, f"label {label_id} not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/{ws}/labels/{label_id}")
def api_delete_label(ws: str, label_id: str) -> dict:
    try:
        delete_label(ws, label_id)
    except KeyError as e:
        raise HTTPException(404, f"label {label_id} not found") from e
    except LabelInUse as e:
        raise HTTPException(409, str(e)) from e
    return {"ok": True}


@router.post("/{ws}/labels/match")
def api_match_label(ws: str, body: MatchRequest) -> dict:
    match = match_label(ws, body.text)
    return {"label": match}
