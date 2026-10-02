"""Business charts of accounts: persona moral (MX) and US LLC.

The two business templates live in ``aurum/business/templates/``, next to the code that uses them,
rather than in ``aurum/ledger/templates/``. ``BeancountLedger.apply_template`` resolves a template *by name*
inside its own directory and has no hook for an external path, so this module reproduces that method's
two public effects instead of reaching into it:

1. ``store.ensure_files(ws, currency)`` — create ``main.beancount`` / ``accounts.beancount``.
2. merge the template's ``open`` directives into ``accounts.beancount`` (``store.accounts_path``),
   preserving whatever is already open and never lowering an existing open date.

Both ``ensure_files`` and ``accounts_path`` are public methods of the store. For a store that has
neither (``InMemoryLedger``), the accounts are registered through ``open_account``. The operation is
idempotent, so it is safe to re-apply a template to a live workspace.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ..ledger.base import LedgerStore, get_ledger

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
EPOCH = date(2000, 1, 1)

TEMPLATES = {
    "mx_persona_moral": "MXN",
    "us_llc": "USD",
}


class TemplateNotFound(FileNotFoundError):
    pass


def template_path(name: str) -> Path:
    path = TEMPLATES_DIR / f"{name}.beancount"
    if not path.exists() or name not in TEMPLATES:
        raise TemplateNotFound(f"no business chart-of-accounts template named {name!r}")
    return path


def template_accounts(name: str) -> list[str]:
    """Account names from a template's ``open`` directives, in file order."""
    out: list[str] = []
    for line in template_path(name).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "open":
            out.append(parts[2])
    return out


def default_currency(name: str) -> str:
    return TEMPLATES[name]


def _existing_opens(text: str) -> dict[str, date]:
    out: dict[str, date] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "open":
            try:
                out[parts[2]] = date.fromisoformat(parts[0])
            except ValueError:
                continue
    return out


def apply_business_template(
    ws_id: str,
    name: str = "mx_persona_moral",
    currency: str | None = None,
    store: LedgerStore | None = None,
) -> list[str]:
    """Open every account of a business template in ``ws_id``. Idempotent; returns the account names."""
    accounts = template_accounts(name)
    currency = currency or default_currency(name)
    store = store or get_ledger()

    ensure_files = getattr(store, "ensure_files", None)
    accounts_path = getattr(store, "accounts_path", None)
    if ensure_files is None or accounts_path is None:
        # InMemoryLedger and any other fake: register the accounts directly.
        open_account = getattr(store, "open_account", None)
        if open_account is not None:
            for account in accounts:
                open_account(ws_id, account)
        return accounts

    ensure_files(ws_id, currency)
    path: Path = accounts_path(ws_id)
    existing = _existing_opens(path.read_text(encoding="utf-8") if path.exists() else "")
    merged = dict(existing)
    for account in accounts:
        if account not in merged or EPOCH < merged[account]:
            merged[account] = EPOCH
    header = f'option "operating_currency" "{currency}"\n\n; Accounts are opened automatically on first use.\n'
    lines = [f"{when.isoformat()} open {account}" for account, when in sorted(merged.items())]
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return accounts


__all__ = [
    "TEMPLATES",
    "TemplateNotFound",
    "apply_business_template",
    "default_currency",
    "template_accounts",
    "template_path",
]
