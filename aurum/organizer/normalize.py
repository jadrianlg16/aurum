"""Merchant normalization: raw bank/ledger descriptions → a stable merchant key.

Deterministic and explainable, in this exact order:

1. uppercase + strip accents;
2. drop bank-noise prefixes (``SPEI ENVIADO``, ``PAGO TARJETA``, ``COMPRA EN``, ``DOMICILIACION`` …);
3. cut at the first ``*`` (``AMAZON PRIME*2X4Y5`` → ``AMAZON PRIME``) and drop URL suffixes
   (``NETFLIX.COM`` → ``NETFLIX``);
4. drop noise tokens: anything containing a digit or a mask (``4152******1234``), phone numbers,
   dates, branch/reference codes (``SUC 0341``, ``REF``), city/country words;
5. match the alias table (priority first, then pattern length, so a brand beats a category word)
   → canonical merchant + category hint + a default kind/essential; otherwise keep the first three
   surviving tokens.

The alias table is data, not policy: an entry only renames and classifies, it never invents an amount.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# --------------------------------------------------------------------------- noise vocabulary

# Prefixes MX/US banks bolt onto a merchant name. Stripped only at the start of the string.
_PREFIXES = [
    "SPEI ENVIADO", "SPEI RECIBIDO", "SPEI", "TRANSFERENCIA A", "TRANSFERENCIA DE", "TRANSFERENCIA",
    "PAGO TARJETA", "PAGO CUENTA DE TERCERO", "PAGO SERVICIO", "PAGO A", "PAGO", "COMPRA EN",
    "COMPRA", "CARGO RECURRENTE", "CARGO AUTOMATICO", "CARGO", "DOMICILIACION", "DEBITO AUTOMATICO",
    "DEPOSITO", "ABONO", "RETIRO", "TDD", "TDC", "POS", "RECURRING PAYMENT", "ACH DEBIT",
    "ACH CREDIT", "DEBIT CARD PURCHASE", "PURCHASE AUTHORIZED ON", "PAYMENT TO", "AUTOPAY",
]

# Whole tokens that never help identify a merchant.
_NOISE_TOKENS = {
    "MX", "MEX", "MEXICO", "CIUDAD", "DE", "CDMX", "DF", "EDO", "ESTADO", "SUC", "SUCURSAL", "REF", "REFERENCIA", "FOLIO", "AUT", "AUTORIZACION", "NO",
    "NUM", "USA", "US", "CA", "TX", "INC", "LLC", "SA", "CV", "SAB", "SAPI", "RFC", "ID", "PAGO",
    "MENSUAL", "MENSUALIDAD", "SERVICIO", "SERVICIOS", "ONLINE", "WWW", "COM", "HTTP", "HTTPS",
}

_MASK = re.compile(r"^[\dX*#]+$")
_HAS_DIGIT = re.compile(r"\d")
_PHONE = re.compile(r"^\+?\d[\d-]{6,}$")


@dataclass(frozen=True)
class Alias:
    """One alias-table row: ``pattern`` matched as a substring of the cleaned description.

    ``priority`` breaks ties before length does, so a brand (``GNP``) beats a category word
    (``SEGUROS``) even though the category word is the longer string.
    """

    pattern: str
    merchant: str
    category_hint: str
    kind: str = "subscription"
    essential: str = "wants"
    priority: int = 1


# Seeded MX/US merchants. Longest pattern wins, so keep specific rows above
# generic ones — the sort in ``_match_alias`` enforces that regardless of the order written here.
ALIASES: list[Alias] = [
    # streaming / music / video
    Alias("NETFLIX", "NETFLIX", "streaming"),
    Alias("SPOTIFY", "SPOTIFY", "music"),
    Alias("DISNEY", "DISNEY+", "streaming"),
    Alias("HBO", "MAX", "streaming"),
    Alias("MAX HELP", "MAX", "streaming"),
    Alias("YOUTUBE PREMIUM", "YOUTUBE PREMIUM", "streaming"),
    Alias("YOUTUBEPREMIUM", "YOUTUBE PREMIUM", "streaming"),
    Alias("AMAZON PRIME", "AMAZON PRIME", "streaming"),
    Alias("PRIME VIDEO", "AMAZON PRIME", "streaming"),
    Alias("PARAMOUNT", "PARAMOUNT+", "streaming"),
    Alias("VIX", "VIX", "streaming"),
    Alias("CRUNCHYROLL", "CRUNCHYROLL", "streaming"),
    Alias("APPLE TV", "APPLE TV+", "streaming"),
    # cloud / software
    Alias("ICLOUD", "ICLOUD", "cloud"),
    Alias("APPLE.COM/BILL", "APPLE", "cloud"),
    Alias("APPLE COM BILL", "APPLE", "cloud"),
    Alias("GOOGLE ONE", "GOOGLE ONE", "cloud"),
    Alias("GOOGLE STORAGE", "GOOGLE ONE", "cloud"),
    Alias("GOOGLE", "GOOGLE", "cloud"),
    Alias("MICROSOFT 365", "MICROSOFT 365", "cloud"),
    Alias("MICROSOFT365", "MICROSOFT 365", "cloud"),
    Alias("MSFT", "MICROSOFT 365", "cloud"),
    Alias("DROPBOX", "DROPBOX", "cloud"),
    Alias("ADOBE", "ADOBE", "cloud"),
    Alias("CHATGPT", "OPENAI", "cloud"),
    Alias("OPENAI", "OPENAI", "cloud"),
    Alias("ANTHROPIC", "ANTHROPIC", "cloud"),
    Alias("CLAUDE.AI", "ANTHROPIC", "cloud"),
    Alias("GITHUB", "GITHUB", "cloud"),
    Alias("NOTION", "NOTION", "cloud"),
    # telecom / internet
    Alias("TELCEL", "TELCEL", "telecom", "bill", "needs"),
    Alias("AT&T", "AT&T", "telecom", "bill", "needs"),
    Alias("ATT ", "AT&T", "telecom", "bill", "needs"),
    Alias("MOVISTAR", "MOVISTAR", "telecom", "bill", "needs"),
    Alias("IZZI", "IZZI", "telecom", "bill", "needs"),
    Alias("TOTALPLAY", "TOTALPLAY", "telecom", "bill", "needs"),
    Alias("TOTAL PLAY", "TOTALPLAY", "telecom", "bill", "needs"),
    Alias("MEGACABLE", "MEGACABLE", "telecom", "bill", "needs"),
    Alias("TELMEX", "TELMEX", "telecom", "bill", "needs"),
    # utilities
    Alias("CFE", "CFE", "utility", "utility", "needs"),
    Alias("COMISION FEDERAL DE ELECTRICIDAD", "CFE", "utility", "utility", "needs"),
    Alias("AGUA Y DRENAJE", "AGUA Y DRENAJE", "utility", "utility", "needs"),
    Alias("GAS NATURAL", "GAS NATURAL", "utility", "utility", "needs"),
    Alias("NATURGY", "GAS NATURAL", "utility", "utility", "needs"),
    # transport
    Alias("UBER ONE", "UBER ONE", "transport"),
    Alias("UBER", "UBER", "transport"),
    Alias("DIDI", "DIDI", "transport"),
    # gym / health
    Alias("SMART FIT", "SMART FIT", "gym", "subscription", "wants"),
    Alias("SMARTFIT", "SMART FIT", "gym", "subscription", "wants"),
    Alias("SPORTS WORLD", "SPORTS WORLD", "gym", "subscription", "wants"),
    Alias("GYM", "GYM", "gym", "subscription", "wants", priority=0),
    Alias("ANYTIME FITNESS", "ANYTIME FITNESS", "gym", "subscription", "wants"),
    # housing / debt / insurance
    Alias("RENTA", "RENTA", "housing", "rent", "needs", priority=0),
    Alias("HIPOTECA", "HIPOTECA", "housing", "loan_payment", "debt"),
    Alias("CREDITO AUTOMOTRIZ", "CREDITO AUTOMOTRIZ", "loan", "loan_payment", "debt"),
    Alias("CREDITO AUTO", "CREDITO AUTOMOTRIZ", "loan", "loan_payment", "debt"),
    Alias("PRESTAMO PERSONAL", "PRESTAMO PERSONAL", "loan", "loan_payment", "debt"),
    Alias("INFONAVIT", "INFONAVIT", "housing", "loan_payment", "debt"),
    Alias("FOVISSSTE", "FOVISSSTE", "housing", "loan_payment", "debt"),
    Alias("SEGUROS", "SEGUROS", "insurance", "insurance", "needs", priority=0),
    Alias("SEGURO", "SEGUROS", "insurance", "insurance", "needs", priority=0),
    Alias("GNP", "GNP", "insurance", "insurance", "needs"),
    Alias("AXA", "AXA", "insurance", "insurance", "needs"),
    Alias("QUALITAS", "QUALITAS", "insurance", "insurance", "needs"),
    # taxes
    Alias("SAT ", "SAT", "tax", "tax", "needs"),
    Alias("IMSS", "IMSS", "tax", "tax", "needs"),
]

_ALIASES_SORTED = sorted(ALIASES, key=lambda a: (-a.priority, -len(a.pattern)))


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _prepare(description: str) -> tuple[str, str]:
    """(pre, cleaned): ``pre`` is steps 1-3, ``cleaned`` also drops the noise tokens (step 4).

    Aliases are matched against ``pre`` first, so a brand whose name *contains* a number
    (``MICROSOFT 365``) is not destroyed by the digit-token filter.
    """
    text = strip_accents(description or "").upper()
    text = text.split("*")[0]                       # AMAZON PRIME*2X4Y5 → AMAZON PRIME
    text = re.sub(r"[,;:/\\|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # bank prefixes, repeatedly (a line may carry two of them)
    changed = True
    while changed:
        changed = False
        for prefix in sorted(_PREFIXES, key=len, reverse=True):
            if text.startswith(prefix + " ") or text == prefix:
                text = text[len(prefix):].strip()
                changed = True
                break
    text = re.sub(r"\.(COM|MX|NET|ORG|IO|AI)\b", " ", text)   # NETFLIX.COM → NETFLIX
    pre = re.sub(r"\s+", " ", text).strip()
    tokens: list[str] = []
    for raw in text.split():
        tok = raw.strip(".-_#()").strip()
        if not tok:
            continue
        if _PHONE.match(tok) or _MASK.match(tok) or _HAS_DIGIT.search(tok):
            continue
        if tok in _NOISE_TOKENS:
            continue
        tokens.append(tok)
    return pre, " ".join(tokens).strip()


def clean(description: str) -> str:
    """Steps 1-4: everything except the alias lookup. Exposed so ``explain`` can show it."""
    return _prepare(description)[1]


def _match_alias(pre: str, cleaned: str) -> Alias | None:
    for text in (pre, cleaned):
        padded = f"{text} "
        for alias in _ALIASES_SORTED:
            if alias.pattern in padded:
                return alias
    return None


def normalize(description: str) -> str:
    """Raw description → canonical merchant key (alias name, else the first three clean tokens)."""
    pre, cleaned = _prepare(description)
    alias = _match_alias(pre, cleaned)
    if alias is not None:
        return alias.merchant
    return " ".join(cleaned.split()[:3]) or (description or "").strip().upper()


def classify(description: str) -> dict[str, str | None]:
    """Merchant + the alias table's defaults. Unknown merchants get no hint and a neutral default."""
    pre, cleaned = _prepare(description)
    alias = _match_alias(pre, cleaned)
    if alias is None:
        return {
            "merchant": " ".join(cleaned.split()[:3]) or (description or "").strip().upper(),
            "category_hint": None,
            "kind": "other",
            "essential": "wants",
            "cleaned": cleaned,
        }
    return {
        "merchant": alias.merchant,
        "category_hint": alias.category_hint,
        "kind": alias.kind,
        "essential": alias.essential,
        "cleaned": cleaned,
    }
