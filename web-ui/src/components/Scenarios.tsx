'use client';

/**
 * Plan › Scenarios (`aurum/plan`).
 *
 * The form is generated from each scenario's own JSON schema, so a new scenario on the API
 * appears here with no UI change. The schema's `type` carries the money discipline: a
 * `"string"` property is a decimal the user types and we send back **verbatim** (money, rates,
 * ratios — never `parseFloat`), while `"integer"`/`"number"` are genuine counts and are sent as
 * numbers. Results, sensitivity and Monte Carlo are all the engine's arithmetic; the only
 * numbers this file computes are SVG coordinates for the p10–p90 band.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Empty, ErrorBox, Loading, Section } from '@/components/Bits';
import { Explain } from '@/components/Explain';
import {
  deleteSavedScenario,
  errorMessage,
  listSavedScenarios,
  listScenarios,
  runMonteCarlo,
  runScenario,
  runSensitivity,
  saveScenario,
} from '@/lib/api';
import { toChartNumber } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import type {
  MonteCarloResult,
  ScenarioField,
  ScenarioInputs,
  ScenarioRun,
  ScenarioSpec,
  SensitivityResult,
} from '@/lib/types';

/** Known scenario ids get a bilingual name; anything new falls back to its own id. */
const NAME_KEYS: Record<string, MsgKey> = {
  regime_mx: 'scn.name.regime_mx',
  entity_us: 'scn.name.entity_us',
  buy_vs_rent: 'scn.name.buy_vs_rent',
  cash_vs_credit: 'scn.name.cash_vs_credit',
  retirement: 'scn.name.retirement',
  debt_payoff: 'scn.name.debt_payoff',
};

/** A three-letter default marks a currency code, which is a label and not a decimal. */
const isCurrencyField = (key: string, f: ScenarioField) =>
  key === 'currency' || (typeof f.default === 'string' && /^[A-Z]{3}$/.test(f.default));

function defaultsOf(spec: ScenarioSpec): ScenarioInputs {
  const out: ScenarioInputs = {};
  for (const [k, f] of Object.entries(spec.schema.properties)) {
    if (f.default !== undefined) out[k] = f.default;
    else out[k] = f.type === 'string' ? '' : f.type === 'boolean' ? false : 0;
  }
  return out;
}

function FieldInput({
  name,
  field,
  value,
  onChange,
}: {
  name: string;
  field: ScenarioField;
  value: string | number | boolean;
  onChange: (v: string | number | boolean) => void;
}) {
  const label = field.title ?? name;
  if (field.type === 'boolean') {
    return (
      <label className="row" style={{ gap: 8, marginBottom: 10 }}>
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        <span>{label}</span>
      </label>
    );
  }
  if (field.type === 'integer' || field.type === 'number') {
    return (
      <label className="field" style={{ display: 'block', marginBottom: 10 }}>
        <span>{label}</span>
        <input
          type="number"
          value={String(value)}
          min={field.minimum}
          max={field.maximum}
          step={field.type === 'integer' ? 1 : 'any'}
          onChange={(e) => {
            const n = Number(e.target.value);
            onChange(field.type === 'integer' ? Math.round(n || 0) : n || 0);
          }}
          style={{ width: '100%', fontFamily: 'var(--mono)' }}
        />
        {field.description && <span className="small muted">{field.description}</span>}
      </label>
    );
  }
  // type === 'string': a decimal (or a currency code) kept exactly as typed.
  const currency = isCurrencyField(name, field);
  return (
    <label className="field" style={{ display: 'block', marginBottom: 10 }}>
      <span>{label}</span>
      <input
        type="text"
        inputMode={currency ? 'text' : 'decimal'}
        value={String(value)}
        onChange={(e) =>
          onChange(currency ? e.target.value.toUpperCase() : e.target.value.replace(/[^\d.-]/g, ''))
        }
        style={{ width: '100%', fontFamily: 'var(--mono)' }}
      />
      {field.description && <span className="small muted">{field.description}</span>}
    </label>
  );
}

