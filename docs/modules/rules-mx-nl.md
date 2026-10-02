# rules-mx-nl — Nuevo León payroll tax, IMSS employer quotas, INFONAVIT

Three rules in `aurum/rules/mx/nl.py`, every constant in `aurum/rules/mx/nl_constants_2026.py`,
vectors in `aurum/rules/vectors/mx.{nl.isn,imss.employer_quotas,infonavit.employer}.yaml`.
Registered from `aurum/rules/registry.py::load_rules()` (the guarded import list).

| Rule | What it computes |
|---|---|
| `mx.nl.isn@2026.1` | Impuesto Sobre Nóminas NL: 3% of the taxable payroll base (LHENL arts. 154-160) |
| `mx.imss.employer_quotas@2026.1` | Employer IMSS quotas by branch on the SBC, with the 25-UMA cap; `breakdown()` returns them per branch |
| `mx.infonavit.employer@2026.1` | 5% of the same capped base (LINFONAVIT art. 29 fr. II) |

`GET /api/business/constants/mx-nl` serves the whole table below as JSON, with `verified` per row.

## Verification pass — 2026-09-06

Primary texts fetched and read on 2026-09-06:

- **Ley de Hacienda del Estado de Nuevo León**, cap. octavo, arts. 154-160 (compiled text published by
  the H. Congreso del Estado de NL): rate 3% (art. 157), base (art. 156), due day 17 (art. 158),
  quarterly option under $36,000 annual tax (art. 158), exemption list (art. 160).
