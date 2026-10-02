'use client';

/**
 * Documents — the CFDI table with filters, an expandable row (fields + pagos/REP), and the
 * upload zones (CFDI XML/ZIP, bank CSV onto a chosen account). Receipt photos are read from the
 * + Agregar dialog (`POST /ingest/{ws}/receipts`), not here.
 */
import { Fragment, useCallback, useState } from 'react';
import { Empty, ErrorBox, Loading, Money, Section } from '@/components/Bits';
import { AccountPicker } from '@/components/ui';
import { errorMessage, importBankCsv, listCfdi, uploadCfdi } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { closePeriod, periodsEndingAt } from '@/lib/period';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { CfdiDirection, CfdiTipo, MetodoPago, UploadResult } from '@/lib/types';

const TIPOS: CfdiTipo[] = ['I', 'E', 'P', 'N', 'T'];

function DropZone({
  label,
  accept,
  disabled,
  note,
  onFiles,
}: {
  label: string;
  accept: string;
  disabled?: boolean;
  note?: string;
  onFiles: (files: File[]) => void;
}) {
  const [over, setOver] = useState(false);
  const inputId = `drop-${label.replace(/\W+/g, '-')}`;
  return (
    <div
      className={`dropzone ${over ? 'over' : ''} ${disabled ? 'disabled' : ''}`}
      onDragOver={(e) => {
        if (disabled) return;
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (disabled) return;
        onFiles(Array.from(e.dataTransfer.files));
      }}
    >
      <label htmlFor={inputId} style={{ cursor: disabled ? 'not-allowed' : 'pointer' }}>
        <strong>{label}</strong>
      </label>
      <input
        id={inputId}
        type="file"
        accept={accept}
        multiple
        disabled={disabled}
        style={{ display: 'block', margin: '8px auto 0' }}
        onChange={(e) => onFiles(Array.from(e.target.files ?? []))}
      />
      {note && <p className="small" style={{ marginBottom: 0 }}>{note}</p>}
    </div>
  );
}

