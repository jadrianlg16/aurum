'use client';

/**
 * The row drawer of Pagos fijos: `GET /commitments/{id}` on a `Sheet`
 * — amount / cadence / next payment, the last occurrences, the price history, the linked-loan
 * progress (server keys: payment, total_paid, total_interest, months, payments_seen,
 * balance_after_seen) and the actions: Editar, Pausar | Reanudar, Cancelar (ConfirmDialog with
 * the cancel note), Borrar (ConfirmDialog). `window.confirm` is gone.
 */
import { useCallback, useState } from 'react';
import { Explain } from '@/components/Explain';
import { Badge, Button, ConfirmDialog, ErrorBox, Field, Money, Sheet, Skeleton, Textarea, useToast } from '@/components/ui';
import { cancelCommitment, deleteCommitment, errorMessage, getCommitment, pauseCommitment, resumeCommitment } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n, useMoney, type MsgKey } from '@/lib/i18n';
import type { Amount, Explain as ExplainModel } from '@/lib/types';
import type { Commitment, CommitmentDetail } from '@/lib/types-organizer';
import { useResource } from '@/lib/useResource';
import { OccDot, StatusBadge } from '../Money';
import { cadenceText, statusTone } from './shared';
import styles from './money.module.css';

/** What `router.py` actually returns for a linked loan (types-organizer `LoanProgress` is an older guess). */
interface ServerLoan {
  loan_id?: string;
  payment?: Amount | string | null;
  total_paid?: Amount | string | null;
  total_interest?: Amount | string | null;
  months?: number | null;
  payments_seen?: number | null;
  balance_after_seen?: Amount | string | null;
  explain?: ExplainModel | null;
}

const asAmount = (v: Amount | string | null | undefined, currency: string): Amount | null =>
  v == null ? null : typeof v === 'string' ? { amount: v, currency } : v;

export interface CommitmentDrawerProps {
  ws: string;
  id: string | null;
  onClose: () => void;
  onChanged: () => void;
  onEdit: (c: Commitment) => void;
}

