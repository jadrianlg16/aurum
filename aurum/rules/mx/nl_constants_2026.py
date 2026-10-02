"""Year-effective constants for Nuevo León payroll taxes and Mexican employer social security, 2026.

Same contract as :mod:`aurum.rules.us.constants_2026`: every number a NL/IMSS/INFONAVIT rule uses is a
:class:`Const` record — ``value``, ``citation``, ``source_url``, ``verified`` — so a reader can tell
which figures were read in a primary source and which are still assumptions. Anything with
``verified=False`` renders ``(verify)`` in the explain summary of any rule that touches it
(never guess a rate).

Verification pass: **2026-09-06**. Primary texts actually fetched and read:

* **Ley de Hacienda del Estado de Nuevo León**, capítulo octavo "Impuesto Sobre Nóminas", arts. 154-160
  (compiled text published by the H. Congreso del Estado de Nuevo León). Rate 3% (art. 157), base
  art. 156, due day 17 (art. 158), exemption list art. 160.
* **Ley del Seguro Social** (Cámara de Diputados, *última reforma DOF 15-01-2026*): arts. 25, 28, 71/72,
  106, 107, 147, 168, 211/212 and the "Décimo Noveno" transitorio of the 1995 law.
* **Ley del INFONAVIT** (Cámara de Diputados, *última reforma DOF 21-02-2025*): art. 29 fr. II — 5%.
* **INEGI**, comunicado de prensa 1/26 (8 January 2026): UMA 2026 — 117.31 daily, from 1 February 2026.
* **CONASAMI** (gob.mx, DOF 09-12-2025): minimum wage 2026 — 315.04 general, 440.87 ZLFN.

What is **not** verified (``(verify)``):

* the **2023-2030 graduated cesantía y vejez employer table** (transitorio Segundo of the DOF
  16-12-2020 decree). That table is published only as an *image* in both the DOF nota and the
  Diputados PDF, so it could not be read. The 2026 column here is the widely published one and it
  reproduces, to ±0.001 pp, a straight-line interpolation between the 3.150% in force through 2022
  and the final art. 168 table (which *was* read) over the eight steps 2023…2030 — a cross-check,
  not a primary reading.
* the **subsidio para el empleo 2026** amount and income ceiling: not yet checked against the DOF decree.
* the **riesgo de trabajo prima**: it is employer-specific (LSS art. 72, siniestralidad formula); only
  the statutory minimum (0.5%) is a constant. Callers pass their own prima.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from ...core.explain import Citation

YEAR = 2026

LHENL_URL = (
    "https://www.hcnl.gob.mx/trabajo_legislativo/leyes/pdf/LEY%20DE%20HACIENDA%20DEL%20ESTADO%20DE%20NUEVO%20LEON.doc"
)
LSS_URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf"
LINFONAVIT_URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/LIFNVT.pdf"
LISR_URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf"
UMA_URL = "https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/uma/uma2026.pdf"
CONASAMI_URL = "https://www.gob.mx/conasami/articulos/incremento-a-los-salarios-minimos-para-2026"
DOF_2020_CV_URL = "https://dof.gob.mx/nota_detalle.php?codigo=5607729&fecha=16/12/2020"

VERIFIED_ON = date(2026, 9, 6)

D = Decimal


@dataclass(frozen=True)
class Const:
    """One year-effective constant with the citation that produced it."""

    key: str
    value: Any
    citation: Citation
    source_url: str
    verified: bool = False
    verified_on: date | None = None
    note: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def mark(self) -> str:
        """``""`` when read in a primary/official source, ``" (verify)"`` otherwise."""
        return "" if self.verified else " (verify)"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": _jsonable(self.value),
            "citation": self.citation.model_dump(mode="json"),
            "source_url": self.source_url,
            "verified": self.verified,
            "verified_on": self.verified_on.isoformat() if self.verified_on else None,
            "note": self.note,
        }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _lhenl(article: str, excerpt: str = "") -> Citation:
    return Citation(
        law="Ley de Hacienda del Estado de Nuevo León",
        article=article,
        url=LHENL_URL,
        effective_from=date(YEAR, 1, 1),
        trust_tier="primary",
        excerpt=excerpt or None,
    )


def _lss(article: str, excerpt: str = "") -> Citation:
    return Citation(
        law="LSS",
        article=article,
        url=LSS_URL,
        effective_from=date(YEAR, 1, 1),
        trust_tier="primary",
        excerpt=excerpt or None,
    )


def _linfonavit(article: str, excerpt: str = "") -> Citation:
    return Citation(
        law="LINFONAVIT",
        article=article,
        url=LINFONAVIT_URL,
        effective_from=date(YEAR, 1, 1),
        trust_tier="primary",
        excerpt=excerpt or None,
    )


# --------------------------------------------------------------------------- reference values

UMA_DAILY = Const(
    key="uma.daily",
    value=D("117.31"),
    citation=Citation(
        law="INEGI",
        article="Comunicado de prensa 1/26 — UMA 2026",
        url=UMA_URL,
        effective_from=date(2026, 2, 1),
        trust_tier="official_guidance",
        excerpt="Los valores de la UMA que entrarán en vigor a partir del 1 de febrero de 2026 son: Diario 117.31 pesos mexicanos.",
    ),
    source_url=UMA_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note=(
        "Read in the INEGI press release PDF (8 January 2026). Monthly 3,566.22 · annual 42,794.64. "
        "In force 2026-02-01 … 2027-01-31; January 2026 still uses the 2025 UMA (113.14)."
    ),
)

UMA_MONTHLY = Const(
    key="uma.monthly",
    value=D("3566.22"),
    citation=UMA_DAILY.citation,
    source_url=UMA_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Same INEGI release: 'Mensual 3 566.22 pesos mexicanos'.",
)

MINIMUM_WAGE_DAILY = Const(
    key="salario_minimo.general_daily",
    value=D("315.04"),
    citation=Citation(
        law="CONASAMI",
        article="Salarios mínimos 2026 (DOF 09-12-2025)",
        url=CONASAMI_URL,
        effective_from=date(2026, 1, 1),
        trust_tier="official_guidance",
        excerpt="A partir del 1 de enero del 2026 el salario mínimo general se incrementa de 278.80 a 315.04 pesos diarios.",
    ),
    source_url=CONASAMI_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Zona Libre de la Frontera Norte: 440.87 (Nuevo León's border municipios only).",
)

MINIMUM_WAGE_ZLFN_DAILY = Const(
    key="salario_minimo.zlfn_daily",
    value=D("440.87"),
    citation=MINIMUM_WAGE_DAILY.citation,
    source_url=CONASAMI_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Zona Libre de la Frontera Norte 2026.",
)

# --------------------------------------------------------------------------- ISN Nuevo León

ISN_RATE = Const(
    key="isn.nl.rate",
    value=D("0.03"),
    citation=_lhenl(
        "157",
        "Este impuesto se causará con tasa del 3% sobre la base a que se refiere el Artículo anterior.",
    ),
    source_url=LHENL_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Art. 157, last reformed P.O. 31 December 2012; read in the Congress's compiled text on 2026-09-06.",
)

ISN_DUE_DAY = Const(
    key="isn.nl.due_day",
    value=17,
    citation=_lhenl(
        "158",
        "El pago del impuesto deberá efectuarse a más tardar el día diecisiete del mes siguiente a aquél al que corresponda dicho pago.",
    ),
    source_url=LHENL_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Same 17th-of-the-following-month rhythm as the federal monthly payments.",
)

ISN_QUARTERLY_THRESHOLD = Const(
    key="isn.nl.quarterly_option_annual_tax",
    value=D("36000"),
    citation=_lhenl(
        "158",
        "Los contribuyentes que en el año inmediato anterior hayan efectuado pagos mensuales, cuyo monto anual "
        "globalizado del impuesto no hubiera excedido de $36,000.00, podrán realizar el pago del impuesto en "
        "forma trimestral.",
    ),
    source_url=LHENL_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Quarterly option requires a prior written aviso to the Secretaría de Finanzas y Tesorería General.",
)

# Art. 154 lists what the base includes; art. 160 lists what is exempt. Keys are the concept names a
# payroll line can carry; ``True`` = exempt from ISN.
ISN_EXEMPT_CONCEPTS = Const(
    key="isn.nl.exempt_concepts",
    value={
        "ptu": "art. 160 I a) — participaciones de los trabajadores en las utilidades",
        "indemnizacion_riesgo": "art. 160 I b) — indemnizaciones por riesgos o enfermedades profesionales",
        "pension": "art. 160 I c) — pensiones y jubilaciones (invalidez, vejez, cesantía, muerte)",
        "indemnizacion_despido": "art. 160 I d) — indemnizaciones por rescisión o terminación",
        "gastos_funerarios": "art. 160 I e) — pagos por gastos funerarios",
        "viaticos": "art. 160 I f) — viáticos efectivamente erogados y comprobados (LISR deducibility terms)",
        "fondo_ahorro": "art. 160 I g) — fondo de ahorro",
        "despensa": "art. 160 I g) — despensas",
        "alimentacion": "art. 160 I g) — alimentación",
        "remuneracion_discapacitado": "art. 160 I h) — remuneraciones a personas discapacitadas (DIF certification)",
    },
    citation=_lhenl(
        "160",
        "Están exentos del pago de este impuesto: I. Las erogaciones que se cubran por concepto de: a) "
        "Participaciones de los trabajadores en las utilidades de las empresas; … g) Fondo de ahorro, "
        "despensas y alimentación; h) Las remuneraciones a personas discapacitadas.",
    ),
    source_url=LHENL_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note=(
        "Art. 160 fr. II also exempts the payroll of non-profit welfare institutions, chambers, unions, "
        "schools, service clubs and religious associations — an entity-level exemption Aurum does not "
        "apply automatically; set `exempt_entity=True` on the rule to claim it."
    ),
)

ISN_TAXABLE_NOTE = Const(
    key="isn.nl.taxable_concepts",
    value=[
        "sueldo",
        "tiempo_extra",
        "aguinaldo",
        "prima_vacacional",
        "comisiones",
        "gratificaciones",
        "premios",
        "donativos",
        "gastos_representacion",
        "honorarios_preponderantes",
        "consejeros",
    ],
    citation=_lhenl(
        "154",
        "Se consideran remuneraciones al trabajo personal todas las contraprestaciones, ordinarias o "
        "extraordinarias, incluyendo viáticos, gastos de representación, comisiones, premios, "
        "gratificaciones, fondo de ahorro, donativos, primas, aguinaldo, tiempo extra, despensas, "
        "alimentación y otros conceptos de naturaleza semejante.",
    ),
    source_url=LHENL_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note=(
        "Art. 154 sweeps concepts in; art. 160 takes some back out (fondo de ahorro, despensa, "
        "alimentación, viáticos). Where they conflict the art. 160 exemption wins."
    ),
)

# --------------------------------------------------------------------------- IMSS: bases and caps

SBC_CAP_UMA = Const(
    key="imss.sbc_cap_uma",
    value=D("25"),
    citation=_lss(
        "28",
        "Los asegurados se inscribirán con el salario base de cotización que perciban en el momento de su "
        "afiliación, estableciéndose como límite superior el equivalente a veinticinco veces el salario "
        "mínimo general que rija en el Distrito Federal.",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note=(
        "Post-desindexación the reference is the UMA, so the 2026 ceiling is 25 × 117.31 = 2,932.75 daily. "
        "The 'salario mínimo general del área geográfica' remains the floor."
    ),
)

EM_EXCEDENTE_THRESHOLD_UMA = Const(
    key="imss.em.excedente_threshold_uma",
    value=D("3"),
    citation=_lss(
        "106 II",
        "Para los asegurados cuyo salario base de cotización sea mayor a tres veces el salario mínimo general "
        "diario … se cubrirá además de la cuota establecida en la fracción anterior, una cuota adicional "
        "patronal … de la cantidad que resulte de la diferencia entre el salario base de cotización y tres "
        "veces el salario mínimo citado.",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Read as 3 UMA after desindexación.",
)

# --------------------------------------------------------------------------- IMSS: branch rates

RT_MINIMUM_PRIMA = Const(
    key="imss.riesgos_trabajo.minimum_prima",
    value=D("0.005"),
    citation=_lss(
        "72",
        "Prima = [(S/365)+V * (I + D)] * (F/N) + M … M = 0.005, que es la prima mínima de riesgo.",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note=(
        "Riesgos de trabajo is employer-specific (LSS art. 71: 'en relación con … los riesgos inherentes a "
        "la actividad'). 0.5% is only the statutory minimum; a real employer passes its own prima."
    ),
)

EM_ESPECIE_FIXED_UMA_RATE = Const(
    key="imss.em.especie.cuota_fija_uma",
    value=D("0.204"),
    citation=_lss(
        "106 I",
        "Por cada asegurado se pagará mensualmente una cuota diaria patronal equivalente al trece punto nueve "
        "por ciento de un salario mínimo general diario … (Décimo Noveno transitorio: la tasa se incrementará "
        "el primero de julio de cada año en sesenta y cinco centésimas de punto porcentual, de 1998 a 2007).",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note=(
        "13.9% + 10 annual increments of 0.65 pp (1998…2007) = 20.4%, fully phased in since 2007. Applied to "
        "the UMA, not to the SBC."
    ),
)

EM_ESPECIE_EXCEDENTE_EMPLOYER = Const(
    key="imss.em.especie.excedente_employer",
    value=D("0.0110"),
    citation=_lss(
        "106 II",
        "…una cuota adicional patronal equivalente al seis por ciento … (Décimo Noveno transitorio: se "
        "reducirán el primero de julio de cada año en cuarenta y nueve centésimas de punto porcentual la que "
        "corresponde a los patrones, de 1998 a 2007).",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="6% − 10 × 0.49 pp = 1.10%, fully phased in since 2007. Applied to (SBC − 3 UMA).",
)

EM_ESPECIE_EXCEDENTE_EMPLOYEE = Const(
    key="imss.em.especie.excedente_employee",
    value=D("0.0040"),
    citation=_lss("106 II", "…y otra adicional obrera del dos por ciento…"),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="2% − 10 × 0.16 pp = 0.40%, fully phased in since 2007. Applied to (SBC − 3 UMA).",
)

EM_DINERO_TOTAL = Const(
    key="imss.em.dinero.total",
    value=D("0.01"),
    citation=_lss(
        "107",
        "Las prestaciones en dinero del seguro de enfermedades y maternidad se financiarán con una cuota del "
        "uno por ciento sobre el salario base de cotización: I. A los patrones les corresponderá pagar el "
        "setenta por ciento; II. A los trabajadores el veinticinco por ciento; III. Al Gobierno Federal el "
        "cinco por ciento restante.",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Employer 0.70% of SBC, employee 0.25% of SBC.",
)

EM_DINERO_EMPLOYER = Const(
    key="imss.em.dinero.employer",
    value=D("0.0070"),
    citation=EM_DINERO_TOTAL.citation,
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="70% of the 1% art. 107 quota.",
)

EM_DINERO_EMPLOYEE = Const(
    key="imss.em.dinero.employee",
    value=D("0.0025"),
    citation=EM_DINERO_TOTAL.citation,
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="25% of the 1% art. 107 quota.",
)

GMP_EMPLOYER = Const(
    key="imss.gastos_medicos_pensionados.employer",
    value=D("0.0105"),
    citation=_lss(
        "25",
        "Para cubrir las prestaciones en especie del seguro de enfermedades y maternidad de los pensionados y "
        "sus beneficiarios … los patrones, los trabajadores y el Estado aportarán una cuota de uno punto cinco "
        "por ciento sobre el salario base de cotización. De dicha cuota corresponderá al patrón pagar el uno "
        "punto cero cinco por ciento, a los trabajadores el cero punto trescientos setenta y cinco por ciento "
        "y al Estado el cero punto cero setenta y cinco por ciento.",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
)

GMP_EMPLOYEE = Const(
    key="imss.gastos_medicos_pensionados.employee",
    value=D("0.00375"),
    citation=GMP_EMPLOYER.citation,
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
)

IV_EMPLOYER = Const(
    key="imss.invalidez_vida.employer",
    value=D("0.0175"),
    citation=_lss(
        "147",
        "A los patrones y a los trabajadores les corresponde cubrir, para el seguro de invalidez y vida el uno "
        "punto setenta y cinco por ciento y el cero punto seiscientos veinticinco por ciento sobre el salario "
        "base de cotización, respectivamente.",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
)

IV_EMPLOYEE = Const(
    key="imss.invalidez_vida.employee",
    value=D("0.00625"),
    citation=IV_EMPLOYER.citation,
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
)

RETIRO_EMPLOYER = Const(
    key="imss.retiro.employer",
    value=D("0.02"),
    citation=_lss(
        "168 I",
        "En el ramo de retiro, a los patrones les corresponde cubrir el importe equivalente al dos por ciento "
        "del salario base de cotización del trabajador.",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
)

CV_EMPLOYEE = Const(
    key="imss.cesantia_vejez.employee",
    value=D("0.01125"),
    citation=_lss(
        "168 II b)",
        "Los trabajadores cubrirán una cuota del uno punto ciento veinticinco por ciento sobre el salario base "
        "de cotización.",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Unchanged by the 2020 pension reform.",
)

# Employer cesantía y vejez, 2026 column of the graduated table (transitorio Segundo, DOF 16-12-2020).
# Brackets are upper bounds of the SBC expressed in UMA; the first row is the exact minimum wage.
# (verify): the transitorio's table is published only as an image — see the module docstring.
CV_EMPLOYER_TABLE_2026 = Const(
    key="imss.cesantia_vejez.employer_table_2026",
    value=[
        {"upper_uma": None, "at_minimum_wage": True, "rate": D("0.03150"), "label": "1.00 SM"},
        {"upper_uma": D("1.50"), "rate": D("0.03676"), "label": "1.01 SM a 1.50 UMA"},
        {"upper_uma": D("2.00"), "rate": D("0.04851"), "label": "1.51 a 2.00 UMA"},
        {"upper_uma": D("2.50"), "rate": D("0.05556"), "label": "2.01 a 2.50 UMA"},
        {"upper_uma": D("3.00"), "rate": D("0.06026"), "label": "2.51 a 3.00 UMA"},
        {"upper_uma": D("3.50"), "rate": D("0.06361"), "label": "3.01 a 3.50 UMA"},
        {"upper_uma": D("4.00"), "rate": D("0.06613"), "label": "3.51 a 4.00 UMA"},
        {"upper_uma": None, "rate": D("0.07513"), "label": "4.01 UMA en adelante"},
    ],
    citation=_lss(
        "168 II a) + transitorio Segundo (DOF 16-12-2020)",
        "La cuota patronal prevista en el artículo 168, fracción II, inciso a), de la Ley del Seguro Social "
        "será aplicable de manera gradual, a partir del 1 de enero de 2023, de conformidad con la siguiente "
        "tabla [publicada como imagen].",
    ),
    source_url=DOF_2020_CV_URL,
    verified=False,
    note=(
        "NOT read in a primary source: the graduated table is an image in both the DOF nota and the "
        "Diputados PDF. Cross-check performed: straight-line interpolation from the 3.150% in force through "
        "2022 to the final art. 168 II a) table (which WAS read: 3.150 / 4.202 / 6.552 / 7.962 / 8.902 / "
        "9.573 / 10.077 / 11.875) over eight steps 2023…2030 reproduces every 2026 value here to ±0.001 pp."
    ),
)

CV_EMPLOYER_TABLE_FINAL = Const(
    key="imss.cesantia_vejez.employer_table_final",
    value=[
        {"upper_uma": None, "at_minimum_wage": True, "rate": D("0.03150"), "label": "1.00 SM"},
        {"upper_uma": D("1.50"), "rate": D("0.04202"), "label": "1.01 SM a 1.50 UMA"},
        {"upper_uma": D("2.00"), "rate": D("0.06552"), "label": "1.51 a 2.00 UMA"},
        {"upper_uma": D("2.50"), "rate": D("0.07962"), "label": "2.01 a 2.50 UMA"},
        {"upper_uma": D("3.00"), "rate": D("0.08902"), "label": "2.51 a 3.00 UMA"},
        {"upper_uma": D("3.50"), "rate": D("0.09573"), "label": "3.01 a 3.50 UMA"},
        {"upper_uma": D("4.00"), "rate": D("0.10077"), "label": "3.51 a 4.00 UMA"},
        {"upper_uma": None, "rate": D("0.11875"), "label": "4.01 UMA en adelante"},
    ],
    citation=_lss(
        "168 II a)",
        "Los patrones cubrirán la cuota que corresponda sobre el salario base de cotización, calculada "
        "conforme a la siguiente tabla: 1.00 SM 3.150%; 1.01 SM a 1.50 UMA 4.202%; 1.51 a 2.00 UMA 6.552%; "
        "2.01 a 2.50 UMA 7.962%; 2.51 a 3.00 UMA 8.902%; 3.01 a 3.50 UMA 9.573%; 3.51 a 4.00 UMA 10.077%; "
        "4.01 UMA en adelante 11.875%.",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="The steady-state table (reached in 2030). Read in the LSS PDF, última reforma DOF 15-01-2026.",
)

GUARDERIAS_EMPLOYER = Const(
    key="imss.guarderias.employer",
    value=D("0.01"),
    citation=_lss(
        "211",
        "El monto de la prima para este seguro será del uno por ciento sobre el salario base de cotización. "
        "(art. 212: los patrones cubrirán íntegramente la prima).",
    ),
    source_url=LSS_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Guarderías y prestaciones sociales — employer only.",
)

# --------------------------------------------------------------------------- INFONAVIT

INFONAVIT_EMPLOYER = Const(
    key="infonavit.employer",
    value=D("0.05"),
    citation=_linfonavit(
        "29 fr. II",
        "Determinar el monto de las aportaciones del cinco por ciento sobre el salario de los trabajadores a "
        "su servicio … En lo que corresponde a la integración y cálculo de la base y límite superior salarial "
        "para el pago de aportaciones, se aplicará lo contenido en la Ley del Seguro Social.",
    ),
    source_url=LINFONAVIT_URL,
    verified=True,
    verified_on=VERIFIED_ON,
    note=(
        "Read in the Diputados PDF, última reforma DOF 21-02-2025. Base and ceiling follow the LSS, so the "
        "same 25-UMA SBC cap applies. Paid bimonthly with RCV; Aurum accrues it monthly."
    ),
)

# --------------------------------------------------------------------------- wage ISR

SUBSIDIO_EMPLEO_MONTHLY = Const(
    key="isr.subsidio_empleo.monthly",
    value=D("536.22"),
    citation=Citation(
        law="LISR",
        article="Subsidio para el empleo (decreto / RMF 2026)",
        url=LISR_URL,
        effective_from=date(2026, 1, 1),
        trust_tier="official_guidance",
        excerpt=None,
    ),
    source_url=LISR_URL,
    verified=False,
    note=(
        "NOT verified: the 2026 subsidio decree has not been read. Since 2024 the subsidio is a "
        "flat monthly amount (a percentage of the monthly UMA) rather than a table, capped by a monthly "
        "income ceiling. Treat the amount and the ceiling as provisional; a payroll run reports "
        "'(verify)' whenever the subsidio is applied."
    ),
)

SUBSIDIO_EMPLEO_INCOME_CAP = Const(
    key="isr.subsidio_empleo.income_cap_monthly",
    value=D("11492.66"),
    citation=SUBSIDIO_EMPLEO_MONTHLY.citation,
    source_url=LISR_URL,
    verified=False,
    note="NOT verified — see SUBSIDIO_EMPLEO_MONTHLY.",
)

ALL: tuple[Const, ...] = (
    UMA_DAILY,
    UMA_MONTHLY,
    MINIMUM_WAGE_DAILY,
    MINIMUM_WAGE_ZLFN_DAILY,
    ISN_RATE,
    ISN_DUE_DAY,
    ISN_QUARTERLY_THRESHOLD,
    ISN_EXEMPT_CONCEPTS,
    ISN_TAXABLE_NOTE,
    SBC_CAP_UMA,
    EM_EXCEDENTE_THRESHOLD_UMA,
    RT_MINIMUM_PRIMA,
    EM_ESPECIE_FIXED_UMA_RATE,
    EM_ESPECIE_EXCEDENTE_EMPLOYER,
    EM_ESPECIE_EXCEDENTE_EMPLOYEE,
    EM_DINERO_TOTAL,
    EM_DINERO_EMPLOYER,
    EM_DINERO_EMPLOYEE,
    GMP_EMPLOYER,
    GMP_EMPLOYEE,
    IV_EMPLOYER,
    IV_EMPLOYEE,
    RETIRO_EMPLOYER,
    CV_EMPLOYEE,
    CV_EMPLOYER_TABLE_2026,
    CV_EMPLOYER_TABLE_FINAL,
    GUARDERIAS_EMPLOYER,
    INFONAVIT_EMPLOYER,
    SUBSIDIO_EMPLEO_MONTHLY,
    SUBSIDIO_EMPLEO_INCOME_CAP,
)


def table() -> list[dict[str, Any]]:
    """Every constant as a JSON-able row — used by ``/api/business`` and by ``docs/modules/rules-mx-nl.md``."""
    return [c.as_dict() for c in ALL]


def unverified() -> list[str]:
    return [c.key for c in ALL if not c.verified]


__all__ = ["ALL", "Const", "table", "unverified"]
