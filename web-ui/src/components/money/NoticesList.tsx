'use client';

/**
 * 'Avisos': the organizer alerts minus the ones already visible in
 * the 7-day list (`upcoming` and `income_expected` whose (commitment, due) pair is there),
 * grouped urgent → warn → info. Title from `money.alert.<kind>` with `money.alert.other` as
 * the fallback for kinds this build does not know; the server's own `title`/`body` are
 * already human (pre-formatted money and dates); `due` goes through `formatDate`, old → new
 * amounts through `<Money>`; dismiss is an `IconButton` 'Entendido'.
 */
import { useState } from 'react';
import { Badge, IconButton, Money, useToast } from '@/components/ui';
import { dismissAlert, errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import type { AlertSeverity, Occurrence, OrgAlert } from '@/lib/types-organizer';
import styles from './money.module.css';

const ORDER: AlertSeverity[] = ['urgent', 'warn', 'info'];
const KNOWN = new Set([
  'price_increase',
  'price_decrease',
  'trial_ending',
  'missed_payment',
  'upcoming',
  'duplicate',
  'annual_renewal',
  'forgotten',
  'income_expected',
  'income_late',
  'income_changed',
  'cancelled_still_charging',
]);

/** Alerts that duplicate a 7-day row are dropped (the row already offers the action). */
export function dedupeAgainstUpcoming(alerts: OrgAlert[], next7: Occurrence[]): OrgAlert[] {
  const seen = new Set(next7.map((o) => `${o.commitment_id}|${o.due}`));
  return alerts.filter((a) => {
    const kind = a.kind as string;
    if (kind !== 'upcoming' && kind !== 'income_expected') return true;
    return !(a.commitment_id && a.due && seen.has(`${a.commitment_id}|${a.due}`));
  });
}

const toneOf = (s: AlertSeverity): 'neg' | 'warn' | 'info' => (s === 'urgent' ? 'neg' : s === 'warn' ? 'warn' : 'info');
const classOf = (s: AlertSeverity): string => (s === 'urgent' ? styles.noticeUrgent : s === 'warn' ? styles.noticeWarn : styles.noticeInfo);

export function NoticesList({ ws, alerts, onChanged }: { ws: string; alerts: OrgAlert[]; onChanged: () => void }) {
  const { t, lang } = useI18n();
  const toast = useToast();
  const [gone, setGone] = useState<Set<string>>(() => new Set());

  const dismiss = async (a: OrgAlert) => {
    setGone((prev) => new Set(prev).add(a.id));
    try {
      await dismissAlert(ws, a.id);
      onChanged();
    } catch (e) {
      setGone((prev) => {
        const next = new Set(prev);
        next.delete(a.id);
        return next;
      });
      toast.error(errorMessage(e, t));
    }
  };

  const visible = alerts.filter((a) => !gone.has(a.id));
  const sorted = [...visible].sort((a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity));
  if (sorted.length === 0) return <p className={styles.noticeMeta}>{t('money.notices.empty')}</p>;

  return (
    <ul className={styles.notices}>
      {sorted.map((a) => {
        const kind = a.kind as string;
        const label = KNOWN.has(kind) ? t(`money.alert.${kind}` as MsgKey) : t('money.alert.other');
        return (
          <li key={a.id} className={[styles.notice, classOf(a.severity)].join(' ')}>
            <div className={styles.noticeBody}>
              <div className={styles.noticeTitle}>
                <Badge tone={toneOf(a.severity)}>{label}</Badge>
                <strong>{a.title}</strong>
              </div>
              {a.body && <p className={styles.noticeText}>{a.body}</p>}
              {(a.due || (a.old_amount && a.new_amount)) && (
                <div className={styles.noticeMeta}>
                  {a.due && <span>{formatDate(a.due, lang)}</span>}
                  {a.due && a.old_amount && a.new_amount && <span aria-hidden="true"> · </span>}
                  {a.old_amount && a.new_amount && (
                    <span>
                      <Money amount={a.old_amount} /> → <Money amount={a.new_amount} />
                    </span>
                  )}
                </div>
              )}
            </div>
            <IconButton icon="check" ariaLabel={`${t('money.notices.dismiss')}: ${a.title}`} bordered onClick={() => void dismiss(a)} />
          </li>
        );
      })}
    </ul>
  );
}
