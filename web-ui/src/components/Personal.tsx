'use client';

/**
 * Helper kept for the onboarding step (`onboarding/StepAccounts.tsx`). The account and income
 * forms live in `components/cuentas/**` and `components/ingresos/**`.
 */
import type { PfAccountType } from '@/lib/types-personal';

export function accountTypeKey(type: PfAccountType) {
  return `acct.type.${type}` as const;
}
