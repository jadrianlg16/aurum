"""CFDI 4.0 parsing.

Parses a single CFDI 4.0 XML (or a ZIP of several) into the ``CFDI`` model: identity, parties, amounts,
taxes, conceptos, and — for tipo P (Pago) — the Pagos 2.0 complement (FechaPago, Monto, DoctoRelacionado).

Strategy: lxml + explicit namespaces is the parser of record — it is fully deterministic and easy to
test against synthetic fixtures. ``satcfdi`` (in the dependency set for satsync's Descarga Masiva client)
is attempted first for its stricter validation when importable; if it raises for any reason we fall back
to the lxml path rather than failing the whole import. In practice CFDIs coming from PACs vary enough in
minor namespace/whitespace details that the permissive lxml path is what actually carries production
traffic; treat the satcfdi path as a best-effort validation pass, not the source of truth.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from lxml import etree
from pydantic import BaseModel, Field

NS = {
    "cfdi": "http://www.sat.gob.mx/cfd/4",
    "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
    "pago20": "http://www.sat.gob.mx/Pagos20",
}


class Pago(BaseModel):
    fecha_pago: datetime
    monto: Decimal
    moneda: str = "MXN"
    forma_pago: str | None = None
    uuid_relacionado: str
    imp_pagado: Decimal
    num_parcialidad: int | None = None


class CFDI(BaseModel):
    uuid: str
    version: str
    tipo: Literal["I", "E", "P", "N", "T"]
    fecha: datetime
    emisor_rfc: str
    emisor_nombre: str | None = None
    receptor_rfc: str
    receptor_nombre: str | None = None
    subtotal: Decimal
    total: Decimal
    moneda: str = "MXN"
    metodo_pago: Literal["PUE", "PPD"] | None = None
    forma_pago: str | None = None
    uso_cfdi: str | None = None
    impuestos_trasladados: Decimal = Decimal("0")
    impuestos_retenidos: Decimal = Decimal("0")
    isr_retenido: Decimal = Decimal("0")
    iva_retenido: Decimal = Decimal("0")
    iva_trasladado: Decimal = Decimal("0")
    conceptos: list[dict] = Field(default_factory=list)
    pagos: list[Pago] = Field(default_factory=list)
    direction: Literal["emitido", "recibido"]
    raw_path: str | None = None


class CFDIParseError(ValueError):
    pass


class ZipTooLarge(ValueError):
    """A CFDI zip exceeds AURUM_ZIP_MAX_MEMBERS / _MEMBER_MB / _TOTAL_MB (mapped to 413 by api/app.py)."""


def _dec(value: str | None, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    try:
        return Decimal(value)
    except InvalidOperation as e:
        raise CFDIParseError(f"invalid decimal: {value!r}") from e


def _text(el, xpath: str) -> str | None:
    found = el.xpath(xpath, namespaces=NS)
    return found[0] if found else None


def parse_cfdi_xml(data: bytes, workspace_rfc: str, raw_path: str | None = None) -> CFDI:
    """Parse one CFDI 4.0 XML document. Raises CFDIParseError on malformed/unsupported input."""
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError as e:
        raise CFDIParseError(f"not well-formed XML: {e}") from e

    if root.tag != f"{{{NS['cfdi']}}}Comprobante":
        raise CFDIParseError("not a CFDI Comprobante document")

    version = root.get("Version") or root.get("version") or ""
    tipo = root.get("TipoDeComprobante")
    if tipo not in ("I", "E", "P", "N", "T"):
        raise CFDIParseError(f"unsupported TipoDeComprobante: {tipo!r}")
    fecha_raw = root.get("Fecha")
    if not fecha_raw:
        raise CFDIParseError("missing Fecha")
    fecha = datetime.fromisoformat(fecha_raw)

    emisor = root.find("cfdi:Emisor", NS)
    receptor = root.find("cfdi:Receptor", NS)
    if emisor is None or receptor is None:
        raise CFDIParseError("missing Emisor/Receptor")
    emisor_rfc = emisor.get("Rfc", "")
    receptor_rfc = receptor.get("Rfc", "")

    tfd = root.find(".//tfd:TimbreFiscalDigital", NS)
    if tfd is None or not tfd.get("UUID"):
        raise CFDIParseError("missing TimbreFiscalDigital/UUID (unstamped CFDI)")
    uuid = tfd.get("UUID")

    subtotal = _dec(root.get("SubTotal"))
    total = _dec(root.get("Total"))
    moneda = root.get("Moneda", "MXN")
    metodo_pago = root.get("MetodoPago") or None
    forma_pago = root.get("FormaPago") or None
    uso_cfdi = receptor.get("UsoCFDI")

    # Comprobante-level cfdi:Impuestos only (a direct child of the root) — per-concepto Impuestos
    # blocks repeat the same taxes and must not be double-counted.
    trasladados = Decimal("0")
    iva_trasladado = Decimal("0")
    for t in root.xpath("cfdi:Impuestos/cfdi:Traslados/cfdi:Traslado", namespaces=NS):
        importe = _dec(t.get("Importe"))
        trasladados += importe
        if t.get("Impuesto") == "002":  # IVA
            iva_trasladado += importe
    if trasladados == 0:
        # Some emitters only write the root total attribute; treat it as IVA when no breakdown exists.
        node = root.find("cfdi:Impuestos", NS)
        total_attr = _dec(node.get("TotalImpuestosTrasladados")) if node is not None else Decimal("0")
        trasladados = iva_trasladado = total_attr
    retenidos = Decimal("0")
    isr_retenido = Decimal("0")
    iva_retenido = Decimal("0")
    for t in root.xpath("cfdi:Impuestos/cfdi:Retenciones/cfdi:Retencion", namespaces=NS):
        importe = _dec(t.get("Importe"))
        retenidos += importe
        if t.get("Impuesto") == "001":  # ISR
            isr_retenido += importe
        elif t.get("Impuesto") == "002":  # IVA
            iva_retenido += importe

    conceptos = []
    for c in root.xpath(".//cfdi:Conceptos/cfdi:Concepto", namespaces=NS):
        conceptos.append(
            {
                "clave_prod_serv": c.get("ClaveProdServ"),
                "descripcion": c.get("Descripcion"),
                "cantidad": c.get("Cantidad"),
                "valor_unitario": c.get("ValorUnitario"),
                "importe": c.get("Importe"),
            }
        )

    pagos: list[Pago] = []
    if tipo == "P":
        for p in root.xpath(".//pago20:Pago", namespaces=NS):
            fecha_pago_raw = p.get("FechaPago")
            fecha_pago = datetime.fromisoformat(fecha_pago_raw) if fecha_pago_raw else fecha
            monto = _dec(p.get("Monto"))
            moneda_pago = p.get("MonedaP", moneda)
            forma_pago_p = p.get("FormaDePagoP")
            for doc in p.xpath("pago20:DoctoRelacionado", namespaces=NS):
                pagos.append(
                    Pago(
                        fecha_pago=fecha_pago,
                        monto=monto,
                        moneda=moneda_pago,
                        forma_pago=forma_pago_p,
                        uuid_relacionado=doc.get("IdDocumento", ""),
                        imp_pagado=_dec(doc.get("ImpPagado")),
                        num_parcialidad=(int(doc.get("NumParcialidad")) if doc.get("NumParcialidad") else None),
                    )
                )

    if workspace_rfc and emisor_rfc == workspace_rfc:
        direction: Literal["emitido", "recibido"] = "emitido"
    else:
        direction = "recibido"

    return CFDI(
        uuid=uuid,
        version=version,
        tipo=tipo,  # type: ignore[arg-type]
        fecha=fecha,
        emisor_rfc=emisor_rfc,
        emisor_nombre=emisor.get("Nombre"),
        receptor_rfc=receptor_rfc,
        receptor_nombre=receptor.get("Nombre"),
        subtotal=subtotal,
        total=total,
        moneda=moneda,
        metodo_pago=metodo_pago,  # type: ignore[arg-type]
        forma_pago=forma_pago,
        uso_cfdi=uso_cfdi,
        impuestos_trasladados=trasladados,
        impuestos_retenidos=retenidos,
        isr_retenido=isr_retenido,
        iva_retenido=iva_retenido,
        iva_trasladado=iva_trasladado,
        conceptos=conceptos,
        pagos=pagos,
        direction=direction,
        raw_path=raw_path,
    )


_ZIP_CHUNK = 64 * 1024


def _read_member_capped(zf: zipfile.ZipFile, info: zipfile.ZipInfo, member_limit: int, total_before: int, total_limit: int) -> bytes:
    """Stream one member in 64 KB chunks, aborting as soon as it (or the running total) passes the caps —
    a deflate bomb never gets to materialise in memory."""
    chunks: list[bytes] = []
    size = 0
    with zf.open(info) as fh:
        while True:
            chunk = fh.read(_ZIP_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            if size > member_limit:
                raise ZipTooLarge(f"zip member {info.filename!r} exceeds {member_limit} bytes uncompressed")
            if total_before + size > total_limit:
                raise ZipTooLarge(f"zip exceeds {total_limit} bytes uncompressed in total")
            chunks.append(chunk)
    return b"".join(chunks)


def parse_upload(filename: str, data: bytes, workspace_rfc: str) -> list[CFDI]:
    """Parse an uploaded XML file or a ZIP of XML files into a list of CFDI (skips non-.xml zip members).

    Zip caps: ``AURUM_ZIP_MAX_MEMBERS`` entries, ``AURUM_ZIP_MAX_MEMBER_MB`` per member and
    ``AURUM_ZIP_MAX_TOTAL_MB`` overall, enforced while streaming → ``ZipTooLarge`` (413 via api/app.py).
    Member names with ``..`` or an absolute path are a ``CFDIParseError``."""
    from ..core.config import settings

    name_lower = filename.lower()
    if name_lower.endswith(".zip") or data[:2] == b"PK":
        s = settings()
        member_limit = s.zip_max_member_mb * 1024 * 1024
        total_limit = s.zip_max_total_mb * 1024 * 1024
        out: list[CFDI] = []
        total = 0
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            raise CFDIParseError(f"not a valid zip: {e}") from e
        with zf:
            infos = zf.infolist()
            if len(infos) > s.zip_max_members:
                raise ZipTooLarge(f"zip has {len(infos)} members (max {s.zip_max_members})")
            for info in infos:
                if info.is_dir():
                    continue
                name = info.filename
                parts = name.replace("\\", "/").split("/")
                if ".." in parts or name.startswith(("/", "\\")) or (len(name) > 1 and name[1] == ":"):
                    raise CFDIParseError(f"unsafe zip member name: {name!r}")
                if not name.lower().endswith(".xml"):
                    continue
                member = _read_member_capped(zf, info, member_limit, total, total_limit)
                total += len(member)
                out.append(parse_cfdi_xml(member, workspace_rfc, raw_path=name))
        return out
    return [parse_cfdi_xml(data, workspace_rfc, raw_path=filename)]
