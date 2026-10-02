/**
 * US tax, cross-border, holdings, plan and credit-report fixtures for the in-browser fake API.
 *
 * Shaped exactly like the live responses captured in `web-ui/docs/api-samples.json` — the same
 * field names, the same nesting, the same decimal *strings*, the same `explain` blocks with
 * their real citations and rule versions. Where the capture elides a long list ("…(7 more)")
 * the elided rows are written out here so the screens have something real to render; every figure
 * that also appears in the capture is copied from it verbatim.
 *
 * Two workspaces exist so the switcher is exercisable: `demo-mx` (RESICO persona física, MXN)
 * and `demo-us` (Texas sole proprietor, USD). US-only endpoints answer for `demo-us`.
 */
import type {
  Citation,
  CreditReportImport,
  CrossborderAssessment,
  CrossborderProfile,
  Explain,
  HoldingsOverview,
  RefsGraph,
  ScenarioSpec,
  TxFranchise,
  UsTaxYear,
  WatchProposal,
  WatchSource,
  WatchSourceHistory,
  Workspace,
} from '../types';

export const US_WS_ID = 'demo-us';
export const usd = (amount: string) => ({ amount, currency: 'USD' });

/** The `demo-us` workspace, exactly as `GET /workspaces` returns it. */
export const US_WORKSPACE: Workspace = {
  id: US_WS_ID,
  name: 'Demo USA (Texas sole proprietor)',
  kind: 'personal',
  jurisdictions: ['US'],
  base_currency: 'USD',
  language: 'en',
  profile: {
    country: 'US',
    state: 'TX',
    entity_type: 'sole_proprietorship',
    business_type: 'other',
    demo: true,
  },
  created_at: '2026-09-06T23:02:29.122389Z',
};

/* ------------------------------------------------------------- citations */

const CITE_SCHED_C: Citation = {
  law: 'IRC',
  article: '61 / 162 (Schedule C)',
  url: 'https://uscode.house.gov/view.xhtml?path=/prelim@title26&edition=prelim',
  effective_from: '2026-01-01',
  effective_to: null,
  trust_tier: 'primary',
  excerpt:
    'Gross income from a trade or business less the ordinary and necessary expenses of carrying it on.',
};

const CITE_SE: Citation = {
  law: 'IRC',
  article: '1401 / 1402',
  url: 'https://uscode.house.gov/view.xhtml?path=/prelim@title26&edition=prelim',
  effective_from: '2026-01-01',
  effective_to: null,
  trust_tier: 'primary',
  excerpt:
    'A tax on self-employment income: the old-age, survivors and disability insurance portion and the hospital insurance portion, plus the additional Medicare tax of § 1401(b)(2).',
};

const CITE_SS_BASE: Citation = {
  law: 'IRS guidance',
  article: 'Topic no. 751 — Social Security wage base 2026',
  url: 'https://www.irs.gov/taxtopics/tc751',
  effective_from: '2026-01-01',
  effective_to: null,
  trust_tier: 'official_guidance',
  excerpt: null,
};

const CITE_BRACKETS: Citation = {
  law: 'IRC',
  article: '1(j)(2) / 63(c)',
  url: 'https://www.irs.gov/pub/irs-drop/rp-25-32.pdf',
  effective_from: '2026-01-01',
  effective_to: null,
  trust_tier: 'primary',
  excerpt: '2026 rate tables and standard deduction as adjusted by Rev. Proc. 2025-32.',
};

const CITE_ESTIMATES: Citation = {
  law: 'IRC',
  article: '6654',
  url: 'https://uscode.house.gov/view.xhtml?path=/prelim@title26&edition=prelim',
  effective_from: '2026-01-01',
  effective_to: null,
  trust_tier: 'primary',
  excerpt:
    'Safe harbour: 100% of the prior year tax (110% above the AGI threshold) or 90% of the current year.',
};

const CITE_TX: Citation = {
  law: 'Texas Tax Code',
  article: 'ch. 171 (§§ 171.002, 171.006, 171.101, 171.1016)',
  url: 'https://comptroller.texas.gov/taxes/franchise/',
  effective_from: '2026-01-01',
  effective_to: null,
  trust_tier: 'official_guidance',
  excerpt:
    'Franchise tax on taxable margin; entities at or below the no-tax-due threshold owe no tax but still file an information report.',
};

const NOT_ADVICE =
  'Informational only — Aurum is not a tax return and not tax advice; review with a licensed preparer.';

const XB_NOT_ADVICE =
  'Informational only — residency, treaty positions and FBAR obligations must be confirmed with a cross-border preparer; Aurum decides nothing.';

const step = (label: string, value: string, formula: string | null = null) => ({
  label,
  formula,
  value,
});

/* ---------------------------------------------------------------- tax/us */

const US_DISCLAIMER =
  'This is an organizer, not a tax return. Aurum never files, signs or transmits anything to the IRS or the Texas Comptroller. Every figure is an estimate from your ledger — take it to a licensed preparer.';

