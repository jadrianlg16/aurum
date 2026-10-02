'use client';

/**
 * Presupuesto · top 3: `GET /pf/{ws}/budgets/status?period` rows
 * sorted by `pct` desc (a percent, not money), the first three as bars toned by `state`
 * (ok / warn / over) with "Restante {remaining}" from the server figure. None → compact
 * EmptyState pointing at /presupuesto/.
 */
import Link from 'next/link';
import { EmptyState, Money } from '@/components/ui';
import { useI18n, useMoney } from '@/lib/i18n';
import type { BudgetsStatus } from '@/lib/types';
import { HomeSection, UsageBar, pctNumber } from './shared';
import styles from './home.module.css';

export function BudgetTop3({ budgets, period }: { budgets: BudgetsStatus; period: string }) {
  const { t } = useI18n();
  const { fmt } = useMoney();
  const href = `/presupuesto/?period=${encodeURIComponent(period)}`;
  const top = [...(budgets.budgets ?? [])].sort((a, b) => pctNumber(b.pct) - pctNumber(a.pct)).slice(0, 3);

  return (
    <HomeSection title={t('nav.presupuesto')} actions={top.length > 0 ? <Link href={href} className={styles.tapLink}>{t('inicio.ver_todos')}</Link> : undefined}>
      {top.length === 0 ? (
        <EmptyState compact title={t('inicio.sin_presupuesto')} primary={{ label: t('inicio.ir_presupuesto'), href: '/presupuesto/', variant: 'secondary' }} />
      ) : (
        <ul className={styles.budgets}>
          {top.map((b) => (
            <li key={b.budget_id ?? b.label_id} className={styles.barBlock}>
              <span className={styles.barHead}>
                <span>{b.label_name}</span>
                <span className="muted">{t('inicio.restante', { amount: fmt(b.remaining) })}</span>
              </span>
              <UsageBar pct={pctNumber(b.pct)} tone={b.state ?? (pctNumber(b.pct) >= 100 ? 'over' : pctNumber(b.pct) >= 80 ? 'warn' : 'ok')} label={`${b.label_name} · ${Math.round(pctNumber(b.pct))}%`} />
              <span className="sr-only">
                <Money amount={b.spent} /> {t('common.of')} <Money amount={b.effective ?? b.budget} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </HomeSection>
  );
}
