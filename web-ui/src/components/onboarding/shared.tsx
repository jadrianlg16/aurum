'use client';

/**
 * Shared bits of the /empezar/ wizard: the step order, the
 * title/hint keys per step, the `?step=` value set, and the step frame (title, hint, "Ya tienes
 * n", the body, the footer).
 */
import { useId, type ReactNode } from 'react';
import { Button } from '@/components/ui';
import { useI18n } from '@/lib/i18n';
import type { OnboardingStep, OnboardingStepKey } from '@/lib/types-personal';
import styles from './onboarding.module.css';

export const STEP_ORDER = ['accounts', 'income', 'recurring', 'first_entries'] as const satisfies readonly OnboardingStepKey[];
export type StepView = OnboardingStepKey | 'done';
/** Everything `?step=` may carry: the four onboarding step ids plus the done screen. */
export const STEP_VIEWS: readonly StepView[] = [...STEP_ORDER, 'done'];

export const STEP_TITLE_KEY = {
  accounts: 'onb.step.accounts',
  income: 'onb.step.income',
  recurring: 'onb.step.recurring',
  first_entries: 'empezar.step.first_entries',
} as const;

export const STEP_HINT_KEY = {
  accounts: 'onb.step.accounts.hint',
  income: 'onb.step.income.hint',
  recurring: 'onb.step.recurring.hint',
  first_entries: 'empezar.step.first_entries.hint',
} as const;

export function stepIndex(id: OnboardingStepKey): number {
  return STEP_ORDER.indexOf(id);
}

export function firstNotDone(steps: OnboardingStep[] | undefined): StepView {
  const byId = new Map((steps ?? []).map((s) => [s.id, s]));
  return STEP_ORDER.find((id) => !(byId.get(id)?.done ?? false)) ?? 'done';
}

/**
 * The frame every step shares. The inline form's submit is the step's only
 * primary, so the footer is `common.next` as secondary + "Lo hago después" as ghost (both
 * advance) and `common.back` as ghost from step 2 on.
 */
export function StepFrame({
  id,
  step,
  children,
  onNext,
  onBack,
}: {
  id: OnboardingStepKey;
  step: OnboardingStep | undefined;
  children: ReactNode;
  onNext: () => void;
  onBack?: () => void;
}) {
  const { t } = useI18n();
  const headingId = useId();
  const n = stepIndex(id) + 1;
  const count = typeof step?.count === 'number' ? step.count : 0;
  return (
    <section className={['card', styles.step].join(' ')} aria-labelledby={headingId}>
      <p className={styles.progress}>{t('empezar.paso', { n, total: STEP_ORDER.length })}</p>
      <h2 id={headingId}>{t(STEP_TITLE_KEY[id])}</h2>
      <p className="muted">{t(STEP_HINT_KEY[id])}</p>
      {count > 0 && <p className={styles.have}>{t('empezar.ya_tienes', { n: count })}</p>}
      <div className={styles.body}>{children}</div>
      <div className={styles.footer}>
        {onBack && (
          <Button variant="ghost" onClick={onBack}>
            {t('common.back')}
          </Button>
        )}
        <span className={styles.footerRight}>
          <Button variant="ghost" onClick={onNext}>
            {t('onb.import.skip')}
          </Button>
          <Button variant="secondary" onClick={onNext}>
            {t('common.next')}
          </Button>
        </span>
      </div>
    </section>
  );
}
