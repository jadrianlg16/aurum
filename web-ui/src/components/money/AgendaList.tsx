'use client';

/**
 * The <768px calendar: a `<ul>` grouped by day — heading
 * `formatDate` + `relativeDay` — with one ≥44px button per item that opens the OccurrenceSheet.
 * No grid is rendered at this width.
 */
import { Badge, Money } from '@/components/ui';
import { formatDate, relativeDay } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import type { CalendarDay, CalendarItem } from '@/lib/types-organizer';
import { displayName } from './OccurrenceSheet';
import { signedAmount, statusTone } from './shared';
import styles from './money.module.css';

export interface AgendaListProps {
  days: CalendarDay[];
  today: string | null;
  onPick: (item: CalendarItem) => void;
}

export function AgendaRow({ item, onPick }: { item: CalendarItem; onPick: (item: CalendarItem) => void }) {
  const { t } = useI18n();
  const income = item.kind === 'income';
  return (
    <button type="button" className={styles.agendaRow} onClick={() => onPick(item)}>
      <span className={styles.agendaName}>{displayName(t, item)}</span>
      <Badge tone={statusTone(item.status)}>{t(`money.occ.${item.status}` as MsgKey)}</Badge>
      {item.kind !== 'card_cut' && <Money amount={signedAmount(income ? 'income' : 'commitment', item.amount)} sign={income ? 'always' : 'auto'} />}
    </button>
  );
}

export function AgendaList({ days, today, onPick }: AgendaListProps) {
  const { t, lang } = useI18n();
  return (
    <ul className={styles.agenda} aria-label={t('money.cal.agenda')} data-money-agenda="">
      {days.map((d) => {
        const rel = today ? relativeDay(d.date, lang, today) : '';
        const abs = formatDate(d.date, lang, 'weekday');
        return (
          <li key={d.date} className={styles.agendaDay}>
            <h3>{rel && rel !== formatDate(d.date, lang) ? `${rel} · ${abs}` : abs}</h3>
            <ul className={styles.agendaItems}>
              {d.items.map((it) => (
                <li key={`${it.kind}-${it.id}-${it.date}`}>
                  <AgendaRow item={it} onPick={onPick} />
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ul>
  );
}
