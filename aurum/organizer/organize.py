"""Bulk relabel + "remember this" rules.

``POST /organize`` moves the expense posting of a transaction to the label's account by calling the
ledger router's own ``update_transaction`` in-process — the ledger stays the single writer, and the
edit lands in the audit log like any other. With ``create_rule`` the normalized merchant is appended
to the label's ``aliases`` (through ``aurum.pf.labels.update_label``, never a direct table write) and
recorded in ``organizer_rules``, so the ingest quick-add path auto-labels the next one.
"""

from __future__ import annotations

from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import Amount
from . import normalize, store


def list_rules(ws_id: str) -> list[dict]:
    conn = store.db()
    rows = conn.execute(
        "SELECT id, pattern, label_id, created_at, hits FROM organizer_rules WHERE ws_id=? "
        "ORDER BY created_at",
        (ws_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_rule(ws_id: str, rule_id: str) -> None:
    conn = store.db()
    cur = conn.execute("DELETE FROM organizer_rules WHERE ws_id=? AND id=?", (ws_id, rule_id))
    conn.commit()
    if cur.rowcount == 0:
        raise KeyError(rule_id)


def create_rule(ws_id: str, pattern: str, label_id: str) -> dict:
    """Persist the rule and teach ``pf_labels`` the alias (that is what auto-labelling reads)."""
    conn = store.db()
    row = conn.execute(
        "SELECT id FROM organizer_rules WHERE ws_id=? AND pattern=?", (ws_id, pattern)
    ).fetchone()
    if row is None:
        rule_id = store.new_id("rule")
        conn.execute(
            "INSERT INTO organizer_rules (id, ws_id, pattern, label_id, created_at, hits) "
            "VALUES (?,?,?,?,?,0)",
            (rule_id, ws_id, pattern, label_id, store.now()),
        )
        conn.commit()
    else:
        rule_id = row["id"]
        conn.execute("UPDATE organizer_rules SET label_id=? WHERE id=?", (label_id, rule_id))
        conn.commit()
    _teach_label_alias(ws_id, pattern, label_id)
    return {"id": rule_id, "pattern": pattern, "label_id": label_id}


def _teach_label_alias(ws_id: str, pattern: str, label_id: str) -> None:
    try:
        from ..pf import labels as pf_labels
    except Exception:  # noqa: BLE001
        return
    try:
        label = pf_labels.get_label(ws_id, label_id)
    except KeyError:
        return
    alias = pattern.lower()
    if alias in [a.lower() for a in label["aliases"]]:
        return
    body = pf_labels.Label(
        name=label["name"], aliases=[*label["aliases"], alias], account=label["account"],
        icon=label["icon"], tax=label["tax"], sort=label["sort"],
    )
    pf_labels.update_label(ws_id, label_id, body)


def match_rule(ws_id: str, description: str) -> str | None:
    """label_id for a description, via the organizer rules (normalized merchant equality)."""
    merchant = normalize.normalize(description)
    conn = store.db()
    row = conn.execute(
        "SELECT id, label_id FROM organizer_rules WHERE ws_id=? AND pattern=?", (ws_id, merchant)
    ).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE organizer_rules SET hits=hits+1 WHERE id=?", (row["id"],))
    conn.commit()
    return row["label_id"]


def _relabel_txn(ws_id: str, txn_id: str, account: str) -> dict:
    """Point the transaction's expense posting at ``account`` (ledger router does the write)."""
    from ..ledger.base import get_ledger
    from ..ledger.router import update_transaction

    txn = None
    for candidate in get_ledger().journal(ws_id):
        if txn_id in (candidate.links or []):
            txn = candidate
            break
    if txn is None:
        raise KeyError(txn_id)
    postings = []
    moved_from = None
    for p in txn.postings:
        if p.account.startswith("Expenses:") and moved_from is None:
            moved_from = p.account
            postings.append(p.model_copy(update={"account": account}))
        else:
            postings.append(p)
    if moved_from is None:
        raise ValueError(f"transaction {txn_id} has no Expenses: posting to relabel")
    new_txn = txn.model_copy(update={"postings": postings})
    update_transaction(ws_id, txn_id, new_txn)
    return {"txn_id": txn_id, "from": moved_from, "to": account}


def organize(ws_id: str, assignments: list[dict], lang: str | None = None) -> dict:
    """Relabel transactions and, where asked, remember the merchant for next time."""
    from ..pf import labels as pf_labels

    lang = lang or ws_lang(ws_id)
    explain = Explain(summary=i18n_t("organizer.organize", lang))
    relabelled: list[dict] = []
    rules: list[dict] = []
    errors: list[dict] = []
    for item in assignments:
        txn_id = item["txn_id"]
        label_id = item["label_id"]
        try:
            label = pf_labels.get_label(ws_id, label_id)
        except KeyError:
            errors.append({"txn_id": txn_id, "error": f"label {label_id} not found"})
            continue
        payee = _payee_for(ws_id, txn_id)
        try:
            relabelled.append({**_relabel_txn(ws_id, txn_id, label["account"]), "label_id": label_id})
        except (KeyError, ValueError) as e:
            errors.append({"txn_id": txn_id, "error": str(e)})
            continue
        explain.add_step(txn_id, label["name"], formula=f"posting → {label['account']}")
        if item.get("create_rule") and payee:
            rules.append(create_rule(ws_id, normalize.normalize(payee), label_id))
            explain.add_step("rule", normalize.normalize(payee), formula=f"→ {label['name']}")
    explain.add_step("relabelled", len(relabelled))
    explain.add_step("rules_created", len(rules))
    return {"relabelled": relabelled, "rules": rules, "errors": errors, "explain": explain.model_dump()}


def _payee_for(ws_id: str, txn_id: str) -> str | None:
    from ..ledger.base import get_ledger

    for txn in get_ledger().journal(ws_id):
        if txn_id in (txn.links or []):
            return txn.payee or txn.narration
    return None


def apply_rules_to_quickadd(ws_id: str, text: str, amount: Amount | None = None) -> dict | None:
    """What a new quick-add line would be labelled as — the auto-label the rules produce.

    Returns ``{"label_id", "label_name", "account", "source": "rule"|"alias"}`` or None. Organizer
    rules win over the generic pf alias match because they were created by an explicit user action.
    """
    label_id = match_rule(ws_id, text)
    try:
        from ..pf import labels as pf_labels
    except Exception:  # noqa: BLE001
        return None
    if label_id:
        try:
            label = pf_labels.get_label(ws_id, label_id)
        except KeyError:
            return None
        return {"label_id": label_id, "label_name": label["name"], "account": label["account"],
                "source": "rule"}
    match = pf_labels.match_label(ws_id, text)
    if match is None:
        return None
    return {"label_id": match["id"], "label_name": match["name"], "account": match["account"],
            "source": "alias"}
