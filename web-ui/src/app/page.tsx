'use client';

/**
 * Inicio — the Tuesday screen, built on the `components/ui` primitives.
 *
 * Data plan, exactly (all through `lib/api.ts`, all behind `WorkspaceGate`):
 *   phase A  `GET /pf/{ws}/accounts` — zero rows → `<StartHere>` (+ `GET /pf/{ws}/onboarding`)
 *            and nothing else: 2 requests;
 *   phase B  `GET /organizer/{ws}/summary`, `GET /organizer/{ws}/calendar?from=today&to=+7d`,
 *            `GET /pf/{ws}/review/{period}`, `GET /pf/{ws}/budgets/status?period`,
 *            `GET /pf/{ws}/entries?from&to&limit=5` — 6 requests in total.
 * Goals come from `review.goals_progress`. Net worth lives on Cuentas (one fewer card here).
 * Never `getMonthClose`, `listInbox`, `getCards` or anything under `/tax/` — nothing here is
 * gated by advanced mode because nothing here is advanced.
 *
 * `today` is read in an effect (never at prerender) and phase B mounts only once it is
 * known, so `formatPeriod`/`relativeDay` never run on the server and the `?period=` deep link
 * (applied by `usePeriodParam` after mount) is honoured by the very first fetch. Every write
 * elsewhere bumps `useAddEntry().version`, which is in every resource's deps.
 */
import { useCallback, useEffect, useState } from 'react';
import { useAddEntry } from '@/components/AddEntry';
import { BudgetTop3 } from '@/components/home/BudgetTop3';
import { GoalsStrip } from '@/components/home/GoalsStrip';
import { HeroDisponible } from '@/components/home/HeroDisponible';
import { RecentMovements } from '@/components/home/RecentMovements';
import { StartHere } from '@/components/home/StartHere';
import { ThisMonth } from '@/components/home/ThisMonth';
import { UpcomingPayments } from '@/components/home/UpcomingPayments';
import { addDaysIso } from '@/components/home/shared';
import styles from '@/components/home/home.module.css';
import { ErrorBox, PageHeader, Skeleton } from '@/components/ui';
import {
  getAccountsOverview,
  getBudgetStatus,
  getOrganizerCalendar,
  getOrganizerSummary,
  getReview,
  listEntries,
} from '@/lib/api';
import { todayLocalIso } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { monthBounds, usePeriodParam } from '@/lib/period';
import { useResource } from '@/lib/useResource';
import { WorkspaceGate, useWorkspace } from '@/lib/workspace';

export default function HomePage() {
  const { t } = useI18n();
  // Inicio is "now" — no month picker here (Movimientos and Presupuesto keep one);
  // a `?period=` deep link still works through the hook.
  const [period] = usePeriodParam();
  return (
    <>
      <PageHeader title={t('home.title')} />
      <WorkspaceGate fallback={<Skeleton variant="stat" what={t('home.title')} />}>
        <HomeBody period={period} />
      </WorkspaceGate>
    </>
  );
}

function HomeBody({ period }: { period: string }) {
  const { t } = useI18n();
  const { ws } = useWorkspace();
  const { version } = useAddEntry();
  const [today, setToday] = useState<string | null>(null);
  useEffect(() => {
    setToday(todayLocalIso());
  }, []);

  const accounts = useResource(
    useCallback(() => getAccountsOverview(ws), [ws]),
    [ws, version],
  );

  if (accounts.error && !accounts.data) return <ErrorBox error={accounts.problem ?? accounts.error} onRetry={accounts.reload} />;
  if (!accounts.data || today === null) return <Skeleton variant="stat" rows={3} what={t('home.title')} />;
  if ((accounts.data.accounts ?? []).length === 0) return <StartHere ws={ws} />;
  return <Dashboard ws={ws} period={period} today={today} reloadAccounts={accounts.reload} version={version} />;
}

