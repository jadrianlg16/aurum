"""Minimal synthetic CFDI 4.0 XML builder for tests (fake RFCs, no real taxpayer data)."""

from __future__ import annotations

RFC_EMISOR = "XAXX010101000"
RFC_RECEPTOR = "EKU9003173C9"


def build_ingreso_pue_xml(
    uuid: str = "AAAAAAAA-1111-2222-3333-444444444444",
    emisor_rfc: str = RFC_EMISOR,
    receptor_rfc: str = RFC_RECEPTOR,
    fecha: str = "2026-08-15T10:00:00",
    subtotal: str = "1000.00",
    total: str = "1160.00",
    metodo_pago: str = "PUE",
) -> bytes:
    iva = "160.00"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
    xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
    Version="4.0" Fecha="{fecha}" TipoDeComprobante="I" SubTotal="{subtotal}" Total="{total}"
    Moneda="MXN" MetodoPago="{metodo_pago}" FormaPago="03" LugarExpedicion="64000">
  <cfdi:Emisor Rfc="{emisor_rfc}" Nombre="Emisor de Prueba SA de CV" RegimenFiscal="626"/>
  <cfdi:Receptor Rfc="{receptor_rfc}" Nombre="Receptor de Prueba" UsoCFDI="G03" DomicilioFiscalReceptor="64000" RegimenFiscalReceptor="616"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="80131500" Descripcion="Servicios de consultoria" Cantidad="1"
        ValorUnitario="{subtotal}" Importe="{subtotal}">
      <cfdi:Impuestos>
        <cfdi:Traslados>
          <cfdi:Traslado Base="{subtotal}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{iva}"/>
        </cfdi:Traslados>
      </cfdi:Impuestos>
    </cfdi:Concepto>
  </cfdi:Conceptos>
  <cfdi:Impuestos TotalImpuestosTrasladados="{iva}">
    <cfdi:Traslados>
      <cfdi:Traslado Base="{subtotal}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{iva}"/>
    </cfdi:Traslados>
  </cfdi:Impuestos>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="{uuid}" FechaTimbrado="{fecha}"
        SelloCFD="x" NoCertificadoSAT="00000000000000000000" SelloSAT="x" RfcProvCertif="SAT970701NN3"/>
  </cfdi:Complemento>
</cfdi:Comprobante>"""
    return xml.encode("utf-8")


def build_pago_xml(
    uuid: str = "BBBBBBBB-1111-2222-3333-444444444444",
    emisor_rfc: str = RFC_RECEPTOR,
    receptor_rfc: str = RFC_EMISOR,
    fecha: str = "2026-09-02T09:00:00",
    fecha_pago: str = "2026-09-01T00:00:00",
    monto: str = "1160.00",
    uuid_relacionado: str = "CCCCCCCC-1111-2222-3333-444444444444",
) -> bytes:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
    xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
    xmlns:pago20="http://www.sat.gob.mx/Pagos20"
    Version="4.0" Fecha="{fecha}" TipoDeComprobante="P" SubTotal="0" Total="0" Moneda="XXX" LugarExpedicion="64000">
  <cfdi:Emisor Rfc="{emisor_rfc}" Nombre="Receptor de Prueba" RegimenFiscal="616"/>
  <cfdi:Receptor Rfc="{receptor_rfc}" Nombre="Emisor de Prueba SA de CV" UsoCFDI="CP01" DomicilioFiscalReceptor="64000" RegimenFiscalReceptor="626"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="84111506" Descripcion="Pago" Cantidad="1" ValorUnitario="0" Importe="0"/>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <pago20:Pagos Version="2.0">
      <pago20:Totales MontoTotalPagos="{monto}"/>
      <pago20:Pago FechaPago="{fecha_pago}" FormaDePagoP="03" MonedaP="MXN" Monto="{monto}">
        <pago20:DoctoRelacionado IdDocumento="{uuid_relacionado}" MonedaDR="MXN" NumParcialidad="1"
            ImpSaldoAnt="{monto}" ImpPagado="{monto}" ImpSaldoInsoluto="0.00"/>
      </pago20:Pago>
    </pago20:Pagos>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="{uuid}" FechaTimbrado="{fecha}"
        SelloCFD="x" NoCertificadoSAT="00000000000000000000" SelloSAT="x" RfcProvCertif="SAT970701NN3"/>
  </cfdi:Complemento>
</cfdi:Comprobante>"""
    return xml.encode("utf-8")
