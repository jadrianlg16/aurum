'use client';

/**
 * Pagos fijos: the list of every non-income commitment as a
 * `ResponsiveTable` (cards below 768px) — Nombre · Cada · Próximo · Cuenta (by name, never a
 * ledger string) · Monto · estado — with kind/status filters, the '+ Nuevo pago fijo' primary
 * first in the tab, the row drawer, the form dialog, and the one-line shortcut in a closed
 * `<details>` BELOW the list. Every write reloads the list.
 *
 * The status filter defaults to 'En curso' (everything but `cancelled`, filtered client-side):
 * DELETE on a commitment is a soft delete (status cancelled + ended), so a quitado row would
 * otherwise stay in the list as 'Cancelado'. 'Todos' shows them again.
 */
import { useCallback, useMemo, useState } from 'react';
import { Button, EmptyState, ErrorBox, Field, Money, ResponsiveTable, Select, Skeleton, useToast, type Column } from '@/components/ui';
import { getAlerts, listCommitments } from '@/lib/api';
import { formatDate, relativeDay } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import { COMMITMENT_KINDS, COMMITMENT_STATUSES, type Commitment, type CommitmentKind, type CommitmentStatus, type OrgAlert } from '@/lib/types-organizer';
import { useResource } from '@/lib/useResource';
import { useAdvanced } from '@/lib/workspace';
import { StatusBadge } from '../Money';
import { CommitmentDialog } from './CommitmentForm';
import { CommitmentDrawer } from './CommitmentDrawer';
import { NoticesList } from './NoticesList';
import { QuickAddCard } from './QuickAddCard';
import { cadenceText } from './shared';
import styles from './money.module.css';

/** Personal kinds only: income has its own tab; tax and transfer are advanced-only words. */
const LIST_KINDS = COMMITMENT_KINDS.filter((k) => k !== 'income' && k !== 'tax' && k !== 'transfer');

export function RecurringList({ ws }: { ws: string }) {
  const { t, lang } = useI18n();
  const toast = useToast();
  const [kind, setKind] = useState<CommitmentKind | ''>('');
  // '' = En curso (all but cancelled, client-side), 'all' = Todos, else one server status.
  const [status, setStatus] = useState<CommitmentStatus | '' | 'all'>('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [editing, setEditing] = useState<Commitment | 'new' | null>(null);
  const advanced = useAdvanced();
  // Simple mode has no Resumen tab, so the organizer's avisos surface here — only
  // when there is one (an empty "Sin avisos" block would be noise on the everyday list).
  const alerts = useResource<OrgAlert[]>(
    useCallback(() => (advanced ? Promise.resolve([]) : getAlerts(ws)), [ws, advanced]),
    [ws, advanced],
  );

  const list = useResource<Commitment[]>(
    useCallback(
      () => listCommitments(ws, { kind: kind || undefined, status: status && status !== 'all' ? status : undefined }),
      [ws, kind, status],
    ),
    [ws, kind, status],
  );

  const rows = useMemo(() => {
    const data = (list.data ?? []).filter((c) => c.kind !== 'income' && (status !== '' || c.status !== 'cancelled'));
    return [...data].sort((a, b) => (a.next_due < b.next_due ? -1 : a.next_due > b.next_due ? 1 : a.name.localeCompare(b.name)));
  }, [list.data, status]);

  const columns: Column<Commitment>[] = [
    { key: 'name', header: t('money.col.name'), mobile: 'title' },
    { key: 'every', header: t('money.col.every'), mobile: 'subtitle', render: (c) => cadenceText(t, c, lang) },
    {
      key: 'next',
      header: t('money.col.next'),
      mobile: 'meta',
      render: (c) => {
        const rel = relativeDay(c.next_due, lang);
        const abs = formatDate(c.next_due, lang);
        return rel === abs ? (
          <span>{abs}</span>
        ) : (
          <span>
            {rel}
            <span className="muted small"> · {abs}</span>
          </span>
        );
      },
    },
    { key: 'account', header: t('money.col.account'), mobile: 'meta', render: (c) => c.account_name ?? '—' },
    { key: 'amount', header: t('money.col.money'), numeric: true, mobile: 'value', render: (c) => <Money amount={c.amount} /> },
    { key: 'status', header: t('money.col.status'), mobile: 'meta', render: (c) => <StatusBadge status={c.status} /> },
  ];

  const saved = (c: Commitment) => {
    setEditing(null);
    toast.success(t('money.fixed.saved'));
    list.reload();
    if (openId === c.id) setOpenId(c.id);
  };

  const openExisting = (id: string) => {
    setEditing(null);
    setOpenId(id);
  };

  // Tipo / Estado filters earn their place only on a long list (or once one is in use).
  const showFilters = advanced || (list.data?.length ?? 0) > 8 || kind !== '' || status !== '';
  const filtersRow = (
    <div className={styles.toolbar}>
      <Button variant="primary" onClick={() => setEditing('new')}>
        {t('money.fixed.new')}
      </Button>
      <span className={styles.grow} />
      {showFilters && (
        <>
          <Field label={t('money.filter.kind')}>
            <Select value={kind} onChange={(e) => setKind(e.target.value as CommitmentKind | '')}>
              <option value="">{t('money.fixed.filter.all')}</option>
              {LIST_KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`money.kind.${k}` as MsgKey)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('money.filter.status')}>
            <Select value={status} onChange={(e) => setStatus(e.target.value as CommitmentStatus | '' | 'all')}>
              <option value="">{t('money.fixed.filter.live')}</option>
              <option value="all">{t('money.fixed.filter.all')}</option>
              {COMMITMENT_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`money.status.${s}` as MsgKey)}
                </option>
              ))}
            </Select>
          </Field>
        </>
      )}
    </div>
  );

  return (
    <div className={styles.section}>
      {(alerts.data?.length ?? 0) > 0 && (
        <section className={styles.section} aria-labelledby="fixed-notices">
          <h2 id="fixed-notices">{t('money.notices')}</h2>
          <NoticesList ws={ws} alerts={alerts.data ?? []} onChanged={() => alerts.reload()} />
        </section>
      )}
      {filtersRow}

      {list.loading ? (
        <Skeleton variant="table" rows={5} what={t('money.fixed.list')} />
      ) : list.error ? (
        <ErrorBox error={list.problem ?? list.error} onRetry={list.reload} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon="list"
          title={t('money.fixed.empty')}
          body={t('money.fixed.empty.body')}
          primary={{ label: t('money.empty.add_fixed'), onClick: () => setEditing('new') }}
          compact
        />
      ) : (
        <div className={styles.list} aria-busy={list.refreshing || undefined}>
          <ResponsiveTable columns={columns} rows={rows} rowKey={(c) => c.id} onRowClick={(c) => setOpenId(c.id)} label={t('money.fixed.list')} />
        </div>
      )}

      <QuickAddCard
        ws={ws}
        onSaved={() => list.reload()}
        onOpenExisting={openExisting}
      />

      <CommitmentDrawer
        ws={ws}
        id={openId}
        onClose={() => setOpenId(null)}
        onChanged={list.reload}
        onEdit={(c) => {
          setOpenId(null);
          setEditing(c);
        }}
      />

      <CommitmentDialog
        ws={ws}
        open={editing !== null}
        commitment={editing === 'new' ? null : editing}
        onClose={() => setEditing(null)}
        onSaved={saved}
        onOpenExisting={openExisting}
      />
    </div>
  );
}
