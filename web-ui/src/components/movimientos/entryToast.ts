'use client';

/**
 * The toasts every movement write shares:
 *
 *   saved    "Guardado · −$250.00 · Comida fuera" + Deshacer (= DELETE the row → bump)
 *   deleted  "Movimiento borrado" + Deshacer (= POST the same fields again as a manual row)
 *
 * Used by the "+ Agregar" dialog, the Movimientos row actions and Captura rápida. `bump` is the
 * caller's `useAddEntry().bump` (passed in, not imported, so this file never depends on the
 * dialog module). Toasts requested while a `<dialog>` is open are held by ToastProvider until it
 * closes — callers close first, then toast.
 */
import { useCallback, useMemo } from 'react';
import { createEntry, deleteEntry, errorMessage } from '@/lib/api';
import { useI18n, useMoney } from '@/lib/i18n';
import type { Entry, EntryInput } from '@/lib/types-personal';
import { useToast } from '@/components/ui';

/** The body a voided row would need to come back as a fresh manual movement (undo of delete). */
export function restoreInput(e: Entry): EntryInput {
  return {
    kind: e.kind,
    date: e.date,
    amount: { amount: e.amount.amount.replace(/^-/, ''), currency: e.amount.currency },
    account_id: e.account_id ?? '',
    to_account_id: e.to_account_id ?? null,
    label_id: e.label_id ?? null,
    payee: e.payee ?? null,
    note: e.note ?? null,
    tags: e.tags ?? [],
    splits: e.splits && e.splits.length > 0 ? e.splits.map((s) => ({ label_id: s.label_id, amount: s.amount, note: s.note ?? null })) : null,
    // A restored row is a new manual movement: the Mi dinero link is not carried over.
  };
}

export interface EntryToastApi {
  /** `Guardado · −$250.00 · Comida fuera`, exactly what the toast shows. */
  savedMessage: (entry: Entry) => string;
  saved: (ws: string, entry: Entry, bump: () => void) => void;
  deleted: (ws: string, entry: Entry, bump: () => void) => void;
}

export function useEntryToast(): EntryToastApi {
  const { t } = useI18n();
  const { fmt } = useMoney();
  const toast = useToast();

  const savedMessage = useCallback(
    (entry: Entry) => {
      const amount = fmt(entry.amount, { sign: 'always' });
      return `${t('add.toast.saved')} · ${amount}${entry.label_name ? ` · ${entry.label_name}` : ''}`;
    },
    [fmt, t],
  );

  const saved = useCallback(
    (ws: string, entry: Entry, bump: () => void) => {
      toast.success(savedMessage(entry), {
        action: {
          label: t('common.undo'),
          onClick: () => {
            deleteEntry(ws, entry.id)
              .then(() => {
                bump();
                toast.info(t('add.toast.undone'));
              })
              .catch((e: unknown) => toast.error(errorMessage(e, t)));
          },
        },
      });
    },
    [savedMessage, t, toast],
  );

  const deleted = useCallback(
    (ws: string, entry: Entry, bump: () => void) => {
      toast.success(t('txn.deleted'), {
        action: {
          label: t('common.undo'),
          onClick: () => {
            createEntry(ws, restoreInput(entry))
              .then(() => {
                bump();
                toast.success(t('txn.restored'));
              })
              .catch((e: unknown) => toast.error(errorMessage(e, t)));
          },
        },
      });
    },
    [t, toast],
  );

  return useMemo(() => ({ savedMessage, saved, deleted }), [savedMessage, saved, deleted]);
}
