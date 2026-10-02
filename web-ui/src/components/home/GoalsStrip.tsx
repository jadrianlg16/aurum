'use client';

/**
 * Metas: `review.goals_progress` (full Goal rows from
 * `GET /pf/{ws}/review/{period}`, no extra request) — top 3 by `pct` as chips linking to
 * /metas/. None → "Ahorra para algo" → /metas/.
 */
import Link from 'next/link';
import { EmptyState } from '@/components/ui';
import { useI18n } from '@/lib/i18n';
import type { Goal } from '@/lib/types';
import { HomeSection, pctNumber } from './shared';
import styles from './home.module.css';

export function GoalsStrip({ goals }: { goals: Goal[] }) {
  const { t } = useI18n();
  const top = [...(goals ?? [])].sort((a, b) => pctNumber(b.pct) - pctNumber(a.pct)).slice(0, 3);
  return (
    <HomeSection title={t('home.goals')} actions={top.length > 0 ? <Link href="/metas/" className={styles.tapLink}>{t('inicio.ver_todos')}</Link> : undefined}>
      {top.length === 0 ? (
        <EmptyState compact title={t('inicio.sin_metas')} primary={{ label: t('inicio.ir_metas'), href: '/metas/', variant: 'secondary' }} />
      ) : (
        <ul className={styles.chips}>
          {top.map((g) => (
            <li key={g.id}>
              <Link href="/metas/" className={styles.goalChip}>
                <span>{g.name} </span>
                <span className={styles.goalPct}>· {Math.round(pctNumber(g.pct))}%</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </HomeSection>
  );
}