export function CommitmentDrawer({ ws, id, onClose, onChanged, onEdit }: CommitmentDrawerProps) {
  const { t, lang } = useI18n();
  const { base } = useMoney();
  const toast = useToast();
  const detail = useResource<CommitmentDetail | null>(
    useCallback(() => (id ? getCommitment(ws, id) : Promise.resolve(null)), [ws, id]),
    [ws, id],
    { keepPrevious: false },
  );
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<'cancel' | 'delete' | null>(null);
  const [cancelNote, setCancelNote] = useState('');

  const c = detail.data;

  const act = async (fn: () => Promise<unknown>, message: string, closeAfter = false) => {
    setBusy(true);
    try {
      await fn();
      if (closeAfter) {
        onClose();
        toast.success(message);
      } else {
        toast.success(message);
        detail.reload();
      }
      onChanged();
    } catch (e) {
      toast.error(errorMessage(e, t));
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  const loan = (c?.loan ?? null) as ServerLoan | null;
  // Bare-string loan figures take the commitment's currency, else the workspace base currency.
  const currency = c?.amount.currency ?? base;

  return (
    <>
      <Sheet open={id !== null} onClose={onClose} title={c?.name ?? t('money.fixed.list')}>
        {detail.loading || !id ? (
          <Skeleton variant="card" rows={3} what={t('money.fixed.list')} />
        ) : detail.error ? (
          <ErrorBox error={detail.problem ?? detail.error} onRetry={detail.reload} />
        ) : !c ? null : (
          <div className={styles.drawer}>
            <div className={styles.drawerHead}>
              <Badge tone="accent">{t(`money.kind.${c.kind}` as MsgKey)}</Badge>
              <StatusBadge status={c.status} />
              {c.essential && <Badge tone="neutral">{t(`money.essential.${c.essential}` as MsgKey)}</Badge>}
            </div>

            <div className={styles.facts}>
              <div className={styles.fact}>
                <span className={styles.factLabel}>{t('money.drawer.amount')}</span>
                <span className={styles.factValue}>
                  <Money amount={c.amount} />
                </span>
              </div>
              <div className={styles.fact}>
                <span className={styles.factLabel}>{t('money.drawer.every')}</span>
                <span>{cadenceText(t, c, lang)}</span>
              </div>
              <div className={styles.fact}>
                <span className={styles.factLabel}>{t('money.drawer.next')}</span>
                <span>{formatDate(c.next_due, lang)}</span>
              </div>
              <div className={styles.fact}>
                <span className={styles.factLabel}>{t('money.col.account')}</span>
                <span>{c.account_name ?? '—'}</span>
              </div>
            </div>

            {c.trial_ends && <p className="banner warn">{t('money.drawer.trial', { date: formatDate(c.trial_ends, lang) })}</p>}

            <div className={styles.actions}>
              <Button onClick={() => onEdit(c)} disabled={busy}>
                {t('common.edit')}
              </Button>
              {c.status === 'paused' ? (
                <Button onClick={() => void act(() => resumeCommitment(ws, c.id), t('money.fixed.resumed'))} disabled={busy}>
                  {t('money.resume')}
                </Button>
              ) : (
                <Button
                  onClick={() => void act(() => pauseCommitment(ws, c.id), t('money.fixed.paused'))}
                  disabled={busy || c.status === 'cancelled'}
                >
                  {t('money.pause')}
                </Button>
              )}
              <Button onClick={() => setConfirm('cancel')} disabled={busy || c.status === 'cancelled'}>
                {t('money.cancel_sub')}
              </Button>
              <span className={styles.grow} />
              <Button variant="ghost" onClick={() => setConfirm('delete')} disabled={busy}>
                {t('money.drawer.delete')}
              </Button>
            </div>

            <section className={styles.section} aria-label={t('money.drawer.occurrences')}>
              <div className={styles.sectionHead}>
                <h3>{t('money.drawer.occurrences')}</h3>
              </div>
              {(c.occurrences ?? []).length === 0 ? (
                <p className="muted small">—</p>
              ) : (
                <ul className={styles.plainList}>
                  {(c.occurrences ?? []).map((o) => (
                    <li key={o.due}>
                      <OccDot status={o.status} />
                      <span className={styles.grow}>{formatDate(o.due, lang)}</span>
                      <Badge tone={statusTone(o.status)}>{t(`money.occ.${o.status}` as MsgKey)}</Badge>
                      <Money amount={o.amount} />
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {(c.price_history ?? []).length > 0 && (
              <section className={styles.section} aria-label={t('money.drawer.price_history')}>
                <div className={styles.sectionHead}>
                  <h3>{t('money.drawer.price_history')}</h3>
                </div>
                <ul className={styles.plainList}>
                  {(c.price_history ?? []).map((p) => (
                    <li key={p.date}>
                      <span className={styles.grow}>{formatDate(p.date, lang)}</span>
                      <Money amount={p.amount} />
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {loan && (
              <section className={styles.section} aria-label={t('money.drawer.loan')}>
                <div className={styles.sectionHead}>
                  <h3>{t('money.drawer.loan')}</h3>
                </div>
                <div className={styles.facts}>
                  {loan.payments_seen != null && (
                    <div className={styles.fact}>
                      <span className={styles.factLabel}>{t('money.drawer.loan.paid')}</span>
                      <span>
                        {loan.payments_seen}
                        {loan.months != null ? ` / ${loan.months}` : ''}
                      </span>
                    </div>
                  )}
                  {asAmount(loan.total_paid, currency) && (
                    <div className={styles.fact}>
                      <span className={styles.factLabel}>{t('money.drawer.loan.total_paid')}</span>
                      <Money amount={asAmount(loan.total_paid, currency)} />
                    </div>
                  )}
                  {asAmount(loan.balance_after_seen, currency) && (
                    <div className={styles.fact}>
                      <span className={styles.factLabel}>{t('money.drawer.loan.balance')}</span>
                      <Money amount={asAmount(loan.balance_after_seen, currency)} />
                    </div>
                  )}
                </div>
                <Explain explain={loan.explain} />
              </section>
            )}

            {(c.notes || c.cancel_notes) && (
              <section className={styles.section} aria-label={t('money.drawer.notes')}>
                <div className={styles.sectionHead}>
                  <h3>{t('money.drawer.notes')}</h3>
                </div>
                {c.notes && <p className={styles.noticeText}>{c.notes}</p>}
                {c.cancel_notes && (
                  <p className={styles.noticeMeta}>
                    {t('money.drawer.cancel_notes')}: {c.cancel_notes}
                  </p>
                )}
              </section>
            )}

            <Explain explain={c.explain} />
          </div>
        )}
      </Sheet>

      {c && (
        <ConfirmDialog
          open={confirm === 'cancel'}
          title={t('money.fixed.cancel.title', { name: c.name })}
          confirmLabel={t('money.fixed.cancel.confirm')}
          busy={busy}
          onCancel={() => setConfirm(null)}
          onConfirm={() => void act(() => cancelCommitment(ws, c.id, cancelNote.trim() || undefined), t('money.fixed.cancelled'))}
          body={
            <div className={styles.form}>
              <p className={styles.noticeText}>{t('money.fixed.cancel.body')}</p>
              <Field label={t('money.cancel_note')} hint={t('money.cancel_note.hint')}>
                <Textarea rows={3} value={cancelNote} onChange={(e) => setCancelNote(e.target.value)} />
              </Field>
            </div>
          }
        />
      )}

      {c && (
        <ConfirmDialog
          open={confirm === 'delete'}
          title={t('money.fixed.delete.title', { name: c.name })}
          confirmLabel={t('money.fixed.delete.confirm')}
          destructive
          busy={busy}
          onCancel={() => setConfirm(null)}
          onConfirm={() => void act(() => deleteCommitment(ws, c.id), t('money.fixed.deleted'), true)}
          body={
            <p className={styles.noticeText}>
              {t('money.fixed.delete.body')} <Money amount={c.amount} /> · {cadenceText(t, c, lang)}
            </p>
          }
        />
      )}
    </>
  );
}
