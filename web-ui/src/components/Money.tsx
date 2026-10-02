'use client';

/**
 * "Mi dinero" — the badge shims other screens still import (`KindBadge`, `StatusBadge`,
 * `OccDot`, `CadenceText`) and the `MoneySummaryPanel` wrapper over `money/Summary.tsx`.
 *
 * No money math anywhere: every figure is a decimal string the API produced.
 */
import { Summary } from './money/Summary';
import { useI18n, type MsgKey } from '@/lib/i18n';
import type { CommitmentKind, CommitmentStatus, OccurrenceStatus } from '@/lib/types-organizer';

/* ---------------------------------------------------------------- badges -- */

const KIND_CLASS: Record<CommitmentKind, string> = {
  subscription: 'badge gold',
  bill: 'badge neutral',
  utility: 'badge neutral',
  rent: 'badge info',
  insurance: 'badge info',
  loan_payment: 'badge warn',
  tax: 'badge warn',
  income: 'badge pos',
  transfer: 'badge neutral',
  other: 'badge neutral',
};

export function KindBadge({ kind }: { kind: CommitmentKind }) {
  const { t } = useI18n();
  return <span className={KIND_CLASS[kind] ?? 'badge neutral'}>{t(`money.kind.${kind}` as MsgKey)}</span>;
}

const STATUS_CLASS: Record<CommitmentStatus, string> = {
  active: 'badge pos',
  paused: 'badge neutral',
  cancelled: 'badge neg',
  trial: 'badge warn',
};

export function StatusBadge({ status }: { status: CommitmentStatus }) {
  const { t } = useI18n();
  return <span className={STATUS_CLASS[status] ?? 'badge neutral'}>{t(`money.status.${status}` as MsgKey)}</span>;
}

/** The paid/unpaid dot the calendar and the "next 7 days" list share. */
export function OccDot({ status }: { status: OccurrenceStatus }) {
  const { t } = useI18n();
  return (
    <span
      className={`occ-dot ${status}`}
      role="img"
      aria-label={t(`money.occ.${status}` as MsgKey)}
      title={t(`money.occ.${status}` as MsgKey)}
    />
  );
}

export function CadenceText({ cadence }: { cadence: string }) {
  const { t } = useI18n();
  return <>{t(`money.cadence.${cadence}` as MsgKey)}</>;
}

/* --------------------------------------------------------------- resumen -- */

/**
 * Resumen lives in `money/Summary.tsx`; this wrapper keeps the
 * original export name and ignores the legacy `onGoTo` prop.
 */
export function MoneySummaryPanel({ ws }: { ws: string; onGoTo?: (tab: 'subs' | 'calendar' | 'plan' | 'setup') => void }) {
  return <Summary ws={ws} />;
}
