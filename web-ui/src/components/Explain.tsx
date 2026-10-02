'use client';

/**
 * <Explain> — the product's signature interaction.
 *
 * Renders an `aurum.core.explain.Explain` at three depths:
 *   1. the one-line `summary`, always visible;
 *   2. the worked math — `steps` as Qué / Cómo / Cuánto;
 *   3. the `citations` (law, article, effective range, trust tier, excerpt, url) plus the
 *      `rule_versions` that produced the figure.
 *
 * The steps are humanized client-side: a known step id maps
 * to a sentence through `explain.id.<id>` (else `_` → space), the value is formatted by kind
 * (money through `useMoney().fmt`, dates medium, percentages, counts), and ledger globs in the
 * formula (`Assets:Bank:*`, `Σ`) become words. Nothing here computes anything: every value is
 * a string the API produced. Rule versions and citations stay hidden in simple mode when there
 * are no citations, and a citation is a link only when `safeHref` accepts its URL.
 */
import { useId, useState } from 'react';
import { formatDate, formatNumber, formatPct } from '@/lib/format';
import { useI18n, useMoney, type MsgKey } from '@/lib/i18n';
import type { Citation, Explain as ExplainModel, Step, TrustTier } from '@/lib/types';

const TRUST_CLASS: Record<TrustTier, string> = {
  primary: 'badge accent',
  official_guidance: 'badge info',
  professional: 'badge neutral',
  blog: 'badge warn',
};

/** Only http(s) URLs become links; anything else (javascript:, data:, relative junk) is text. */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.toString() : null;
  } catch {
    return null;
  }
}

type ValueKind = 'money' | 'date' | 'pct' | 'count' | 'text';

/** The known step ids (forecast.py, accounts.py, budgets.py, goals.py) and how their value reads. */
const STEP_KIND: Record<string, ValueKind> = {
  liquid_balance: 'money',
  until: 'date',
  committed_until: 'money',
  budgeted_remaining: 'money',
  buffer: 'money',
  safe_to_spend: 'money',
  net_worth: 'money',
  effective_budget: 'money',
  spent: 'money',
  remaining: 'money',
  pct: 'pct',
  months_left: 'count',
  monthly_required: 'money',
};

const DECIMAL_RE = /^[+-]?\d+(\.\d+)?$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Guess a kind when the id is unknown: a date looks like a date, a decimal like money. */
function guessKind(value: string): ValueKind {
  const v = value.trim();
  if (DATE_RE.test(v)) return 'date';
  if (DECIMAL_RE.test(v)) return 'money';
  return 'text';
}

export function TrustBadge({ tier }: { tier: TrustTier }) {
  const { t } = useI18n();
  return <span className={TRUST_CLASS[tier]}>{t(`trust.${tier}`)}</span>;
}