export const US_TAX: UsTaxYear = {
  workspace: US_WS_ID,
  year: 2026,
  applicable: true,
  currency: 'USD',
  profile: {
    filing_status: 'single',
    entity_type: 'sole_proprietorship',
    business_type: 'other',
    state: 'TX',
  },
  schedule_c: {
    gross_receipts: usd('141000.00'),
    returns_and_allowances: usd('1500.00'),
    cost_of_goods_sold: usd('12000.00'),
    expenses: usd('9810.00'),
    expenses_by_account: {
      'Expenses:US:Insurance': usd('1800.00'),
      'Expenses:US:Office': usd('960.00'),
      'Expenses:US:Professional': usd('1500.00'),
      'Expenses:US:Software': usd('2400.00'),
      'Expenses:US:Travel': usd('3150.00'),
    },
    income_by_account: {
      'Income:US:Consulting': usd('130500.00'),
      'Income:US:Training': usd('9000.00'),
    },
    transactions: 27,
    net: usd('117690.00'),
    explain: {
      summary: `Schedule C net profit for the year: 117690.00 USD (gross 141000.00 − returns 1500.00 − COGS 12000.00 − expenses 9810.00). ${NOT_ADVICE}`,
      steps: [
        step('Gross receipts or sales (line 1)', '141000.00'),
        step('Returns and allowances (line 2)', '1500.00'),
        step('Cost of goods sold (line 4)', '12000.00'),
        step('Gross profit (line 5)', '127500.00', '141000.00 − 1500.00 − 12000.00'),
        step('Insurance (line 15)', '1800.00'),
        step('Office expense (line 18)', '960.00'),
        step('Legal and professional services (line 17)', '1500.00'),
        step('Software / other expenses (part V)', '2400.00'),
        step('Travel (line 24a)', '3150.00'),
        step('Total expenses (line 28)', '9810.00'),
        step('Net profit (line 31)', '117690.00', '127500.00 − 9810.00'),
      ],
      citations: [CITE_SCHED_C],
      rule_versions: ['us.fed.schedule_c_net@2026.1'],
      confidence: null,
    },
  },
  se_tax: {
    value: usd('16629.06'),
    deductible_half: usd('8314.53'),
    explain: {
      summary: `Self-employment tax for 2026: 16629.06 USD (OASDI 13477.15 + Medicare 3151.91 + additional Medicare 0.00) (verify). ${NOT_ADVICE}`,
      steps: [
        step('Schedule C net profit', '117690.00'),
        step('Net earnings from self-employment (verify)', '108686.72', '117690.00 × 0.9235 (§ 1402(a)(12))'),
        step('W-2 wages already subject to FICA', '0.00'),
        step('Social Security wage base 2026 (verify)', '184500.00'),
        step('OASDI base subject to tax', '108686.72'),
        step('OASDI at 12.4%', '13477.15', '108686.72 × 0.124'),
        step('Medicare at 2.9%', '3151.91', '108686.72 × 0.029'),
        step('Additional Medicare threshold, single (verify)', '200000.00'),
        step('Additional Medicare at 0.9%', '0.00'),
        step('Self-employment tax', '16629.06', '13477.15 + 3151.91 + 0.00'),
        step('Deductible half (§ 164(f))', '8314.53', '16629.06 ÷ 2'),
      ],
      citations: [
        CITE_SE,
        CITE_SS_BASE,
        {
          law: 'IRC',
          article: '1401(b)(2)(A)',
          url: 'https://uscode.house.gov/view.xhtml?path=/prelim@title26&edition=prelim',
          effective_from: '2026-01-01',
          effective_to: null,
          trust_tier: 'primary',
          excerpt: 'Threshold amounts by filing status.',
        },
      ],
      rule_versions: ['us.fed.se_tax@2026.1'],
      confidence: null,
    },
  },
  income_tax: {
    value: usd('15232.60'),
    explain: {
      summary: `Federal income tax for 2026 (single): 15232.60 USD on taxable income 93275.47; marginal rate 22%, effective 16.33%. ${NOT_ADVICE}`,
      steps: [
        step('Schedule C net profit', '117690.00'),
        step('Other income', '0.00'),
        step('Less: deductible half of SE tax (§ 164(f))', '8314.53'),
        step('Adjusted gross income', '109375.47'),
        step('Standard deduction, single 2026 (verify)', '16100.00'),
        step('Taxable income', '93275.47', '109375.47 − 16100.00'),
        step('Bracket 10% · 0 – 12400', '1240.00', '12400.00 × 0.10'),
        step('Bracket 12% · 12400 – 50400', '4560.00', '38000.00 × 0.12'),
        step('Bracket 22% · 50400 – 93275.47', '9432.60', '42875.47 × 0.22'),
        step('Federal income tax', '15232.60', '1240.00 + 4560.00 + 9432.60'),
        step('Marginal rate', '22%'),
        step('Effective rate', '16.33%', '15232.60 ÷ 93275.47'),
      ],
      citations: [
        CITE_BRACKETS,
        {
          law: 'IRC',
          article: '1(j)(2)',
          url: 'https://uscode.house.gov/view.xhtml?path=/prelim@title26&edition=prelim',
          effective_from: '2026-01-01',
          effective_to: null,
          trust_tier: 'primary',
          excerpt: '2026 rate tables as adjusted by Rev. Proc. 2025-32 § 4.01.',
        },
        {
          law: 'IRC',
          article: '63(c)(2)',
          url: 'https://uscode.house.gov/view.xhtml?path=/prelim@title26&edition=prelim',
          effective_from: '2026-01-01',
          effective_to: null,
          trust_tier: 'primary',
          excerpt: 'Standard deduction by filing status, as adjusted.',
        },
      ],
      rule_versions: ['us.fed.income_tax@2026.1'],
      confidence: null,
    },
  },
  total_tax: usd('31861.66'),
  quarterly: {
    due_dates: ['2026-04-15', '2026-06-15', '2026-09-15', '2027-01-15'],
    amount_each: usd('6000.00'),
    explain: {
      summary: `Estimated tax: 6000.00 USD per quarter (24000.00 for the year) under the prior-year safe harbour (verify). ${NOT_ADVICE}`,
      steps: [
        step('Prior year tax', '24000.00'),
        step('Safe-harbour percentage (verify)', '100%', 'prior-year AGI 118000.00 below the 150000 threshold'),
        step('Required annual payment', '24000.00'),
        step('Per quarter', '6000.00', '24000.00 ÷ 4'),
      ],
      citations: [CITE_ESTIMATES, CITE_SS_BASE],
      rule_versions: ['us.fed.quarterly_estimate@2026.1'],
      confidence: null,
    },
  },
  organizer_url: `/api/tax/us/${US_WS_ID}/2026/organizer.pdf`,
  tx_franchise_url: `/api/tax/us/${US_WS_ID}/2026/tx-franchise`,
  unverified_constants: [
    'se.net_earnings_factor',
    'tx.franchise.margin_revenue_share',
    'tx.franchise.margin_flat_deduction',
    'se.social_security_wage_base',
    'se.additional_medicare_threshold',
    'fed.standard_deduction',
    'fed.brackets_2026',
    'estimates.safe_harbor_pct',
  ],
  warnings: [],
  disclaimer: US_DISCLAIMER,
  status: null,
};

