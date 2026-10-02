'use client';

/**
 * Este mes: Entró / Salió / Te queda from `GET /pf/{ws}/review/{period}`
 * with explicit signs (the server sends `expense` positive; the screen shows it as an outflow),
 * one sentence comparing spending with last month (the delta is a bare decimal string on the
 * wire, formatted with the review's currency — a wrap, not a sum) and the "Presupuesto usado" bar from
 * `GET /pf/{ws}/budgets/status?period` `totals` (hidden when the budget is 0).
 *
 * The title is "Este mes · sep 2026" only for the current period; any other period is just
 * its own name — a past month is never called "Este mes".
 */
import Link from 'next/link';
import { Money, Stat } from '@/components/ui';
import { decimalSign, formatPeriod, toChartNumber } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import type { BudgetsStatus, MonthlyReview } from '@/lib/types';
import { HomeSection, UsageBar, negate, negated, sameDecimal } from './shared';
import styles from './home.module.css';

export function ThisMonth({
  review,
  budgets,
  period,
  isCurrentPeriod,
}: {
  review: MonthlyReview;
  budgets: BudgetsStatus | null;
  period: string;
  isCurrentPeriod: boolean;
}) {
  const { t, lang } = useI18n();
  const { fmt } = useMoney();
  const title = isCurrentPeriod ? `${t('home.month')} · ${formatPeriod(period, lang)}` : formatPeriod(period, lang);
  const currency = review.income.currency;
  // One plain sentence about spending vs last month instead of two signed deltas
  // (a green "+$1,130" under Salió read as good news). Skipped when last month had no spending
  // (delta == expense) or nothing changed.
  const delta = review.vs_previous_month.expense_delta;
  const deltaSign = decimalSign(delta);
  const spendingNote =
    deltaSign === 0 || sameDecimal(delta, review.expense.amount)
      ? null
      : t(deltaSign > 0 ? 'inicio.gasto.mas' : 'inicio.gasto.menos', {
          amount: fmt({ amount: deltaSign > 0 ? delta : negate(delta), currency }),
        });
  const totals = budgets?.totals;
  const showBar = Boolean(totals && decimalSign(totals.budget.amount) > 0);
  // Pixel geometry only (toChartNumber is the one float allowed on an amount).
  const usedPct = showBar && totals ? (toChartNumber(totals.spent) / toChartNumber(totals.budget)) * 100 : 0;

  return (
    <HomeSection title={title}>
      <div className={styles.stats}>
        <Stat label={t('inicio.entro')} value={<Money amount={review.income} sign="always" />} />
        <Stat label={t('inicio.salio')} value={<Money amount={negated(review.expense)} sign="always" />} />
        <Stat
          label={isCurrentPeriod ? t('inicio.te_queda') : t('inicio.te_quedo')}
          value={<Money amount={review.net} sign="always" />}
        />
      </div>
      {spendingNote && <p className="muted small">{spendingNote}</p>}
      {showBar && totals && (
        <div className={styles.barBlock}>
          <span className={styles.barHead}>
            <span>{t('inicio.presupuesto_usado')}</span>
            <span className={['muted', styles.barLink].join(' ')}>
              {t('inicio.presupuesto_restante', { amount: fmt(totals.remaining) })}
              <Link href={`/presupuesto/?period=${encodeURIComponent(period)}`} className={styles.tapLink}>
                {t('inicio.ver_todos')}
              </Link>
            </span>
          </span>
          <UsageBar pct={usedPct} tone={usedPct >= 100 ? 'over' : usedPct >= 80 ? 'warn' : 'ok'} label={t('inicio.presupuesto_usado')} />
        </div>
      )}
    </HomeSection>
  );
}
