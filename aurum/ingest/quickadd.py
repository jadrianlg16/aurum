"""Rule-based quick-add parser: '250 tacos comida' → a pf entry preview.

Grammar (loose, order-tolerant):
    [-]<amount>[,<amount>][.<cents>] [<currency>] <word> [<word> ...]   or   <words> <amount>
The amount is the first token that looks like a number (optional leading '-' or '$', optional 3-letter
currency after it). A negative amount — or a word like "ingreso"/"depósito"/"cobro" — means income.
The remaining words pick the category (``pf.labels.match_label``: whole-word, accent-insensitive, scoped
to the workspace) and the account (a whole-word match on a pf account's name or institution); what is
left becomes the payee. Date = today.

Account resolution: an explicit ``account_id`` (404 when unknown) → a name/institution word match
→ the single non-archived cash/checking account → ``NoAccount`` (400 "Primero agrega una cuenta").
Commit goes through ``pf.entries.create_entry(source="quickadd")`` — an editable movement, no inbox row.

``parse_quickadd(text, ws_id, base_currency)`` is the legacy wrapper (Telegram + insights) returning a
``QuickAddResult`` with a ``Transaction``: it uses the resolved pf account when there is one and otherwise
the old ``Assets:Cash`` proposal for the inbox path only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import Amount, q2
from ..ledger.base import Posting, Transaction

_AMOUNT_RE = re.compile(r"^-?\$?(\d[\d,]*)(?:\.(\d{1,2}))?$")
_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")
_KNOWN_CURRENCIES = {"MXN", "USD", "EUR", "CAD", "GBP"}
_INCOME_WORDS = {"ingreso", "deposito", "cobro", "income"}
_DEFAULT_TYPES = ("cash", "checking")


class NoAccount(ValueError):
    """No pf account could be resolved for the text → 400."""


@dataclass
class QuickAddPreview:
    entry: object  # pf.entries.EntryIn
    account_name: str
    label_name: str | None
    confidence: float
    warnings: list[str] = field(default_factory=list)
    account: dict | None = None
    label: dict | None = None


@dataclass
class QuickAddResult:
    """Legacy shape (Telegram/inbox path)."""

    transaction: Transaction
    confidence: float
    warnings: list[str] = field(default_factory=list)


def _fold(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in norm if not unicodedata.combining(c)).lower()


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9ñ]+", _fold(text)) if w]


@dataclass
class ParsedText:
    amount: Decimal  # magnitude
    negative: bool
    currency: str | None
    words: list[str]  # remaining original tokens (not folded)


def parse_text(text: str) -> ParsedText:
    tokens = (text or "").strip().split()
    if not tokens:
        raise ValueError("empty quick-add text")
    idx = next((i for i, tok in enumerate(tokens) if _AMOUNT_RE.match(tok[1:] if tok.startswith("-") else tok)), None)
    if idx is None:
        raise ValueError(f"could not find an amount in {text!r}")
    raw_amount = tokens[idx]
    negative = raw_amount.startswith("-")
    body = raw_amount[1:] if negative else raw_amount
    m = _AMOUNT_RE.match(body)
    assert m is not None
    whole, cents = m.groups()
    amount_str = whole.replace(",", "") + ("." + cents if cents else "")
    try:
        amount = Decimal(amount_str)
    except InvalidOperation as e:
        raise ValueError(f"invalid amount: {amount_str!r}") from e
    if amount <= 0:
        raise ValueError("amount must be greater than zero")
    rest = tokens[:idx] + tokens[idx + 1:]
    currency = None
    if len(tokens) > idx + 1 and _CURRENCY_RE.match(tokens[idx + 1]) and tokens[idx + 1].upper() in _KNOWN_CURRENCIES:
        currency = tokens[idx + 1].upper()
        rest = tokens[:idx] + tokens[idx + 2:]
    return ParsedText(amount=q2(amount), negative=negative, currency=currency, words=rest)


def resolve_account(ws_id: str, words: list[str], account_id: str | None = None) -> tuple[dict, set[str]]:
    """→ (pf account row, folded words consumed by the match). KeyError for an unknown id, NoAccount when
    nothing resolves."""
    from ..pf import accounts_admin

    if account_id:
        row = accounts_admin.get_row(ws_id, account_id)  # KeyError → 404
        return row, set()
    rows = accounts_admin.list_rows(ws_id, include_archived=False)
    folded = set(_words(" ".join(words)))
    best: tuple[int, dict, set[str]] | None = None
    for row in rows:
        for source in (row["name"], row.get("institution") or ""):
            keys = set(_words(source))
            if not keys:
                continue
            hit = keys & folded
            if hit and (best is None or len(hit) > best[0]):
                best = (len(hit), row, hit)
    if best is not None:
        return best[1], best[2]
    defaults = [r for r in rows if r["type"] in _DEFAULT_TYPES]
    if len(defaults) == 1:
        return defaults[0], set()
    raise NoAccount(i18n_t("pf.quickadd.no_account", ws_lang(ws_id)))


def parse_entry(ws_id: str, text: str, account_id: str | None = None, today: date | None = None) -> QuickAddPreview:
    from ..pf import entries as pf_entries
    from ..pf import labels as pf_labels
    from ..pf import store as pf_store

    lang = ws_lang(ws_id)
    parsed = parse_text(text)
    warnings: list[str] = []
    account, used = resolve_account(ws_id, parsed.words, account_id)
    folded_words = _words(" ".join(parsed.words))
    kind = "income" if parsed.negative or any(w in _INCOME_WORDS for w in folded_words) else "expense"

    label = pf_labels.match_label(ws_id, " ".join(parsed.words))
    label_words: set[str] = set()
    if label is not None:
        if label["kind"] != kind:
            warnings.append(
                i18n_t("pf.quickadd.label_kind_dropped", lang, label=label["name"],
                       kind=i18n_t(f"pf.entry.kind_plural.{label['kind']}", lang))
            )
            label = None
        else:
            for cand in (label["name"], *label["aliases"]):
                cw = set(_words(cand))
                if cw and cw <= set(folded_words):
                    label_words |= cw
    if label is None:
        warnings.append(i18n_t("pf.quickadd.no_label", lang))

    consumed = used | label_words | _INCOME_WORDS
    remaining = [w for w in parsed.words if _words(w) and _words(w)[0] not in consumed]
    payee = " ".join(remaining) if remaining else None
    confidence = 0.9 if label is not None else 0.5
    if account_id is None and not used and account["type"] in _DEFAULT_TYPES:
        confidence = min(confidence, 0.8)

    entry = pf_entries.EntryIn(
        kind=kind,
        date=(today or date.today()).isoformat(),
        amount=Amount(amount=parsed.amount, currency=parsed.currency or account["currency"] or pf_store.base_currency(ws_id)),
        account_id=account["id"],
        label_id=label["id"] if label else None,
        payee=payee,
        note=None,
        tags=[],
        source="quickadd",
    )
    return QuickAddPreview(
        entry=entry, account_name=account["name"], label_name=label["name"] if label else None,
        confidence=confidence, warnings=warnings, account=account, label=label,
    )


def transaction_for(preview: QuickAddPreview, text: str) -> Transaction:
    """The ledger transaction a commit would write (for the ``proposed`` key of the route response)."""
    entry = preview.entry
    account = preview.account or {}
    label_account = (preview.label or {}).get("account") or ("Income:Other" if entry.kind == "income" else "Expenses:Other")
    signed = entry.amount.amount if entry.kind == "income" else -entry.amount.amount
    meta = {"source": "quickadd", "raw_text": text}
    if preview.label_name:
        meta["label"] = preview.label_name
    return Transaction(
        date=date.fromisoformat(entry.date),
        payee=entry.payee,
        narration=text,
        postings=[
            Posting(account=account.get("account", "Assets:Cash"), amount=Amount(amount=signed, currency=entry.amount.currency)),
            Posting(account=label_account, amount=None),
        ],
        meta=meta,
    )


def parse_quickadd(text: str, ws_id: str, base_currency: str = "MXN") -> QuickAddResult:
    """Legacy wrapper: a ``Transaction`` proposal for the inbox path (Telegram). With a resolvable pf account
    the proposal matches what a commit would write; without one it falls back to ``Assets:Cash``."""
    from ..pf import labels as pf_labels

    try:
        preview = parse_entry(ws_id, text)
        return QuickAddResult(transaction=transaction_for(preview, text), confidence=preview.confidence,
                              warnings=list(preview.warnings))
    except (NoAccount, KeyError):
        pass
    parsed = parse_text(text)
    currency = parsed.currency or base_currency
    negative = parsed.negative
    warnings: list[str] = []
    label = pf_labels.match_label(ws_id, " ".join(parsed.words))
    kind = "income" if negative else "expense"
    if label is not None and label["kind"] != kind:
        label = None
    if label is not None:
        label_account = label["account"]
        confidence = 0.9
    else:
        label_account = "Income:Uncategorized" if negative else "Expenses:Uncategorized"
        confidence = 0.5
        warnings.append("no matching label; using Uncategorized")
    if not parsed.words:
        warnings.append("no payee/label words found")
    signed = parsed.amount if negative else -parsed.amount
    meta = {"source": "quickadd", "raw_text": text}
    if label is not None:
        meta["label"] = label["name"]
    txn = Transaction(
        date=date.today(),
        payee=" ".join(parsed.words) or None,
        narration=text,
        postings=[
            Posting(account="Assets:Cash", amount=Amount(amount=signed, currency=currency)),
            Posting(account=label_account, amount=None),
        ],
        meta=meta,
    )
    return QuickAddResult(transaction=txn, confidence=confidence, warnings=warnings)


def llm_quickadd_hook(text: str, ws_id: str):  # pragma: no cover - opt-in path, not implemented here
    """Optional LLM-assisted quick-add. Enabled only via AURUM_LLM_QUICKADD=1.

    Calls into an ``aurum.llm`` quick-add module when one is importable and otherwise raises
    NotImplementedError so callers fall back to the rule-based parser.
    """
    try:
        from ..llm import quickadd as llm_module  # type: ignore
    except ImportError as e:
        raise NotImplementedError("aurum.llm not available") from e
    return llm_module.parse(text, ws_id)