export const TX_FRANCHISE: TxFranchise = {
  workspace: US_WS_ID,
  year: 2026,
  applicable: true,
  currency: 'USD',
  entity_type: 'sole_proprietorship',
  business_type: 'other',
  total_revenue: usd('141000.00'),
  no_tax_due_threshold: usd('2650000.00'),
  no_tax_due: true,
  tax: usd('0.00'),
  explain: {
    summary: `Texas franchise tax 2026: no tax due — a sole proprietorship (not an LLC) is not a taxable entity under Tex. Tax Code § 171.0002(b)(1) (verify). ${NOT_ADVICE}`,
    steps: [
      step('Annualized total revenue', '141000.00'),
      step('Taxable entity', 'False', '§ 171.0002'),
      step('No-tax-due threshold (2026)', '2650000', 'source: https://comptroller.texas.gov/taxes/franchise/'),
      step('Revenue at or below threshold', 'True'),
      step('Franchise tax due', '0.00'),
    ],
    citations: [
      CITE_TX,
      {
        law: 'Texas Tax Code',
        article: 'ch. 171 (§ 171.006 adjustment)',
        url: 'https://comptroller.texas.gov/taxes/franchise/',
        effective_from: '2026-01-01',
        effective_to: null,
        trust_tier: 'official_guidance',
        excerpt: 'No tax due threshold for 2026 reports.',
      },
    ],
    rule_versions: ['us.tx.franchise_no_tax_due@2026.1'],
    confidence: null,
  },
  warnings: [],
  disclaimer: US_DISCLAIMER,
};

/* ------------------------------------------------------------ crossborder */

export const XB_PROFILE: CrossborderProfile = {
  days_mx: 210,
  days_us: 150,
  days_us_prior_1: 150,
  days_us_prior_2: 150,
  days_abroad_for_feie: 210,
  bona_fide_resident_abroad: false,
  home_mx: true,
  home_us: true,
  green_card: false,
  citizenship: ['US', 'MX'],
  filing_status: 'single',
  main_professional_center: 'MX',
  mx_source_income_share: '0.20',
  foreign_tax_paid_usd: '1800.00',
  income_sources: [
    { country: 'US', kind: 'self_employment', amount: '132000.00', currency: 'USD' },
    { country: 'MX', kind: 'self_employment', amount: '9000.00', currency: 'USD' },
  ],
  foreign_accounts: [
    { country: 'MX', institution: 'Banco Demo Uno', max_balance_usd: '14500.00' },
    { country: 'MX', institution: 'Banco Demo Ahorro', max_balance_usd: '2200.00' },
  ],
  treaty_permanent_home: null,
  treaty_center_of_vital_interests: 'MX',
  treaty_habitual_abode: 'MX',
  treaty_nationality: null,
};

const XB_DISCLAIMER =
  'Informational only. Residency, treaty positions, FBAR and the FEIE/FTC choice all have consequences Aurum cannot see — take this to a cross-border preparer. Aurum decides nothing.';

/**
 * The assessment for a given profile. The residency arithmetic (weighted US days and the
 * FBAR aggregate) is recomputed from the profile so editing the wizard visibly changes the
 * answer; everything else is the captured fixture text.
 */
