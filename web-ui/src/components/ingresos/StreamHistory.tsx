'use client';

/**
 * `StreamHistory` — 'Esperado contra recibido' for one income stream.
 *
 * `GET /income/streams/{id}/history` answers one row per occurrence `{due, expected, received,
 * status}` (aurum/pf/streams.py; the client wrapper adds a derived `period`). The badge is
 * decided by the money first — received ≥ expected → 'Llegó', received < expected → 'Llegó
 * menos' — then by the status (`missed` → 'No llegó', `skipped` → 'Se omitió'), else 'No llegó
 * todavía'; that way the live statuses (`upcoming|due|paid|missed|skipped`) and the mock's
 * (`received|late|pending|missed`) both render. `r.due ?? r.period` is read defensively.
 */
import { useCallback } from 'react';
import { Badge, EmptyState, ErrorBox, Money, ResponsiveTable, Skeleton, type BadgeTone, type Column } from '@/components/ui';
import { getStreamHistory } from '@/lib/api';
import { decimalSign, formatDate } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import type { Amount } from '@/lib/types';
import type { IncomeStream, StreamHistoryRow } from '@/lib/types-personal';
import { useResource } from '@/lib/useResource';
import { sumDecimals } from '@/lib/validate';

type StatusKey = 'received' | 'less' | 'missed' | 'skipped' | 'pending';

/** Money first, then the status word — both the live and the mock vocabularies land somewhere. */
export function historyStatus(r: { expected?: Amount | null; received?: Amount | null; status?: string | null }): StatusKey {
  if (r.received) {
    if (!r.expected) return 'received';
    return decimalSign(sumDecimals([r.received.amount, `-${r.expected.amount}`])) >= 0 ? 'received' : 'less';
  }
  if (r.status === 'missed') return 'missed';
  if (r.status === 'skipped') return 'skipped';
  return 'pending';
}

const TONE: Record<StatusKey, BadgeTone> = {
  received: 'pos',
  less: 'warn',
  missed: 'neg',
  skipped: 'neutral',
  pending: 'info',
};

export function StreamHistory({ ws, stream }: { ws: string; stream: IncomeStream }) {
  const { t, lang } = useI18n();
  const history = useResource(
    useCallback((signal: AbortSignal) => getStreamHistory(ws, stream.id, { signal }), [ws, stream.id]),
    [ws, stream.id],
  );
  if (history.loading) return <Skeleton variant="table" rows={3} what={t('inc.history')} />;
  if (history.error && !history.data) return <ErrorBox error={history.problem ?? history.error} onRetry={history.reload} />;
  const rows = history.data?.periods ?? [];
  if (rows.length === 0) return <EmptyState compact title={t('inc.history.empty')} />;

  const columns: Column<StreamHistoryRow>[] = [
    { key: 'due', header: t('inc.history.due'), mobile: 'title', render: (r) => formatDate(r.due ?? r.period, lang) },
    { key: 'expected', header: t('inc.history.expected'), numeric: true, mobile: 'meta', render: (r) => (r.expected ? <Money amount={r.expected} /> : '—') },
    { key: 'received', header: t('inc.history.received'), numeric: true, mobile: 'value', render: (r) => (r.received ? <Money amount={r.received} /> : '—') },
    {
      key: 'status',
      header: t('inc.history.status'),
      mobile: 'subtitle',
      render: (r) => {
        const k = historyStatus(r);
        return <Badge tone={TONE[k]}>{t(`inc.status.${k}`)}</Badge>;
      },
    },
  ];
  return (
    <ResponsiveTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.due ?? r.period}
      label={`${t('inc.history')} · ${stream.name}`}
    />
  );
}
