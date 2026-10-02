'use client';

/**
 * The step rail: numbers + titles, `aria-current="step"` on the
 * active one, a tick on the ones the API reports done. Non-interactive: the footer buttons
 * move between steps, so no tap target smaller than 44px lives here.
 */
import { Icon } from '@/components/ui';
import { useI18n } from '@/lib/i18n';
import type { OnboardingStep } from '@/lib/types-personal';
import { STEP_ORDER, STEP_TITLE_KEY, type StepView } from './shared';
import styles from './onboarding.module.css';

export function StepRail({ active, steps }: { active: StepView; steps: OnboardingStep[] | undefined }) {
  const { t } = useI18n();
  const byId = new Map((steps ?? []).map((s) => [s.id, s]));
  return (
    <nav aria-label={t('empezar.pasos')}>
      <ol className={styles.rail}>
        {STEP_ORDER.map((id, i) => {
          const done = byId.get(id)?.done ?? false;
          return (
            <li key={id} className={done ? styles.done : undefined} aria-current={active === id ? 'step' : undefined}>
              <span className={styles.num} aria-hidden="true">
                {done ? <Icon name="check" size={12} /> : i + 1}
              </span>
              <span>{t(STEP_TITLE_KEY[id])}</span>
              {done && <span className="sr-only">{t('onb.done')}</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