export function xbAssessment(p: CrossborderProfile): CrossborderAssessment {
  // Weighted days: current 1 + prior 1/3 + second prior 1/6, kept to two decimals as strings.
  const weightedHundredths =
    p.days_us * 100 + Math.round((p.days_us_prior_1 * 100) / 3) + Math.round((p.days_us_prior_2 * 100) / 6);
  const weighted = `${Math.floor(weightedHundredths / 100)}.${String(weightedHundredths % 100).padStart(2, '0')}`;
  const usResident = p.green_card || (p.days_us >= 31 && weightedHundredths >= 18300);
  const mxResident = p.home_mx && (!p.home_us || p.main_professional_center === 'MX');
  const dual = usResident && mxResident;

  const aggCents = p.foreign_accounts.reduce((sum, a) => {
    const [int = '0', frac = ''] = (a.max_balance_usd || '0').split('.');
    return sum + BigInt(int || '0') * 100n + BigInt((frac + '00').slice(0, 2));
  }, 0n);
  const aggregate = `${aggCents / 100n}.${(aggCents % 100n).toString().padStart(2, '0')}`;
  const fbarRequired = p.citizenship.includes('US') || p.green_card ? aggCents > 1000000n : false;

  const ladder = [
    { step: 1, key: 'permanent_home', label: 'Permanent home available in only one State' },
    { step: 2, key: 'center_of_vital_interests', label: 'Centre of vital interests (personal and economic relations)' },
    { step: 3, key: 'habitual_abode', label: 'Habitual abode' },
    { step: 4, key: 'nationality', label: 'Nationality' },
    { step: 5, key: 'mutual_agreement', label: 'Mutual agreement procedure between the competent authorities' },
  ];
  const answered: (string | null | undefined)[] = [
    p.treaty_permanent_home,
    p.treaty_center_of_vital_interests,
    p.treaty_habitual_abode,
    p.treaty_nationality,
  ];
  const resolvedIdx = answered.findIndex((a) => a);
  const resolvedStep = dual && resolvedIdx >= 0 ? resolvedIdx + 1 : null;
  const resolvedCountry = resolvedIdx >= 0 ? answered[resolvedIdx] : null;

  return {
    workspace: US_WS_ID,
    profile: p,
    residency: {
      mx: mxResident,
      us: usResident,
      dual,
      weighted_us_days: { amount: weighted, currency: 'DAY' },
      explain: {
        summary: `Residency: ${
          dual ? 'resident of both Mexico and the US on these facts' : usResident ? 'US resident' : 'Mexican resident'
        }. Weighted US days ${weighted} vs the 183 threshold (verify). ${XB_NOT_ADVICE}`,
        steps: [
          step('Days in the US, current year', String(p.days_us)),
          step('Days in the US, first preceding year', String(p.days_us_prior_1), 'counted at 1/3'),
          step('Days in the US, second preceding year', String(p.days_us_prior_2), 'counted at 1/6'),
          step('Weighted days', weighted, 'current + prior/3 + second prior/6'),
          step('Substantial presence threshold (verify)', '183'),
          step('At least 31 days in the current year', String(p.days_us >= 31)),
          step('US resident under § 7701(b)(3)', String(usResident)),
          step('Casa habitación in Mexico (CFF art. 9)', String(p.home_mx)),
          step('Also a home abroad', String(p.home_us)),
          step('Centre of vital interests', p.main_professional_center ?? 'unanswered'),
        ],
        citations: [
          {
            law: 'IRC',
            article: '7701(b)(3) · CFF art. 9',
            url: 'https://www.irs.gov/individuals/international-taxpayers/substantial-presence-test',
            effective_from: '2026-01-01',
            effective_to: null,
            trust_tier: 'primary',
            excerpt:
              'Substantial presence: 31 days in the current year and 183 weighted days over three years (current 1, prior 1/3, second prior 1/6). CFF art. 9: casa habitación, then centre of vital interests.',
          },
          {
            law: 'CFF',
            article: '9',
            url: 'https://www.diputados.gob.mx/LeyesBiblio/pdf/CFF.pdf',
            effective_from: '2026-01-01',
            effective_to: null,
            trust_tier: 'primary',
            excerpt:
              'Se consideran residentes en México las personas físicas que hayan establecido su casa habitación en México; cuando también tengan casa habitación en otro país, se considerará el centro de intereses vitales.',
          },
        ],
        rule_versions: ['xb.residency@2026.1'],
        confidence: 0.6,
      },
    },
    treaty: {
      applies: dual,
      resolved_at_step: resolvedStep,
      checklist: ladder,
      explain: {
        summary: dual
          ? `Dual residency: the art. 4 ladder points to ${resolvedCountry ?? 'no country yet'}${
              resolvedStep ? ` at step ${resolvedStep} (${ladder[resolvedStep - 1].label})` : ''
            } (verify). ${XB_NOT_ADVICE}`
          : `Not a dual resident on these facts, so the art. 4 tie-breaker is not reached. ${XB_NOT_ADVICE}`,
        steps: [
          step('Resident of both countries', String(dual)),
          ...ladder.slice(0, 4).map((l, i) =>
            step(
              `Step ${l.step} · ${l.label}`,
              answered[i] ?? 'unanswered',
              answered[i] ? 'decisive' : 'not decisive on these facts',
            ),
          ),
          step('Form 8833 needed to claim a treaty position', 'True'),
        ],
        citations: [
          {
            law: 'US–MX income tax treaty',
            article: '4 (Residence)',
            url: 'https://www.irs.gov/businesses/international-businesses/mexico-tax-treaty-documents',
            effective_from: '2026-01-01',
            effective_to: null,
            trust_tier: 'primary',
            excerpt:
              'Tie-breaker: permanent home → centre of vital interests → habitual abode → nationality → mutual agreement.',
          },
        ],
        rule_versions: ['xb.treaty_tiebreaker@2026.1'],
        confidence: 0.5,
      },
    },
    fbar: {
      required: fbarRequired,
      aggregate: usd(aggregate),
      threshold: '10000',
      explain: {
        summary: `Foreign accounts peak at ${aggregate} USD against the 10000 USD threshold — an FBAR is ${
          fbarRequired ? 'likely required' : 'not indicated on these facts'
        }. ${XB_NOT_ADVICE}`,
        steps: [
          step('US person', String(p.citizenship.includes('US') || p.green_card)),
          ...p.foreign_accounts.map((a) =>
            step(
              `Account · ${a.country} ${a.institution ?? ''}`.trim(),
              a.max_balance_usd,
              'highest balance at any point in the calendar year',
            ),
          ),
          step('Aggregate high balance', aggregate),
          step('Threshold (31 C.F.R. 1010.350)', '10000.00'),
          step('FBAR indicated', String(fbarRequired)),
        ],
        citations: [
          {
            law: '31 C.F.R.',
            article: '1010.350 (FinCEN Form 114)',
            url: 'https://www.fincen.gov/report-foreign-bank-and-financial-accounts',
            effective_from: '2026-01-01',
            effective_to: null,
            trust_tier: 'primary',
            excerpt:
              'A US person with a financial interest in foreign financial accounts exceeding USD 10,000 in aggregate at any time during the calendar year must report them.',
          },
          {
            law: 'IRS guidance',
            article: 'Report of Foreign Bank and Financial Accounts (FBAR)',
            url: 'https://www.irs.gov/businesses/small-businesses-self-employed/report-of-foreign-bank-and-financial-accounts-fbar',
            effective_from: '2026-01-01',
            effective_to: null,
            trust_tier: 'official_guidance',
            excerpt: null,
          },
        ],
        rule_versions: ['xb.fbar@2026.1'],
        confidence: null,
      },
    },
    feie_vs_ftc: {
      options: [
        { option: 'FEIE', citation: 'IRC 911', value: usd('0.00') },
        { option: 'FTC', citation: 'IRC 901', value: usd(p.foreign_tax_paid_usd || '0.00') },
      ],
      explain: {
        summary: `FEIE could exclude 0.00 USD (2026 cap 132900 (verify)); foreign tax paid of ${
          p.foreign_tax_paid_usd || '0.00'
        } USD points at the foreign tax credit instead. ${XB_NOT_ADVICE}`,
        steps: [
          step('Days abroad for the physical-presence test', String(p.days_abroad_for_feie)),
          step('330-day test met', String(p.days_abroad_for_feie >= 330)),
          step('Bona fide residence test met', String(p.bona_fide_resident_abroad)),
          step('FEIE cap 2026 (verify)', '132900.00'),
        ],
        citations: [
          {
            law: 'IRC',
            article: '911',
            url: 'https://uscode.house.gov/view.xhtml?path=/prelim@title26&edition=prelim',
            effective_from: '2026-01-01',
            effective_to: null,
            trust_tier: 'primary',
            excerpt: 'Foreign earned income exclusion: bona fide residence or physical presence.',
          },
          {
            law: 'IRC',
            article: '901',
            url: 'https://uscode.house.gov/view.xhtml?path=/prelim@title26&edition=prelim',
            effective_from: '2026-01-01',
            effective_to: null,
            trust_tier: 'primary',
            excerpt: 'Credit for income taxes paid to a foreign country.',
          },
          {
            law: 'IRS guidance',
            article: 'Foreign earned income exclusion — 2026 amount',
            url: 'https://www.irs.gov/individuals/international-taxpayers/foreign-earned-income-exclusion',
            effective_from: '2026-01-01',
            effective_to: null,
            trust_tier: 'official_guidance',
            excerpt: '(verify)',
          },
        ],
        rule_versions: ['xb.feie_vs_ftc@2026.1'],
        confidence: 0.5,
      },
    },
    flags: [
      ...(fbarRequired
        ? [
            `FBAR likely required — foreign accounts peaked at ${aggregate} USD, above the 10000 USD threshold (FinCEN Form 114, 31 C.F.R. 1010.350).`,
          ]
        : []),
      ...(dual
        ? [
            'Possible dual residency — treaty tie-breaker: US-MX treaty art. 4 decides which country wins, and claiming it needs Form 8833. Explore with a preparer.',
          ]
        : []),
      'FEIE vs FTC — explore with a preparer: you have foreign earned income but neither the 330-day nor the bona fide residence test is met on these facts, so the foreign tax credit is the path to look at.',
    ],
    unverified_constants: [
      'xb.feie.physical_presence_days',
      'xb.mx.residency_cff9',
      'xb.treaty.article_4',
      'xb.feie.exclusion_2026',
    ],
    disclaimer: XB_DISCLAIMER,
  };
}

