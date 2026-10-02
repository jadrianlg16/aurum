'use client';

/**
 * Empty workspace: rendered when `GET /pf/{ws}/accounts` has zero
 * rows. One EmptyState "Empieza aquí" plus the `GET /pf/{ws}/onboarding` checklist (tick when
 * done, count shown); the primary goes to `/empezar/?step=<first not done>` and the secondary
 * switches to the demo workspace through the provider (`setWs`, persisted) — never a
 * `?ws=` link, which the provider reads only once at mount and ignores on a client-side
 * navigation. No demo workspace listed → no secondary. No hero, no cards, no other request.
 */
import Link from 'next/link';
import { useCallback } from 'react';
import { EmptyState, ErrorBox, Icon, Skeleton } from '@/components/ui';
import { getOnboarding } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import type { OnboardingStepKey } from '@/lib/types-personal';
import type { Workspace } from '@/lib/types';
import { useWorkspace } from '@/lib/workspace';
import styles from './home.module.css';

export const STEP_ORDER = ['accounts', 'income', 'recurring', 'first_entries'] as const satisfies readonly OnboardingStepKey[];

export const STEP_TITLE_KEY = {
  accounts: 'onb.step.accounts',
  income: 'onb.step.income',
  recurring: 'onb.step.recurring',
  first_entries: 'empezar.step.first_entries',
} as const;

export const DEMO_WS_ID = 'demo-personal';

/** The demo to show: `demo-personal` when listed, else the first personal demo, else none. */
export function pickDemoWorkspace(list: Workspace[]): Workspace | null {
  return (
    list.find((w) => w.id === DEMO_WS_ID) ??
    list.find((w) => w.kind === 'personal' && w.profile?.demo === true && !w.hidden) ??
    null
  );
}

export function StartHere({ ws }: { ws: string }) {
  const { t } = useI18n();
  const { workspaces, setWs } = useWorkspace();
  const demo = pickDemoWorkspace(workspaces);
  const onboarding = useResource(
    useCallback((signal: AbortSignal) => getOnboarding(ws, { signal }), [ws]),
    [ws],
  );
  const steps = onboarding.data?.steps ?? [];
  const byId = new Map(steps.map((s) => [s.id, s]));
  const first = STEP_ORDER.find((id) => !(byId.get(id)?.done ?? false)) ?? STEP_ORDER[0];

  return (
    <div className="card">
      <EmptyState
        icon="home"
        title={t('inicio.empieza')}
        body={t('inicio.vacio.cuerpo')}
        primary={{ label: t('inicio.empieza.cta'), href: `/empezar/?step=${first}` }}
        secondary={demo ? { label: t('inicio.ver_demo'), onClick: () => setWs(demo.id) } : undefined}
      />
      {onboarding.loading ? (
        <Skeleton variant="list" rows={4} what={t('onb.title')} />
      ) : onboarding.error ? (
        <ErrorBox error={onboarding.problem ?? onboarding.error} onRetry={onboarding.reload} />
      ) : (
        <ol className={styles.checklist} aria-label={t('empezar.pasos')}>
          {STEP_ORDER.map((id, i) => {
            const step = byId.get(id);
            const done = step?.done ?? false;
            return (
              <li key={id} className={done ? styles.done : undefined}>
                <span className={styles.checkNum} aria-hidden="true">
                  {done ? <Icon name="check" size={14} /> : i + 1}
                </span>
                <Link href={`/empezar/?step=${id}`}>{t(STEP_TITLE_KEY[id])}</Link>
                {typeof step?.count === 'number' && step.count > 0 && <span className="muted">· {step.count}</span>}
                {done && <span className="sr-only">{t('onb.done')}</span>}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
