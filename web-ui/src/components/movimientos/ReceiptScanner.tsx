'use client';

/**
 * "Foto del recibo" inside + Agregar. A labelled shortcut: the person takes
 * or picks a photo, `POST /ingest/{ws}/receipts` keeps it and reads it, and the parent pre-fills only
 * the fields that are still empty. The card shows what was read — amount, shop, category, date — with
 * "revisa" on anything unsure, and "¿Cómo lo leímos?" lists the reasons and the raw text. Nothing is
 * saved until the person presses Guardar; the movement then carries the photo as `attachment`.
 *
 * No `capture` attribute on the input: phones offer both the camera and the gallery. The thumbnail
 * of a fresh photo is the local file (no round trip); a saved movement's photo is fetched through the
 * request layer (`receiptObjectUrl`) because an `<img src>` could not send the access key.
 */
import { useEffect, useId, useRef, useState, type ChangeEvent } from 'react';
import { Badge, Button, Money } from '@/components/ui';
import { ApiError, errorMessage, receiptObjectUrl, scanReceipt } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import type { ReceiptConfidence, ReceiptScan } from '@/lib/types-personal';
import styles from './movimientos.module.css';

export interface ReceiptScannerProps {
  ws: string;
  /** The receipt this movement already carries (edit mode) or the one just scanned. */
  attachment: string | null;
  scan: ReceiptScan | null;
  onScanned: (scan: ReceiptScan) => void;
  onRemove: () => void;
  disabled?: boolean;
}

function Unsure({ c }: { c: ReceiptConfidence }) {
  const { t } = useI18n();
  if (c !== 'low') return null;
  return <Badge tone="warn">{t('receipt.check')}</Badge>;
}

export function ReceiptScanner({ ws, attachment, scan, onScanned, onRemove, disabled }: ReceiptScannerProps) {
  const { t, lang } = useI18n();
  const { fmt } = useMoney();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const hintId = useId();

  // Object URLs are revoked when replaced or on unmount.
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  // A saved movement's photo (edit mode, no fresh scan): fetch it once for the thumbnail.
  useEffect(() => {
    if (!attachment || scan || preview) return undefined;
    let alive = true;
    receiptObjectUrl(ws, attachment)
      .then((url) => {
        if (alive) setPreview(url);
        else URL.revokeObjectURL(url);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [ws, attachment, scan, preview]);

  const pick = () => inputRef.current?.click();

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // picking the same file again still fires
    if (!file) return;
    setError(null);
    setBusy(true);
    setPreview(URL.createObjectURL(file));
    try {
      onScanned(await scanReceipt(ws, file));
    } catch (err) {
      // The server's own sentence for a refused file (not a photo, HEIC) is the clearest one.
      setError(err instanceof ApiError && err.status === 400 ? err.message : errorMessage(err, t));
      setPreview(null);
    } finally {
      setBusy(false);
    }
  };

  const remove = () => {
    setPreview(null);
    setError(null);
    onRemove();
  };

  const s = scan?.suggestion ?? null;
  const dup = scan?.duplicate ?? null;
  const input = (
    <input
      ref={inputRef}
      type="file"
      accept="image/jpeg,image/png,image/webp,image/*"
      className="sr-only"
      tabIndex={-1}
      aria-hidden="true"
      onChange={(e) => void onFile(e)}
    />
  );

  if (!attachment && !busy) {
    return (
      <div className={styles.receiptPick}>
        {input}
        <Button variant="secondary" icon="camera" onClick={pick} disabled={disabled} aria-describedby={hintId}>
          {t('receipt.pick')}
        </Button>
        <span id={hintId} className="small muted">
          {t('receipt.pick.hint')}
        </span>
        {error && (
          <p className="ui-field-error" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <section className={styles.receiptCard} aria-label={t('receipt.title')} aria-busy={busy || undefined}>
      {input}
      {preview ? (
        <a href={preview} target="_blank" rel="noreferrer" className={styles.receiptThumb}>
          {/* eslint-disable-next-line @next/next/no-img-element -- a local object URL, not an optimisable asset */}
          <img src={preview} alt={t('receipt.photo_alt')} />
        </a>
      ) : (
        <span className={styles.receiptThumb} aria-hidden="true" />
      )}
      <div className={styles.receiptBody}>
        {busy ? (
          <p className="small" role="status">
            {t('receipt.reading')}
          </p>
        ) : s ? (
          <>
            <p className={styles.receiptFound}>
              {s.amount ? (
                <span>
                  <Money amount={s.amount} /> <Unsure c={s.confidence.amount} />
                </span>
              ) : (
                <span className="muted">{t('receipt.no_amount')}</span>
              )}
              {s.payee && (
                <span>
                  {s.payee} <Unsure c={s.confidence.payee} />
                </span>
              )}
              {s.label_name && (
                <span>
                  {s.label_name} <Unsure c={s.confidence.label} />
                </span>
              )}
              {s.date && <span>{formatDate(s.date, lang, 'short')}</span>}
            </p>
            <p className="small muted">{scan?.message ?? t('receipt.review')}</p>
          </>
        ) : scan ? (
          <p className="small">{scan.message ?? t('receipt.saved_only')}</p>
        ) : (
          <p className="small">
            <span aria-hidden="true">📎 </span>
            {t('receipt.attached')}
          </p>
        )}

        {dup && (
          <p className={styles.receiptDup} role="status">
            {t(dup.same_photo ? 'receipt.duplicate.photo' : 'receipt.duplicate', {
              date: formatDate(dup.date, lang, 'short'),
              amount: fmt(dup.amount),
              payee: dup.payee ?? '—',
            })}
          </p>
        )}

        {scan && (scan.reasons.length > 0 || scan.ocr.text) && (
          <details className={styles.receiptWhy}>
            <summary>{t('receipt.why')}</summary>
            {scan.reasons.length > 0 && (
              <ul>
                {scan.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
            {scan.ocr.text && (
              <details>
                <summary>{t('receipt.text')}</summary>
                <pre className={styles.receiptText}>{scan.ocr.text}</pre>
              </details>
            )}
          </details>
        )}

        {error && (
          <p className="ui-field-error" role="alert">
            {error}
          </p>
        )}
        {!busy && (
          <div className="row">
            <Button variant="ghost" size="sm" icon="camera" onClick={pick} disabled={disabled}>
              {t('receipt.replace')}
            </Button>
            <Button variant="ghost" size="sm" onClick={remove} disabled={disabled}>
              {t('receipt.remove')}
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
