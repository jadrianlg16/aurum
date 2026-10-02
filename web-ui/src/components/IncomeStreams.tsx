'use client';

/**
 * Ingresos — income streams set up by hand.
 *
 * `IncomeStreamsPanel` is rendered as the Ingresos tab of "Mi dinero" and by step 2 of the
 * onboarding wizard, so there is exactly one income list in the app. A `ResponsiveTable`
 * (Nombre · Cada · Próximo depósito · Cuenta · Monto) with row actions Registrar ingreso /
 * Editar / Borrar, a 'Historial' toggle per row (a `Button aria-expanded` — `RowAction` has no
 * aria attrs) that mounts `StreamHistory` only while the stream still exists, and the one
 * `StreamForm` in a Dialog without form mode.
 *
 * 'Registrar ingreso' opens + Agregar on the Ingreso tab prefilled from the row, with
 * `commitment_id` only when it is unambiguous: the single mirrored commitment, or — with
 * several — the one whose `next_due` equals the row's `next_expected`, else the earliest.
 *
 * Legacy `toast` / `currency` props are accepted and ignored so older callers keep compiling.
 */
import { useCallback, useMemo, useRef, useState } from 'react';
import { useAddEntry } from '@/components/AddEntry';
import { StreamForm, weekdayNames } from '@/components/ingresos/StreamForm';
import { StreamHistory } from '@/components/ingresos/StreamHistory';
import {
  Badge,
  Button,
  ConfirmDialog,
  Dialog,
  EmptyState,
  ErrorBox,
  Money,
  ResponsiveTable,
  Skeleton,
  useToast,
  type Column,
} from '@/components/ui';
import { deleteStream, errorMessage, listCommitments, listPfAccounts, listStreams } from '@/lib/api';
import { relativeDay, todayLocalIso } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import type { IncomeStream } from '@/lib/types-personal';
import { useResource } from '@/lib/useResource';

export interface IncomeStreamsPanelProps {
  ws: string;
  /** In the onboarding wizard the section chrome is supplied by the step. */
  compact?: boolean;
  onChanged?: () => void;
  /** @deprecated ignored — the panel uses `useToast()` from `components/ui`. */
  toast?: unknown;
  /** @deprecated ignored — the amount is in the account's currency. */
  currency?: string;
}

/**
 * The organizer commitment to link a logged income to: one id → that one; several →
 * the one due on `next_expected`, else the earliest `next_due`; none → undefined (the server
 * matches by payee).
 */
export async function resolveCommitmentId(ws: string, s: IncomeStream): Promise<string | undefined> {
  const ids = s.commitment_ids ?? [];
  if (ids.length === 0) return undefined;
  if (ids.length === 1) return ids[0];
  try {
    const all = await listCommitments(ws);
    const mine = all.filter((c) => ids.includes(c.id));
    if (mine.length === 0) return undefined;
    const exact = s.next_expected ? mine.find((c) => c.next_due === s.next_expected) : undefined;
    if (exact) return exact.id;
    const sorted = [...mine].sort((a, b) => (a.next_due ?? '').localeCompare(b.next_due ?? ''));
    return sorted[0]?.id;
  } catch {
    return undefined;
  }
}

