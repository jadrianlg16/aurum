'use client';

/**
 * Empezar (`/empezar/`) — the manual-first onboarding wizard.
 *
 * Steps, in order: accounts → income → recurring → first_entries; then the done screen.
 * Progress is `GET /pf/{ws}/onboarding` (computed from what exists, so the wizard is
 * resumable). The active step is `?step=<id>` when valid (read once after mount through
 * `useQueryParam`), else the first step the API reports not done, else the done screen; every
 * step change writes `?step=` back with `replaceState`, so `location.pathname` stays
 * `/empezar/` from start to finish (the shared + Agregar dialog opens over it in step 4).
 *
 * The inline forms are the `AccountForm` / `StreamForm` / `CommitmentForm` exports;
 * their submit is each step's only primary.
 */
import { useCallback, useEffect } from 'react';
import { useAddEntry } from '@/components/AddEntry';
import { DoneScreen } from '@/components/onboarding/DoneScreen';
import { StepAccounts } from '@/components/onboarding/StepAccounts';
import { StepFirstEntries } from '@/components/onboarding/StepFirstEntries';
import { StepFixed } from '@/components/onboarding/StepFixed';
import { StepIncome } from '@/components/onboarding/StepIncome';
import { StepRail } from '@/components/onboarding/StepRail';
import { STEP_ORDER, STEP_VIEWS, firstNotDone, type StepView } from '@/components/onboarding/shared';
import { ErrorBox, PageHeader, Skeleton } from '@/components/ui';
import { getOnboarding } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useQueryParam } from '@/lib/query';
import { useResource } from '@/lib/useResource';
import { WorkspaceGate, useWorkspace } from '@/lib/workspace';

type StepParam = StepView | '';

export default function EmpezarPage() {
  const { t } = useI18n();
  return (
    <>
      <PageHeader title={t('onb.title')} subtitle={t('onb.sub')} />
      <WorkspaceGate fallback={<Skeleton variant="card" rows={2} what={t('onb.title')} />}>
        <Wizard />
      </WorkspaceGate>
    </>
  );
}

function Wizard() {
  const { t } = useI18n();
  const { ws } = useWorkspace();
  const { version } = useAddEntry();
  const [stepParam, setStepParam] = useQueryParam<StepParam>('step', '', STEP_VIEWS as readonly StepParam[]);

  const onboarding = useResource(
    useCallback((signal: AbortSignal) => getOnboarding(ws, { signal }), [ws]),
    [ws, version],
  );
  const steps = onboarding.data?.steps;

  // No (valid) ?step= → the first step not done, written back so the URL says where we are.
  useEffect(() => {
    if (stepParam === '' && steps) setStepParam(firstNotDone(steps));
    // setStepParam is stable per useQueryParam; only the resolution matters here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepParam, steps]);

  const view: StepView | null = stepParam === '' ? null : stepParam;
  const byId = new Map((steps ?? []).map((s) => [s.id, s]));
  const go = (next: StepView) => {
    setStepParam(next);
    if (typeof window !== 'undefined') window.scrollTo({ top: 0 });
  };
  const after = (id: (typeof STEP_ORDER)[number]): StepView => STEP_ORDER[STEP_ORDER.indexOf(id) + 1] ?? 'done';
  const before = (id: (typeof STEP_ORDER)[number]): StepView => STEP_ORDER[STEP_ORDER.indexOf(id) - 1] ?? id;
  const reload = onboarding.reload;

  if (onboarding.error && !onboarding.data) return <ErrorBox error={onboarding.problem ?? onboarding.error} onRetry={reload} />;
  if (view === null) return <Skeleton variant="card" rows={2} what={t('onb.title')} />;

  return (
    <div className="stack">
      <StepRail active={view} steps={steps} />
      {view === 'accounts' && <StepAccounts ws={ws} step={byId.get('accounts')} onSaved={reload} onNext={() => go(after('accounts'))} />}
      {view === 'income' && (
        <StepIncome ws={ws} step={byId.get('income')} onSaved={reload} onNext={() => go(after('income'))} onBack={() => go(before('income'))} />
      )}
      {view === 'recurring' && (
        <StepFixed ws={ws} step={byId.get('recurring')} onSaved={reload} onNext={() => go(after('recurring'))} onBack={() => go(before('recurring'))} />
      )}
      {view === 'first_entries' && (
        <StepFirstEntries
          ws={ws}
          step={byId.get('first_entries')}
          onSaved={reload}
          onNext={() => go('done')}
          onBack={() => go(before('first_entries'))}
        />
      )}
      {view === 'done' && <DoneScreen ws={ws} onSaved={reload} />}
    </div>
  );
}
