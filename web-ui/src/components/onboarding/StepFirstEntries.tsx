'use client';

/**
 * Step 4 — first movements: the shared + Agregar dialog opens
 * over /empezar/ (never an inline copy) from the primary "Agregar un gasto" or from a chip that
 * prefills the merchant (Súper / Comida fuera / Transporte); `onSaved` reloads the onboarding
 * status and the `GET /pf/{ws}/entries?limit=5` list below (a failed list is an inline
 * ErrorBox with Reintentar; the chips stay usable).
 */
import { useCallback } from 'react';
import { useAddEntry } from '@/components/AddEntry';
import { Button, ErrorBox, Money, ResponsiveTable, Skeleton, type Column } from '@/components/ui';
import { listEntries, listLabels } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import type { Entry, OnboardingStep } from '@/lib/types-personal';
import { StepFrame } from './shared';
import styles from './onboarding.module.css';

/** Each chip opens + Agregar on its seeded category (by name; a renamed one opens it blank). */
const CHIPS: { key: 'empezar.chip.super' | 'empezar.chip.comida' | 'empezar.chip.transporte'; category: string }[] = [
  { key: 'empezar.chip.super', category: 'Súper' },
  { key: 'empezar.chip.comida', category: 'Comida fuera' },
  { key: 'empezar.chip.transporte', category: 'Transporte/Gasolina' },
];

export function StepFirstEntries({
  ws,
  step,
  onSaved,
  onNext,
  onBack,
}: {
  ws: string;
  step: OnboardingStep | undefined;
  onSaved: () => void;
  onNext: () => void;
  onBack: () => void;
}) {
  const { t, lang } = useI18n();
  const { open, version } = useAddEntry();
  const entries = useResource(
    useCallback((signal: AbortSignal) => listEntries(ws, { limit: 5 }, { signal }), [ws]),
    [ws, version, step?.count],
  );
  const rows = entries.data?.entries ?? [];

  const labels = useResource(
    useCallback(() => listLabels(ws, { kind: 'expense' }), [ws]),
    [ws],
  );
  const categoryId = (name: string) => (Array.isArray(labels.data) ? labels.data : []).find((l) => l.name === name)?.id;

  const add = (category?: string) => {
    const labelId = category ? categoryId(category) : undefined;
    open({ kind: 'expense', prefill: labelId ? { label_id: labelId } : undefined, onSaved: () => onSaved() });
  };

  const columns: Column<Entry>[] = [
    { key: 'date', header: t('common.date'), mobile: 'meta', render: (e) => formatDate(e.date, lang, 'short') },
    { key: 'who', header: t('add.payee'), mobile: 'title', render: (e) => e.payee || e.label_name || '—' },
    { key: 'account', header: t('common.account'), mobile: 'subtitle', render: (e) => e.account_name ?? '' },
    { key: 'amount', header: t('add.amount'), align: 'right', numeric: true, mobile: 'value', render: (e) => <Money amount={e.amount} sign="always" /> },
  ];

  return (
    <StepFrame id="first_entries" step={step} onNext={onNext} onBack={onBack}>
      <div className={styles.chips}>
        <Button variant="primary" icon="plus" onClick={() => add()}>
          {t('empezar.agregar_gasto')}
        </Button>
        {CHIPS.map((c) => (
          <Button key={c.key} variant="secondary" onClick={() => add(c.category)}>
            {t(c.key)}
          </Button>
        ))}
      </div>
      {entries.loading ? (
        <Skeleton variant="table" rows={3} what={t('inicio.ultimos')} />
      ) : entries.error ? (
        <ErrorBox error={entries.problem ?? entries.error} onRetry={entries.reload} />
      ) : rows.length > 0 ? (
        <ResponsiveTable columns={columns} rows={rows} rowKey={(e) => e.id} label={t('inicio.ultimos')} />
      ) : null}
    </StepFrame>
  );
}
