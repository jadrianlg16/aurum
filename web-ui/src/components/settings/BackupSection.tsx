'use client';

/**
 * Ajustes › Copia de seguridad.
 *
 * Both downloads go through `fetch` rather than a plain `<a href>`: when the API requires a
 * token (`useHealth().authRequired`) the bearer has to travel in a header, which a link cannot
 * carry. The response becomes a Blob → object URL → a programmatic anchor click. The zip names
 * itself through `Content-Disposition`; `movimientos.csv` sends none, so it is
 * named here as `aurum-<ws>-movimientos-<from>-<to>.csv`.
 *
 * A failed download is mapped through `mapApiError` / `errorMessage` like every other call, so
 * the copy is human and translated and a 401 keeps the "Ajustes" link of `ErrorBox`; Reintentar
 * repeats the same download.
 */
import { useEffect, useState } from 'react';
import { Button, ErrorBox, Field, MonthPicker, useToast } from '@/components/ui';
import { ApiError, backupUrl, errorMessage, getApiToken, mapApiError, movimientosCsvUrl } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { currentPeriod, monthBounds, shiftPeriod } from '@/lib/period';

function filenameFrom(disposition: string | null): string | null {
  if (!disposition) return null;
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  return m ? decodeURIComponent(m[1].trim()) : null;
}

async function download(url: string, fallbackName: string, token: string): Promise<void> {
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  let res: Response;
  try {
    res = await fetch(url, { headers, credentials: 'same-origin' });
  } catch (e) {
    throw new ApiError(e instanceof Error ? e.message : String(e), 0, { code: 'network', detail: e });
  }
  if (!res.ok) {
    let body: unknown;
    try {
      const text = await res.text();
      body = text ? JSON.parse(text) : undefined;
    } catch {
      body = undefined;
    }
    throw mapApiError(res.status, body, res.statusText);
  }
  const blob = await res.blob();
  const name = filenameFrom(res.headers.get('Content-Disposition')) ?? fallbackName;
  const href = URL.createObjectURL(blob);
  try {
    const a = document.createElement('a');
    a.href = href;
    a.download = name;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(href), 10_000);
  }
}

export function BackupSection({ ws }: { ws: string }) {
  const { t } = useI18n();
  const toast = useToast();
  const [busyZip, setBusyZip] = useState(false);
  const [busyCsv, setBusyCsv] = useState(false);
  // What `ErrorBox` reads: the translated copy plus the status (401 → the Ajustes link).
  const [error, setError] = useState<{ message: string; status: number | null; retry: () => void } | null>(null);
  const fail = (e: unknown, retry: () => void) =>
    setError({ message: errorMessage(e, t), status: e instanceof ApiError ? e.status : null, retry });
  // The default range (last three months) is computed after mount: no Date at prerender.
  const [from, setFrom] = useState<string>('');
  const [to, setTo] = useState<string>('');
  useEffect(() => {
    const now = currentPeriod();
    setFrom((v) => v || shiftPeriod(now, -2));
    setTo((v) => v || now);
  }, []);
  const fromValue = from;
  const toValue = to;

  // The bearer travels in a header (a link cannot carry it). It is sent whenever a token is
  // stored — always the case when `useHealth().authRequired` is true and the app works at all;
  // without one the request goes out bare, exactly like every other call.
  const token = () => getApiToken();

  const zip = async () => {
    setBusyZip(true);
    setError(null);
    try {
      await download(backupUrl(ws), `aurum-${ws}.zip`, token());
      toast.success(t('settings.backup.done'));
    } catch (e) {
      fail(e, () => void zip());
    } finally {
      setBusyZip(false);
    }
  };

  const csv = async () => {
    setBusyCsv(true);
    setError(null);
    try {
      const a = monthBounds(fromValue <= toValue ? fromValue : toValue);
      const b = monthBounds(fromValue <= toValue ? toValue : fromValue);
      await download(movimientosCsvUrl(ws, a.from, b.to), `aurum-${ws}-movimientos-${a.from}-${b.to}.csv`, token());
      toast.success(t('settings.backup.done'));
    } catch (e) {
      fail(e, () => void csv());
    } finally {
      setBusyCsv(false);
    }
  };

  return (
    <div className="stack">
      <p className="small muted">{t('settings.backup.hint')}</p>
      <div className="row">
        <Button variant="secondary" onClick={() => void zip()} loading={busyZip} disabled={!ws}>
          {t('settings.backup.download')}
        </Button>
      </div>
      {fromValue && toValue && (
        <div className="row">
          <Field label={t('settings.backup.from')} asGroup>
            <MonthPicker value={fromValue} onChange={setFrom} />
          </Field>
          <Field label={t('settings.backup.to')} asGroup>
            <MonthPicker value={toValue} onChange={setTo} />
          </Field>
        </div>
      )}
      <div className="row">
        <Button variant="secondary" onClick={() => void csv()} loading={busyCsv} disabled={!ws || !fromValue || !toValue}>
          {t('settings.backup.csv')}
        </Button>
      </div>
      {error && <ErrorBox error={error} onRetry={error.retry} />}
      <p className="small muted">{t('settings.backup.where')}</p>
    </div>
  );
}