/** Renders whatever `results` shape a scenario returns, without knowing any of them. */
function ResultTree({ node, depth = 0 }: { node: unknown; depth?: number }) {
  if (node === null || node === undefined) return <span className="muted">—</span>;
  if (typeof node === 'string' || typeof node === 'number' || typeof node === 'boolean') {
    return <span className="money">{String(node)}</span>;
  }
  if (Array.isArray(node)) {
    if (node.length === 0) return <span className="muted">—</span>;
    const rows = node.slice(0, 24);
    const keys =
      typeof rows[0] === 'object' && rows[0] !== null ? Object.keys(rows[0] as object) : null;
    return (
      <div className="table-scroll" style={{ maxHeight: 300, overflowY: 'auto' }}>
        <table>
          {keys && (
            <thead>
              <tr>
                {keys.map((k) => (
                  <th key={k}>{k}</th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {keys ? (
                  keys.map((k) => (
                    <td key={k} className="num">
                      <ResultTree node={(r as Record<string, unknown>)[k]} depth={depth + 1} />
                    </td>
                  ))
                ) : (
                  <td>
                    <ResultTree node={r} depth={depth + 1} />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {node.length > rows.length && <p className="small muted">… {node.length - rows.length}</p>}
      </div>
    );
  }
  const entries = Object.entries(node as Record<string, unknown>);
  return (
    <table>
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <td className="small" style={{ width: 240, verticalAlign: 'top' }}>
              {k}
            </td>
            <td>
              <ResultTree node={v} depth={depth + 1} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** p10 · p50 · p90 as a simple band. The coordinates are geometry; the labels are the strings. */
function BandChart({ p10, p50, p90 }: { p10: string; p50: string; p90: string }) {
  const lo = toChartNumber({ amount: p10, currency: '' });
  const mid = toChartNumber({ amount: p50, currency: '' });
  const hi = toChartNumber({ amount: p90, currency: '' });
  const span = hi - lo || 1;
  const x = (v: number) => 4 + ((v - lo) / span) * 92;
  return (
    <svg viewBox="0 0 100 26" preserveAspectRatio="none" style={{ width: '100%', height: 52 }} role="img"
      aria-label={`p10 ${p10}, p50 ${p50}, p90 ${p90}`}>
      <rect x={x(lo)} y={9} width={Math.max(0.5, x(hi) - x(lo))} height={8} rx={4} fill="var(--gold)" opacity={0.3} />
      <line x1={x(mid)} x2={x(mid)} y1={6} y2={20} stroke="var(--gold)" strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
      <circle cx={x(lo)} cy={13} r={1.6} fill="var(--gold)" />
      <circle cx={x(hi)} cy={13} r={1.6} fill="var(--gold)" />
    </svg>
  );
}

export function ScenariosPanel({ ws }: { ws: string }) {
  const { t } = useI18n();
  const catalog = useResource(useCallback(() => listScenarios(ws), [ws]), [ws]);
  const saved = useResource(useCallback(() => listSavedScenarios(ws), [ws]), [ws]);

  const [id, setId] = useState<string | null>(null);
  const [inputs, setInputs] = useState<ScenarioInputs>({});
  const [run, setRun] = useState<ScenarioRun | null>(null);
  const [sens, setSens] = useState<SensitivityResult | null>(null);
  const [mc, setMc] = useState<MonteCarloResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [varyField, setVaryField] = useState('');
  const [rangePct, setRangePct] = useState(10);
  const [n, setN] = useState(200);
  const [seed, setSeed] = useState(7);
  const [saveName, setSaveName] = useState('');

  const spec = useMemo(
    () => catalog.data?.find((s) => s.id === id) ?? catalog.data?.[0] ?? null,
    [catalog.data, id],
  );

  // Selecting a scenario resets the form to that scenario's own schema defaults.
  useEffect(() => {
    if (!spec) return;
    setId(spec.id);
    setInputs(defaultsOf(spec));
    setRun(null);
    setSens(null);
    setMc(null);
    setVaryField(Object.keys(spec.schema.properties)[0] ?? '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec?.id]);

  const guard = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (catalog.loading) return <Loading />;
  if (catalog.error) return <ErrorBox message={catalog.error} onRetry={catalog.reload} />;
  if (!spec) return <Empty />;

  const label = (sid: string) => (NAME_KEYS[sid] ? t(NAME_KEYS[sid]) : sid);
  const fields = Object.entries(spec.schema.properties);

  return (
    <div className="stack">
      <Section title={t('scn.catalog')}>
        <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
          {catalog.data!.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`btn ${s.id === spec.id ? 'primary' : 'ghost'}`}
              onClick={() => setId(s.id)}
            >
              {label(s.id)}
            </button>
          ))}
        </div>
        <p className="small muted" style={{ marginTop: 8 }}>
          {t('scn.metric')}: <span className="rule-chip">{spec.metric_path.join(' › ')}</span>
        </p>
      </Section>

      <div className="grid cols-2">
        <Section title={t('scn.inputs')}>
          {fields.map(([k, f]) => (
            <FieldInput
              key={k}
              name={k}
              field={f}
              value={inputs[k] ?? ''}
              onChange={(v) => setInputs((prev) => ({ ...prev, [k]: v }))}
            />
          ))}
          {error && <p className="err">{error}</p>}
          <div className="row" style={{ marginTop: 8 }}>
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              onClick={() =>
                void guard(async () => {
                  setRun(await runScenario(ws, spec.id, inputs));
                })
              }
            >
              {t('scn.run')}
            </button>
            <div style={{ flex: 1 }} />
            <input
              type="text"
              placeholder={t('scn.save_name')}
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              style={{ width: 170 }}
            />
            <button
              type="button"
              className="btn"
              disabled={busy || !saveName.trim()}
              onClick={() =>
                void guard(async () => {
                  await saveScenario(ws, { scenario_id: spec.id, name: saveName.trim(), inputs });
                  setSaveName('');
                  saved.reload();
                })
              }
            >
              {t('scn.save')}
            </button>
          </div>
        </Section>

        <Section title={t('scn.saved')}>
          {(saved.data?.length ?? 0) === 0 ? (
            <Empty />
          ) : (
            <div className="table-scroll">
              <table>
                <tbody>
                  {saved.data!.map((s) => (
                    <tr key={s.id}>
                      <td>{s.name}</td>
                      <td className="small muted">{label(s.scenario_id)}</td>
                      <td>
                        <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
                          <button
                            type="button"
                            className="btn ghost"
                            onClick={() => {
                              setId(s.scenario_id);
                              setInputs(s.inputs);
                            }}
                          >
                            {t('scn.load')}
                          </button>
                          <button
                            type="button"
                            className="btn ghost"
                            onClick={() =>
                              void guard(async () => {
                                await deleteSavedScenario(ws, s.id);
                                saved.reload();
                              })
                            }
                          >
                            {t('form.delete')}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>

      {run && (
        <Section title={t('scn.results')}>
          <ResultTree node={run.results} />
          <Explain explain={run.explain} defaultOpen />
        </Section>
      )}

      <Section title={t('scn.sensitivity')}>
        <div className="row" style={{ flexWrap: 'wrap' }}>
          <label className="field">
            {t('scn.vary')}
            <select value={varyField} onChange={(e) => setVaryField(e.target.value)}>
              {fields
                .filter(([, f]) => f.type !== 'boolean')
                .map(([k, f]) => (
                  <option key={k} value={k}>
                    {f.title ?? k}
                  </option>
                ))}
            </select>
          </label>
          <label className="field">
            {t('scn.range_pct')}
            <input
              type="number"
              min={1}
              max={90}
              value={rangePct}
              onChange={(e) => setRangePct(Math.max(1, Number(e.target.value) || 1))}
              style={{ width: 90 }}
            />
          </label>
          <button
            type="button"
            className="btn"
            disabled={busy || !varyField}
            onClick={() =>
              void guard(async () => {
                setSens(
                  await runSensitivity(ws, spec.id, { inputs, vary: [varyField], range_pct: rangePct }),
                );
              })
            }
          >
            {t('scn.run')}
          </button>
        </div>
        {sens && (
          <div className="table-scroll" style={{ marginTop: 10 }}>
            <table>
              <thead>
                <tr>
                  <th>{t('scn.vary')}</th>
                  <th className="num">{t('scn.low')}</th>
                  <th className="num">{t('scn.high')}</th>
                  <th className="num">{t('scn.range')}</th>
                </tr>
              </thead>
              <tbody>
                {sens.rows.map((r) => (
                  <tr key={r.field}>
                    <td>{r.field}</td>
                    <td className="num money">{r.low}</td>
                    <td className="num money">{r.high}</td>
                    <td className="num money">{r.range}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {sens?.explain && <Explain explain={sens.explain} />}
      </Section>

      <Section title={t('scn.montecarlo')}>
        <div className="row" style={{ flexWrap: 'wrap' }}>
          <label className="field">
            {t('scn.n')}
            <input
              type="number"
              min={10}
              max={5000}
              value={n}
              onChange={(e) => setN(Math.max(10, Number(e.target.value) || 10))}
              style={{ width: 100 }}
            />
          </label>
          <label className="field">
            {t('scn.seed')}
            <input
              type="number"
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value) || 0)}
              style={{ width: 90 }}
            />
          </label>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() =>
              void guard(async () => {
                setMc(await runMonteCarlo(ws, spec.id, { inputs, n, seed }));
              })
            }
          >
            {t('scn.run')}
          </button>
        </div>
        {mc && (
          <>
            <div className="grid cols-4" style={{ marginTop: 10 }}>
              <div>
                <div className="metric-label">p10</div>
                <div className="metric-value sm money">{mc.results.p10}</div>
              </div>
              <div>
                <div className="metric-label">p50</div>
                <div className="metric-value sm money">{mc.results.p50}</div>
              </div>
              <div>
                <div className="metric-label">p90</div>
                <div className="metric-value sm money">{mc.results.p90}</div>
              </div>
              <div>
                <div className="metric-label">{t('scn.mean')}</div>
                <div className="metric-value sm money">{mc.results.mean}</div>
              </div>
            </div>
            <div className="small muted" style={{ marginTop: 8 }}>
              {t('scn.band')}
            </div>
            <BandChart p10={mc.results.p10} p50={mc.results.p50} p90={mc.results.p90} />
            <div className="row small muted">
              <span>
                {t('scn.n')}: {mc.results.iterations}
              </span>
              <span>
                {t('scn.seed')}: {mc.results.seed}
              </span>
              {mc.results.success_rate_pct && (
                <span>
                  {t('scn.success')}: {mc.results.success_rate_pct}%
                </span>
              )}
            </div>
            <Explain explain={mc.explain} />
          </>
        )}
      </Section>
    </div>
  );
}
