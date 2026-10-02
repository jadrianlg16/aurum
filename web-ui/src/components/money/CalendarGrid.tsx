'use client';

/**
 * The ≥768px month grid: 7 equal columns from module CSS
 * (`repeat(7, minmax(0, 1fr))`, no minimum width, no gutter column), every day of the month
 * rendered, today highlighted, at most 3 chips per day + '+N'. The whole cell is one `button`
 * that opens the day sheet; chips are plain spans inside it (full name with ellipsis, compact
 * amount, tones: income `pos`, missed `neg`, card_due `warn`).
 */
import { Money } from '@/components/ui';
import { formatDate } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import type { CalendarItem } from '@/lib/types-organizer';
import type { GridCell } from './monthGrid';
import { displayName } from './OccurrenceSheet';
import { signedAmount } from './shared';
import styles from './money.module.css';

const MAX_CHIPS = 3;

function chipClass(it: CalendarItem): string {
  const tone = it.kind === 'income' ? styles.chipPos : it.status === 'missed' ? styles.chipNeg : it.kind === 'card_due' ? styles.chipWarn : '';
  return [styles.chip, tone].filter(Boolean).join(' ');
}

export function Chip({ item }: { item: CalendarItem }) {
  const { t } = useI18n();
  const name = displayName(t, item);
  return (
    <span className={chipClass(item)} title={name}>
      <span className={styles.chipName}>{name}</span>
      {item.kind !== 'card_cut' && (
        <span className={styles.chipAmt}>
          <Money amount={signedAmount(item.kind === 'income' ? 'income' : 'commitment', item.amount)} compactCents sign={item.kind === 'income' ? 'always' : 'auto'} />
        </span>
      )}
    </span>
  );
}

export interface CalendarGridProps {
  weeks: GridCell[][];
  headers: string[];
  today: string | null;
  onPickDay: (cell: GridCell) => void;
}

export function CalendarGrid({ weeks, headers, today, onPickDay }: CalendarGridProps) {
  const { t, lang } = useI18n();
  return (
    <div role="grid" aria-label={t('money.cal.grid')} data-money-grid="">
      <div className={styles.calHead} role="row">
        {headers.map((h, i) => (
          <div key={`${h}-${i}`} className={styles.calHeadCell} role="columnheader">
            {h}
          </div>
        ))}
      </div>
      {weeks.map((week, wi) => (
        <div className={styles.calWeek} role="row" key={`w-${wi}`}>
          {week.map((cell) => {
            const cls = [styles.calCell, cell.inMonth ? '' : styles.calCellOut, cell.iso === today ? styles.calCellToday : ''].filter(Boolean).join(' ');
            const extra = cell.items.length - MAX_CHIPS;
            const inner = (
              <>
                <span className={styles.calDay}>{cell.day}</span>
                {cell.items.slice(0, MAX_CHIPS).map((it) => (
                  <Chip key={`${it.kind}-${it.id}-${it.date}`} item={it} />
                ))}
                {extra > 0 && <span className={styles.chipMore}>{t('money.cal.more', { n: extra })}</span>}
              </>
            );
            return (
              <div key={cell.iso} role="gridcell">
                {cell.inMonth ? (
                  <button type="button" className={cls} aria-label={t('money.cal.open_day', { date: formatDate(cell.iso, lang, 'weekday') })} onClick={() => onPickDay(cell)}>
                    {inner}
                  </button>
                ) : (
                  <div className={cls} aria-hidden="true">
                    {inner}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
