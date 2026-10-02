'use client';

/**
 * The one-line shortcut of Pagos fijos: a closed `<details>` below
 * the list — 'Atajo: escríbelo en una línea' → `POST /quickadd` preview → a confirmation card
 * ('Así lo entendimos', no confidence figure) → Guardar (`?save=1`). On save the server answers
 * the created row (`'id' in r`); the mock answers `{preview, saved}` — both are handled. A
 * duplicate 409 shows the same inline choice as the form; 'Guardar de todas formas' goes
 * through `createCommitment(ws, {...preview, force: true})` because `organizerQuickAdd` has no
 * `force` argument.
 */
import { useState, type FormEvent } from 'react';
import { Badge, Button, Field, Input, Money, useToast } from '@/components/ui';
import { ApiError, createCommitment, errorMessage, organizerQuickAdd } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import type { Commitment, CommitmentInput, CommitmentPreview } from '@/lib/types-organizer';
import { cadenceText } from './shared';
import styles from './money.module.css';

function toInput(p: CommitmentPreview, force: boolean): CommitmentInput {
  return {
    kind: p.kind,
    name: p.name,
    merchant_patterns: p.merchant_patterns ?? [],
    amount: p.amount,
    amount_variable: p.amount_variable,
    cadence: p.cadence,
    interval_days: p.interval_days ?? null,
    anchor_day: p.anchor_day ?? null,
    weekday: p.weekday ?? null,
    next_due: p.next_due,
    account_id: p.account_id ?? null,
    label_id: p.label_id ?? null,
    essential: p.essential,
    status: p.status ?? 'active',
    trial_ends: p.trial_ends ?? null,
    auto_pay: p.auto_pay,
    notes: p.notes ?? null,
    force,
  };
}

function duplicateOf(e: unknown): { existingId: string; name: string } | null {
  if (!(e instanceof ApiError) || e.status !== 409) return null;
  const d = e.detail as { code?: string; existing_id?: string; existing_name?: string } | null;
  if (!d || typeof d !== 'object' || d.code !== 'duplicate') return null;
  return { existingId: String(d.existing_id ?? ''), name: d.existing_name ?? '' };
}

export function QuickAddCard({ ws, onSaved, onOpenExisting }: { ws: string; onSaved: (c: Commitment) => void; onOpenExisting?: (id: string) => void }) {
  const { t, lang } = useI18n();
  const toast = useToast();
  const [text, setText] = useState('');
  const [preview, setPreview] = useState<CommitmentPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dup, setDup] = useState<{ existingId: string; name: string } | null>(null);

  const parse = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    setDup(null);
    try {
      const r = await organizerQuickAdd(ws, text.trim(), false);
      setPreview(r.preview);
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  const finish = (c: Commitment) => {
    setText('');
    setPreview(null);
    toast.success(t('money.fixed.saved'));
    onSaved(c);
  };

  const save = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setDup(null);
    try {
      const r = (await organizerQuickAdd(ws, text.trim(), true)) as unknown as Commitment | { preview: CommitmentPreview; saved: boolean };
      const row = 'id' in r && typeof r.id === 'string' ? (r as Commitment) : ({ ...(r as { preview: CommitmentPreview }).preview } as Commitment);
      finish(row);
    } catch (err) {
      const d = duplicateOf(err);
      if (d) setDup({ ...d, name: d.name || preview?.name || text.trim() });
      else setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  const force = async () => {
    if (!preview || busy) return;
    setBusy(true);
    setError(null);
    try {
      finish(await createCommitment(ws, toInput(preview, true)));
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className={styles.details}>
      <summary>{t('money.fixed.shortcut')}</summary>
      <div className={styles.detailsBody}>
        <form onSubmit={(e) => void parse(e)} className={styles.toolbar}>
          <div className={styles.grow}>
            <Field label={t('money.quickadd')} hint={t('money.fixed.shortcut.hint')}>
              <Input
                value={text}
                placeholder={t('money.quickadd.placeholder')}
                autoComplete="off"
                onChange={(e) => {
                  setText(e.target.value);
                  setPreview(null);
                  setDup(null);
                }}
              />
            </Field>
          </div>
          <Button type="submit" variant="secondary" disabled={busy || !text.trim()} loading={busy && !preview}>
            {t('money.quickadd.parse')}
          </Button>
        </form>

        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}

        {preview && (
          <div className="card" data-testid="quickadd-preview">
            <div className={styles.sectionHead}>
              <h3>{t('money.fixed.suggested')}</h3>
              <Badge tone="accent">{t(`money.kind.${preview.kind}` as MsgKey)}</Badge>
            </div>
            <div className={styles.preview}>
              <div>
                <span className={styles.previewLabel}>{t('money.col.name')}</span>
                <strong>{preview.name}</strong>
              </div>
              <div>
                <span className={styles.previewLabel}>{t('money.col.money')}</span>
                <Money amount={preview.amount} />
              </div>
              <div>
                <span className={styles.previewLabel}>{t('money.col.every')}</span>
                {cadenceText(t, preview, lang)}
              </div>
              <div>
                <span className={styles.previewLabel}>{t('money.col.next')}</span>
                {formatDate(preview.next_due, lang)}
              </div>
            </div>
            {dup && (
              <p className={styles.dup} role="alert">
                <span>{t('money.fixed.duplicate', { name: dup.name })}</span>
                {onOpenExisting && dup.existingId && (
                  <>
                    <span aria-hidden="true">—</span>
                    <button type="button" className={styles.linkBtn} onClick={() => onOpenExisting(dup.existingId)}>
                      {t('money.fixed.duplicate.open')}
                    </button>
                  </>
                )}
                <Button variant="secondary" onClick={() => void force()} disabled={busy}>
                  {t('money.fixed.duplicate.force')}
                </Button>
              </p>
            )}
            <div className={styles.formFoot}>
              <Button variant="ghost" onClick={() => setPreview(null)} disabled={busy}>
                {t('money.quickadd.discard')}
              </Button>
              <span className={styles.grow} />
              <Button variant="primary" onClick={() => void save()} loading={busy}>
                {t('money.f.save')}
              </Button>
            </div>
          </div>
        )}
      </div>
    </details>
  );
}
