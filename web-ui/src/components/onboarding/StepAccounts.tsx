'use client';

/**
 * Step 1 — accounts. What already exists (`GET /pf/{ws}/accounts`
 * rows: name · type · balance) and the inline `AccountForm`; a save toasts, reloads the
 * onboarding status and the list, and never auto-advances. A failed list is an inline ErrorBox
 * (the form stays usable); a row without a balance shows no figure (no invented currency).
 */
import { useCallback } from 'react';
import { AccountForm } from '@/components/cuentas/AccountForm';
import { accountTypeKey } from '@/components/Personal';
import { ErrorBox, Money, Skeleton, useToast } from '@/components/ui';
import { listPfAccounts } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import type { OnboardingStep } from '@/lib/types-personal';
import { StepFrame } from './shared';
import styles from './onboarding.module.css';

export function StepAccounts({
  ws,
  step,
  onSaved,
  onNext,
}: {
  ws: string;
  step: OnboardingStep | undefined;
  onSaved: () => void;
  onNext: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const accounts = useResource(
    useCallback((signal: AbortSignal) => listPfAccounts(ws, {}, { signal }), [ws]),
    [ws, step?.count],
  );
  const rows = (accounts.data ?? []).filter((a) => !a.archived);

  return (
    <StepFrame id="accounts" step={step} onNext={onNext}>
      {accounts.loading ? (
        <Skeleton variant="list" rows={2} what={t('nav.cuentas')} />
      ) : accounts.error ? (
        <ErrorBox error={accounts.problem ?? accounts.error} onRetry={accounts.reload} />
      ) : rows.length > 0 ? (
        <ul className={styles.list} aria-label={t('nav.cuentas')}>
          {rows.map((a) => {
            const balance = a.balance_signed ?? a.balance ?? null;
            return (
              <li key={a.id}>
                <span>
                  <strong>{a.name}</strong> <span className="muted">· {t(accountTypeKey(a.type))}</span>
                </span>
                {balance && <Money amount={balance} sign="auto" />}
              </li>
            );
          })}
        </ul>
      ) : null}
      <div className={styles.form}>
        <AccountForm
          ws={ws}
          inline
          onSaved={() => {
            toast.success(t('acct.saved'));
            accounts.reload();
            onSaved();
          }}
        />
      </div>
    </StepFrame>
  );
}
