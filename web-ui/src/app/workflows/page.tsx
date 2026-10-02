'use client';

/**
 * Automatizaciones — the workflows screen.
 *
 * A workflow is a YAML list of API calls. This screen edits that YAML, runs it, shows the
 * per-step trace the runner produced, keeps the run history, sets the cron schedule, and can
 * ask the model for a draft.
 *
 * Two product rules are enforced in the markup, not just in the copy:
 *  - **the AI proposal is never saved and never run.** `POST /propose` returns YAML into a
 *    separate read-only box with its own validation result; the only way it becomes a
 *    workflow is the user pressing "use it", which loads it into the editor for review.
 *  - **the catalog is a whitelist.** It is displayed next to the editor so the user can see
 *    which endpoints a step is even allowed to call.
 *
 * Shapes verified against the real API (2026-09): `GET /workflows/{ws}` is a bare summary
 * list (no yaml); the yaml and parsed `definition` only come back from the per-workflow
 * detail endpoint, so selecting a workflow fetches it. A run reports one trace entry per
 * step with an HTTP `status_code`/`duration_ms`/`response_excerpt`; the runs list has no
 * `steps` at all — "ver traza" fetches the run detail. Every optional field is guarded so an
 * unexpected shape renders as text instead of throwing.
 */
import { useCallback, useState } from 'react';
import { Empty, ErrorBox, Loading, Section } from '@/components/Bits';
import { CopyButton, useToast } from '@/components/Ui3';
import { Dialog } from '@/components/Form';
import {
  createWorkflow,
  deleteWorkflow,
  deleteWorkflowSchedule,
  errorMessage,
  getWorkflow,
  getWorkflowCatalog,
  getWorkflowRun,
  listWorkflowRuns,
  listWorkflows,
  proposeWorkflow,
  runWorkflow,
  scheduleWorkflow,
  updateWorkflow,
} from '@/lib/api';
import { useHealth, writeGuard } from '@/lib/health';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import { CRON_PRESETS, validateWorkflowYaml } from '@/lib/wfyaml';
import { useWorkspace } from '@/lib/workspace';
import type {
  WorkflowDetail,
  WorkflowProposal,
  WorkflowRun,
  WorkflowRunStep,
  WorkflowRunSummary,
  WorkflowSummary,
} from '@/lib/types';

const NEW_YAML = `id: nuevo-flujo
name: nuevo-flujo
description: ""
schedule: null
steps:
  - id: cierre_del_mes
    method: GET
    path: /tax/mx/resico/{{ ws }}/{{ period }}
`;