/* -------------------------------------------------------------- holdings */

const HOLDINGS_EXPLAIN: Explain = {
  summary:
    "Positions are FIFO lots from recorded trades; realized gains match sells to the oldest open lot first (verify against your jurisdiction's actual lot-method election).",
  steps: [],
  citations: [
    {
      law: 'LISR',
      article: '129/133/150',
      url: null,
      effective_from: null,
      effective_to: null,
      trust_tier: 'primary',
      excerpt: '(verify)',
    },
    {
      law: 'IRC',
      article: '§ 1(h) / § 1222',
      url: null,
      effective_from: null,
      effective_to: null,
      trust_tier: 'primary',
      excerpt: '(verify)',
    },
  ],
  rule_versions: [],
  confidence: null,
};

const TAX_LENS_MX: Explain = {
  summary:
    'MX: gains on securities held through a Mexican broker are generally subject to withholding by the intermediary; personal capital-gains treatment depends on the asset and holding structure (verify).',
  steps: [],
  citations: [
    {
      law: 'LISR',
      article: '129',
      url: null,
      effective_from: null,
      effective_to: null,
      trust_tier: 'primary',
      excerpt: '(verify) enajenación de acciones',
    },
    {
      law: 'LISR',
      article: '133',
      url: null,
      effective_from: null,
      effective_to: null,
      trust_tier: 'primary',
      excerpt: '(verify) intereses',
    },
    {
      law: 'LISR',
      article: '150',
      url: null,
      effective_from: null,
      effective_to: null,
      trust_tier: 'primary',
      excerpt: '(verify) declaración anual',
    },
  ],
  rule_versions: [],
  confidence: 0.4,
};

const TAX_LENS_US: Explain = {
  summary:
    'US: long-term gains (lots held over a year) are taxed at the preferential § 1(h) rates; short-term gains are ordinary income. Lot method is an election you make with your broker (verify).',
  steps: [],
  citations: [
    {
      law: 'IRC',
      article: '§ 1(h)',
      url: null,
      effective_from: null,
      effective_to: null,
      trust_tier: 'primary',
      excerpt: '(verify) maximum capital gains rate',
    },
    {
      law: 'IRC',
      article: '§ 1222',
      url: null,
      effective_from: null,
      effective_to: null,
      trust_tier: 'primary',
      excerpt: '(verify) short-term vs long-term',
    },
  ],
  rule_versions: [],
  confidence: 0.4,
};

const SYMBOLS_MX = [
  { ws_id: 'demo-mx', symbol: 'BTC', name: 'Bitcoin', asset_class: 'crypto', currency: 'USD' },
  { ws_id: 'demo-mx', symbol: 'CETES', name: 'Cetes (Certificados de la Tesorería)', asset_class: 'bond', currency: 'MXN' },
  { ws_id: 'demo-mx', symbol: 'VOO', name: 'Vanguard S&P 500 ETF', asset_class: 'equity', currency: 'USD' },
  { ws_id: 'demo-mx', symbol: 'NAFTRAC', name: 'iShares NAFTRAC', asset_class: 'equity', currency: 'MXN' },
];

const SYMBOLS_US = SYMBOLS_MX.map((s) => ({ ...s, ws_id: US_WS_ID }));