function Dashboard({
  ws,
  period,
  today,
  reloadAccounts,
  version,
}: {
  ws: string;
  period: string;
  today: string;
  reloadAccounts: () => void;
  version: number;
}) {
  const { t } = useI18n();
  const to = addDaysIso(today, 7);
  const { from: monthFrom, to: monthTo } = monthBounds(period);
  const isCurrent = period === today.slice(0, 7);

  const summary = useResource(
    useCallback(() => getOrganizerSummary(ws), [ws]),
    [ws, version],
  );
  const calendar = useResource(
    useCallback(() => getOrganizerCalendar(ws, today, to), [ws, today, to]),
    [ws, today, to, version],
  );
  const review = useResource(
    useCallback(() => getReview(ws, period), [ws, period]),
    [ws, period, version],
  );
  const budgets = useResource(
    useCallback(() => getBudgetStatus(ws, period), [ws, period]),
    [ws, period, version],
  );
  const entries = useResource(
    useCallback(
      (signal: AbortSignal) => listEntries(ws, { from: monthFrom, to: monthTo, limit: 5 }, { signal }),
      [ws, monthFrom, monthTo],
    ),
    [ws, monthFrom, monthTo, version],
  );

  const { reload: reloadSummary } = summary;
  const { reload: reloadCalendar } = calendar;
  const { reload: reloadEntries } = entries;
  const { reload: reloadReview } = review;
  const { reload: reloadBudgets } = budgets;
  const reloadAll = useCallback(() => {
    reloadSummary();
    reloadCalendar();
    reloadEntries();
    reloadReview();
    reloadBudgets();
    reloadAccounts();
  }, [reloadSummary, reloadCalendar, reloadEntries, reloadReview, reloadBudgets, reloadAccounts]);

  return (
    <div className="stack">
      {summary.data ? (
        <HeroDisponible summary={summary.data} />
      ) : summary.error ? (
        <ErrorBox error={summary.problem ?? summary.error} onRetry={summary.reload} />
      ) : (
        <div className="card headline">
          <Skeleton variant="stat" what={t('inicio.como_se_calcula')} />
        </div>
      )}

      <div className={styles.grid}>
        <div className={styles.col}>
          {/* Gated on the calendar alone: a failed calendar is an ErrorBox, never "Nada por
              pagar"; the alerts badge reads `summary.data` independently (null until it lands). */}
          {calendar.data ? (
            <UpcomingPayments ws={ws} today={today} summary={summary.data} calendar={calendar.data} reloadAll={reloadAll} />
          ) : calendar.error ? (
            <ErrorBox error={calendar.problem ?? calendar.error} onRetry={calendar.reload} />
          ) : (
            <div className="card">
              <Skeleton variant="list" rows={4} what={t('inicio.proximos')} />
            </div>
          )}

          {entries.data ? (
            <RecentMovements entries={entries.data.entries} period={period} isCurrentPeriod={isCurrent} />
          ) : entries.error ? (
            <ErrorBox error={entries.problem ?? entries.error} onRetry={entries.reload} />
          ) : (
            <div className="card">
              <Skeleton variant="table" rows={5} what={t('inicio.ultimos')} />
            </div>
          )}
        </div>

        <div className={styles.col}>
          {review.data ? (
            <ThisMonth review={review.data} budgets={budgets.data} period={period} isCurrentPeriod={isCurrent} />
          ) : review.error ? (
            <ErrorBox error={review.problem ?? review.error} onRetry={review.reload} />
          ) : (
            <div className="card">
              <Skeleton variant="stat" rows={3} what={t('home.month')} />
            </div>
          )}

          {budgets.data ? (
            <BudgetTop3 budgets={budgets.data} period={period} />
          ) : budgets.error ? (
            <ErrorBox error={budgets.problem ?? budgets.error} onRetry={budgets.reload} />
          ) : (
            <div className="card">
              <Skeleton variant="list" rows={3} what={t('nav.presupuesto')} />
            </div>
          )}

          {review.data && <GoalsStrip goals={review.data.goals_progress ?? []} />}
        </div>
      </div>
    </div>
  );
}