- **Ley del Seguro Social**, Cámara de Diputados PDF, *última reforma DOF 15-01-2026*: arts. 25, 28,
  71/72, 106, 107, 147, 168, 211/212, plus the "Décimo Noveno" transitorio of the 1995 law (the
  1998-2007 phase-in that turns art. 106's 13.9% into 20.4% and its 6%/2% into 1.10%/0.40%).
- **Ley del INFONAVIT**, *última reforma DOF 21-02-2025*: art. 29 fr. II — 5%.
- **INEGI** comunicado 1/26 (8 Jan 2026): UMA 2026 = 117.31 daily, in force from 1 Feb 2026.
- **CONASAMI** (gob.mx, DOF 09-12-2025): minimum wage 2026 = 315.04 general / 440.87 ZLFN.

## Constants

| Constant | Value | Source (article) | URL | Verified |
|---|---|---|---|---|
| `uma.daily` | `117.31` | INEGI art. Comunicado de prensa 1/26 — UMA 2026 | [link](https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/uma/uma2026.pdf) | yes |
| `uma.monthly` | `3566.22` | INEGI art. Comunicado de prensa 1/26 — UMA 2026 | [link](https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/uma/uma2026.pdf) | yes |
| `salario_minimo.general_daily` | `315.04` | CONASAMI art. Salarios mínimos 2026 (DOF 09-12-2025) | [link](https://www.gob.mx/conasami/articulos/incremento-a-los-salarios-minimos-para-2026) | yes |
| `salario_minimo.zlfn_daily` | `440.87` | CONASAMI art. Salarios mínimos 2026 (DOF 09-12-2025) | [link](https://www.gob.mx/conasami/articulos/incremento-a-los-salarios-minimos-para-2026) | yes |
| `isn.nl.rate` | `0.03` | Ley de Hacienda del Estado de Nuevo León art. 157 | [link](https://www.hcnl.gob.mx/trabajo_legislativo/leyes/pdf/LEY%20DE%20HACIENDA%20DEL%20ESTADO%20DE%20NUEVO%20LEON.doc) | yes |
| `isn.nl.due_day` | `17` | Ley de Hacienda del Estado de Nuevo León art. 158 | [link](https://www.hcnl.gob.mx/trabajo_legislativo/leyes/pdf/LEY%20DE%20HACIENDA%20DEL%20ESTADO%20DE%20NUEVO%20LEON.doc) | yes |
| `isn.nl.quarterly_option_annual_tax` | `36000` | Ley de Hacienda del Estado de Nuevo León art. 158 | [link](https://www.hcnl.gob.mx/trabajo_legislativo/leyes/pdf/LEY%20DE%20HACIENDA%20DEL%20ESTADO%20DE%20NUEVO%20LEON.doc) | yes |
| `isn.nl.exempt_concepts` | see module | Ley de Hacienda del Estado de Nuevo León art. 160 | [link](https://www.hcnl.gob.mx/trabajo_legislativo/leyes/pdf/LEY%20DE%20HACIENDA%20DEL%20ESTADO%20DE%20NUEVO%20LEON.doc) | yes |
| `isn.nl.taxable_concepts` | see module | Ley de Hacienda del Estado de Nuevo León art. 154 | [link](https://www.hcnl.gob.mx/trabajo_legislativo/leyes/pdf/LEY%20DE%20HACIENDA%20DEL%20ESTADO%20DE%20NUEVO%20LEON.doc) | yes |
| `imss.sbc_cap_uma` | `25` | LSS art. 28 | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.em.excedente_threshold_uma` | `3` | LSS art. 106 II | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.riesgos_trabajo.minimum_prima` | `0.005` | LSS art. 72 | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.em.especie.cuota_fija_uma` | `0.204` | LSS art. 106 I | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.em.especie.excedente_employer` | `0.0110` | LSS art. 106 II | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.em.especie.excedente_employee` | `0.0040` | LSS art. 106 II | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.em.dinero.total` | `0.01` | LSS art. 107 | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.em.dinero.employer` | `0.0070` | LSS art. 107 | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.em.dinero.employee` | `0.0025` | LSS art. 107 | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.gastos_medicos_pensionados.employer` | `0.0105` | LSS art. 25 | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.gastos_medicos_pensionados.employee` | `0.00375` | LSS art. 25 | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.invalidez_vida.employer` | `0.0175` | LSS art. 147 | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.invalidez_vida.employee` | `0.00625` | LSS art. 147 | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.retiro.employer` | `0.02` | LSS art. 168 I | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.cesantia_vejez.employee` | `0.01125` | LSS art. 168 II b) | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.cesantia_vejez.employer_table_2026` | see module | LSS art. 168 II a) + transitorio Segundo (DOF 16-12-2020) | [link](https://dof.gob.mx/nota_detalle.php?codigo=5607729&fecha=16/12/2020) | **(verify)** |
| `imss.cesantia_vejez.employer_table_final` | see module | LSS art. 168 II a) | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `imss.guarderias.employer` | `0.01` | LSS art. 211 | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | yes |
| `infonavit.employer` | `0.05` | LINFONAVIT art. 29 fr. II | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LIFNVT.pdf) | yes |
| `isr.subsidio_empleo.monthly` | `536.22` | LISR art. Subsidio para el empleo (decreto / RMF 2026) | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf) | **(verify)** |
| `isr.subsidio_empleo.income_cap_monthly` | `11492.66` | LISR art. Subsidio para el empleo (decreto / RMF 2026) | [link](https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf) | **(verify)** |

## What is NOT verified

1. **`imss.cesantia_vejez.employer_table_2026`** — the 2023-2030 graduated employer table lives in the
   *transitorio Segundo* of the DOF 16-12-2020 decree, and both the DOF nota and the Diputados PDF
   publish it **as an image**, so it could not be read. The 2026 column used here (3.150 / 3.676 /
   4.851 / 5.556 / 6.026 / 6.361 / 6.613 / 7.513 %) is the widely published one, and
   `tests/business/test_rules_mx_nl.py::test_the_2026_cesantia_column_interpolates_the_verified_final_table`
   checks it against a straight-line interpolation from the 3.150% in force through 2022 to the final
   art. 168 II a) table (which *was* read) over the eight steps 2023…2030 — it matches to ±0.001 pp.
   That is a cross-check, **not** a primary reading, so the constant stays `verified=False` and every
   payroll run carries a `(verify)` warning.
2. **`isr.subsidio_empleo.*`** — not yet checked against the 2026 subsidio decree. The amount (536.22 monthly) and
   the income ceiling (11,492.66) are provisional; a run that applies the subsidy says so.
3. **Riesgo de trabajo prima** — employer-specific by law (LSS art. 71/72 siniestralidad formula).
   Only the statutory minimum `M = 0.005` is a constant; callers pass `riesgo_prima` and the explain
   marks the default `(verify)`.

## ISN base and exemptions

Art. 154 sweeps in every remuneration (including viáticos, despensa, fondo de ahorro, aguinaldo, tiempo
extra, comisiones, premios, honorarios preponderantes and payments to directors/comisarios); art. 160
then takes some back out — PTU, indemnizaciones por riesgo, pensiones, indemnizaciones por despido,
gastos funerarios, viáticos comprobados, fondo de ahorro, despensa, alimentación and remuneraciones to
certified disabled workers. Where they overlap, the art. 160 exemption wins. Art. 160 fr. II also
exempts whole *employers* (welfare non-profits, chambers, unions, schools, service clubs, religious
associations) — Aurum never assumes this; pass `exempt_entity=true`.

## Rule inputs

```
mx.nl.isn                 payroll?, concepts?{concept: amount}, exempt_amount?, exempt_entity?, currency?
mx.imss.employer_quotas   sbc_daily, days=30, riesgo_prima?, currency?   (+ .breakdown(**same) -> per branch)
mx.infonavit.employer     sbc_daily, days=30 | base, currency?
```

## Adding a year

Do not mutate a rule: add the new constants (a new `nl_constants_2027.py` or dated entries), register a
new **version** with its own `effective_from`, and ship its vectors. `registry.get(id, on=date)` then
resolves history correctly. The UMA changes every 1 February, so a period straddling January uses the
prior year's UMA — currently the rules use the 2026 UMA for the whole year `(verify for January)`.

## Tests

`tests/business/test_rules_mx_nl.py` (rules, constants, the cesantía cross-check) plus the YAML vectors
run by `tests/rules/test_vectors.py`.
