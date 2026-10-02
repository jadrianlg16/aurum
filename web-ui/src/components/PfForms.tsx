'use client';

/**
 * Legacy home of the pf write forms, which now live elsewhere:
 *
 * - budgets → `components/plan/BudgetDialog.tsx` (used by `/presupuesto/`),
 * - goals → `components/plan/GoalDialog.tsx` (used by `/metas/`),
 * - labels → `components/settings/CategoryDialog.tsx` (Ajustes › Categorías),
 * - cards / MSI / loans / scores → `components/plan/CreditDialogs.tsx` (re-exported below so
 *   the old import path keeps resolving).
 *
 * What stays here is `ConfirmDelete`, the yes/no used by the credit tab for scores (it still
 * accepts the other kinds so no importer breaks), now on the `ui/ConfirmDialog` primitive.
 */
import { useState } from 'react';
import { ConfirmDialog, useToast } from '@/components/ui';
import { deleteBudget, deleteGoal, deleteLabel, deleteScore, errorMessage } from '@/lib/api';
import { useI18n } from '@/lib/i18n';

export { CardDialog, LoanDialog, MsiDialog, ScoreDialog } from './plan/CreditDialogs';

export function ConfirmDelete({
  what,
  ws,
  kind,
  id,
  onClose,
}: {
  what: string;
  ws: string;
  kind: 'goal' | 'budget' | 'label' | 'score';
  id: string;
  onClose: (saved: boolean) => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const call = () => {
    if (kind === 'goal') return deleteGoal(ws, id);
    if (kind === 'budget') return deleteBudget(ws, id);
    if (kind === 'label') return deleteLabel(ws, id);
    return deleteScore(ws, id);
  };
  const confirm = async () => {
    setBusy(true);
    try {
      await call();
      onClose(true);
      toast.success(kind === 'score' ? t('score.deleted') : t('common.saved'));
    } catch (e) {
      onClose(false);
      toast.error(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };
  const title =
    kind === 'score'
      ? t('score.delete.title', { name: what })
      : kind === 'goal'
        ? t('goal.delete.title', { name: what })
        : kind === 'budget'
          ? t('budget.delete.title', { name: what })
          : t('cat.delete.title', { name: what });
  return (
    <ConfirmDialog
      title={title}
      confirmLabel={t('score.delete')}
      destructive
      busy={busy}
      onConfirm={() => void confirm()}
      onCancel={() => onClose(false)}
    />
  );
}
