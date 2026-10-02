"""Keyword reader for receipt text: how much, when, where and what.

Input is plain OCR text from any engine (`receipt_ocr.py`); output is a *suggestion* a person confirms
in + Agregar — nothing here writes to the ledger and nothing is a model output. Every guess is a table
lookup or a regex, and every guess carries a reason code so the UI can say why ("la línea TOTAL",
"por la palabra MAGNA"). Pure functions only: no workspace, no I/O, so the rules are unit-tested on
synthetic receipt text (tests/ingest/test_receipt_parse.py).

- **Monto**: the amount on the strongest TOTAL-like line, never SUBTOTAL / IVA / CAMBIO / EFECTIVO /
  ARTÍCULOS; the amount may sit on the next line when OCR splits the columns. Cross-checked against
  SUBTOTAL + IVA and the card line when present. Without any keyword, the largest amount is offered
  with low confidence.
- **Fecha**: day-first numeric dates (MX), ISO dates and month names (ENE…DIC / JAN…DEC); a line that
  says FECHA/DATE wins; anything in the future or older than ~13 months is ignored.
- **Comercio**: a table of known MX/US chains, else the first header line that is not an address, RFC,
  folio or greeting.
- **Categoría**: the chain's category, else keyword rules (MAGNA/LITROS → gasolina, PROPINA/MESA →
  comida fuera, FARMACIA → medicinas…). Names are the seeded category names (`aurum/pf/labels.py`);
  the caller maps them to the workspace's label ids and layers "what you chose last time" on top.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

MAX_AMOUNT = Decimal("1000000")
PAST_DAYS = 400


def fold(text: str) -> str:
    """Upper case without accents: 'Súper Farmacia' → 'SUPER FARMACIA'."""
    norm = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in norm if not unicodedata.combining(c)).upper()


# ------------------------------------------------------------------------------------------ amounts

# 1,234.56 · 1234.56 · 79,50 · 1.234,56 — the last separator followed by exactly two digits is the
# decimal point, the others are thousands. `$ 80` (no cents) only counts when the dollar sign is there.
_MONEY_RE = re.compile(r"(?<![\d.,])(\$\s?)?(\d{1,3}(?:[.,\s]\d{3})+|\d+)[.,](\d{2})(?![\d])")
_MONEY_NO_CENTS_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?![\d.,])")

_STRONG = (
    "TOTAL A PAGAR", "TOTAL CON PROPINA", "GRAN TOTAL", "IMPORTE TOTAL", "MONTO TOTAL", "TOTAL MXN",
    "TOTAL M.N", "TOTAL NETO", "TOTAL VENTA", "TOTAL DE LA VENTA", "TOTAL PAGADO", "AMOUNT DUE",
    "TOTAL DUE", "BALANCE DUE", "GRAND TOTAL",
)
_TOTAL_WORD = re.compile(r"\bT[O0]TAL\b")
_CARD = re.compile(r"\b(TARJETA|VISA|MASTER\s?CARD|AMEX|AMERICAN EXPRESS|DEBITO|CREDITO|DEBIT|CREDIT)\b")
_WEAK = re.compile(r"\b(IMPORTE|MONTO|A PAGAR|CARGO|AMOUNT)\b")
_EXCLUDE = re.compile(
    r"SUB\s?-?\s?T[O0]TAL|\bI\.?V\.?A\b|\bIEPS\b|IMPUESTO|\bTAX\b|CAMBIO|\bEFECTIVO\b|RECIBIDO|PAGO CON|PAGA CON|"
    r"DESCUENTO|AHORR|\bPUNTOS\b|\bSALDO\b|ARTICULO|\bPIEZAS\b|\bPZAS?\b|\bCHANGE\b|\bCASH\b|\bTENDER|DISCOUNT|"
    r"SAVINGS|SUGERIDA|\bRFC\b|\bTEL\b|FOLIO|TICKET|\bCP\b|C\.P\."
)
_SUBTOTAL = re.compile(r"SUB\s?-?\s?T[O0]TAL")
_IVA = re.compile(r"\bI\.?V\.?A\b|\bTAX\b")


def _to_decimal(whole: str, cents: str | None) -> Decimal | None:
    digits = re.sub(r"[.,\s]", "", whole)
    try:
        value = Decimal(f"{digits}.{cents}" if cents else digits)
    except InvalidOperation:
        return None
    return value if Decimal("0") < value < MAX_AMOUNT else None


def amounts_in(line: str) -> list[Decimal]:
    """Every money-looking figure in one folded line, left to right."""
    out: list[Decimal] = []
    for m in _MONEY_RE.finditer(line):
        value = _to_decimal(m.group(2), m.group(3))
        if value is not None:
            out.append(value)
    if not out:
        for m in _MONEY_NO_CENTS_RE.finditer(line):
            value = _to_decimal(m.group(1), None)
            if value is not None:
                out.append(value)
    return out


@dataclass
class AmountGuess:
    value: Decimal
    confidence: str  # high | medium | low
    line: str
    reason: str  # total_line | total_next_line | card_line | weak_line | largest
    checks: list[str] = field(default_factory=list)  # subtotal_iva | card_match


def _score(line: str) -> tuple[int, str]:
    if any(s in line for s in _STRONG):
        return 5, "total_line"
    if _EXCLUDE.search(line):
        return 0, ""
    if _TOTAL_WORD.search(line):
        return 4, "total_line"
    if _CARD.search(line):
        return 2, "card_line"
    if _WEAK.search(line):
        return 2, "weak_line"
    return 0, ""


def find_amount(lines: list[str]) -> AmountGuess | None:
    best: tuple[int, Decimal, int, str, str] | None = None  # score, value, index, line, reason
    for i, line in enumerate(lines):
        score, reason = _score(line)
        if score == 0:
            continue
        values = amounts_in(line)
        shown = line
        if not values and i + 1 < len(lines) and not _EXCLUDE.search(lines[i + 1]):
            values = amounts_in(lines[i + 1])  # OCR put the figure on its own line
            shown = f"{line} {lines[i + 1]}"
            reason = "total_next_line" if reason == "total_line" else reason
        if not values:
            continue
        value = values[-1]  # the right-most figure on a receipt line is the line total
        # Higher score wins; on a tie the larger figure (a TOTAL printed before the tip line).
        if best is None or (score, value) > (best[0], best[1]):
            best = (score, value, i, shown, reason)

    if best is None:
        candidates = [
            (v, line) for line in lines if not _EXCLUDE.search(line) for v in amounts_in(line)
        ]
        if not candidates:
            return None
        value, line = max(candidates, key=lambda c: c[0])
        return AmountGuess(value=value, confidence="low", line=line.strip(), reason="largest")

    score, value, _, line, reason = best
    checks: list[str] = []
    subtotal = next((amounts_in(ln)[-1] for ln in lines if _SUBTOTAL.search(ln) and amounts_in(ln)), None)
    iva = next(
        (amounts_in(ln)[-1] for ln in lines if _IVA.search(ln) and not _SUBTOTAL.search(ln) and amounts_in(ln)),
        None,
    )
    if subtotal is not None and iva is not None and abs(subtotal + iva - value) <= Decimal("0.02"):
        checks.append("subtotal_iva")
    elif subtotal is not None and abs(subtotal - value) <= Decimal("0.02"):
        checks.append("subtotal_iva")  # prices with IVA included
    if reason != "card_line" and any(
        _CARD.search(ln) and not _EXCLUDE.search(ln) and value in amounts_in(ln) for ln in lines
    ):
        checks.append("card_match")
    if score >= 4 and (checks or score == 5):
        confidence = "high"
    elif score >= 4 or checks:
        confidence = "medium"
    else:
        confidence = "low"
    return AmountGuess(value=value, confidence=confidence, line=line.strip(), reason=reason, checks=checks)


def find_currency(text: str) -> str | None:
    if re.search(r"\bUSD\b|\bUS\s?\$|\bDLLS?\b|\bDOLARES\b|\bDOLLARS?\b", text):
        return "USD"
    if re.search(r"\bMXN\b|\bM\.?N\.?\b|\bPESOS\b", text):
        return "MXN"
    return None


# --------------------------------------------------------------------------------------------- dates

_MONTHS = {
    "ENE": 1, "JAN": 1, "FEB": 2, "MAR": 3, "ABR": 4, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7,
    "AGO": 8, "AUG": 8, "SEP": 9, "SET": 9, "OCT": 10, "NOV": 11, "DIC": 12, "DEC": 12,
}
_MON = "|".join(_MONTHS)
_ISO_RE = re.compile(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_NUM_RE = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b")
_DMY_TXT_RE = re.compile(rf"\b(\d{{1,2}})[\s\-/.]*({_MON})[A-Z]*\.?[\s\-/.,]*(\d{{4}}|\d{{2}})\b")
_MDY_TXT_RE = re.compile(rf"\b({_MON})[A-Z]*\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b")


@dataclass
class DateGuess:
    value: date
    confidence: str
    line: str


def _year(raw: str) -> int:
    y = int(raw)
    return 2000 + y if y < 100 else y


def _valid(y: int, m: int, d: int, today: date) -> date | None:
    try:
        value = date(y, m, d)
    except ValueError:
        return None
    if value > today + timedelta(days=1) or value < today - timedelta(days=PAST_DAYS):
        return None
    return value


def _dates_in(line: str, today: date, day_first: bool) -> list[date]:
    out: list[date] = []
    for m in _ISO_RE.finditer(line):
        if (v := _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)), today)) is not None:
            out.append(v)
    for m in _NUM_RE.finditer(line):
        a, b, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
        if a > 12:
            order = [(b, a)]  # (month, day): only day-first works
        elif b > 12:
            order = [(a, b)]
        else:
            order = [(b, a), (a, b)] if day_first else [(a, b), (b, a)]
        for month, day in order:
            if (v := _valid(y, month, day, today)) is not None:
                out.append(v)
                break
    for m in _DMY_TXT_RE.finditer(line):
        if (v := _valid(_year(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)), today)) is not None:
            out.append(v)
    for m in _MDY_TXT_RE.finditer(line):
        if (v := _valid(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)), today)) is not None:
            out.append(v)
    return out


def find_date(lines: list[str], today: date, day_first: bool = True) -> DateGuess | None:
    first: DateGuess | None = None
    for line in lines:
        found = _dates_in(line, today, day_first)
        if not found:
            continue
        if re.search(r"\bFECHA\b|\bDATE\b", line):
            return DateGuess(value=found[0], confidence="high", line=line.strip())
        if first is None:
            first = DateGuess(value=found[0], confidence="medium", line=line.strip())
    return first


# ------------------------------------------------------------------------------ merchant & category

# (pattern on folded text, display name, seeded category name or None). Order matters: the more
# specific pattern first (OXXO GAS before OXXO, UBER EATS before UBER).
_MERCHANTS: list[tuple[str, str, str | None]] = [
    (r"\bOXXO\s*GAS\b", "OXXO Gas", "Transporte/Gasolina"),
    (r"\bPEMEX\b", "Pemex", "Transporte/Gasolina"),
    (r"\bG\s?500\b", "G500", "Transporte/Gasolina"),
    (r"\bSHELL\b", "Shell", "Transporte/Gasolina"),
    (r"\bMOBIL\b", "Mobil", "Transporte/Gasolina"),
    (r"\bHIDROSINA\b", "Hidrosina", "Transporte/Gasolina"),
    (r"\bUBER\s*EATS\b", "Uber Eats", "Comida fuera"),
    (r"\bDIDI\s*FOOD\b", "DiDi Food", "Comida fuera"),
    (r"\bRAPPI\b", "Rappi", "Comida fuera"),
    (r"\bUBER\b", "Uber", "Uber/Taxi"),
    (r"\bDIDI\b", "DiDi", "Uber/Taxi"),
    (r"\bCABIFY\b", "Cabify", "Uber/Taxi"),
    (r"\bOXXO\b", "OXXO", "Súper"),
    (r"\b7[\s-]?ELEVEN\b", "7-Eleven", "Súper"),
    (r"\bCIRCLE\s?K\b", "Circle K", "Súper"),
    (r"\bBODEGA\s+AURRERA\b|\bAURRERA\b", "Bodega Aurrera", "Súper"),
    (r"\bWAL[\s-]?MART\b", "Walmart", "Súper"),
    (r"\bSORIANA\b", "Soriana", "Súper"),
    (r"\bCHEDRAUI\b", "Chedraui", "Súper"),
    (r"\bH[\s-]E[\s-]B\b|\bHEB\b", "HEB", "Súper"),
    (r"\bCOSTCO\b", "Costco", "Súper"),
    (r"\bSAM'?S\s+CLUB\b", "Sam's Club", "Súper"),
    (r"\bLA\s+COMER\b", "La Comer", "Súper"),
    (r"\bCITY\s+MARKET\b", "City Market", "Súper"),
    (r"\bSUPERAMA\b", "Superama", "Súper"),
    (r"\bCASA\s+LEY\b", "Casa Ley", "Súper"),
    (r"\bALSUPER\b", "Alsuper", "Súper"),
    (r"\bKROGER\b", "Kroger", "Súper"),
    (r"\bWHOLE\s+FOODS\b", "Whole Foods", "Súper"),
    (r"\bTRADER\s+JOE'?S\b", "Trader Joe's", "Súper"),
    (r"\bFARMACIAS?\s+GUADALAJARA\b", "Farmacias Guadalajara", "Medicinas"),
    (r"\bFARMACIAS?\s+DEL\s+AHORRO\b", "Farmacias del Ahorro", "Medicinas"),
    (r"\bBENAVIDES\b", "Farmacias Benavides", "Medicinas"),
    (r"\bFARMACIAS?\s+SAN\s+PABLO\b", "Farmacia San Pablo", "Medicinas"),
    (r"\bSIMILARES\b|\bDR\.?\s*SIMI\b", "Farmacias Similares", "Medicinas"),
    (r"\bFARMACIAS?\s+YZA\b", "Farmacias Yza", "Medicinas"),
    (r"\bWALGREENS\b", "Walgreens", "Medicinas"),
    (r"\bCVS\b", "CVS", "Medicinas"),
    (r"\bSTARBUCKS\b", "Starbucks", "Comida fuera"),
    (r"\bSANBORNS\b", "Sanborns", "Comida fuera"),
    (r"\bVIPS\b", "Vips", "Comida fuera"),
    (r"\bTOKS\b", "Toks", "Comida fuera"),
    (r"\bMC\s?DONALD'?S\b", "McDonald's", "Comida fuera"),
    (r"\bBURGER\s+KING\b", "Burger King", "Comida fuera"),
    (r"\bKFC\b", "KFC", "Comida fuera"),
    (r"\bDOMINO'?S\b", "Domino's", "Comida fuera"),
    (r"\bLITTLE\s+CAESARS\b", "Little Caesars", "Comida fuera"),
    (r"\bPIZZA\s+HUT\b", "Pizza Hut", "Comida fuera"),
    (r"\bSUBWAY\b", "Subway", "Comida fuera"),
    (r"\bCARL'?S\s+JR\b", "Carl's Jr.", "Comida fuera"),
    (r"\bITALIANNI'?S\b", "Italianni's", "Comida fuera"),
    (r"\bCINEPOLIS\b", "Cinépolis", "Entretenimiento"),
    (r"\bCINEMEX\b", "Cinemex", "Entretenimiento"),
    (r"\bLIVERPOOL\b", "Liverpool", "Ropa"),
    (r"\bPALACIO\s+DE\s+HIERRO\b", "El Palacio de Hierro", "Ropa"),
    (r"\bSUBURBIA\b", "Suburbia", "Ropa"),
    (r"\bZARA\b", "Zara", "Ropa"),
    (r"\bH\s?&\s?M\b", "H&M", "Ropa"),
    (r"\bC\s?&\s?A\b", "C&A", "Ropa"),
    (r"\bCOMISION\s+FEDERAL\s+DE\s+ELECTRICIDAD\b|\bCFE\b", "CFE", "Servicios (luz/agua/gas)"),
    (r"\bNATURGY\b", "Naturgy", "Servicios (luz/agua/gas)"),
    (r"\bTOTAL\s?PLAY\b", "Totalplay", "Internet/Teléfono"),
    (r"\bTELMEX\b", "Telmex", "Internet/Teléfono"),
    (r"\bTELCEL\b", "Telcel", "Internet/Teléfono"),
    (r"\bIZZI\b", "izzi", "Internet/Teléfono"),
    (r"\bMEGACABLE\b", "Megacable", "Internet/Teléfono"),
    (r"\bAT\s?&\s?T\b", "AT&T", "Internet/Teléfono"),
    (r"\bPETCO\b", "Petco", "Mascotas"),
    (r"\+\s?KOTA\b", "+Kota", "Mascotas"),
    (r"\bHOME\s+DEPOT\b", "The Home Depot", None),
    (r"\bOFFICE\s+DEPOT\b", "Office Depot", None),
    (r"\bCOPPEL\b", "Coppel", None),
]
_MERCHANT_RES = [(re.compile(p), name, cat) for p, name, cat in _MERCHANTS]

# (seeded category name, keywords). A header hit counts double; the most hits wins, ties keep order.
_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("Transporte/Gasolina", ("MAGNA", "PREMIUM", "DIESEL", "GASOLINA", "LITROS", "LTS", "COMBUSTIBLE",
                             "DESPACHADOR", "BOMBA", "GASOLINERA", "CASETA", "PEAJE", "ESTACIONAMIENTO")),
    ("Comida fuera", ("PROPINA", "MESERO", "MESA", "COMENSALES", "RESTAURANTE", "RESTAURANT", "TAQUERIA",
                      "TACOS", "PIZZA", "PIZZERIA", "SUSHI", "HAMBURGUESA", "HAMBURGUESAS", "CAFETERIA",
                      "FONDA", "COCINA", "LONCHERIA", "BAR", "CANTINA", "MARISQUERIA", "PANADERIA")),
    ("Medicinas", ("FARMACIA", "FARMACIAS", "MEDICAMENTO", "MEDICAMENTOS", "TABLETAS", "CAPSULAS",
                   "RECETA", "GENERICO", "JARABE")),
    ("Salud/Médico", ("CONSULTA", "CLINICA", "HOSPITAL", "LABORATORIO", "DENTAL", "DENTISTA", "OPTICA",
                      "MEDICO")),
    ("Súper", ("ABARROTES", "SUPERMERCADO", "DESPENSA", "MINISUPER", "SUPER", "FRUTAS", "VERDURAS",
               "CARNICERIA")),
    ("Servicios (luz/agua/gas)", ("KWH", "ENERGIA ELECTRICA", "GAS LP", "GAS NATURAL", "AGUA POTABLE",
                                  "DRENAJE")),
    ("Internet/Teléfono", ("RECARGA", "TIEMPO AIRE", "INTERNET", "TELEFONIA", "PAQUETE DE DATOS")),
    ("Uber/Taxi", ("TAXI", "SITIO")),
    ("Entretenimiento", ("CINE", "BOLETO", "BOLETOS", "FUNCION", "TAQUILLA", "CONCIERTO", "TEATRO")),
    ("Ropa", ("TALLA", "PRENDA", "CALZADO", "ZAPATO", "ZAPATOS", "ZAPATERIA", "BOUTIQUE", "PLAYERA",
              "PANTALON", "VESTIDO")),
    ("Mascotas", ("VETERINARIA", "VETERINARIO", "MASCOTA", "MASCOTAS", "CROQUETAS", "ESTETICA CANINA")),
    ("Viajes", ("HOTEL", "HOSPEDAJE", "VUELO", "AEROLINEA", "EQUIPAJE", "AEROPUERTO")),
    ("Educación/Colegiaturas", ("COLEGIATURA", "INSCRIPCION", "COLEGIO", "UNIVERSIDAD")),
]
_KEYWORD_RES = [(name, [(w, re.compile(rf"\b{re.escape(w)}\b")) for w in words]) for name, words in _KEYWORDS]

_HEADER_NOISE = re.compile(
    r"\bRFC\b|R\.F\.C|\bC\.?P\.?\s*\d|\bTEL\b|TELEFONO|\bAV\b|AVENIDA|\bCALLE\b|\bCOL\b|COLONIA|SUCURSAL|"
    r"\bSUC\b|TICKET|FOLIO|FECHA|\bHORA\b|\bCAJA\b|CAJERO|BIENVENID|GRACIAS|FACTURA|REGIMEN|\bCLIENTE\b|"
    r"\bNO\.?\s*\d|\bKM\b|\bMZ\b|\bLOTE\b|\bCIUDAD\b|MEXICO|\bESTADO\b|\bEDO\b|\bCDMX\b|"
    r"ESTACION DE SERVICIO|\bE\.S\.|\bVENTA\b|\bCOMPROBANTE\b|\bORIGINAL\b|\bCOPIA\b|"
    # card-terminal slips print the acquiring bank / terminal brand on top, not the shop
    r"\bBBVA\b|BANORTE|SANTANDER|BANAMEX|CITIBANAMEX|\bHSBC\b|SCOTIABANK|INBURSA|BANCO|\bCLIP\b|GETNET|"
    r"MERCADO\s?PAGO|BILLPOCKET|\bNETPAY\b"
)
# "COMERCIO: TAQUERIA EL GUERO" on a card slip names the shop outright.
_MERCHANT_LINE = re.compile(r"\b(?:COMERCIO|NEGOCIO|ESTABLECIMIENTO|MERCHANT)\s*[:.]\s*(.+)$")
_COMPANY_SUFFIX = re.compile(r"\b(S\.?\s?A\.?\s?P?\.?\s?I?\.?\s*DE\s+C\.?\s?V\.?|S\.?\s?DE\s+R\.?\s?L\.?.*|S\.?\s?C\.?)\s*$")
HEADER_LINES = 6


@dataclass
class MerchantGuess:
    name: str
    confidence: str
    source: str  # known | header
    category: str | None = None  # seeded category name for a known chain


@dataclass
class CategoryGuess:
    name: str
    words: list[str]


def find_merchant(lines: list[str]) -> MerchantGuess | None:
    header = "\n".join(lines[:HEADER_LINES])
    body = "\n".join(lines)
    for scope, confidence in ((header, "high"), (body, "medium")):
        for rx, name, category in _MERCHANT_RES:
            if rx.search(scope):
                return MerchantGuess(name=name, confidence=confidence, source="known", category=category)
    named = [m.group(1) for line in lines if (m := _MERCHANT_LINE.search(line))]
    for line in [*named, *lines[:HEADER_LINES]]:
        text = line.strip(" -*=.:#")
        if len(re.findall(r"[A-Z]", text)) < 3 or _HEADER_NOISE.search(text) or amounts_in(text):
            continue
        text = _COMPANY_SUFFIX.sub("", text).strip(" ,.-")
        if len(text) < 3:
            continue
        pretty = " ".join(w.capitalize() if w.isalpha() else w for w in text.split())
        return MerchantGuess(name=pretty[:40], confidence="low", source="header")
    return None


def find_category(lines: list[str]) -> CategoryGuess | None:
    header = "\n".join(lines[:HEADER_LINES])
    body = "\n".join(lines)
    best: tuple[int, str, list[str]] | None = None
    for name, words in _KEYWORD_RES:
        hits: list[str] = []
        score = 0
        for word, rx in words:
            if rx.search(body):
                hits.append(word)
                score += 2 if rx.search(header) else 1
        if hits and (best is None or score > best[0]):
            best = (score, name, hits)
    if best is None:
        return None
    return CategoryGuess(name=best[1], words=best[2][:4])


# ------------------------------------------------------------------------------------------- driver


@dataclass
class ReceiptReading:
    amount: AmountGuess | None
    currency: str | None
    date: DateGuess | None
    merchant: MerchantGuess | None
    category: CategoryGuess | None
    lines: int


def normalize_lines(text: str) -> list[str]:
    out = []
    for raw in (text or "").splitlines():
        line = re.sub(r"[ \t]+", " ", fold(raw)).strip()
        if line:
            out.append(line)
    return out


def read_receipt(text: str, today: date, day_first: bool = True) -> ReceiptReading:
    lines = normalize_lines(text)
    return ReceiptReading(
        amount=find_amount(lines),
        currency=find_currency("\n".join(lines)),
        date=find_date(lines, today, day_first),
        merchant=find_merchant(lines),
        category=find_category(lines),
        lines=len(lines),
    )
