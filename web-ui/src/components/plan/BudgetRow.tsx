'use client';

/**
 * One budget row of `/presupuesto/`. Everything shown comes from
 * `GET /budgets/status` as the server computed it: `pct` is a percent number (85 → 85 %), the
 * tone follows `state`, and the copy is "Gastado $X de $Y · queda $Z" with `effective` as the
 * "de" figure. Nothing is recomputed here — `carried` is only *displayed* when its amount is
 * positive, and `min(pct, 100)` is the bar's pixel width, never a figure.
 *
 * The wrapper carries the ui-check selectors (`data-testid="budget-row"`, `data-label-id`,
 * `data-state`, `data-pct`) because `ResponsiveTable` rows accept no caller `data-*`.
 */
import { Badge } from '@/components/ui';
import { decimalSign } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import type { BudgetStatusRow } from '@/lib/types';

export type BudgetTone = 'pos' | 'warn' | 'neg';

export function budgetTone(state: BudgetStatusRow['state']): BudgetTone {
  if (state === 'over') return 'neg';
  if (state === 'warn') return 'warn';
  return 'pos';
}

/** The bar width: the server's percent clamped to the track. Geometry only. */
export function barWidth(pct: BudgetStatusRow['pct']): number {
  const n = Number(pct);
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.min(n, 100);
}

export function BudgetRow({ row }: { row: BudgetStatusRow }) {
  const { t } = useI18n();
  const { fmt } = useMoney();
  const state = row.state ?? 'ok';
  const tone = budgetTone(state);
  const pctNum = Number(row.pct);
  const pctText = Number.isFinite(pctNum) ? String(Math.round(pctNum)) : '—';
  const carriedShown = row.carried && decimalSign(row.carried.amount) > 0;
  const overBy = state === 'over' ? { amount: row.remaining.amount.replace(/^-/, ''), currency: row.remaining.currency } : null;
  const badgeTone = tone === 'pos' ? 'pos' : tone === 'warn' ? 'warn' : 'neg';

  return (
    <div
      data-testid="budget-row"
      data-label-id={row.label_id}
      data-state={state}
      data-pct={String(row.pct)}
    >
      <div className="row">
        <strong>
          {row.icon ? <span aria-hidden="true">{row.icon} </span> : null}
          {row.label_name}
        </strong>
        <Badge tone={badgeTone}>{t(`budget.state.${state}`)}</Badge>
        <span className="small muted num">{t('budget.pct', { pct: pctText })}</span>
      </div>
      <div className={`bar ${tone}`} aria-hidden="true">
        <span style={{ width: `${barWidth(row.pct)}%` }} />
      </div>
      <p className="small muted">
        {t('budget.row.spent', {
          spent: fmt(row.spent),
          of: fmt(row.effective ?? row.budget),
          left: fmt(row.remaining),
        })}
        {carriedShown && <> · {t('budget.row.carried', { amount: fmt(row.carried) })}</>}
        {overBy && <> · {t('budget.over', { amount: fmt(overBy) })}</>}
      </p>
    </div>
  );
}