export function holdingsSeed(ws: string): HoldingsOverview {
  const us = ws === US_WS_ID;
  return {
    positions: [
      {
        symbol: 'VOO',
        account: 'Assets:Investments:Brokerage',
        units: '2',
        cost_basis: usd('760.00'),
        market_value: null,
        unrealized_gain: null,
        asset_class: 'equity',
        name: 'Vanguard S&P 500 ETF',
        price_as_of: null,
      },
    ],
    realized_gains: [],
    allocation: { by_asset_class: {}, total_market_value: '0.00' },
    explain: HOLDINGS_EXPLAIN,
    contributions: {
      year: 2026,
      limits: [
        {
          key: 'ppr',
          jurisdiction: 'MX',
          label: 'Aportaciones a plan personal de retiro, tope deducible (verify)',
          limit: { amount: '152331', currency: 'MXN' },
          contributed: { amount: '0.00', currency: 'MXN' },
          remaining: { amount: '152331.00', currency: 'MXN' },
          verified: false,
        },
        {
          key: '401k',
          jurisdiction: 'US',
          label: '401(k) elective deferral limit (verify)',
          limit: usd('23500'),
          contributed: usd('0.00'),
          remaining: usd('23500.00'),
          verified: false,
        },
        {
          key: 'hsa_family',
          jurisdiction: 'US',
          label: 'HSA family coverage limit (verify)',
          limit: usd('8550'),
          contributed: usd('0.00'),
          remaining: usd('8550.00'),
          verified: false,
        },
        {
          key: 'ira',
          jurisdiction: 'US',
          label: 'IRA contribution limit (verify)',
          limit: usd('7000'),
          contributed: usd('0.00'),
          remaining: usd('7000.00'),
          verified: false,
        },
        {
          key: 'hsa_self',
          jurisdiction: 'US',
          label: 'HSA self-only coverage limit (verify)',
          limit: usd('4300'),
          contributed: usd('0.00'),
          remaining: usd('4300.00'),
          verified: false,
        },
      ],
    },
    tax_explain: us ? TAX_LENS_US : TAX_LENS_MX,
    symbols: us ? SYMBOLS_US : SYMBOLS_MX,
  };
}

/* ---------------------------------------------------------- creditreport */

export const CREDIT_EXPLAIN: Explain = {
  summary:
    'Factors that generally move a Buró de Crédito score: payment history, credit utilization, credit age/mix, and recent inquiries (verify against current Buró/CONDUSEF text).',
  steps: [
    step('payment_history', 'largest single factor (verify exact weighting)'),
    step('utilization', 'lower balance-to-limit ratio generally helps (verify)'),
    step('credit_age_mix', 'older, varied accounts generally help (verify)'),
    step('recent_inquiries', 'several hard inquiries in a short window generally hurt (verify)'),
  ],
  citations: [
    {
      law: 'Buró de Crédito',
      article: '¿Cómo se calcula mi score?',
      url: 'https://www.burodecredito.com.mx',
      effective_from: null,
      effective_to: null,
      trust_tier: 'official_guidance',
      excerpt: '(verify)',
    },
    {
      law: 'CONDUSEF',
      article: 'Reporte de Crédito Especial',
      url: 'https://www.condusef.gob.mx',
      effective_from: null,
      effective_to: null,
      trust_tier: 'official_guidance',
      excerpt: '(verify)',
    },
  ],
  rule_versions: [],
  confidence: 0.4,
};

/** Two imports so the score history has something to draw; both synthetic. */
export const CREDIT_IMPORTS: CreditReportImport[] = [
  {
    id: 'crimp-2',
    ws_id: 'demo-mx',
    filename: 'reporte-credito-especial-2026-08.pdf',
    imported_at: '2026-08-14T10:22:04',
    score: { value: 712, bureau: 'Buró de Crédito' },
    accounts: [
      {
        grantor: 'Banco Demo Uno',
        type: 'Tarjeta de crédito',
        limit: '85000.00',
        balance: '12400.00',
        status: 'Al corriente',
        opened: '2021-03-15',
      },
      {
        grantor: 'Financiera Demo',
        type: 'Crédito automotriz',
        limit: '320000.00',
        balance: '184300.00',
        status: 'Al corriente',
        opened: '2024-06-01',
      },
      {
        grantor: 'Tienda Demo',
        type: 'Crédito revolvente',
        limit: '15000.00',
        balance: '0.00',
        status: 'Cerrada',
        opened: '2019-11-20',
      },
    ],
    warnings: ['La fecha de apertura de 1 cuenta se leyó de una tabla sin encabezado (verify).'],
  },
  {
    id: 'crimp-1',
    ws_id: 'demo-mx',
    filename: 'reporte-credito-especial-2026-02.pdf',
    imported_at: '2026-02-09T09:05:41',
    score: { value: 688, bureau: 'Buró de Crédito' },
    accounts: [
      {
        grantor: 'Banco Demo Uno',
        type: 'Tarjeta de crédito',
        limit: '70000.00',
        balance: '21750.00',
        status: 'Al corriente',
        opened: '2021-03-15',
      },
    ],
    warnings: [],
  },
];

/* -------------------------------------------------------------------- plan */

const money = (title: string, def: string, description?: string) => ({
  type: 'string' as const,
  title,
  default: def,
  ...(description ? { description } : {}),
});
const count = (title: string, def: number, minimum: number, maximum: number) => ({
  type: 'integer' as const,
  title,
  default: def,
  minimum,
  maximum,
});
const ccy = (def: string) => ({ type: 'string' as const, title: 'Currency', default: def });

