'use client';

/**
 * Step 3 — fixed payments: chips that pre-select
 * `initial = {name, kind}` on the inline `CommitmentForm` — Renta → rent, Luz/Internet →
 * utility, Streaming → subscription, Tarjeta → loan_payment ("Préstamo o tarjeta"). The
 * "o busca en mi estado de cuenta" shortcut only in advanced mode. Never auto-advances.
 */
import Link from 'next/link';
import { useState } from 'react';
import { CommitmentForm } from '@/components/money/CommitmentForm';
import { Button, useToast } from '@/components/ui';
import { useI18n } from '@/lib/i18n';
import type { CommitmentInput } from '@/lib/types-organizer';
import type { OnboardingStep } from '@/lib/types-personal';
import { useAdvanced } from '@/lib/workspace';
import { StepFrame } from './shared';
import styles from './onboarding.module.css';

type ChipKey = 'empezar.tpl.renta' | 'empezar.tpl.luz' | 'empezar.tpl.internet' | 'empezar.tpl.streaming' | 'empezar.tpl.tarjeta';

const CHIPS: { id: string; key: ChipKey; kind: CommitmentInput['kind'] }[] = [
  { id: 'renta', key: 'empezar.tpl.renta', kind: 'rent' },
  { id: 'luz', key: 'empezar.tpl.luz', kind: 'utility' },
  { id: 'internet', key: 'empezar.tpl.internet', kind: 'utility' },
  { id: 'streaming', key: 'empezar.tpl.streaming', kind: 'subscription' },
  { id: 'tarjeta', key: 'empezar.tpl.tarjeta', kind: 'loan_payment' },
];

export function StepFixed({
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
  const advanced = useAdvanced();
  const [chip, setChip] = useState<string | null>(null);
  const picked = CHIPS.find((c) => c.id === chip);
  const initial: Partial<CommitmentInput> | undefined = picked ? { name: t(picked.key), kind: picked.kind } : undefined;

  return (
    <StepFrame id="recurring" step={step} onNext={onNext} onBack={onBack}>
      <div className={styles.chips} role="group" aria-label={t('empezar.plantillas')}>
        {CHIPS.map((c) => (
          <Button key={c.id} variant="secondary" aria-pressed={chip === c.id} onClick={() => setChip(c.id)}>
            {t(c.key)}
          </Button>
        ))}
      </div>
      <div className={styles.form}>
        <CommitmentForm
          key={chip ?? 'none'}
          ws={ws}
          inline
          initial={initial}
          onSaved={() => {
            toast.success(t('empezar.pago_guardado'));
            onSaved();
          }}
        />
      </div>
      {advanced && (
        <p className="small muted">
          <Link href="/money/?tab=setup">{t('onb.secondary.detect')}</Link> · {t('onb.secondary.note')}
        </p>
      )}
    </StepFrame>
  );
}
