'use client';

/**
 * 'Próximos 7 días': a `ResponsiveTable` over
 * `summary.next_7_days` joined with `listCommitments` by `commitment_id` (for `label_id`,
 * `account_id` and — defensively — `amount_variable`). Columns Nombre · Cuándo (`relativeDay`)
 * · Monto (explicit sign; income adds the 'Te llega' badge) · Estado · action. The action per
 * row: fixed due/upcoming/missed → 'Pagado'; variable → 'Registrar' (+ Agregar prefilled);
 * income → 'Ya llegó'; paid/skipped → 'Deshacer'. The row flips immediately and reverts on
 * error; success toasts carry Deshacer; the parent reloads after every write.
 */
import { useEffect } from 'react';
import { Badge, Button, Money, ResponsiveTable, type Column } from '@/components/ui';
import { relativeDay } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import type { Commitment, Occurrence, OccurrenceStatus } from '@/lib/types-organizer';
import { actionLabel, isIncomeKind, occKey, primaryAction, signedAmount, statusTone, useOccurrenceActions, type OccTarget } from './shared';

export interface UpcomingListProps {
  ws: string;
  rows: Occurrence[];
  commitments: Commitment[];
  today: string | null;
  onChanged: () => void;
}

interface Row extends OccTarget {
  key: string;
  effective: OccurrenceStatus;
}

export function UpcomingList({ ws, rows, commitments, today, onChanged }: UpcomingListProps) {
  const { t, lang } = useI18n();
  const actions = useOccurrenceActions(ws, { onDone: onChanged });

  // Fresh rows landed: the local flips have done their job.
  useEffect(() => {
    actions.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  const byId = new Map(commitments.map((c) => [c.id, c]));
  const data: Row[] = rows.map((o) => {
    const c = byId.get(o.commitment_id);
    const target: OccTarget = {
      commitment_id: o.commitment_id,
      due: o.due,
      name: o.name ?? c?.name ?? o.commitment_id,
      amount: o.amount,
      kind: o.kind ?? c?.kind ?? null,
      status: o.status,
      amount_variable: o.amount_variable ?? c?.amount_variable ?? null,
      account_id: c?.account_id ?? null,
      label_id: c?.label_id ?? null,
      // `summary.py` sends `entry_id` next to `txn_id`; the type only lists the latter.
      entry_id: (o as Occurrence & { entry_id?: string | null }).entry_id ?? o.txn_id ?? null,
    };
    const key = occKey(target);
    return { ...target, key, effective: actions.overrides[key] ?? o.status };
  });

  const columns: Column<Row>[] = [
    { key: 'name', header: t('money.col.name'), mobile: 'title', render: (r) => r.name },
    { key: 'when', header: t('money.col.when'), mobile: 'subtitle', render: (r) => (today ? relativeDay(r.due, lang, today) : '') },
    {
      key: 'amount',
      header: t('money.col.money'),
      numeric: true,
      mobile: 'value',
      render: (r) =>
        isIncomeKind(r.kind) ? (
          <span>
            <Money amount={r.amount} sign="always" /> <Badge tone="pos">{t('money.badge.incoming')}</Badge>
          </span>
        ) : (
          <Money amount={signedAmount(r.kind, r.amount)} />
        ),
    },
    {
      key: 'status',
      header: t('money.col.status'),
      mobile: 'meta',
      render: (r) => <Badge tone={statusTone(r.effective)}>{t(`money.occ.${r.effective}` as MsgKey)}</Badge>,
    },
    {
      key: 'action',
      header: t('common.actions'),
      align: 'right',
      mobile: 'meta',
      render: (r) => {
        const action = primaryAction({ ...r, status: r.effective });
        if (!action) return null;
        const busy = actions.busy === r.key;
        return (
          <Button
            variant={action === 'undo' ? 'ghost' : 'secondary'}
            loading={busy}
            disabled={actions.busy !== null && !busy}
            onClick={(e) => {
              e.stopPropagation();
              actions.run(action, { ...r, status: r.effective });
            }}
          >
            {actionLabel(t, action)}
          </Button>
        );
      },
    },
  ];

  return <ResponsiveTable columns={columns} rows={data} rowKey={(r) => r.key} label={t('money.next7')} />;
}
