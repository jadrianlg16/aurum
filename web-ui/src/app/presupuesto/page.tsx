'use client';

/**
 * `/presupuesto/` — the month's budgets.
 *
 * One request: `GET /pf/{ws}/budgets/status?period=` (rows carry `budget_id`, so `/budgets` is
 * never listed here). Three figures come straight from `totals`; the third is always
 * "Presupuesto restante" — `safe_to_spend` in this payload is compat only and is not rendered
 * (the one "Disponible" lives on Home, from the organizer). Rows are sorted by the server's
 * `pct`; tone, bar and copy are `BudgetRow`'s. An empty month with `has_previous` offers
 * "Copiar del mes anterior" (`POST /budgets/copy`, idempotent); a first month asks for three
 * categories. Every write is followed by `reload()` (no optimistic rows).
 */
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { BudgetDialog } from '@/components/plan/BudgetDialog';
import { BudgetRow } from '@/components/plan/BudgetRow';
import {
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorBox,
  Money,
  PageHeader,
  ResponsiveTable,
  Skeleton,
  Stat,
  useToast,
  type Column,
} from '@/components/ui';
import { copyBudgets, deleteBudget, errorMessage, getBudgetStatus } from '@/lib/api';
import { decimalSign, formatPeriod } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { usePeriodParam } from '@/lib/period';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { BudgetStatusRow } from '@/lib/types';

export default function PresupuestoPage() {
  const { t, tn, lang } = useI18n();
  const { ws } = useWorkspace();
  const router = useRouter();
  const toast = useToast();
  const [period, setPeriod] = usePeriodParam();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const status = useResource(
    useCallback(() => getBudgetStatus(ws, period), [ws, period]),
    [ws, period],
  );

  const [form, setForm] = useState<{ budget: BudgetStatusRow | null } | null>(null);
  const [confirm, setConfirm] = useState<BudgetStatusRow | null>(null);
  const [busy, setBusy] = useState(false);

  const data = status.data;
  const rows = [...(data?.budgets ?? [])].sort((a, b) => Number(b.pct) - Number(a.pct));

  const copyLast = async () => {
    if (!data?.previous_period) return;
    setBusy(true);
    try {
      const r = await copyBudgets(ws, data.previous_period, period);
      toast.success(tn('budget.copied', r.created));
      status.reload();
    } catch (e) {
      toast.error(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm) return;
    const row = confirm;
    setBusy(true);
    try {
      await deleteBudget(ws, row.budget_id);
      setConfirm(null);
      toast.success(t('budget.deleted'));
      status.reload();
    } catch (e) {
      setConfirm(null);
      toast.error(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const openMovements = (row: BudgetStatusRow) => {
    router.push(`/movimientos/?period=${encodeURIComponent(period)}&label_id=${encodeURIComponent(row.label_id)}`);
  };

  const columns: Column<BudgetStatusRow>[] = [
    { key: 'row', header: t('budget.col.category'), mobile: 'title', render: (r) => <BudgetRow row={r} /> },
    {
      key: 'left',
      header: t('budget.col.left'),
      numeric: true,
      mobile: 'value',
      render: (r) => <Money amount={r.remaining} tone="auto" />,
    },
  ];

  const remainingTone = data?.totals ? (decimalSign(data.totals.remaining.amount) < 0 ? 'neg' : 'pos') : undefined;
  const periodLabel = mounted ? formatPeriod(period, lang, 'long') : period;

  return (
    <>
      <PageHeader
        title={t('budget.title')}
        subtitle={t('budget.sub')}
        month={{ value: period, onChange: setPeriod }}
        actions={
          <Button variant="secondary" icon="plus" data-testid="budget-new" onClick={() => setForm({ budget: null })}>
            {t('budget.new')}
          </Button>
        }
      />

      {status.loading ? (
        <Skeleton variant="list" rows={4} what={t('budget.title')} />
      ) : status.error && !data ? (
        <ErrorBox error={status.problem ?? status.error} onRetry={status.reload} />
      ) : !data ? null : (
        <div className="stack">
          {status.error && <ErrorBox error={status.problem ?? status.error} onRetry={status.reload} />}
          {data.totals && rows.length > 0 && (
            <div className="grid cols-3">
              <Stat label={t('budget.stat.budgeted')} value={<Money amount={data.totals.budget} />} />
              <Stat label={t('budget.stat.spent')} value={<Money amount={data.totals.spent} />} />
              <div data-testid="budget-stat-remaining">
                <Stat
                  label={t('budget.stat.left')}
                  value={<Money amount={data.totals.remaining} tone="auto" />}
                  tone={remainingTone}
                  explain={data.explain ?? null}
                />
              </div>
            </div>
          )}

          {rows.length === 0 ? (
            data.has_previous && data.previous_period ? (
              // `EmptyState.primary` takes no `data-*`; the ui-check selector wraps it
              // (`[data-testid="budget-copy-last"] button`). ui-check itself matches the text.
              <div data-testid="budget-copy-last" data-previous-period={data.previous_period}>
                <EmptyState
                  icon="wallet"
                  title={t('budget.empty.title', { period: periodLabel })}
                  body={t('budget.empty.body')}
                  primary={{ label: t('budget.copy_last'), onClick: () => void copyLast() }}
                />
              </div>
            ) : (
              <EmptyState
                icon="wallet"
                title={t('budget.first.title')}
                body={t('budget.empty.body')}
                primary={{ label: t('budget.new'), onClick: () => setForm({ budget: null }) }}
              />
            )
          ) : (
            <div className="card" aria-busy={status.refreshing || undefined}>
              <ResponsiveTable
                label={t('budget.list')}
                columns={columns}
                rows={rows}
                rowKey={(r) => r.budget_id}
                onRowClick={openMovements}
                actions={(r) => [
                  { label: t('common.edit'), onClick: () => setForm({ budget: r }) },
                  { label: t('budget.see_movements'), onClick: openMovements },
                  { label: t('budget.delete'), onClick: () => setConfirm(r), destructive: true },
                ]}
              />
            </div>
          )}
        </div>
      )}

      {form && (
        <BudgetDialog
          ws={ws}
          period={period}
          budget={form.budget}
          onClose={(saved) => {
            setForm(null);
            if (saved) status.reload();
          }}
        />
      )}
      {confirm && (
        <ConfirmDialog
          title={t('budget.delete.title', { name: confirm.label_name })}
          body={<p>{t('budget.delete.body')}</p>}
          confirmLabel={t('budget.delete')}
          destructive
          busy={busy}
          onConfirm={() => void remove()}
          onCancel={() => setConfirm(null)}
        />
      )}
    </>
  );
}
