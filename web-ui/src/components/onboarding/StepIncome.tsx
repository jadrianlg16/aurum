'use client';

/**
 * Step 2 — income: template chips (quincenal 15 y 30 / mensual /
 * freelance) and the inline `StreamForm` keyed by the chosen template. A save toasts,
 * reloads the onboarding status, never auto-advances.
 */
import { useState } from 'react';
import { StreamForm } from '@/components/ingresos/StreamForm';
import { Button, useToast } from '@/components/ui';
import { useI18n } from '@/lib/i18n';
import type { OnboardingStep } from '@/lib/types-personal';
import { StepFrame } from './shared';
import styles from './onboarding.module.css';

type Template = 'salary_semimonthly' | 'salary_monthly' | 'freelance';

const TEMPLATES: { id: Template; key: 'empezar.tpl.quincenal' | 'empezar.tpl.mensual' | 'empezar.tpl.freelance' }[] = [
  { id: 'salary_semimonthly', key: 'empezar.tpl.quincenal' },
  { id: 'salary_monthly', key: 'empezar.tpl.mensual' },
  { id: 'freelance', key: 'empezar.tpl.freelance' },
];

export function StepIncome({
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
  const { t } = useI18n();
  const toast = useToast();
  const [template, setTemplate] = useState<Template>('salary_semimonthly');

  return (
    <StepFrame id="income" step={step} onNext={onNext} onBack={onBack}>
      <div className={styles.chips} role="group" aria-label={t('empezar.plantillas')}>
        {TEMPLATES.map((tpl) => (
          <Button key={tpl.id} variant="secondary" aria-pressed={template === tpl.id} onClick={() => setTemplate(tpl.id)}>
            {t(tpl.key)}
          </Button>
        ))}
      </div>
      <div className={styles.form}>
        <StreamForm
          key={template}
          ws={ws}
          inline
          template={template}
          onSaved={() => {
            toast.success(t('inc.saved'));
            onSaved();
          }}
        />
      </div>
    </StepFrame>
  );
}