export default function DocumentsPage() {
  const { t, lang } = useI18n();
  const { ws } = useWorkspace();

  const [period, setPeriod] = useState(closePeriod());
  const [tipo, setTipo] = useState<CfdiTipo | ''>('');
  const [metodo, setMetodo] = useState<MetodoPago | ''>('');
  const [direction, setDirection] = useState<CfdiDirection | ''>('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [bank, setBank] = useState('BBVA');
  // Bank lines become pf entries on a chosen account (the API requires account_id)
  const [csvAccountId, setCsvAccountId] = useState('');
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const cfdis = useResource(
    useCallback(
      () =>
        listCfdi(ws, {
          period: period || undefined,
          tipo: tipo || undefined,
          metodo_pago: metodo || undefined,
          direction: direction || undefined,
        }),
      [ws, period, tipo, metodo, direction],
    ),
    [ws, period, tipo, metodo, direction],
  );

  const report = (r: UploadResult) => {
    setUploadMsg(`${t('docs.uploaded')}: ${r.accepted}${r.warnings.length ? ` — ${r.warnings.join(' ')}` : ''}`);
    cfdis.reload();
  };

  const run = async (fn: () => Promise<UploadResult>) => {
    setUploading(true);
    setUploadErr(null);
    setUploadMsg(null);
    try {
      report(await fn());
    } catch (e) {
      setUploadErr(errorMessage(e));
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>{t('docs.title')}</h1>
      </div>

      <div className="stack">
        <Section title={t('docs.upload')}>
          <div className="grid cols-2">
            <DropZone label={t('docs.dropzone_xml')} accept=".xml,.zip" onFiles={(f) => f.length && void run(() => uploadCfdi(ws, f))} />
            <div>
              <label className="field" style={{ marginBottom: 8 }}>
                {t('docs.bank_name')}
                <input type="text" value={bank} onChange={(e) => setBank(e.target.value)} />
              </label>
              <div className="field" style={{ marginBottom: 8 }}>
                <AccountPicker ws={ws} value={csvAccountId} onChange={(id) => setCsvAccountId(id)} placeholder={t('docs.csv.account')} />
              </div>
              <DropZone
                label={t('docs.dropzone_bank')}
                accept=".csv,.txt"
                onFiles={(f) =>
                  f[0] &&
                  csvAccountId &&
                  void run(async () => {
                    const r = await importBankCsv(ws, f[0], csvAccountId, bank);
                    // same report shape as the CFDI upload: created rows count as accepted
                    return { accepted: r.created.length, inbox_items: [], warnings: [
                      ...(r.skipped_duplicates ? [t('docs.csv.skipped', { n: r.skipped_duplicates })] : []),
                      ...r.errors.map((e) => t('docs.csv.line', { line: e.line, detail: e.detail })),
                    ] };
                  })
                }
              />
            </div>
          </div>
          {uploading && <p className="small muted">{t('docs.uploading')}</p>}
          {uploadMsg && <p className="small" style={{ color: 'var(--pos)' }}>{uploadMsg}</p>}
          {uploadErr && <p className="err">{uploadErr}</p>}
        </Section>

        <Section
          title={t('docs.cfdi')}
          actions={
            <div className="row" style={{ gap: 8 }}>
              <label className="field">
                {t('common.period')}
                <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                  <option value="">{t('common.all')}</option>
                  {periodsEndingAt(closePeriod(), 12).map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                {t('docs.filter.tipo')}
                <select value={tipo} onChange={(e) => setTipo(e.target.value as CfdiTipo | '')}>
                  <option value="">{t('common.all')}</option>
                  {TIPOS.map((x) => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                {t('docs.filter.metodo')}
                <select value={metodo} onChange={(e) => setMetodo(e.target.value as MetodoPago | '')}>
                  <option value="">{t('common.all')}</option>
                  <option value="PUE">PUE</option>
                  <option value="PPD">PPD</option>
                </select>
              </label>
              <label className="field">
                {t('docs.filter.direction')}
                <select value={direction} onChange={(e) => setDirection(e.target.value as CfdiDirection | '')}>
                  <option value="">{t('common.all')}</option>
                  <option value="emitido">{t('docs.emitido')}</option>
                  <option value="recibido">{t('docs.recibido')}</option>
                </select>
              </label>
            </div>
          }
        >
          {cfdis.loading ? (
            <Loading />
          ) : cfdis.error ? (
            <ErrorBox message={cfdis.error} onRetry={cfdis.reload} />
          ) : (cfdis.data?.length ?? 0) === 0 ? (
            <Empty />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t('common.date')}</th>
                    <th>{t('docs.filter.tipo')}</th>
                    <th>{t('docs.filter.metodo')}</th>
                    <th>{t('docs.filter.direction')}</th>
                    <th>{t('docs.emisor')}</th>
                    <th>{t('docs.receptor')}</th>
                    <th className="num">{t('docs.subtotal')}</th>
                    <th className="num">{t('docs.iva')}</th>
                    <th className="num">{t('common.total')}</th>
                  </tr>
                </thead>
                <tbody>
                  {cfdis.data!.map((c) => (
                    <Fragment key={c.uuid}>
                      <tr
                        className={expanded === c.uuid ? 'selected' : ''}
                        onClick={() => setExpanded(expanded === c.uuid ? null : c.uuid)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td>{formatDate(c.fecha.slice(0, 10), lang)}</td>
                        <td>
                          <span className="badge neutral">{c.tipo}</span>
                        </td>
                        <td>{c.metodo_pago ?? '—'}</td>
                        <td>{c.direction === 'emitido' ? t('docs.emitido') : t('docs.recibido')}</td>
                        <td className="money">{c.emisor_rfc}</td>
                        <td className="money">{c.receptor_rfc}</td>
                        <td className="num">
                          <Money value={{ amount: c.subtotal, currency: c.moneda }} />
                        </td>
                        <td className="num">
                          <Money value={{ amount: c.iva_trasladado, currency: c.moneda }} />
                        </td>
                        <td className="num">
                          <Money value={{ amount: c.total, currency: c.moneda }} />
                        </td>
                      </tr>
                      {expanded === c.uuid && (
                        <tr>
                          <td colSpan={9}>
                            <div className="grid cols-2">
                              <div>
                                <h3>{t('docs.uuid')}</h3>
                                <p className="money small">{c.uuid}</p>
                                <div className="row small">
                                  <span className="rule-chip">
                                    {t('docs.uso')}: {c.uso_cfdi ?? '—'}
                                  </span>
                                  <span className="rule-chip">
                                    {t('docs.forma')}: {c.forma_pago ?? '—'}
                                  </span>
                                  <span className="rule-chip">v{c.version}</span>
                                  <span className="rule-chip">
                                    {t('docs.retenido')}: {c.impuestos_retenidos}
                                  </span>
                                </div>
                                <h3 style={{ marginTop: 12 }}>{t('docs.conceptos')}</h3>
                                <ul className="small">
                                  {c.conceptos.map((x, i) => (
                                    <li key={i}>
                                      {String(x.descripcion ?? '')} — {String(x.importe ?? '')}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                              <div>
                                <h3>{t('docs.pagos')}</h3>
                                {c.pagos.length === 0 ? (
                                  <Empty />
                                ) : (
                                  <table>
                                    <thead>
                                      <tr>
                                        <th>{t('common.date')}</th>
                                        <th className="num">{t('common.amount')}</th>
                                        <th>{t('docs.uuid')}</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {c.pagos.map((p) => (
                                        <tr key={`${p.uuid_relacionado}-${p.fecha_pago}`}>
                                          <td>{formatDate(p.fecha_pago, lang)}</td>
                                          <td className="num">
                                            <Money value={{ amount: p.monto, currency: p.moneda ?? 'MXN' }} />
                                          </td>
                                          <td className="money small">{p.uuid_relacionado}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>
    </>
  );
}
