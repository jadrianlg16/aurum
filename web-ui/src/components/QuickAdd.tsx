'use client';

/**
 * "Captura rápida (atajo)" — one line in, a reviewed *movement* out (an ordinary, editable
 * entry). Honest about what it is: a shortcut next to the normal "+ Agregar" form, opened from
 * the ⋯ menu (and `/`) in advanced mode only (Shell.tsx).
 *
 * Flow: text + account → "Revisar" = `POST /ingest/{ws}/quickadd` (preview, nothing saved) →
 * Monto · Categoría · Cuenta · Comercio · Fecha from `preview`, the parser's warnings, and a
 * "No estoy seguro" badge under 0.8 confidence (never a percentage, never postings) →
 * "Guardar movimiento" = the same call with `commit: true`, which writes a normal editable pf
 * entry (source quickadd, no inbox row) → the shared "Guardado · … · Deshacer" toast and
 * `useAddEntry().bump()` so every list refreshes. "Descartar" persists nothing.
 */
import { useEffect, useRef, useState } from 'react';
import { errorMessage, quickAddCommit, quickAddPreview } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import type { QuickAddResult } from '@/lib/types-personal';
import { useWorkspace } from '@/lib/workspace';
import { useAddEntry } from './AddEntry';
import { useEntryToast } from './movimientos/entryToast';
import styles from './movimientos/movimientos.module.css';
import { readLastAccount } from './movimientos/prefs';
import { AccountPicker, Badge, Button, Dialog, Field, Input } from './ui';

const LOW_CONFIDENCE = 0.8;

export function QuickAddModal({ open, onClose }: { open: boolean; onClose: (accepted: boolean) => void }) {
  const { t, lang } = useI18n();
  const { fmt } = useMoney();
  const { ws } = useWorkspace();
  const { bump } = useAddEntry();
  const entryToast = useEntryToast();
  const [text, setText] = useState('');
  const [accountId, setAccountId] = useState('');
  const [preview, setPreview] = useState<QuickAddResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Fresh state every time it opens; focus after paint so the "/" that opened it is not typed.
  useEffect(() => {
    if (!open) return undefined;
    setText('');
    setPreview(null);
    setError(null);
    setBusy(false);
    setAccountId(ws ? readLastAccount(ws) ?? '' : '');
    const id = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(id);
  }, [open, ws]);

  const parse = async () => {
    const line = text.trim();
    if (!line || !ws || busy) return;
    setBusy(true);
    setError(null);
    try {
      setPreview(await quickAddPreview(ws, line, accountId || null));
    } catch (e) {
      setError(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    const line = text.trim();
    if (!line || !ws || busy || !preview) return;
    setBusy(true);
    setError(null);
    try {
      const result = await quickAddCommit(ws, line, accountId || null);
      onClose(true);
      if (result.entry) entryToast.saved(ws, result.entry, bump);
      bump();
    } catch (e) {
      setError(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const act = () => {
    if (busy) return;
    if (preview) void save();
    else void parse();
  };

  const p = preview?.preview;
  const lowConfidence = preview !== null && preview.confidence < LOW_CONFIDENCE;

  return (
    <Dialog
      open={open}
      onClose={() => onClose(false)}
      title={t('qa.title')}
      description={t('qa.explainer')}
      size="md"
      error={error}
      footer={
        <>
          <Button variant="ghost" onClick={() => onClose(false)} disabled={busy}>
            {t('qa.discard')}
          </Button>
          <span className="spacer" />
          <Button variant="primary" onClick={act} loading={busy} disabled={busy || !text.trim()}>
            {preview ? t('qa.save') : t('qa.parse')}
          </Button>
        </>
      }
    >
      <Field label={t('qa.text')}>
        <Input
          ref={inputRef}
          type="text"
          value={text}
          autoComplete="off"
          onChange={(e) => {
            setText(e.target.value);
            // A changed line needs a new review before it can be saved.
            if (preview) setPreview(null);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              act();
            }
          }}
        />
      </Field>
      <Field label={t('txn.filter.account')}>
        <AccountPicker
          ws={ws}
          value={accountId}
          onChange={(id) => {
            setAccountId(id);
            if (preview) setPreview(null);
          }}
        />
      </Field>

      {preview && p && (
        <div className={styles.qaPreview} role="status" aria-live="polite">
          <dl>
            <dt>{t('add.amount')}</dt>
            <dd>{fmt({ amount: p.kind === 'income' ? p.amount.amount : `-${p.amount.amount.replace(/^-/, '')}`, currency: p.amount.currency }, { sign: 'always' })}</dd>
            <dt>{t('add.category')}</dt>
            <dd>{p.label_name ?? t('common.no_category')}</dd>
            <dt>{t('txn.filter.account')}</dt>
            <dd>{p.account_name ?? '—'}</dd>
            <dt>{t('add.payee')}</dt>
            <dd>{p.payee ?? '—'}</dd>
            <dt>{t('add.date')}</dt>
            <dd>{formatDate(p.date, lang, 'medium')}</dd>
          </dl>
          {lowConfidence && <Badge tone="warn">{t('qa.low_confidence')}</Badge>}
          {preview.warnings.length > 0 && (
            <ul className={styles.qaWarnings}>
              {preview.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <p className={styles.qaHint}>{t('qa.form_hint')}</p>
    </Dialog>
  );
}
