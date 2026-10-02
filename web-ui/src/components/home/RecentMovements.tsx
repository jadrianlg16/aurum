'use client';

/**
 * Últimos movimientos: the latest 5 rows of
 * `GET /pf/{ws}/entries?from&to&limit=5` (the server sorts `(date, id)` desc) in a
 * `ResponsiveTable`; amounts through `<Money sign="always">` (sr-only entrada/salida comes
 * from the primitive). "Ver todos" → `/movimientos/?period=`; "Agregar" opens the shared
 * dialog. Nothing is summed here — `entries.totals` is the server's and this block does not
 * even show it.
 */
import Link from 'next/link';
import { useAddEntry } from '@/components/AddEntry';
import { Button, EmptyState, Money, ResponsiveTable, type Column } from '@/components/ui';
import { formatDate, formatPeriod } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import type { Entry } from '@/lib/types-personal';
import { HomeSection } from './shared';
import styles from './home.module.css';

export function RecentMovements({
  entries,
  period,
  isCurrentPeriod,
}: {
  entries: Entry[];
  period: string;
  isCurrentPeriod: boolean;
}) {
  const { t, lang } = useI18n();
  const { open } = useAddEntry();

  const columns: Column<Entry>[] = [
    { key: 'date', header: t('common.date'), mobile: 'meta', render: (e) => formatDate(e.date, lang, 'short') },
    { key: 'who', header: t('add.payee'), mobile: 'title', render: (e) => e.payee || e.label_name || '—' },
    { key: 'account', header: t('common.account'), mobile: 'subtitle', render: (e) => e.account_name ?? '' },
    {
      key: 'amount',
      header: t('add.amount'),
      align: 'right',
      numeric: true,
      mobile: 'value',
      render: (e) => <Money amount={e.amount} sign="always" />,
    },
  ];

  return (
    <HomeSection
      title={t('inicio.ultimos')}
      actions={
        <>
          <Link href={`/movimientos/?period=${encodeURIComponent(period)}`} className={styles.tapLink}>
            {t('inicio.ver_todos')}
          </Link>
          <Button variant="secondary" icon="plus" onClick={() => open('expense')}>
            {t('common.add')}
          </Button>
        </>
      }
    >
      {entries.length === 0 ? (
        isCurrentPeriod ? (
          <EmptyState
            compact
            title={t('inicio.sin_movimientos')}
            primary={{ label: t('inicio.sin_movimientos.cta'), onClick: () => open('expense') }}
          />
        ) : (
          <EmptyState compact title={t('inicio.sin_movimientos_periodo', { period: formatPeriod(period, lang) })} />
        )
      ) : (
        <ResponsiveTable columns={columns} rows={entries} rowKey={(e) => e.id} label={t('inicio.ultimos')} />
      )}
    </HomeSection>
  );
}