export default function WorkflowsPage() {
  const { t } = useI18n();
  const { ws } = useWorkspace();
  const { demoMode } = useHealth();
  const toast = useToast();

  const workflows = useResource(useCallback(() => listWorkflows(ws), [ws]), [ws]);
  const catalog = useResource(useCallback(() => getWorkflowCatalog(), []), []);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<WorkflowDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [yaml, setYaml] = useState('');
  const [localErrors, setLocalErrors] = useState<string[] | null>(null);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [runs, setRuns] = useState<WorkflowRunSummary[] | null>(null);
  const [scheduleFor, setScheduleFor] = useState<WorkflowSummary | null>(null);
  const [proposal, setProposal] = useState<WorkflowProposal | null>(null);
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const loadDetail = useCallback(
    (id: string) => {
      setDetailLoading(true);
      setDetailError(null);
      getWorkflow(ws, id)
        .then((d) => {
          setDetail(d);
          setYaml(d.yaml ?? '');
        })
        .catch((e: unknown) => setDetailError(errorMessage(e)))
        .finally(() => setDetailLoading(false));
    },
    [ws],
  );

  const pick = (w: WorkflowSummary) => {
    setSelectedId(w.id);
    setCreating(false);
    setDetail(null);
    setLocalErrors(null);
    setRun(null);
    setRuns(null);
    loadDetail(w.id);
  };

  const startNew = () => {
    setSelectedId(null);
    setCreating(true);
    setDetail(null);
    setYaml(NEW_YAML);
    setLocalErrors(null);
    setRun(null);
    setRuns(null);
  };

  const call = <T,>(tag: string, p: Promise<T>, ok: (v: T) => void) => {
    setBusy(tag);
    setErr(null);
    p.then(ok)
      .catch((e: unknown) => setErr(errorMessage(e)))
      .finally(() => setBusy(null));
  };

  const validate = () => {
    const v = validateWorkflowYaml(yaml);
    setLocalErrors(v.errors);
    toast.show(v.valid ? t('wf.valid') : t('wf.invalid'));
    return v.valid;
  };

  const selectedSummary = (workflows.data ?? []).find((w) => w.id === selectedId) ?? null;

  const save = () => {
    // Validate on save: a workflow that cannot parse locally never reaches the API.
    if (!validate()) return;
    if (creating || !selectedId) {
      call('save', createWorkflow(ws, { yaml }), (d) => {
        workflows.reload();
        setCreating(false);
        setSelectedId(d.id);
        setDetail(d);
        toast.show(t('common.save'));
      });
    } else {
      call('save', updateWorkflow(ws, selectedId, { yaml }), (d) => {
        workflows.reload();
        setDetail(d);
        toast.show(t('common.save'));
      });
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>{t('wf.title')}</h1>
        <div className="spacer" />
        <button
          type="button"
          className="btn primary"
          onClick={startNew}
          {...writeGuard(demoMode, t('settings.demo.tooltip'))}
        >
          {t('wf.new')}
        </button>
      </div>

      <div className="two-pane" style={{ marginTop: 12 }}>
        <Section
          title={t('wf.list')}
          actions={
            <button type="button" className="btn ghost" onClick={workflows.reload}>
              {t('common.refresh')}
            </button>
          }
        >
          {workflows.loading ? (
            <Loading />
          ) : workflows.error ? (
            <ErrorBox message={workflows.error} onRetry={workflows.reload} />
          ) : (workflows.data ?? []).length === 0 ? (
            <Empty text={t('wf.none')} />
          ) : (
            <ul className="wf-list">
              {(workflows.data ?? []).map((w) => (
                <li key={w.id}>
                  <button
                    type="button"
                    className={`wf-item ${selectedId === w.id ? 'active' : ''}`}
                    aria-current={selectedId === w.id ? 'true' : undefined}
                    onClick={() => pick(w)}
                  >
                    <span>{w.name ?? w.id}</span>
                    <span className="small muted">{w.schedule ? `⏱ ${w.schedule}` : t('wf.schedule.none')}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={t('wf.catalog')}>
          {catalog.loading ? (
            <Loading />
          ) : catalog.error ? (
            <ErrorBox message={catalog.error} onRetry={catalog.reload} />
          ) : !catalog.data ? (
            <Empty />
          ) : (
            <div className="table-scroll" style={{ maxHeight: 260 }}>
              <table>
                <thead>
                  <tr>
                    <th>{t('wf.catalog.methods')}</th>
                    <th>{t('wf.catalog.endpoint')}</th>
                  </tr>
                </thead>
                <tbody>
                  {(catalog.data.endpoints ?? []).map((e, i) => (
                    <tr key={`${e.method ?? '?'}-${e.path ?? i}`}>
                      <td className="small">{e.method ?? '—'}</td>
                      <td className="mono small">
                        {e.path ?? '—'}
                        {e.summary ? <span className="muted"> · {e.summary}</span> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>

      {(selectedId || creating) && (
        <Section
          title={t('wf.yaml')}
          actions={
            <div className="row" style={{ gap: 6 }}>
              <button type="button" className="btn ghost" onClick={validate}>
                {t('wf.validate')}
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={busy === 'save' || detailLoading}
                onClick={save}
                {...writeGuard(demoMode, t('settings.demo.tooltip'))}
              >
                {t('common.save')}
              </button>
              {selectedId && (
                <>
                  <button
                    type="button"
                    className="btn"
                    disabled={busy === 'run'}
                    onClick={() =>
                      call('run', runWorkflow(ws, selectedId), (r) => {
                        setRun(r);
                        toast.show(`${t('wf.run')} · ${r.status ?? '—'}`);
                      })
                    }
                    {...writeGuard(demoMode, t('settings.demo.tooltip'))}
                  >
                    {t('wf.run')}
                  </button>
                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() => call('runs', listWorkflowRuns(ws, selectedId), setRuns)}
                  >
                    {t('wf.runs')}
                  </button>
                  {selectedSummary && (
                    <button type="button" className="btn ghost" onClick={() => setScheduleFor(selectedSummary)}>
                      {t('wf.schedule')}
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() => {
                      if (!window.confirm(t('wf.delete_confirm'))) return;
                      call('delete', deleteWorkflow(ws, selectedId), () => {
                        setSelectedId(null);
                        setDetail(null);
                        workflows.reload();
                      });
                    }}
                    {...writeGuard(demoMode, t('settings.demo.tooltip'))}
                  >
                    {t('common.delete')}
                  </button>
                </>
              )}
            </div>
          }
        >
          {detailLoading ? (
            <Loading />
          ) : detailError ? (
            <ErrorBox message={detailError} onRetry={() => selectedId && loadDetail(selectedId)} />
          ) : (
            <>
              <label className="field">
                {t('wf.yaml')}
                <textarea
                  className="mono"
                  rows={16}
                  spellCheck={false}
                  value={yaml}
                  aria-invalid={Boolean(localErrors && localErrors.length > 0)}
                  onChange={(e) => setYaml(e.target.value)}
                />
              </label>
              {localErrors && (
                <div className={localErrors.length === 0 ? 'ok' : 'err'}>
                  {localErrors.length === 0 ? (
                    t('wf.valid')
                  ) : (
                    <ul>
                      {localErrors.map((e) => (
                        <li key={e}>{e}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {detail?.errors && detail.errors.length > 0 && (
                <div className="err">
                  <p className="small">{t('wf.invalid')}</p>
                  <ul>
                    {detail.errors.map((e) => (
                      <li key={e}>{e}</li>
                    ))}
                  </ul>
                </div>
              )}
              {detail?.warnings && detail.warnings.length > 0 && (
                <ul className="small muted">
                  {detail.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              )}
              {detail?.definition?.steps && detail.definition.steps.length > 0 && (
                <div className="table-scroll" style={{ marginTop: 10 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>{t('wf.run.step')}</th>
                        <th>{t('common.status')}</th>
                        <th>{t('wf.run.endpoint')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.definition.steps.map((s, i) => (
                        <tr key={s.id ?? i}>
                          <td className="mono small">{s.id ?? `#${i}`}</td>
                          <td className="small">{s.method ?? '—'}</td>
                          <td className="mono small">{s.path ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
          {err && <p className="err">{err}</p>}
        </Section>
      )}

      {run && <RunTrace run={run} title={t('wf.run.trace')} />}

      {runs && (
        <Section title={t('wf.runs')}>
          {runs.length === 0 ? (
            <Empty />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t('wf.run.started')}</th>
                    <th>{t('common.status')}</th>
                    <th>{t('wf.run.detail')}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id}>
                      <td className="small">{(r.started_at ?? '').replace('T', ' ').slice(0, 19) || '—'}</td>
                      <td>
                        <span className={`badge ${r.status === 'success' ? 'pos' : r.status === 'failed' ? 'neg' : 'neutral'}`}>
                          {r.status ?? '—'}
                        </span>
                      </td>
                      <td className="small">{r.error ?? '—'}</td>
                      <td>
                        {selectedId && (
                          <button
                            type="button"
                            className="btn ghost"
                            disabled={busy === `run-${r.id}`}
                            onClick={() => call(`run-${r.id}`, getWorkflowRun(ws, selectedId, r.id), setRun)}
                          >
                            {t('wf.runs.trace')}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}

      <Section title={t('wf.propose')}>
        <p className="small muted">{t('wf.propose.note')}</p>
        <label className="field">
          {t('wf.propose.describe')}
          <textarea
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t('wf.propose.describe')}
          />
        </label>
        <button
          type="button"
          className="btn primary"
          disabled={busy === 'propose' || description.trim() === ''}
          onClick={() => call('propose', proposeWorkflow(ws, description), setProposal)}
        >
          {t('wf.propose.button')}
        </button>

        {proposal && (
          <div style={{ marginTop: 14 }}>
            <div className="row" style={{ gap: 8 }}>
              <h3 style={{ margin: 0 }}>{t('wf.propose.result')}</h3>
              <span className={`badge ${proposal.valid ? 'pos' : 'warn'}`}>
                {proposal.valid ? t('wf.valid') : t('wf.invalid')}
              </span>
              {proposal.source && <span className="badge neutral">{proposal.source}</span>}
              <div style={{ flex: 1 }} />
              <CopyButton text={proposal.yaml} onDone={(ok) => toast.show(ok ? t('common.copied') : t('common.error'))} />
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setCreating(true);
                  setSelectedId(null);
                  setDetail(null);
                  setYaml(proposal.yaml);
                  setLocalErrors(null);
                }}
              >
                {t('common.open')}
              </button>
            </div>
            <pre className="yaml-preview">{proposal.yaml}</pre>
            {(proposal.errors ?? []).length > 0 && (
              <ul className="err">
                {proposal.errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            )}
            {(proposal.warnings ?? []).map((n) => (
              <p className="small muted" key={n}>
                {n}
              </p>
            ))}
          </div>
        )}
      </Section>

      {scheduleFor && (
        <ScheduleDialog
          ws={ws}
          workflow={scheduleFor}
          onClose={(saved) => {
            setScheduleFor(null);
            if (saved) {
              workflows.reload();
              toast.show(t('wf.schedule'));
            }
          }}
        />
      )}

      {toast.node}
    </>
  );
}

function RunTrace({ run, title }: { run: WorkflowRun; title: string }) {
  const { t } = useI18n();
  const steps: WorkflowRunStep[] = run.steps ?? [];
  return (
    <Section
      title={`${title} · ${run.id}`}
      actions={
        <span className={`badge ${run.status === 'success' ? 'pos' : run.status === 'failed' ? 'neg' : 'neutral'}`}>
          {run.status ?? '—'}
        </span>
      }
    >
      <p className="small muted">
        {t('wf.run.started')}: {(run.started_at ?? '').replace('T', ' ').slice(0, 19) || '—'}
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th className="num">#</th>
              <th>{t('wf.run.step')}</th>
              <th>{t('wf.run.endpoint')}</th>
              <th>{t('wf.run.status_code')}</th>
              <th className="num">{t('wf.run.duration')}</th>
              <th>{t('wf.run.response')}</th>
            </tr>
          </thead>
          <tbody>
            {steps.map((s, i) => (
              <tr key={`${s.step_index ?? i}-${s.step_id ?? i}`}>
                <td className="num">{s.step_index ?? i}</td>
                <td className="mono small">{s.step_id ?? '—'}</td>
                <td className="mono small">
                  {s.method ?? '—'} {s.path ?? '—'}
                </td>
                <td>
                  <span
                    className={`badge ${
                      s.status_code == null ? 'neutral' : s.status_code < 400 ? 'pos' : 'neg'
                    }`}
                  >
                    {s.status_code ?? '—'}
                  </span>
                </td>
                <td className="num">{s.duration_ms ?? '—'} ms</td>
                <td className="small">
                  {s.error ? (
                    <span className="err">{s.error}</span>
                  ) : s.response_excerpt ? (
                    <details>
                      <summary>{t('wf.run.response')}</summary>
                      <pre className="yaml-preview">{s.response_excerpt}</pre>
                    </details>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {run.error && <p className="err">{run.error}</p>}
    </Section>
  );
}

function ScheduleDialog({
  ws,
  workflow,
  onClose,
}: {
  ws: string;
  workflow: WorkflowSummary;
  onClose: (saved: boolean) => void;
}) {
  const { t } = useI18n();
  const [cron, setCron] = useState(workflow.schedule ?? '');
  const [gated, setGated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = (next: string | null) => {
    setBusy(true);
    setError(null);
    const p = next === null ? deleteWorkflowSchedule(ws, workflow.id) : scheduleWorkflow(ws, workflow.id, next);
    p.then((r) => {
      const isGated = Boolean(r && typeof r === 'object' && 'gated' in r && (r as { gated?: boolean }).gated);
      if (isGated) {
        // Leave the dialog open one extra beat so the "scheduler is off" note is actually
        // read, instead of closing straight into a toast the user may miss.
        setGated(true);
        setBusy(false);
      } else {
        onClose(true);
      }
    }).catch((e: unknown) => {
      setError(errorMessage(e));
      setBusy(false);
    });
  };

  return (
    <Dialog
      title={`${t('wf.schedule')} · ${workflow.name ?? workflow.id}`}
      onCancel={() => onClose(false)}
      busy={busy}
      error={error}
      onSubmit={() => submit(cron.trim() || null)}
    >
      <label className="field">
        {t('wf.schedule.cron')}
        <input
          value={cron}
          onChange={(e) => setCron(e.target.value)}
          placeholder="0 8 * * *"
          aria-describedby="cron-presets"
        />
      </label>
      <div id="cron-presets" className="row small" style={{ gap: 6, flexWrap: 'wrap' }}>
        <span className="muted">{t('wf.schedule.presets')}:</span>
        {CRON_PRESETS.map((p) => (
          <button key={p.cron} type="button" className="btn ghost" onClick={() => setCron(p.cron)}>
            {p.label}
          </button>
        ))}
      </div>
      {workflow.schedule && (
        <button
          type="button"
          className="btn ghost"
          style={{ marginTop: 10 }}
          disabled={busy}
          onClick={() => submit(null)}
        >
          {t('wf.schedule.remove')}
        </button>
      )}
      {gated && (
        <>
          <p className="small muted" style={{ marginTop: 10 }}>
            {t('wf.schedule.gated')}
          </p>
          <button type="button" className="btn primary" onClick={() => onClose(true)}>
            {t('wf.schedule.close')}
          </button>
        </>
      )}
    </Dialog>
  );
}