export const SCENARIOS: ScenarioSpec[] = [
  {
    id: 'regime_mx',
    schema: {
      title: 'Inputs',
      type: 'object',
      properties: {
        monthly_income: money('Monthly Income', '30000.00', 'Uniform monthly income (MXN, before IVA).'),
        monthly_deductible_expenses: money(
          'Monthly Deductible Expenses',
          '6000.00',
          'Uniform monthly authorized deductions (only used by the general regime).',
        ),
        months: count('Months', 12, 1, 12),
        currency: ccy('MXN'),
      },
    },
    metric_path: ['results', 'general', 'annual_isr'],
  },
  {
    id: 'entity_us',
    schema: {
      title: 'Inputs',
      type: 'object',
      properties: {
        annual_net_profit: money('Annual Net Profit', '100000.00', 'Net profit before any owner compensation, USD.'),
        reasonable_salary: money('Reasonable Salary', '60000.00', 'S-corp sketch: the W-2 salary paid to the owner-employee.'),
        currency: ccy('USD'),
      },
    },
    metric_path: ['results', 's_corp_sketch', 'estimated_savings_vs_sole_prop'],
  },
  {
    id: 'buy_vs_rent',
    schema: {
      title: 'Inputs',
      type: 'object',
      properties: {
        home_price: money('Home Price', '3000000.00'),
        down_payment_pct: money('Down Payment Pct', '0.20'),
        mortgage_annual_rate: money('Mortgage Annual Rate', '0.11'),
        mortgage_years: count('Mortgage Years', 20, 1, 40),
        monthly_rent: money('Monthly Rent', '18000.00'),
        rent_annual_growth: money('Rent Annual Growth', '0.05'),
        home_appreciation_annual: money('Home Appreciation Annual', '0.04'),
        property_tax_insurance_monthly: money('Property Tax Insurance Monthly', '1500.00'),
        maintenance_monthly: money('Maintenance Monthly', '1000.00'),
        selling_cost_pct: money('Selling Cost Pct', '0.06'),
        discount_rate_annual: money('Discount Rate Annual', '0.08'),
        horizon_years: count('Horizon Years', 10, 1, 40),
        currency: ccy('MXN'),
      },
    },
    metric_path: ['results', 'buy_npv_cost'],
  },
  {
    id: 'cash_vs_credit',
    schema: {
      title: 'Inputs',
      type: 'object',
      properties: {
        purchase_amount: money('Purchase Amount', '30000.00'),
        msi_months: count('Msi Months', 12, 1, 24),
        annual_rate: money('Annual Rate', '0.00'),
        opportunity_annual_return: money('Opportunity Annual Return', '0.09'),
        currency: ccy('MXN'),
      },
    },
    metric_path: ['results', 'credit_npv_cost'],
  },
  {
    id: 'retirement',
    schema: {
      title: 'Inputs',
      type: 'object',
      properties: {
        starting_balance: money('Starting Balance', '200000.00'),
        monthly_contribution: money('Monthly Contribution', '8000.00'),
        expected_annual_return: money('Expected Annual Return', '0.07'),
        annual_volatility: money('Annual Volatility', '0.15'),
        inflation_annual: money('Inflation Annual', '0.045'),
        horizon_years: count('Horizon Years', 25, 1, 60),
        iterations: count('Iterations', 200, 10, 5000),
        seed: count('Seed', 7, 0, 999999),
        currency: ccy('MXN'),
      },
    },
    metric_path: ['results', 'p50'],
  },
  {
    id: 'debt_payoff',
    schema: {
      title: 'Inputs',
      type: 'object',
      properties: {
        extra_monthly: money('Extra Monthly', '2000.00'),
        currency: ccy('MXN'),
      },
    },
    metric_path: ['results', 'avalanche', 'total_interest'],
  },
];

/** Per-scenario fixture results, shaped like the live `POST .../run` responses. */
export const SCENARIO_RESULTS: Record<string, { results: Record<string, unknown>; summary: string; rules: string[] }> = {
  regime_mx: {
    results: {
      resico: { annual_isr: '3844.56', effective_rate: '0.01100017167381974248927038627' },
      general: { annual_isr: '36613.85', effective_rate: '0.1047606580829756795422031474' },
      cheaper: 'regime_mx.resico',
      deduction_ratio_breakeven: '0.8078',
      months: Array.from({ length: 12 }, (_, i) => ({
        month: i + 1,
        resico_isr: '320.38',
        general_provisional: i % 2 === 0 ? '3051.15' : '3051.16',
      })),
    },
    summary:
      'RESICO: 3844.56 MXN de ISR anual vs. Actividad Empresarial: 36613.85 MXN. Conviene regime_mx.resico.',
    rules: ['mx.resico.isr_monthly@2026.1', 'mx.general.isr_provisional@2026.1'],
  },
  entity_us: {
    results: {
      sole_prop: { se_tax: '14129.55', total_tax: '31861.66' },
      llc_single_member: { note: 'Disregarded for federal tax; same as a sole proprietorship (verify).' },
      s_corp_sketch: {
        reasonable_salary: '60000.00',
        payroll_taxes: '9180.00',
        estimated_savings_vs_sole_prop: '4949.55',
        caveat: 'Sketch only: payroll cost, state filings and reasonable-compensation risk are not modelled (verify).',
      },
    },
    summary:
      'S-corp sketch saves roughly 4949.55 USD of self-employment tax at this profit, before payroll and filing costs (verify). Informational only.',
    rules: ['us.fed.se_tax@2026.1'],
  },
  buy_vs_rent: {
    results: {
      buy_npv_cost: '2184310.42',
      rent_npv_cost: '2010887.05',
      cheaper: 'rent',
      breakeven_year: 12,
    },
    summary:
      'Sobre 10 años y con una tasa de descuento de 8%, rentar cuesta 173423.37 MXN menos en valor presente; el punto de equilibrio llega hacia el año 12.',
    rules: [],
  },
  cash_vs_credit: {
    results: {
      cash_npv_cost: '30000.00',
      credit_npv_cost: '28742.19',
      cheaper: 'credit',
      opportunity_gain: '1257.81',
    },
    summary:
      'A 12 MSI sin intereses, pagar a crédito y mantener el dinero invertido al 9% ahorra 1257.81 MXN en valor presente.',
    rules: [],
  },
  retirement: {
    results: {
      p10: '5559130.73',
      p50: '10215309.93',
      p90: '18349080.32',
      mean: '11114907.06',
      success_rate_pct: '100.00',
      iterations: 200,
      seed: 7,
    },
    summary:
      'A 25 años con 200 simulaciones (seed 7): saldo final p50 = 10215309.93 MXN (rango p10-p90: 5559130.73 - 18349080.32).',
    rules: [],
  },
  debt_payoff: {
    results: {
      avalanche: { months: 26, total_interest: '18422.71' },
      snowball: { months: 27, total_interest: '19510.44' },
      cheaper: 'avalanche',
      difference: '1087.73',
    },
    summary:
      'Avalancha (mayor tasa primero) termina un mes antes y paga 1087.73 MXN menos de intereses que bola de nieve.',
    rules: [],
  },
};

/* ----------------------------------------------------------- research refs */

export const REFS: Record<string, RefsGraph> = {
  'LISR|113-E': {
    law: 'LISR',
    article: '113-E',
    cites: [
      { law: 'LISR', article: '113-F' },
      { law: 'CFF', article: '29-A' },
    ],
    cited_by: [
      { law: 'RMF', article: '3.13.10' },
      { law: 'RMF', article: '3.13.25' },
      { law: 'LISR', article: '113-G' },
    ],
  },
  'LIVA|5': {
    law: 'LIVA',
    article: '5',
    cites: [{ law: 'LIVA', article: '1-B' }],
    cited_by: [{ law: 'RMF', article: '2.7.1.32' }],
  },
};

