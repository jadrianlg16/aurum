'use client';

/**
 * "Plan" — the envelope-style spending plan.
 *
 * Four group rows (Needs / Wants / Savings / Debt), each with planned vs actual vs left and
 * its item rows; the planned column is editable inline and saved with `PUT /plan`. The
 * "Planear desde mis últimos 3 meses" button is the shortcut that makes the screen usable on
 * day one: `POST /plan/auto {months:3}` proposes every envelope from history, then the plan
 * is re-fetched.
 *
 * Below it, the uncategorized list with checkbox multi-select, a label picker and the
 * "create rule" checkbox — `POST /organize` relabels the ledger and, when asked, teaches a
 * rule so the same payee lands labelled next time.
 */
import { useCallback, useMemo, useState } from 'react';
import { Empty, ErrorBox, Loading, Money, Pct, ProgressBar, Section } from './Bits';
import { Explain } from './Explain';
import type { Toaster } from './Ui3';
import {
  autoPlan,
  deleteOrganizerRule,
  errorMessage,
  getOrganizerPlan,
  listLabels,
  listOrganizerRules,
  organizeTxns,
  putOrganizerPlan,
} from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import type { OrganizerPlan, OrganizerRule } from '@/lib/types-organizer';

export function MoneyPlanPanel({ ws, toast }: { ws: string; toast: Toaster }) {
  const { t, lang } = useI18n();
  const plan = useResource<OrganizerPlan>(useCallback(() => getOrganizerPlan(ws), [ws]), [ws]);
  const labels = useResource(useCallback(() => listLabels(ws), [ws]), [ws]);
  const rules = useResource<OrganizerRule[]>(useCallback(() => listOrganizerRules(ws), [ws]), [ws]);

  const [busy, setBusy] = useState(false);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [labelId, setLabelId] = useState('');
  const [createRule, setCreateRule] = useState(true);

  const p = plan.data;
  const uncategorized = useMemo(() => p?.uncategorized ?? [], [p]);

  const runAuto = async () => {
    setBusy(true);
    try {
      const next = await autoPlan(ws, 3);
      plan.set(() => next);
      setEdits({});
      toast.show(t('money.plan.auto_done'));
    } catch (e) {
      toast.show(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const savePlanned = async () => {
    const items = Object.entries(edits).map(([label_id, planned]) => ({ label_id, planned }));
    if (items.length === 0) return;
    setBusy(true);
    try {
      const next = await putOrganizerPlan(ws, items);
      plan.set(() => next);
      setEdits({});
      toast.show(t('money.plan.saved'));
    } catch (e) {
      toast.show(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const organize = async () => {
    if (selected.size === 0 || !labelId) return;
    setBusy(true);
    try {
      const r = await organizeTxns(
        ws,
        [...selected].map((txn_id) => ({ txn_id, label_id: labelId, create_rule: createRule })),
      );
      toast.show(`${r.assigned} ${t('money.plan.organized')}`);
      setSelected(new Set());
      plan.reload();
      rules.reload();
    } catch (e) {
      toast.show(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (plan.loading) return <Loading />;
  if (plan.error) return <ErrorBox message={plan.error} onRetry={plan.reload} />;
  if (!p) return <Empty text={t('money.empty.plan')} />;

  const dirty = Object.keys(edits).length > 0;

  return (
    <div className="stack">
      <div className="grid cols-3">
        <div className="card">
          <div className="metric-label">{t('money.plan.income_expected')}</div>
          <div className="metric-value">
            <Money value={p.income_expected} compactCents />
          </div>
          <div className="small muted" style={{ marginTop: 4 }}>
            {t('money.plan.income_actual')}: <Money value={p.income_actual} compactCents />
          </div>
        </div>
        <div className="card">
          <div className="metric-label">{t('money.plan.savings_rate')}</div>
          <div className="metric-value">
            <Pct value={Number(p.savings_rate ?? '0') || 0} />
          </div>
        </div>
        <div className="card">
          <div className="metric-label">{t('money.plan.auto')}</div>
          <button
            type="button"
            className="btn primary"
            style={{ marginTop: 8 }}
            disabled={busy}
            data-testid="plan-auto"
            onClick={() => void runAuto()}
          >
            {t('money.plan.auto')}
          </button>
        </div>
      </div>

      <Section
        title={t('money.tab.plan')}
        actions={
          <button type="button" className="btn" disabled={!dirty || busy} onClick={() => void savePlanned()}>
            {t('money.plan.save')}
          </button>
        }
      >
        {(p.groups ?? []).length === 0 ? (
          <Empty text={t('money.empty.plan')} />
        ) : (
          <div className="stack" style={{ gap: 18 }}>
            {(p.groups ?? []).map((g) => {
              const plannedN = Number(g.planned.amount) || 0;
              const actualN = Number(g.actual.amount) || 0;
              const pct = plannedN > 0 ? actualN / plannedN : 0;
              return (
                <div key={g.group}>
                  <div className="row" style={{ gap: 10, marginBottom: 4 }}>
                    <strong>{t(`money.essential.${g.group}` as MsgKey)}</strong>
                    <div style={{ flex: 1 }} />
                    <span className="small muted">
                      {t('money.plan.actual')} <Money value={g.actual} /> / {t('money.plan.planned')}{' '}
                      <Money value={g.planned} />
                    </span>
                    <span className="small">
                      {t('money.plan.left')} <Money value={g.left} sign />
                    </span>
                  </div>
                  <ProgressBar pct={pct} tone={pct > 1 ? 'neg' : pct > 0.85 ? 'warn' : 'pos'} />

                  <table style={{ marginTop: 8 }}>
                    <tbody>
                      {(g.items ?? []).map((it) => {
                        const key = it.label_id ?? it.commitment_id ?? it.name;
                        const editable = Boolean(it.label_id ?? it.commitment_id);
                        return (
                          <tr key={key}>
                            <td>{it.name}</td>
                            <td className="num" style={{ width: 140 }}>
                              {editable ? (
                                <input
                                  type="text"
                                  inputMode="decimal"
                                  className="inline-num"
                                  aria-label={`${t('money.plan.planned')} ${it.name}`}
                                  value={edits[key] ?? it.planned.amount}
                                  onChange={(e) => setEdits((v) => ({ ...v, [key]: e.target.value }))}
                                />
                              ) : (
                                <Money value={it.planned} />
                              )}
                            </td>
                            <td className="num">
                              <Money value={it.actual} />
                            </td>
                            <td className="num">
                              <Money value={it.left} sign />
                            </td>
                            <td style={{ width: 120 }}>
                              <ProgressBar pct={Number(it.pct ?? '0') || 0} tone={(Number(it.pct ?? '0') || 0) > 1 ? 'neg' : undefined} />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </div>
        )}
        <Explain explain={p.explain} />
      </Section>

      <Section title={`${t('money.plan.uncategorized')} · ${uncategorized.length}`}>
        {uncategorized.length === 0 ? (
          <Empty text={t('money.empty.uncategorized')} />
        ) : (
          <>
            <table>
              <thead>
                <tr>
                  <th style={{ width: 32 }}>
                    <input
                      type="checkbox"
                      aria-label={t('money.plan.select_all')}
                      checked={selected.size === uncategorized.length && uncategorized.length > 0}
                      onChange={(e) =>
                        setSelected(e.target.checked ? new Set(uncategorized.map((u) => u.txn_id)) : new Set())
                      }
                    />
                  </th>
                  <th>{t('common.date')}</th>
                  <th>{t('common.payee')}</th>
                  <th className="num">{t('common.amount')}</th>
                </tr>
              </thead>
              <tbody>
                {uncategorized.map((u) => (
                  <tr key={u.txn_id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={u.payee}
                        checked={selected.has(u.txn_id)}
                        onChange={(e) =>
                          setSelected((prev) => {
                            const next = new Set(prev);
                            if (e.target.checked) next.add(u.txn_id);
                            else next.delete(u.txn_id);
                            return next;
                          })
                        }
                      />
                    </td>
                    <td>{formatDate(u.date, lang)}</td>
                    <td>{u.payee}</td>
                    <td className="num">
                      <Money value={u.amount} sign />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="row" style={{ gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
              <label className="field">
                {t('common.label')}
                <select value={labelId} onChange={(e) => setLabelId(e.target.value)} data-testid="organize-label">
                  <option value="">—</option>
                  {(labels.data ?? []).map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="row small" style={{ gap: 6 }}>
                <input type="checkbox" checked={createRule} onChange={(e) => setCreateRule(e.target.checked)} />
                {t('money.plan.create_rule')}
              </label>
              <div style={{ flex: 1 }} />
              <button
                type="button"
                className="btn primary"
                disabled={busy || selected.size === 0 || !labelId}
                data-testid="organize-apply"
                onClick={() => void organize()}
              >
                {t('money.plan.assign')} ({selected.size})
              </button>
            </div>
          </>
        )}
      </Section>

      <Section title={t('money.plan.rules')}>
        {(rules.data ?? []).length === 0 ? (
          <Empty />
        ) : (
          <table>
            <tbody>
              {(rules.data ?? []).map((r) => (
                <tr key={r.id}>
                  <td className="formula">{r.pattern}</td>
                  <td>{r.label_name ?? r.label_id}</td>
                  <td className="num">
                    <button
                      type="button"
                      className="btn ghost"
                      aria-label={`${t('money.plan.rule_delete')}: ${r.pattern}`}
                      onClick={() => {
                        void deleteOrganizerRule(ws, r.id).then(rules.reload).catch(() => rules.reload());
                      }}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  );
}
