'use client';

/**
 * One occurrence on a small `Dialog`: name, date, amount,
 * status badge, account — and the actions: 'Ya lo pagué' ('Ya llegó' for income) — fixed
 * amount → `markOccurrence(... log_entry)`, variable → `useAddEntry().open` prefilled and then
 * `markOccurrence(entry_id)`; 'Este mes no' → skipped; paid/skipped → 'Deshacer'. `card_*` and
 * `loan` items have no actions. The dialog stays open after a write and reports the result on
 * an in-dialog `role="status"` line; the toast (with Deshacer) shows once it
 * closes. Esc returns focus to the chip/cell that opened it (native dialog contract).
 */
import { useEffect, useState } from 'react';
import { Badge, Button, Dialog, Money } from '@/components/ui';
import { formatDate } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import type { CalendarItem, OccurrenceStatus } from '@/lib/types-organizer';
import { actionLabel, isIncomeKind, primaryAction, signedAmount, statusTone, useOccurrenceActions, type OccTarget } from './shared';
import styles from './money.module.css';

export interface OccurrenceSheetProps {
  ws: string;
  item: CalendarItem | null;
  /** `label_id`/`amount_variable` come from the commitments list, joined by `item.id`. */
  labelId?: string | null;
  amountVariable?: boolean | null;
  onClose: () => void;
  onChanged: () => void;
}

export function displayName(t: (key: MsgKey, vars?: Record<string, string | number>) => string, it: Pick<CalendarItem, 'kind' | 'name'>): string {
  if (it.kind === 'card_cut') return t('money.cal.cut', { name: it.name });
  if (it.kind === 'card_due') return t('money.cal.pay', { name: it.name });
  return it.name;
}

export function OccurrenceSheet({ ws, item, labelId, amountVariable, onClose, onChanged }: OccurrenceSheetProps) {
  const { t, lang } = useI18n();
  const [status, setStatus] = useState<string | null>(null);
  const actions = useOccurrenceActions(ws, { onDone: onChanged, onStatus: setStatus });

  // Fresh status line per item.
  useEffect(() => {
    setStatus(null);
    actions.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item?.id, item?.date]);

  const actionable = item !== null && (item.kind === 'commitment' || item.kind === 'income');
  const target: OccTarget | null = item
    ? {
        commitment_id: item.id,
        due: item.date,
        name: item.name,
        amount: item.amount,
        kind: item.kind === 'income' ? 'income' : item.commitment_kind ?? 'bill',
        status: item.status,
        amount_variable: amountVariable ?? item.amount_variable,
        account_id: item.account_id,
        label_id: labelId ?? null,
        entry_id: item.entry_id,
      }
    : null;
  const effective: OccurrenceStatus | null = target ? actions.overrides[`${target.commitment_id}|${target.due}`] ?? target.status : null;
  const primary = target && effective ? primaryAction({ ...target, status: effective }) : null;
  const busy = actions.busy !== null;
  const income = isIncomeKind(target?.kind);

  return (
    <Dialog open={item !== null} onClose={onClose} title={item ? displayName(t, item) : ''} size="sm">
      {item && target && effective && (
        <div className={styles.occ}>
          <div className={styles.occFacts}>
            <span>{formatDate(item.date, lang)}</span>
            <Badge tone={statusTone(effective)}>{t(`money.occ.${effective}` as MsgKey)}</Badge>
          </div>
          <div className={styles.occAmount}>
            <Money amount={signedAmount(item.kind === 'income' ? 'income' : 'commitment', item.amount)} sign={income ? 'always' : 'auto'} />
          </div>
          {item.account_name && (
            <div className={styles.noticeMeta}>
              {t('money.occ.account')}: {item.account_name}
            </div>
          )}
          <p className={styles.status} role="status" aria-live="polite">
            {status ?? ''}
          </p>
          {actionable ? (
            <div className={styles.actions}>
              {primary === 'undo' ? (
                <Button variant="secondary" onClick={() => actions.run('undo', { ...target, status: effective })} loading={busy}>
                  {t('common.undo')}
                </Button>
              ) : (
                <>
                  <Button
                    variant="primary"
                    onClick={() => actions.run(primary ?? 'register', { ...target, status: effective })}
                    loading={busy}
                  >
                    {primary === 'arrived' ? t('money.occ.arrived') : primary === 'register' ? t('money.action.register') : t('money.occ.paid_now')}
                  </Button>
                  {!income && (
                    <Button variant="ghost" onClick={() => actions.run('skip', { ...target, status: effective })} disabled={busy}>
                      {actionLabel(t, 'skip')}
                    </Button>
                  )}
                </>
              )}
            </div>
          ) : (
            <p className={styles.noticeMeta}>{t('money.occ.no_actions')}</p>
          )}
        </div>
      )}
    </Dialog>
  );
}