/* -------------------------------------------------------------------- watch */

export const WATCH_SOURCES: WatchSource[] = [
  {
    id: 'dof-daily',
    name: 'Diario Oficial de la Federación — edición diaria',
    jurisdiction: 'MX',
    doc_type: 'statute',
    fetch_method: 'bulk',
    cadence: 'daily',
    trust_tier: 'primary',
    url: 'https://www.dof.gob.mx/index_113.php',
    domains: ['isr', 'iva', 'cfdi'],
  },
  {
    id: 'sat-rmf',
    name: 'SAT — Resolución Miscelánea Fiscal (RMF) vigente',
    jurisdiction: 'MX',
    doc_type: 'guidance',
    fetch_method: 'bulk',
    cadence: 'weekly',
    trust_tier: 'official_guidance',
    url: 'https://www.sat.gob.mx/normatividad/15224/normatividad-de-resolucion-miscelanea-fiscal',
    domains: ['resico', 'cfdi'],
  },
  {
    id: 'sat-cfdi-catalogos',
    name: 'SAT — catálogos CFDI (c_TipoDeComprobante, c_UsoCFDI, etc.)',
    jurisdiction: 'MX',
    doc_type: 'guidance',
    fetch_method: 'bulk',
    cadence: 'monthly',
    trust_tier: 'official_guidance',
    url: 'https://www.sat.gob.mx/consulta/93726/catalogos-de-la-factura-electronica',
    domains: ['cfdi'],
  },
  {
    id: 'irs-standard-deduction',
    name: 'IRS — inflation adjustments (standard deduction, brackets)',
    jurisdiction: 'US',
    doc_type: 'guidance',
    fetch_method: 'html',
    cadence: 'monthly',
    trust_tier: 'official_guidance',
    url: 'https://www.irs.gov/newsroom/irs-provides-tax-inflation-adjustments',
    domains: ['standard_deduction', 'se_tax'],
  },
  {
    id: 'irs-feie',
    name: 'IRS — foreign earned income exclusion',
    jurisdiction: 'US',
    doc_type: 'guidance',
    fetch_method: 'html',
    cadence: 'monthly',
    trust_tier: 'official_guidance',
    url: 'https://www.irs.gov/individuals/international-taxpayers/foreign-earned-income-exclusion',
    domains: ['feie'],
  },
  {
    id: 'fincen-fbar',
    name: 'FinCEN — Report of Foreign Bank and Financial Accounts',
    jurisdiction: 'US',
    doc_type: 'guidance',
    fetch_method: 'html',
    cadence: 'monthly',
    trust_tier: 'official_guidance',
    url: 'https://www.fincen.gov/report-foreign-bank-and-financial-accounts',
    domains: ['fbar'],
  },
  {
    id: 'tx-comptroller-franchise',
    name: 'Texas Comptroller — franchise tax',
    jurisdiction: 'US',
    doc_type: 'guidance',
    fetch_method: 'html',
    cadence: 'weekly',
    trust_tier: 'official_guidance',
    url: 'https://comptroller.texas.gov/taxes/franchise/',
    domains: ['franchise_tax'],
  },
  {
    id: 'tx-comptroller-sales',
    name: 'Texas Comptroller — sales and use tax rates',
    jurisdiction: 'US',
    doc_type: 'guidance',
    fetch_method: 'api',
    cadence: 'monthly',
    trust_tier: 'official_guidance',
    url: 'https://comptroller.texas.gov/taxes/sales/',
    domains: ['sales_tax'],
  },
  {
    id: 'ecfr-title26',
    name: 'eCFR — Title 26 (Internal Revenue)',
    jurisdiction: 'US',
    doc_type: 'regulation',
    fetch_method: 'api',
    cadence: 'weekly',
    trust_tier: 'primary',
    url: 'https://www.ecfr.gov/current/title-26',
    domains: ['se_tax', 'standard_deduction'],
  },
];

export const WATCH_HISTORY: Record<string, WatchSourceHistory> = {
  'sat-rmf': {
    source_id: 'sat-rmf',
    snapshots: [
      { source_id: 'sat-rmf', fetched_at: '2026-09-06T04:00:11.482913', content_hash: 'a19f4c0d7b2e5518aa30', bytes: 4823104 },
      { source_id: 'sat-rmf', fetched_at: '2026-08-30T04:00:09.117402', content_hash: 'a19f4c0d7b2e5518aa30', bytes: 4823104 },
      { source_id: 'sat-rmf', fetched_at: '2026-08-23T04:00:07.884120', content_hash: '77c2be91045fa3106d18', bytes: 4811990 },
    ],
    changes: [],
  },
  'tx-comptroller-franchise': {
    source_id: 'tx-comptroller-franchise',
    snapshots: [
      {
        source_id: 'tx-comptroller-franchise',
        fetched_at: '2026-09-05T05:12:44.900011',
        content_hash: '5ce1099ab3d740f2c9aa',
        bytes: 118422,
      },
    ],
    changes: [],
  },
};

export const WATCH_PROPOSALS: WatchProposal[] = [
  {
    id: 'prop_ea1cfecd722c',
    change_id: 'chg_86130b1553a1',
    rule_id: 'mx.platform_withholding.sat_access',
    field: 'requirement',
    old_value: 'no real-time access requirement',
    new_value: 'real-time SAT access required from 2026-04-01; notice via forma 168/CFF by 2026-04-30',
    status: 'proposed',
    created_at: '2026-09-06T14:59:47+00:00',
  },
  {
    id: 'prop_3b7d9a10ffcc',
    change_id: 'chg_9d21b7740e55',
    rule_id: 'us.fed.standard_deduction',
    field: 'single',
    old_value: '15750.00',
    new_value: '16100.00',
    status: 'proposed',
    created_at: '2026-09-04T11:20:03+00:00',
  },
];