export function CitationCard({ citation }: { citation: Citation }) {
  const { t, lang } = useI18n();
  const range =
    citation.effective_from || citation.effective_to
      ? `${formatDate(citation.effective_from ?? null, lang)} → ${
          citation.effective_to ? formatDate(citation.effective_to, lang) : '…'
        }`
      : null;
  const href = safeHref(citation.url);

  return (
    <div className="citation">
      <div className="cite-head">
        <span>
          {citation.law} · {t('explain.source')} {citation.article}
        </span>
        <TrustBadge tier={citation.trust_tier} />
        {range && (
          <span className="muted small">
            {t('explain.effective')}: {range}
          </span>
        )}
        {href ? (
          <a className="small" href={href} target="_blank" rel="noreferrer noopener">
            {href.replace(/^https?:\/\//, '').slice(0, 46)}
            <span className="sr-only"> ({t('a11y.new_window')})</span>
          </a>
        ) : citation.url ? (
          <span className="small muted">{citation.url.slice(0, 46)}</span>
        ) : null}
      </div>
      {citation.excerpt && <blockquote>{citation.excerpt}</blockquote>}
    </div>
  );
}

/** `Assets:Bank:*` → "todas las cuentas", `Σ` → "suma de", `_` → space. Words, not ledger paths. */
function humanizeFormula(formula: string, words: { all: string; sum: string }): string {
  return formula
    .replace(/\b(Assets|Liabilities|Income|Expenses|Equity):[A-Za-z0-9:_-]*\*?/g, (m) => {
      if (/^Assets:/.test(m)) return words.all;
      return m.replace(/^[A-Za-z]+:/, '').replace(/[:*]/g, ' ').replace(/_/g, ' ').trim().toLowerCase();
    })
    .replace(/Σ\s*/g, `${words.sum} `)
    .replace(/\b([a-z]+)_([a-z_]+)\b/g, (m) => m.replace(/_/g, ' '));
}

function StepRow({ step, index }: { step: Step; index: number }) {
  const { t, lang } = useI18n();
  const { fmt } = useMoney();
  const idKey = `explain.id.${step.label}`;
  const label = isKnownKey(idKey) ? t(idKey as MsgKey) : step.label.replace(/_/g, ' ');
  const kind = STEP_KIND[step.label] ?? guessKind(step.value);
  let value: string = step.value;
  if (kind === 'money') value = fmt(step.value);
  else if (kind === 'date') value = formatDate(step.value, lang, 'medium');
  else if (kind === 'pct') value = formatPct(step.value, lang);
  else if (kind === 'count') value = formatNumber(step.value, lang);
  const formula = step.formula
    ? humanizeFormula(step.formula, { all: t('explain.words.all_accounts'), sum: t('explain.words.sum') })
    : '—';
  return (
    <tr key={`${step.label}-${index}`}>
      <td>{label}</td>
      <td className="formula">{formula}</td>
      <td className={`num ${kind === 'money' ? 'money' : ''}`}>{value}</td>
    </tr>
  );
}

/** The `explain.id.*` keys are exactly the STEP_KIND ids (`i18n/core.ts`); anything else is raw. */
function isKnownKey(key: string): boolean {
  return key.startsWith('explain.id.') && STEP_KIND[key.slice('explain.id.'.length)] !== undefined;
}

export function Explain({
  explain,
  defaultOpen = false,
  hideSummaryIfSameAs,
  /** Simple mode hides rule versions and the confidence figure when there are no citations. */
  simple = true,
  /**
   * Everyday screens: the summary sentence moves inside "¿Cómo se calcula?" so a
   * figure is never followed by a paragraph of method; opening the toggle shows it first.
   */
  quiet = false,
}: {
  explain?: ExplainModel | null;
  defaultOpen?: boolean;
  /** Skip the summary line when it repeats text already shown next to it (e.g. an alert body). */
  hideSummaryIfSameAs?: string | null;
  simple?: boolean;
  quiet?: boolean;
}) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();
  if (!explain) return null;

  const steps = explain.steps ?? [];
  const citations = explain.citations ?? [];
  const rules = explain.rule_versions ?? [];
  const showMeta = !simple || citations.length > 0;
  const hideSummary = hideSummaryIfSameAs != null && explain.summary.trim() === hideSummaryIfSameAs.trim();
  const summaryInside = quiet && !hideSummary && explain.summary.trim() !== '';
  const hasDetail = summaryInside || steps.length > 0 || citations.length > 0 || (showMeta && rules.length > 0);

  return (
    <div className="explain">
      {!hideSummary && !quiet && <p className="explain-summary">{explain.summary}</p>}
      {hasDetail && (
        <button
          type="button"
          className="explain-toggle"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls={bodyId}
        >
          {open ? `▾ ${t('explain.hide')}` : `▸ ${t('explain.steps')}`}
        </button>
      )}
      {open && hasDetail && (
        <div className="explain-body" id={bodyId}>
          {summaryInside && <p className="explain-summary">{explain.summary}</p>}
          {steps.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t('explain.step')}</th>
                    <th scope="col">{t('explain.formula')}</th>
                    <th scope="col" className="num">
                      {t('explain.value')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {steps.map((s, i) => (
                    <StepRow key={`${s.label}-${i}`} step={s} index={i} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {citations.length > 0 && (
            <div className="stack" style={{ gap: 8 }}>
              <h3>{t('explain.citations')}</h3>
              {citations.map((c, i) => (
                <CitationCard key={`${c.law}-${c.article}-${i}`} citation={c} />
              ))}
            </div>
          )}

          {showMeta && (rules.length > 0 || typeof explain.confidence === 'number') && (
            <div className="row small muted">
              {rules.length > 0 && (
                <>
                  <span>{t('explain.rule_versions')}:</span>
                  {rules.map((r) => (
                    <span key={r} className="rule-chip">
                      {r}
                    </span>
                  ))}
                </>
              )}
              {typeof explain.confidence === 'number' && (
                <span style={{ marginLeft: 'auto' }}>
                  {t('explain.confidence')}: {formatPct(explain.confidence, lang)}
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
