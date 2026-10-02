'use client';

/**
 * "Pagos fijos" — a thin wrapper kept for the page and for any older importer. The tab
 * itself lives in `components/money/RecurringList.tsx`; the legacy
 * `toast` prop is accepted and ignored (every new panel uses `components/ui` `useToast`).
 */
import { RecurringList } from './money/RecurringList';

export { CommitmentDialog } from './money/CommitmentForm';

export function MoneySubsPanel({ ws }: { ws: string; toast?: unknown }) {
  return <RecurringList ws={ws} />;
}
