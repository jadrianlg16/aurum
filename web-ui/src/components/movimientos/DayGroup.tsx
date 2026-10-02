'use client';

/**
 * One day of movements: a heading ("Hoy · vie 12 sep", `lib/format.formatDayHeading`), the
 * day's display-only subtotal (sr-labelled "Total del día") and the rows in a
 * `ResponsiveTable` (a table from 768px, cards below). Columns and actions come from
 * MovementRow.tsx; the page owns selection, paging and the edit/duplicate/delete handlers.
 * Only the first day shows the column header (the rest keep it for screen
 * readers) and every day table has fixed column widths, so the stack reads as one list.
 */
import { formatDayHeading } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import type { Entry } from '@/lib/types-personal';
import { Money, ResponsiveTable, type Column, type RowAction } from '@/components/ui';
import type { DayGroupData } from './dayGroups';
import styles from './movimientos.module.css';

export function DayGroup({
  group,
  today,
  columns,
  actions,
  onRowClick,
  first = false,
}: {
  group: DayGroupData;
  /** The first day on screen shows the column header; the others keep it sr-only. */
  first?: boolean;
  /** Local ISO date read in an effect (never at prerender). */
  today: string | null;
  columns: Column<Entry>[];
  actions: (row: Entry) => RowAction<Entry>[];
  onRowClick: (row: Entry) => void;
}) {
  const { t, lang } = useI18n();
  const heading = today ? formatDayHeading(group.date, lang, today) : group.date;
  return (
    <section aria-label={heading}>
      <div className={styles.dayHead}>
        <h3>{heading}</h3>
        {/* No figure when the day's rows mix currencies (dayGroups.ts): a wrong sum is worse than none. */}
        {group.subtotal !== null && (
          <span className={styles.daySubtotal}>
            <span className="sr-only">{t('txn.day.subtotal')}: </span>
            <Money amount={{ amount: group.subtotal, currency: group.currency }} sign="always" />
          </span>
        )}
      </div>
      <ResponsiveTable
        columns={columns}
        rows={group.rows}
        rowKey={(r) => r.id}
        onRowClick={onRowClick}
        actions={actions}
        label={heading}
        tableClassName={styles.dayTable}
        quietHeader={!first}
      />
    </section>
  );
}
