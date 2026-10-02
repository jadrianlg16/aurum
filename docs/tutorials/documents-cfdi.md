# Documents: getting CFDIs in

**What it does.** Parses CFDI 4.0 XML (facturas de ingreso/egreso and *complementos de pago*) into
structured rows, files them under the workspace, and proposes ledger entries.

**Three ways in, most private first**
1. **Drop XML or a ZIP** on Documentos → *Subir CFDI*. Works with any PAC or SAT portal export.
2. **SAT sync (opt-in)** — Herramientas → *Bóveda e.firma*: upload `.cer`, `.key` and the key password
   with a passphrase of your choosing. The files are encrypted at rest; the passphrase lives only in
   memory while a sync runs; nothing here can sign or submit. Then *Sincronizar* for a date range.
   Status: the real SAT Descarga Masiva client is **not yet verified** in this build (the installed `satcfdi`
   lacks the expected service; the endpoint returns 501). The fixture-driven `FakeSAT` path is what the
   demo and tests use (`AURUM_SAT_FAKE_DIR`).
3. **Aggregators** (Belvo Fiscal, Syntage) — not wired; a later, optional, privacy trade-off.

**What Aurum reads from each XML**: UUID, tipo (I/E/P), fecha, RFC emisor/receptor, subtotal/total,
**método de pago (PUE/PPD)**, forma de pago, uso CFDI, IVA trasladado, ISR/IVA retenido, and for
complementos de pago the `FechaPago`, monto and related UUIDs. Those payment fields drive cash-basis
income (see month-close-prefill-audit.md), so they are first-class columns in the table.

**Filters** on the Documentos table: period, tipo, PUE/PPD, emitido/recibido. A row expands to its
fields and, for a REP, the payments it covers.

**API equivalent**
```
POST /api/ingest/demo-mx/cfdi        multipart file=<xml|zip>
GET  /api/ingest/demo-mx/cfdi?period=2026-08
```

**Gotchas**
- The parser takes taxes from the comprobante-level `cfdi:Impuestos` block; per-concepto blocks are
  ignored to avoid double counting. If an emitter writes only `TotalImpuestosTrasladados`, that total is
  treated as IVA.
- Real RFCs never belong in fixtures or commits. The demo uses `XAXX010101000`-style placeholders.
