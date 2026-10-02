'use client';

/**
 * Resumen: `GET /summary` + `GET /alerts` + `GET /commitments`
 * through `useResource` (stale-while-refresh). The hero is the one 'Disponible hasta el
 * {date}' figure from `safe_to_spend` (its four parts listed under it, the API's own explain
 * behind '¿Cómo se calcula?'), then 'Pagos fijos del mes' and either 'Ingresos esperados este
 * mes' (when the organizer sends `income_expected`) or 'Próximo ingreso' (`relativeDay(until)`),
 * the 7-day list with its actions and the deduped Avisos. No client-side money math.
 *
 * Empty organizer (no commitments and no income): an `EmptyState` whose primary opens the
 * `StreamForm` inline inside a Dialog (no form mode, so no nested form) and whose secondary
 * opens the `CommitmentDialog`; detection is never offered.
 */
import { useCallback, useEffect, useState } from 'react';
import { StreamForm } from '@/components/ingresos/StreamForm';
import { Dialog, EmptyState, ErrorBox, Money, Skeleton, Stat, useToast } from '@/components/ui';
import { getAlerts, getOrganizerSummary, listCommitments } from '@/lib/api';
import { formatDate, relativeDay, todayLocalIso } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import type { Amount } from '@/lib/types';
import type { Commitment, OrgAlert, OrganizerSummary } from '@/lib/types-organizer';
import { useResource } from '@/lib/useResource';
import { CommitmentDialog } from './CommitmentForm';
import { dedupeAgainstUpcoming, NoticesList } from './NoticesList';
import { UpcomingList } from './UpcomingList';
import styles from './money.module.css';

type SummaryPlus = OrganizerSummary & { income_expected?: Amount | null };

const PARTS = ['balance', 'fixed_pending', 'budgets_remaining', 'buffer'] as const;

export function Summary({ ws }: { ws: string }) {
  const { t, lang } = useI18n();
  const toast = useToast();
  const [today, setToday] = useState<string | null>(null);
  const [adding, setAdding] = useState<'income' | 'fixed' | null>(null);

  useEffect(() => {
    setToday(todayLocalIso());
  }, []);

  const summary = useResource<SummaryPlus>(useCallback(() => getOrganizerSummary(ws), [ws]), [ws]);
  const alerts = useResource<OrgAlert[]>(useCallback(() => getAlerts(ws), [ws]), [ws]);
  const commitments = useResource<Commitment[]>(useCallback(() => listCommitments(ws), [ws]), [ws]);

  const reloadAll = () => {
    summary.reload();
    alerts.reload();
    commitments.reload();
  };

  if (summary.loading) return <Skeleton variant="stat" what={t('money.tab.summary')} />;
  if (summary.error) return <ErrorBox error={summary.problem ?? summary.error} onRetry={summary.reload} />;
  const s = summary.data;
  if (!s) return null;

  const empty = !s.setup?.has_commitments && !s.setup?.has_income;
  if (empty) {
    return (
      <>
        <EmptyState
          icon="wallet"
          title={t('money.empty.title')}
          body={t('money.empty.body')}
          primary={{ label: t('money.empty.add_income'), onClick: () => setAdding('income') }}
          secondary={{ label: t('money.empty.add_fixed'), onClick: () => setAdding('fixed') }}
        />
        <Dialog open={adding === 'income'} onClose={() => setAdding(null)} title={t('money.empty.add_income')} size="lg">
          {adding === 'income' && (
            <StreamForm
              ws={ws}
              inline
              onSaved={() => {
                setAdding(null);
                reloadAll();
              }}
            />
          )}
        </Dialog>
        <CommitmentDialog
          ws={ws}
          open={adding === 'fixed'}
          onClose={() => setAdding(null)}
          onSaved={() => {
            setAdding(null);
            toast.success(t('money.fixed.saved'));
            reloadAll();
          }}
        />
      </>
    );
  }

  const sts = s.safe_to_spend;
  const next7 = s.next_7_days ?? [];
  const notices = dedupeAgainstUpcoming(alerts.data ?? [], next7);

  return (
    <div className={styles.section} aria-busy={summary.refreshing || undefined}>
      <div className={['card', styles.hero].join(' ')}>
        <Stat
          size="lg"
          label={t('money.available_until', { date: formatDate(sts?.until, lang) })}
          value={<Money amount={sts?.amount} sign="auto" />}
          explain={sts?.explain}
          sub={
            sts?.parts ? (
              <span className={styles.parts}>
                {PARTS.map((p) => (
                  <span key={p} className={styles.part}>
                    <span className={styles.partLabel}>{t(`money.part.${p}`)}</span>
                    <Money amount={sts.parts?.[p]} />
                  </span>
                ))}
              </span>
            ) : undefined
          }
        />
      </div>

      <div className={styles.stats}>
        <div className="card">
          <Stat label={t('money.stat.fixed_month')} value={<Money amount={s.monthly_committed?.total} />} />
        </div>
        <div className="card">
          {s.income_expected ? (
            <Stat label={t('money.stat.income_expected')} value={<Money amount={s.income_expected} sign="always" />} />
          ) : (
            <Stat label={t('money.stat.next_income')} value={today ? relativeDay(sts?.until, lang, today) : ''} sub={formatDate(sts?.until, lang)} />
          )}
        </div>
      </div>

      <section className={styles.section} aria-labelledby="money-next7">
        <div className={styles.sectionHead}>
          <h2 id="money-next7">{t('money.next7')}</h2>
        </div>
        {next7.length === 0 ? (
          <p className={styles.noticeMeta}>{t('money.upcoming.empty')}</p>
        ) : (
          <UpcomingList ws={ws} rows={next7} commitments={commitments.data ?? []} today={today} onChanged={reloadAll} />
        )}
      </section>

      <section className={styles.section} aria-labelledby="money-notices">
        <div className={styles.sectionHead}>
          <h2 id="money-notices">{t('money.notices')}</h2>
        </div>
        {alerts.loading ? (
          <Skeleton variant="list" rows={2} what={t('money.notices')} />
        ) : alerts.error ? (
          <ErrorBox error={alerts.problem ?? alerts.error} onRetry={alerts.reload} />
        ) : (
          <NoticesList ws={ws} alerts={notices} onChanged={() => summary.reload()} />
        )}
      </section>
    </div>
  );
}
