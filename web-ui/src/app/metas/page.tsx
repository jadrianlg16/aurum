'use client';

/**
 * `/metas/` — goals. One request, `GET /pf/{ws}/goals`, reloaded
 * after every write here and after any + Agregar save (`useAddEntry().version`), because a
 * contribution is an ordinary transfer and the server recomputes `progress`/`pct` from the
 * account balance. Cards are `GoalCard`; create/edit is `GoalDialog`; delete confirms and
 * reloads (no undo — only entries, mark paid, account archive and commitment cancel have one).
 */
import { useCallback, useState } from 'react';
import { useAddEntry } from '@/components/AddEntry';
import { GoalCard } from '@/components/plan/GoalCard';
import { GoalDialog, type GoalTemplate } from '@/components/plan/GoalDialog';
import { Button, ConfirmDialog, EmptyState, ErrorBox, PageHeader, Skeleton, useToast } from '@/components/ui';
import { deleteGoal, errorMessage, listGoals } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { Goal } from '@/lib/types';

export default function MetasPage() {
  const { t } = useI18n();
  const { ws } = useWorkspace();
  const toast = useToast();
  const { version } = useAddEntry();

  const goals = useResource(useCallback(() => listGoals(ws), [ws]), [ws, version]);
  const [form, setForm] = useState<{ goal: Goal | null; template?: GoalTemplate } | null>(null);
  const [confirm, setConfirm] = useState<Goal | null>(null);
  const [busy, setBusy] = useState(false);

  const remove = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      await deleteGoal(ws, confirm.id);
      setConfirm(null);
      toast.success(t('goal.deleted'));
      goals.reload();
    } catch (e) {
      setConfirm(null);
      toast.error(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const rows = goals.data ?? [];

  return (
    <>
      <PageHeader
        title={t('goal.title')}
        subtitle={t('goal.sub')}
        actions={
          <Button variant="secondary" icon="plus" data-testid="goal-new" onClick={() => setForm({ goal: null })}>
            {t('goal.new')}
          </Button>
        }
      />

      {goals.loading ? (
        <Skeleton variant="card" rows={2} what={t('goal.title')} />
      ) : goals.error && !goals.data ? (
        <ErrorBox error={goals.problem ?? goals.error} onRetry={goals.reload} />
      ) : rows.length === 0 ? (
        <div className="stack">
          <EmptyState
            icon="target"
            title={t('goal.empty.title')}
            body={t('goal.empty.body')}
            primary={{ label: t('goal.empty.cta'), onClick: () => setForm({ goal: null }) }}
          />
          <div className="row">
            <Button variant="secondary" size="sm" onClick={() => setForm({ goal: null, template: 'emergency' })}>
              {t('goal.template.emergency')}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setForm({ goal: null, template: 'trip' })}>
              {t('goal.template.trip')}
            </Button>
          </div>
        </div>
      ) : (
        <div className="stack">
          {goals.error && <ErrorBox error={goals.problem ?? goals.error} onRetry={goals.reload} />}
          <div className="grid cols-2" aria-busy={goals.refreshing || undefined} aria-label={t('goal.list')}>
            {rows.map((g) => (
              <GoalCard
                key={g.id}
                ws={ws}
                goal={g}
                onEdit={() => setForm({ goal: g })}
                onDelete={() => setConfirm(g)}
                onChanged={goals.reload}
              />
            ))}
          </div>
        </div>
      )}

      {form && (
        <GoalDialog
          ws={ws}
          goal={form.goal}
          template={form.template}
          onClose={(saved) => {
            setForm(null);
            if (saved) goals.reload();
          }}
        />
      )}
      {confirm && (
        <ConfirmDialog
          title={t('goal.delete.title', { name: confirm.name })}
          body={<p>{t('goal.delete.body')}</p>}
          confirmLabel={t('goal.delete')}
          destructive
          busy={busy}
          onConfirm={() => void remove()}
          onCancel={() => setConfirm(null)}
        />
      )}
    </>
  );
}
