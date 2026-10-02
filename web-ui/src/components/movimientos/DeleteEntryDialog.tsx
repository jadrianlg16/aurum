'use client';

/**
 * "¿Borrar este movimiento?" — the one confirm used by the Agregar dialog (edit mode) and by
 * the Movimientos row menu. The body names the thing with its
 * formatted amount and date; confirming voids the row (`DELETE /entries/{id}`) and hands
 * control back so the caller can close whatever is open and then toast "Movimiento borrado ·
 * Deshacer" (entryToast.ts). A failed delete is reported through the same toast channel.
 */
import { useState } from 'react';
import { deleteEntry, errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import type { Entry } from '@/lib/types-personal';
import { ConfirmDialog, useToast } from '@/components/ui';
import { useEntryToast } from './entryToast';
import { useOpenAfterMount } from './useOpenAfterMount';

export function DeleteEntryDialog({
  ws,
  entry,
  bump,
  onDone,
  onCancel,
}: {
  ws: string;
  entry: Entry;
  bump: () => void;
  /** Called after the row was voided (before the toast) so the caller can close its dialog. */
  onDone: () => void;
  onCancel: () => void;
}) {
  const { t, lang } = useI18n();
  const { fmt } = useMoney();
  const toast = useToast();
  const entryToast = useEntryToast();
  const [busy, setBusy] = useState(false);
  const shown = useOpenAfterMount();

  const confirm = async () => {
    setBusy(true);
    try {
      await deleteEntry(ws, entry.id);
      onDone();
      entryToast.deleted(ws, entry, bump);
      bump();
    } catch (e) {
      onCancel();
      toast.error(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const body = t('txn.delete.body', {
    kind: t(`txn.kind.${entry.kind}`),
    amount: fmt(entry.amount),
    payee: entry.payee?.trim() || '—',
    date: formatDate(entry.date, lang, 'medium'),
  });

  return (
    <ConfirmDialog
      open={shown}
      title={t('txn.delete.confirm')}
      body={<p>{body}</p>}
      confirmLabel={t('form.delete')}
      destructive
      busy={busy}
      onConfirm={() => void confirm()}
      onCancel={onCancel}
    />
  );
}
