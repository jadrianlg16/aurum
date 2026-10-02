"""Synthetic demo workspace ``demo-mx``.

Three months (2026-06 … 2026-08) of CFDI 4.0 XML, a BBVA-shaped bank CSV per month, and the Beancount
postings behind them. The data is *designed* so the August prefill audit produces one of each
difference; ``docs/demo-manifest.json`` records what the audit must find, so tests and manual
verification assert against a written expectation rather than against whatever the code returns.

Everything here is fake: RFCs use the SAT's own generic placeholders and invented demo patterns, and
no real client, bank or CFDI ever enters this repo (synthetic fixtures only).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from lxml import etree

from ..core.money import Amount, q2
from ..core.workspaces import Modules, Workspace, get_workspace, save_workspace
from ..ledger.base import Posting, Transaction
from ..ledger.beancount_store import BeancountLedger

WS_ID = "demo-mx"
RFC = "XAXX010101000"  # SAT's generic "público en general" RFC — safe as a synthetic own-RFC
CLIENT_PM = ("DPM010101AA1", "Cliente Alfa SA de CV")  # invented, persona moral
CLIENT_PF = ("DPF010101BB2", "Cliente Beta")  # invented, persona física
SUPPLIER = ("DPR010101CC3", "Proveedor Gamma SA de CV")
CURRENCY = "MXN"
PERIODS = ["2026-06", "2026-07", "2026-08"]

CFDI_NS = "http://www.sat.gob.mx/cfd/4"
TFD_NS = "http://www.sat.gob.mx/TimbreFiscalDigital"
PAGO_NS = "http://www.sat.gob.mx/Pagos20"
NSMAP = {"cfdi": CFDI_NS, "tfd": TFD_NS, "pago20": PAGO_NS}


def D(value: str) -> Decimal:
    return Decimal(value)


@dataclass
class Doc:
    uuid: str
    tipo: str
    direction: str
    fecha: str
    subtotal: Decimal = Decimal("0")
    iva_trasladado: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    emisor_rfc: str = RFC
    emisor_nombre: str = "Contribuyente Demo"
    receptor_rfc: str = CLIENT_PF[0]
    receptor_nombre: str = CLIENT_PF[1]
    metodo_pago: str | None = None
    forma_pago: str | None = None
    uso_cfdi: str | None = None
    isr_retenido: Decimal = Decimal("0")
    iva_retenido: Decimal = Decimal("0")
    concepto: str = "Servicios profesionales"
    pagos: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "version": "4.0",
            "tipo": self.tipo,
            "direction": self.direction,
            "fecha": self.fecha,
            "emisor_rfc": self.emisor_rfc,
            "receptor_rfc": self.receptor_rfc,
            "subtotal": str(self.subtotal),
            "total": str(self.total),
            "moneda": CURRENCY,
            "metodo_pago": self.metodo_pago,
            "forma_pago": self.forma_pago,
            "uso_cfdi": self.uso_cfdi,
            "iva_trasladado": str(self.iva_trasladado),
            "impuestos_retenidos": str(self.isr_retenido + self.iva_retenido),
            "isr_retenido": str(self.isr_retenido),
            "iva_retenido": str(self.iva_retenido),
            "conceptos": [{"descripcion": self.concepto, "importe": str(self.subtotal)}],
            "pagos": self.pagos,
            "raw_path": f"docs/cfdi/{self.uuid}.xml",
        }


def documents() -> list[Doc]:
    """The scripted three months. Amounts are round numbers so the math is easy to check by hand."""
    return [
        # ---- June: one PUE collected, one PPD that gets paid in July -------------------
        Doc(
            uuid="JUN-PUE-A",
            tipo="I",
            direction="emitido",
            fecha="2026-06-05T10:00:00",
            subtotal=D("20000.00"),
            iva_trasladado=D("3200.00"),
            total=D("23200.00"),
            receptor_rfc=CLIENT_PM[0],
            receptor_nombre=CLIENT_PM[1],
            metodo_pago="PUE",
            forma_pago="03",
            uso_cfdi="G03",
            isr_retenido=D("250.00"),
        ),
        Doc(
            uuid="JUN-PPD-B",
            tipo="I",
            direction="emitido",
            fecha="2026-06-20T10:00:00",
            subtotal=D("30000.00"),
            iva_trasladado=D("4800.00"),
            total=D("34800.00"),
            metodo_pago="PPD",
            forma_pago="99",
            uso_cfdi="G03",
        ),
        Doc(
            uuid="REC-JUN-1",
            tipo="I",
            direction="recibido",
            fecha="2026-06-10T12:00:00",
            subtotal=D("3000.00"),
            iva_trasladado=D("480.00"),
            total=D("3480.00"),
            emisor_rfc=SUPPLIER[0],
            emisor_nombre=SUPPLIER[1],
            receptor_rfc=RFC,
            receptor_nombre="Contribuyente Demo",
            metodo_pago="PUE",
            forma_pago="03",
            uso_cfdi="G03",
            concepto="Servicio de nube",
        ),
        # ---- July: the REP arrives, plus a PUE ----------------------------------------
        Doc(
            uuid="REP-JUL-1",
            tipo="P",
            direction="emitido",
            fecha="2026-07-08T09:00:00",
            metodo_pago=None,
            pagos=[
                {
                    "fecha_pago": "2026-07-08",
                    "monto": "34800.00",
                    "uuid_relacionado": "JUN-PPD-B",
                    "forma_pago": "03",
                }
            ],
        ),
        Doc(
            uuid="JUL-PUE-C",
            tipo="I",
            direction="emitido",
            fecha="2026-07-10T10:00:00",
            subtotal=D("15000.00"),
            iva_trasladado=D("2400.00"),
            total=D("17400.00"),
            metodo_pago="PUE",
            forma_pago="03",
            uso_cfdi="G03",
        ),
        Doc(
            uuid="REC-JUL-1",
            tipo="I",
            direction="recibido",
            fecha="2026-07-15T12:00:00",
            subtotal=D("4000.00"),
            iva_trasladado=D("640.00"),
            total=D("4640.00"),
            emisor_rfc=SUPPLIER[0],
            emisor_nombre=SUPPLIER[1],
            receptor_rfc=RFC,
            receptor_nombre="Contribuyente Demo",
            metodo_pago="PUE",
            forma_pago="28",
            uso_cfdi="G03",
            concepto="Papelería y oficina",
        ),
        # ---- August: every difference the prefill audit can produce --------------------
        Doc(
            uuid="AGO-PUE-D",
            tipo="I",
            direction="emitido",
            fecha="2026-08-05T10:00:00",
            subtotal=D("25000.00"),
            iva_trasladado=D("4000.00"),
            total=D("29000.00"),
            receptor_rfc=CLIENT_PM[0],
            receptor_nombre=CLIENT_PM[1],
            metodo_pago="PUE",
            forma_pago="03",
            uso_cfdi="G03",
            isr_retenido=D("312.50"),
        ),
        Doc(  # invoiced, never paid → pue_not_collected
            uuid="AGO-PUE-E",
            tipo="I",
            direction="emitido",
            fecha="2026-08-18T10:00:00",
            subtotal=D("12000.00"),
            iva_trasladado=D("1920.00"),
            total=D("13920.00"),
            metodo_pago="PUE",
            forma_pago="99",
            uso_cfdi="G03",
        ),
        Doc(  # PPD with no complement → ppd_missing_rep
            uuid="AGO-PPD-F",
            tipo="I",
            direction="emitido",
            fecha="2026-08-22T10:00:00",
            subtotal=D("8000.00"),
            iva_trasladado=D("1280.00"),
            total=D("9280.00"),
            metodo_pago="PPD",
            forma_pago="99",
            uso_cfdi="G03",
        ),
        Doc(  # ordinary creditable expense
            uuid="REC-AGO-1",
            tipo="I",
            direction="recibido",
            fecha="2026-08-07T12:00:00",
            subtotal=D("5000.00"),
            iva_trasladado=D("800.00"),
            total=D("5800.00"),
            emisor_rfc=SUPPLIER[0],
            emisor_nombre=SUPPLIER[1],
            receptor_rfc=RFC,
            receptor_nombre="Contribuyente Demo",
            metodo_pago="PUE",
            forma_pago="03",
            uso_cfdi="G03",
            concepto="Licencias de software",
        ),
        Doc(  # paid in cash → cash_paid_expense
            uuid="REC-AGO-2",
            tipo="I",
            direction="recibido",
            fecha="2026-08-09T14:00:00",
            subtotal=D("1000.00"),
            iva_trasladado=D("160.00"),
            total=D("1160.00"),
            emisor_rfc=SUPPLIER[0],
            emisor_nombre=SUPPLIER[1],
            receptor_rfc=RFC,
            receptor_nombre="Contribuyente Demo",
            metodo_pago="PUE",
            forma_pago="01",
            uso_cfdi="G03",
            concepto="Comida de trabajo",
        ),
        Doc(  # investment → fixed_asset_iva
            uuid="REC-AGO-3",
            tipo="I",
            direction="recibido",
            fecha="2026-08-12T11:00:00",
            subtotal=D("20000.00"),
            iva_trasladado=D("3200.00"),
            total=D("23200.00"),
            emisor_rfc=SUPPLIER[0],
            emisor_nombre=SUPPLIER[1],
            receptor_rfc=RFC,
            receptor_nombre="Contribuyente Demo",
            metodo_pago="PUE",
            forma_pago="03",
            uso_cfdi="I04",
            concepto="Equipo de cómputo",
        ),
    ]


# --------------------------------------------------------------------------- XML


def _sub(parent, tag: str, **attrs: str):
    el = etree.SubElement(parent, tag, nsmap=None)
    for key, value in attrs.items():
        el.set(key, value)
    return el


def cfdi_xml(doc: Doc) -> bytes:
    root = etree.Element(f"{{{CFDI_NS}}}Comprobante", nsmap=NSMAP)
    root.set("Version", "4.0")
    root.set("Fecha", doc.fecha)
    root.set("Moneda", CURRENCY)
    root.set("TipoDeComprobante", doc.tipo)
    root.set("SubTotal", str(doc.subtotal))
    root.set("Total", str(doc.total))
    root.set("Exportacion", "01")
    root.set("LugarExpedicion", "06000")  # a generic postal code (demo)
    if doc.metodo_pago:
        root.set("MetodoPago", doc.metodo_pago)
    if doc.forma_pago:
        root.set("FormaPago", doc.forma_pago)

    emisor = _sub(root, f"{{{CFDI_NS}}}Emisor", Rfc=doc.emisor_rfc, Nombre=doc.emisor_nombre)
    emisor.set("RegimenFiscal", "626")  # RESICO personas físicas
    receptor = _sub(root, f"{{{CFDI_NS}}}Receptor", Rfc=doc.receptor_rfc, Nombre=doc.receptor_nombre)
    receptor.set("DomicilioFiscalReceptor", "64000")
    receptor.set("RegimenFiscalReceptor", "601")
    if doc.uso_cfdi:
        receptor.set("UsoCFDI", doc.uso_cfdi)

    if doc.tipo != "P":
        conceptos = etree.SubElement(root, f"{{{CFDI_NS}}}Conceptos")
        concepto = _sub(
            conceptos,
            f"{{{CFDI_NS}}}Concepto",
            ClaveProdServ="84111506",
            Cantidad="1",
            ClaveUnidad="E48",
            Descripcion=doc.concepto,
            ValorUnitario=str(doc.subtotal),
            Importe=str(doc.subtotal),
            ObjetoImp="02",
        )
        impuestos_c = etree.SubElement(concepto, f"{{{CFDI_NS}}}Impuestos")
        traslados = etree.SubElement(impuestos_c, f"{{{CFDI_NS}}}Traslados")
        _sub(
            traslados,
            f"{{{CFDI_NS}}}Traslado",
            Base=str(doc.subtotal),
            Impuesto="002",
            TipoFactor="Tasa",
            TasaOCuota="0.160000",
            Importe=str(doc.iva_trasladado),
        )
        impuestos = etree.SubElement(root, f"{{{CFDI_NS}}}Impuestos")
        impuestos.set("TotalImpuestosTrasladados", str(doc.iva_trasladado))
        # Real CFDI 4.0 repeats the per-tax summary at the root; parsers read it from here.
        traslados_root = etree.SubElement(impuestos, f"{{{CFDI_NS}}}Traslados")
        _sub(
            traslados_root,
            f"{{{CFDI_NS}}}Traslado",
            Base=str(doc.subtotal),
            Impuesto="002",
            TipoFactor="Tasa",
            TasaOCuota="0.160000",
            Importe=str(doc.iva_trasladado),
        )
        if doc.isr_retenido or doc.iva_retenido:
            impuestos.set("TotalImpuestosRetenidos", str(doc.isr_retenido + doc.iva_retenido))
            retenciones = etree.SubElement(impuestos, f"{{{CFDI_NS}}}Retenciones")
            if doc.isr_retenido:
                _sub(retenciones, f"{{{CFDI_NS}}}Retencion", Impuesto="001", Importe=str(doc.isr_retenido))
            if doc.iva_retenido:
                _sub(retenciones, f"{{{CFDI_NS}}}Retencion", Impuesto="002", Importe=str(doc.iva_retenido))

    complemento = etree.SubElement(root, f"{{{CFDI_NS}}}Complemento")
    if doc.tipo == "P":
        pagos = etree.SubElement(complemento, f"{{{PAGO_NS}}}Pagos")
        pagos.set("Version", "2.0")
        for pago in doc.pagos:
            pago_el = _sub(
                pagos,
                f"{{{PAGO_NS}}}Pago",
                FechaPago=f"{pago['fecha_pago']}T12:00:00",
                FormaDePagoP=str(pago.get("forma_pago", "03")),
                MonedaP=CURRENCY,
                Monto=str(pago["monto"]),
            )
            _sub(
                pago_el,
                f"{{{PAGO_NS}}}DoctoRelacionado",
                IdDocumento=str(pago["uuid_relacionado"]),
                MonedaDR=CURRENCY,
                NumParcialidad="1",
                ImpPagado=str(pago["monto"]),
            )
    tfd = _sub(complemento, f"{{{TFD_NS}}}TimbreFiscalDigital", UUID=doc.uuid)
    tfd.set("Version", "1.1")
    tfd.set("FechaTimbrado", doc.fecha)
    tfd.set("RfcProvCertif", "AAA010101AAA")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# --------------------------------------------------------------------------- bank


@dataclass
class BankRow:
    fecha: str
    descripcion: str
    cargo: Decimal
    abono: Decimal
    cfdi_uuid: str | None = None


def bank_rows() -> list[BankRow]:
    """BBVA-shaped rows. August deliberately omits AGO-PUE-E and adds an unbacked deposit."""
    return [
        BankRow("2026-06-06", "SPEI RECIBIDO CLIENTE ALFA", D("0"), D("22950.00"), "JUN-PUE-A"),
        BankRow("2026-06-10", "PAGO PROVEEDOR GAMMA", D("3480.00"), D("0"), "REC-JUN-1"),
        BankRow("2026-07-08", "SPEI RECIBIDO CLIENTE BETA", D("0"), D("34800.00"), "JUN-PPD-B"),
        BankRow("2026-07-11", "SPEI RECIBIDO CLIENTE BETA", D("0"), D("17400.00"), "JUL-PUE-C"),
        BankRow("2026-07-15", "COMPRA PROVEEDOR GAMMA", D("4640.00"), D("0"), "REC-JUL-1"),
        BankRow("2026-08-06", "SPEI RECIBIDO CLIENTE ALFA", D("0"), D("28687.50"), "AGO-PUE-D"),
        BankRow("2026-08-07", "PAGO PROVEEDOR GAMMA", D("5800.00"), D("0"), "REC-AGO-1"),
        BankRow("2026-08-12", "COMPRA EQUIPO DE COMPUTO", D("23200.00"), D("0"), "REC-AGO-3"),
        BankRow("2026-08-15", "DEPOSITO EN EFECTIVO VENTANILLA", D("0"), D("6500.00"), None),
    ]


def write_bank_csvs(ws_dir: Path) -> list[Path]:
    bank_dir = ws_dir / "docs" / "bank"
    bank_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for period in PERIODS:
        rows = [r for r in bank_rows() if r.fecha.startswith(period)]
        path = bank_dir / f"bbva-{period}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Fecha", "Descripcion", "Cargo", "Abono", "Referencia"])
            for row in rows:
                writer.writerow(
                    [row.fecha, row.descripcion, str(row.cargo), str(row.abono), row.cfdi_uuid or ""]
                )
        written.append(path)
    return written


# --------------------------------------------------------------------------- ledger

EXPENSE_ACCOUNT = {
    "REC-JUN-1": "Expenses:Software",
    "REC-JUL-1": "Expenses:Office",
    "REC-AGO-1": "Expenses:Software",
    "REC-AGO-2": "Expenses:Food:Restaurants",
    "REC-AGO-3": "Assets:FixedAssets:Equipo",
}


def _mx(value: Decimal) -> Amount:
    return Amount(amount=q2(value), currency=CURRENCY)


def _post_ledger(ledger: BeancountLedger, docs: list[Doc]) -> int:
    by_uuid = {d.uuid: d for d in docs}
    count = 0

    ledger.append(
        WS_ID,
        Transaction(
            date=date(2026, 6, 1),
            payee=None,
            narration="Saldos iniciales / Opening balances",
            postings=[
                Posting(account="Assets:Bank:BBVA", amount=_mx(D("50000.00"))),
                Posting(account="Assets:Cash", amount=_mx(D("5000.00"))),
                Posting(account="Equity:Opening"),
            ],
            meta={"source": "demo"},
            links=["demo-opening"],
            tags=["demo"],
        ),
    )
    count += 1

    for row in bank_rows():
        day = date.fromisoformat(row.fecha)
        doc = by_uuid.get(row.cfdi_uuid or "")
        meta: dict[str, str] = {"source": "demo-bank"}
        if row.cfdi_uuid:
            meta["cfdi_uuid"] = row.cfdi_uuid
        if row.abono > 0:  # deposit
            if doc is None:
                postings = [
                    Posting(account="Assets:Bank:BBVA", amount=_mx(row.abono)),
                    Posting(account="Income:Other"),
                ]
            else:
                postings = [
                    Posting(account="Assets:Bank:BBVA", amount=_mx(row.abono)),
                    Posting(account="Assets:Taxes:ISR-Retenido", amount=_mx(doc.isr_retenido)),
                    Posting(account="Income:Freelance", amount=_mx(-doc.subtotal)),
                    Posting(account="Liabilities:Taxes:IVA-Trasladado", amount=_mx(-doc.iva_trasladado)),
                ]
                if doc.isr_retenido == 0:
                    postings = [p for p in postings if p.account != "Assets:Taxes:ISR-Retenido"]
        else:
            assert doc is not None, "every withdrawal in the demo has a CFDI behind it"
            postings = [
                Posting(account=EXPENSE_ACCOUNT[doc.uuid], amount=_mx(doc.subtotal)),
                Posting(account="Assets:Taxes:IVA-Acreditable", amount=_mx(doc.iva_trasladado)),
                Posting(account="Assets:Bank:BBVA", amount=_mx(-row.cargo)),
            ]
        ledger.append(
            WS_ID,
            Transaction(
                date=day,
                payee=row.descripcion.title(),
                narration=row.descripcion,
                postings=postings,
                meta=meta,
                links=[f"bank-{row.fecha}-{row.cfdi_uuid or 'sin-cfdi'}"],
                tags=["demo"],
            ),
        )
        count += 1

    # Cash-paid expense: never touches the bank, so it has no CSV row.
    cash = by_uuid["REC-AGO-2"]
    ledger.append(
        WS_ID,
        Transaction(
            date=date(2026, 8, 9),
            payee=SUPPLIER[1],
            narration="Comida de trabajo pagada en efectivo",
            postings=[
                Posting(account=EXPENSE_ACCOUNT[cash.uuid], amount=_mx(cash.total)),
                Posting(account="Assets:Cash"),
            ],
            meta={"source": "demo", "cfdi_uuid": cash.uuid, "forma_pago": "01"},
            links=["cash-REC-AGO-2"],
            tags=["demo"],
        ),
    )
    count += 1

    # Invoices issued but not collected stay as receivables.
    for uuid in ("AGO-PUE-E", "AGO-PPD-F"):
        doc = by_uuid[uuid]
        ledger.append(
            WS_ID,
            Transaction(
                date=date.fromisoformat(doc.fecha[:10]),
                payee=doc.receptor_nombre,
                narration=f"Factura {uuid} emitida, pendiente de cobro",
                postings=[
                    Posting(account="Assets:Receivable:Clients", amount=_mx(doc.total)),
                    Posting(account="Income:Freelance", amount=_mx(-doc.subtotal)),
                    Posting(account="Liabilities:Taxes:IVA-Trasladado", amount=_mx(-doc.iva_trasladado)),
                ],
                meta={"source": "demo", "cfdi_uuid": uuid},
                links=[f"ar-{uuid}"],
                tags=["demo"],
            ),
        )
        count += 1
    return count


# --------------------------------------------------------------------------- manifest

EXPECTED_DIFFS = [
    {"kind": "pue_not_collected", "amount": "13920.00", "documents": ["AGO-PUE-E"]},
    {"kind": "ppd_missing_rep", "amount": "9280.00", "documents": ["AGO-PPD-F"]},
    {"kind": "deposit_without_cfdi", "amount": "6500.00", "documents": []},
    {"kind": "cash_paid_expense", "amount": "160.00", "documents": ["REC-AGO-2"]},
    {"kind": "fixed_asset_iva", "amount": "3200.00", "documents": ["REC-AGO-3"]},
]

EXPECTED_FIGURES = {
    "2026-06": {"income_collected": "20000.00", "isr": "200.00", "iva_payable": "2720.00"},
    "2026-07": {"income_collected": "45000.00", "isr": "495.00", "iva_payable": "6560.00"},
    "2026-08": {
        "income_collected": "37000.00",
        "isr": "407.00",
        "iva_trasladado": "5920.00",
        "iva_acreditable": "800.00",
        "iva_payable": "5120.00",
        "isr_retenido": "312.50",
    },
}


def manifest(docs: list[Doc]) -> dict[str, Any]:
    return {
        "workspace": WS_ID,
        "rfc": RFC,
        "regime": "RESICO_PF",
        "currency": CURRENCY,
        "periods": PERIODS,
        "audit_period": "2026-08",
        "documents": len(docs),
        "expected_diffs": EXPECTED_DIFFS,
        "expected_figures": EXPECTED_FIGURES,
        "notes": [
            "Todo es sintético: RFC, clientes, proveedores y movimientos bancarios son inventados.",
            "AGO-PUE-E se factura pero nunca se cobra; el depósito del 2026-08-15 no tiene CFDI.",
            "REC-AGO-2 se pagó en efectivo (forma 01) y REC-AGO-3 es inversión (uso I04).",
        ],
    }


# --------------------------------------------------------------------------- entry point


def build_demo(data_dir: str | Path | None = None, force: bool = False) -> dict[str, Any]:
    """Create the ``demo-mx`` workspace. Idempotent: an existing workspace is left untouched."""
    import os

    if data_dir is not None:
        os.environ["AURUM_DATA_DIR"] = str(data_dir)

    from ..core.config import settings

    ws_dir = settings().workspace_dir(WS_ID)
    manifest_path = ws_dir / "docs" / "demo-manifest.json"
    if manifest_path.exists() and not force:
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    try:
        get_workspace(WS_ID)
    except Exception:  # noqa: BLE001 — WorkspaceNotFound, or an unreadable file we are replacing
        save_workspace(
            Workspace(
                id=WS_ID,
                name="Demo México (RESICO)",
                kind="personal",
                jurisdictions=["MX"],
                base_currency=CURRENCY,
                language="es",
                profile={"rfc": RFC, "regime": "RESICO_PF", "state": "NL", "country": "MX", "demo": True},
                # the RESICO demo shows the tax side; tax nudges/calendar items are gated on this flag
                modules=Modules(tax=True),
            )
        )

    docs = documents()
    cfdi_dir = ws_dir / "docs" / "cfdi"
    cfdi_dir.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        (cfdi_dir / f"{doc.uuid}.xml").write_bytes(cfdi_xml(doc))
    (cfdi_dir / "index.json").write_text(
        json.dumps({"documents": [d.as_dict() for d in docs]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    write_bank_csvs(ws_dir)

    ledger = BeancountLedger()
    ledger.apply_template(WS_ID, "mx_resico_pf", CURRENCY)
    posted = _post_ledger(ledger, docs)

    data = manifest(docs)
    data["transactions_posted"] = posted

    from .extras import seed_extras  # ingest table + pf tables (labels, budgets, goals, card, loan)

    data["extras"] = seed_extras(WS_ID, ws_dir, RFC, PERIODS[-1], CURRENCY)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return data
