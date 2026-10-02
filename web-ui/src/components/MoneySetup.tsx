'use client';

/**
 * "Configurar" — the 3-step wizard that fills the hub from real data.
 *
 *   1. Do we have anything to read? `GET /setup/status` says whether bank lines exist; if
 *      not, the only sensible action is a link to Documentos to upload a statement.
 *   2. `POST /setup/run {months:3}` detects recurring charges and paydays; each candidate is
 *      a card with its evidence rows and a confidence bar, accepted or dismissed one by one.
 *   3. The proposed plan, summarised, and done.
 *
 * Resumable: the step is derived from `/setup/status`, and candidates persist server-side, so
 * closing the tab and coming back lands the user where they were.
 */
import Link from 'next/link';
import { useCallback, useState } from 'react';
import { Empty, ErrorBox, Loading, Money, ProgressBar, Section } from './Bits';
import { Explain } from './Explain';
import { CadenceText, KindBadge } from './Money';
import type { Toaster } from './Ui3';
import {
  acceptCandidate,
  dismissCandidate,
  errorMessage,
  getSetupStatus,
  runSetup,
} from '@/lib/api';
import { formatDate, formatPct } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import type { Candidate, Payday, SetupRunResult, SetupStatus } from '@/lib/types-organizer';

export function MoneySetupPanel({ ws, toast, onDone }: { ws: string; toast: Toaster; onDone: () => void }) {
  const { t, lang } = useI18n();
  const status = useResource<SetupStatus>(useCallback(() => getSetupStatus(ws), [ws]), [ws]);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [result, setResult] = useState<SetupRunResult | null>(null);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [paydays, setPaydays] = useState<Payday[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await runSetup(ws, 3);
      setResult(r);
      setCandidates(r.candidates ?? []);
      setPaydays(r.paydays ?? []);
      setStep(2);
      status.reload();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const accept = async (c: Candidate) => {
    setBusy(true);
    try {
      await acceptCandidate(ws, c.id);
      setCandidates((prev) => (prev ?? []).filter((x) => x.id !== c.id));
      toast.show(`${t('money.setup.accepted')}: ${c.preview.name}`);
      status.reload();
    } catch (e) {
      toast.show(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const dismiss = async (c: Candidate) => {
    setBusy(true);
    try {
      await dismissCandidate(ws, c.id);
      setCandidates((prev) => (prev ?? []).filter((x) => x.id !== c.id));
    } catch (e) {
      toast.show(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (status.loading) return <Loading />;
  if (status.error) return <ErrorBox message={status.error} onRetry={status.reload} />;
  const s = status.data;

  return (
    <div className="stack">
      <ol className="wizard-steps" aria-label={t('money.setup.title')}>
        {([1, 2, 3] as const).map((n) => (
          <li key={n} className={step === n ? 'active' : step > n ? 'done' : ''} aria-current={step === n ? 'step' : undefined}>
            <span className="wizard-num">{n}</span>
            {t(`money.setup.step${n}` as MsgKey)}
          </li>
        ))}
      </ol>

      {error && <p className="err">{error}</p>}

      {step === 1 && (
        <Section title={t('money.setup.step1')}>
          {s?.has_bank_lines ? (
            <>
              <p className="ok">{t('money.setup.step1.ok')}</p>
              {s.counts?.bank_lines != null && <p className="small muted">{s.counts.bank_lines}</p>}
              <button type="button" className="btn primary" disabled={busy} data-testid="setup-run" onClick={() => void run()}>
                {busy ? t('money.setup.running') : t('money.setup.run')}
              </button>
            </>
          ) : (
            <>
              <p>{t('money.setup.step1.none')}</p>
              <Link className="btn primary" href="/documents/">
                {t('money.setup.upload')}
              </Link>
            </>
          )}
        </Section>
      )}

      {step === 2 && (
        <>
          <Section title={`${t('money.setup.candidates')}: ${(candidates ?? []).length}`}>
            {(candidates ?? []).length === 0 ? (
              <Empty />
            ) : (
              <div className="grid cols-2">
                {(candidates ?? []).map((c) => (
                  <article className="card" key={c.id}>
                    <div className="row" style={{ gap: 8 }}>
                      <strong>{c.preview.name}</strong>
                      <KindBadge kind={c.preview.kind} />
                      <div style={{ flex: 1 }} />
                      <Money value={c.preview.amount} />
                    </div>
                    <div className="small muted" style={{ marginTop: 4 }}>
                      <CadenceText cadence={c.preview.cadence} /> · {t('money.col.next_due')}{' '}
                      {formatDate(c.preview.next_due, lang)}
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <div className="small muted">
                        {t('money.setup.confidence')}: {formatPct(c.confidence, lang)}
                      </div>
                      <ProgressBar pct={c.confidence} tone={c.confidence > 0.85 ? 'pos' : 'warn'} />
                    </div>

                    <details className="line-detail" style={{ marginTop: 8 }}>
                      <summary>{t('money.setup.evidence')}</summary>
                      <table>
                        <tbody>
                          {(c.evidence ?? []).map((e) => (
                            <tr key={`${e.date}-${e.description}`}>
                              <td>{formatDate(e.date, lang)}</td>
                              <td className="small">{e.description}</td>
                              <td className="num">
                                <Money value={e.amount} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </details>

                    <div className="row" style={{ marginTop: 10, gap: 8 }}>
                      <button type="button" className="btn ghost" disabled={busy} onClick={() => void dismiss(c)}>
                        {t('money.setup.dismiss')}
                      </button>
                      <div style={{ flex: 1 }} />
                      <button
                        type="button"
                        className="btn primary"
                        disabled={busy}
                        data-testid="candidate-accept"
                        onClick={() => void accept(c)}
                      >
                        {t('money.setup.accept')}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
            <Explain explain={result?.explain} />
          </Section>

          {paydays.length > 0 && (
            <Section title={t('money.setup.paydays')}>
              <table>
                <tbody>
                  {paydays.map((p) => (
                    <tr key={p.date}>
                      <td>{formatDate(p.date, lang)}</td>
                      <td>{p.cadence ? <CadenceText cadence={p.cadence} /> : null}</td>
                      <td className="num">
                        <Money value={p.amount} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          )}

          <div className="row">
            <button type="button" className="btn ghost" onClick={() => setStep(1)}>
              {t('money.setup.back')}
            </button>
            <div style={{ flex: 1 }} />
            <button type="button" className="btn primary" onClick={() => setStep(3)}>
              {t('money.setup.next')}
            </button>
          </div>
        </>
      )}

      {step === 3 && (
        <>
          <Section title={t('money.setup.plan')}>
            {result?.plan ? (
              <table>
                <tbody>
                  {(result.plan.groups ?? []).map((g) => (
                    <tr key={g.group}>
                      <td>{t(`money.essential.${g.group}` as MsgKey)}</td>
                      <td className="num">
                        <Money value={g.planned} />
                      </td>
                    </tr>
                  ))}
                  {result.plan.income_expected && (
                    <tr>
                      <td>{t('money.plan.income_expected')}</td>
                      <td className="num">
                        <Money value={result.plan.income_expected} />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            ) : (
              <Empty text={t('money.empty.plan')} />
            )}
          </Section>

          <div className="banner info">{t('money.setup.done')}</div>
          <div className="row">
            <button type="button" className="btn ghost" onClick={() => setStep(2)}>
              {t('money.setup.back')}
            </button>
            <div style={{ flex: 1 }} />
            <button type="button" className="btn primary" onClick={onDone}>
              {t('money.setup.finish')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