export function IncomeStreamsPanel({ ws, compact, onChanged }: IncomeStreamsPanelProps) {
  const { t, lang } = useI18n();
  const toast = useToast();
  const { open, version } = useAddEntry();
  const [form, setForm] = useState<{ stream: IncomeStream | null } | null>(null);
  const [confirm, setConfirm] = useState<IncomeStream | null>(null);
  const lastConfirm = useRef<IncomeStream | null>(null);
  if (confirm) lastConfirm.current = confirm;
  const confirmName = (confirm ?? lastConfirm.current)?.name ?? '';
  const confirmAmount = (confirm ?? lastConfirm.current)?.amount ?? null;
  const [deleting, setDeleting] = useState(false);
  const [openHistory, setOpenHistory] = useState<string | null>(null);

  const streams = useResource(useCallback((signal: AbortSignal) => listStreams(ws, { signal }), [ws]), [ws, version]);
  const accounts = useResource(useCallback((signal: AbortSignal) => listPfAccounts(ws, {}, { signal }), [ws]), [ws]);
  const rows = useMemo(() => streams.data ?? [], [streams.data]);
  const weekdays = useMemo(() => weekdayNames(lang), [lang]);

  const accountName = (s: IncomeStream): string => {
    if (s.account_name) return s.account_name;
    const hit = (accounts.data ?? []).find((a) => a.id === s.account_id);
    return hit?.name ?? '—';
  };

  const every = (s: IncomeStream): string => {
    const cadence = t(`inc.cadence.${s.cadence}`);
    const days = s.anchor_days ?? [];
    if ((s.cadence === 'monthly' || s.cadence === 'semimonthly') && days.length) {
      const words = days.map((d) => (d === 31 ? t('inc.day.last').toLowerCase() : String(d)));
      return `${cadence} · ${t('inc.days.summary', { days: words.join(', ') })}`;
    }
    if ((s.cadence === 'weekly' || s.cadence === 'biweekly') && s.weekday !== null && s.weekday !== undefined) {
      return `${cadence} · ${weekdays[s.weekday] ?? ''}`;
    }
    return cadence;
  };

  const register = async (s: IncomeStream) => {
    const commitment_id = await resolveCommitmentId(ws, s);
    open({
      kind: 'income',
      accountId: s.account_id ?? undefined,
      prefill: {
        amount: s.amount,
        label_id: s.label_id ?? null,
        payee: s.name,
        date: todayLocalIso(),
        ...(commitment_id ? { commitment_id } : {}),
      },
    });
  };

  const remove = async () => {
    if (!confirm) return;
    const s = confirm;
    setDeleting(true);
    try {
      await deleteStream(ws, s.id);
      // The history panel must be gone before the row is (IncomeStreams.tsx:155-160 crash).
      setOpenHistory((prev) => (prev === s.id ? null : prev));
      setConfirm(null);
      streams.reload();
      onChanged?.();
      toast.success(t('inc.deleted'));
    } catch (e) {
      setConfirm(null);
      toast.error(errorMessage(e, t));
    } finally {
      setDeleting(false);
    }
  };

  const columns: Column<IncomeStream>[] = [
    {
      key: 'name',
      header: t('inc.name'),
      mobile: 'title',
      render: (s) => (
        <span data-testid={`inc-row-${s.id}`}>
          <strong>{s.name}</strong>
          {s.active === false && (
            <>
              {' '}
              <Badge tone="neutral">{t('inc.stopped')}</Badge>
            </>
          )}
          <span className="small muted"> · {t(`inc.source.${s.source_type}`)}</span>
        </span>
      ),
    },
    { key: 'every', header: t('inc.col.every'), mobile: 'subtitle', render: every },
    {
      key: 'next',
      header: t('inc.col.next'),
      mobile: 'meta',
      render: (s) => (s.next_expected ? relativeDay(s.next_expected, lang) : '—'),
    },
    { key: 'account', header: t('inc.col.account'), mobile: 'subtitle', render: accountName },
    {
      key: 'amount',
      header: t('inc.col.amount'),
      numeric: true,
      mobile: 'value',
      render: (s) => <Money amount={s.amount} sign="always" />,
    },
    {
      key: 'history',
      header: t('inc.history.toggle'),
      mobile: 'meta',
      render: (s) => (
        <Button
          variant="ghost"
          aria-expanded={openHistory === s.id}
          onClick={() => setOpenHistory((prev) => (prev === s.id ? null : s.id))}
          data-testid="inc-history"
        >
          {t('inc.history.toggle')}
        </Button>
      ),
    },
  ];

  const openStream = rows.find((s) => s.id === openHistory);
  const newButton = (
    <Button variant="primary" icon="plus" onClick={() => setForm({ stream: null })} data-testid="inc-new">
      {t('inc.new')}
    </Button>
  );

  let body;
  if (streams.loading) {
    body = <Skeleton variant="table" rows={3} what={t('inc.title')} />;
  } else if (streams.error && rows.length === 0) {
    body = <ErrorBox error={streams.problem ?? streams.error} onRetry={streams.reload} />;
  } else if (rows.length === 0) {
    body = (
      <EmptyState
        compact={compact}
        icon="wallet"
        title={t('inc.empty.title')}
        body={t('inc.empty.body')}
        primary={{ label: t('inc.empty.cta'), onClick: () => setForm({ stream: null }) }}
      />
    );
  } else {
    body = (
      <>
        <ResponsiveTable
          columns={columns}
          rows={rows}
          rowKey={(s) => s.id}
          label={t('inc.title')}
          actions={() => [
            { label: t('inc.register'), onClick: (row) => void register(row) },
            { label: t('common.edit'), onClick: (row) => setForm({ stream: row }) },
            { label: t('common.delete'), onClick: (row) => setConfirm(row), destructive: true },
          ]}
        />
        {openStream && (
          <section className="card" aria-label={`${t('inc.history')} · ${openStream.name}`}>
            <h3>
              {t('inc.history')} · {openStream.name}
            </h3>
            <StreamHistory ws={ws} stream={openStream} />
          </section>
        )}
      </>
    );
  }

  return (
    <>
      {compact ? (
        rows.length > 0 && <div className="row">{newButton}</div>
      ) : (
        <div className="page-head">
          <div>
            <h2>{t('inc.title')}</h2>
            <div className="sub">{t('inc.sub')}</div>
          </div>
          <span className="spacer" />
          {rows.length > 0 && newButton}
        </div>
      )}
      <div className="stack">
        {streams.error && rows.length > 0 && <ErrorBox error={streams.problem ?? streams.error} onRetry={streams.reload} />}
        {body}
      </div>

      {/* StreamForm owns its submit; the Dialog is NOT in form mode (no nested form). */}
      <Dialog open={form !== null} onClose={() => setForm(null)} title={form?.stream ? t('inc.edit') : t('inc.new')} size="md">
        {form && (
          <StreamForm
            ws={ws}
            stream={form.stream}
            onSaved={() => {
              setForm(null);
              streams.reload();
              onChanged?.();
              toast.success(t('inc.saved'));
            }}
            onCancel={() => setForm(null)}
          />
        )}
      </Dialog>

      {/* Mounted once and driven by `open` (a Dialog that mounts open closes itself under StrictMode). */}
      <ConfirmDialog
        open={confirm !== null}
        title={t('inc.delete.title', { name: confirmName })}
        body={
          <p>
            {t('inc.delete.body')} {confirmAmount && <Money amount={confirmAmount} sign="always" />}
          </p>
        }
        confirmLabel={t('common.delete')}
        destructive
        busy={deleting}
        onConfirm={() => void remove()}
        onCancel={() => setConfirm(null)}
      />
    </>
  );
}
