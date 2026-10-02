'use client';

/**
 * One goal card of `/metas/`.
 *
 * Every figure is the server's: `progress`, `target`, `pct`, `monthly_required`. The card only
 * decides what to *say* — "Meta cumplida" at 100 %, "Necesitas ahorrar $A al mes para el <fecha>"
 * when the server produced `monthly_required` (i.e. the goal has a date), "Sin fecha límite"
 * otherwise. `target` arrives as an Amount object from the current server and as a bare decimal
 * string from older servers/the mock — it always goes through `<Money>`.
 *
 * "Aportar" opens + Agregar as a transfer prefilled to the goal's account with the monthly
 * figure (a goal without `account_id` — older rows, the mock — opens the transfer unprefilled);
 * the page reloads through `onSaved`. The projection is fetched lazily, when the
 * "Cómo va" details open. The what-if is debt-only (the server's `/whatif` simulates a loan and
 * answers `{error}` with HTTP 200 for anything else).
 */
import { useCallback, useEffect, useState } from 'react';
import { useAddEntry } from '@/components/AddEntry';
import tap from '@/components/plan/tap.module.css';
import { Badge, Button, Field, Icon, IconButton, MoneyInput, Sheet, Sparkline, useToast, type IconName } from '@/components/ui';
import { errorMessage, getGoalProjection, goalWhatIf } from '@/lib/api';
import { formatDate, formatPeriod } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import type { Amount, Goal, GoalKind } from '@/lib/types';
import * as v from '@/lib/validate';

export const GOAL_ICON: Record<GoalKind, IconName> = {
  savings: 'wallet',
  emergency: 'alert',
  debt: 'bank',
  purchase: 'target',
};

/** The decimal string of `target` whatever wire shape it came in (Amount object or bare string). */
export function goalTargetString(goal: Goal): string {
  const raw: unknown = goal.target;
  if (typeof raw === 'string') return raw;
  if (raw && typeof raw === 'object' && typeof (raw as Amount).amount === 'string') return (raw as Amount).amount;
  return '';
}

/** Pixel width of the progress bar: the server's percent clamped to the track. */
export function goalBarWidth(pct: Goal['pct']): number {
  const n = Number(pct);
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.min(n, 100);
}

export interface GoalCardProps {
  ws: string;
  goal: Goal;
  onEdit: () => void;
  onDelete: () => void;
  /** After a contribution was saved through + Agregar. */
  onChanged: () => void;
}

export function GoalCard({ ws, goal, onEdit, onDelete, onChanged }: GoalCardProps) {
  const { t, lang } = useI18n();
  const { fmt } = useMoney();
  const toast = useToast();
  const addEntry = useAddEntry();
  const [menu, setMenu] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const pctNum = Number(goal.pct);
  const done = Number.isFinite(pctNum) && pctNum >= 100;
  const kind: GoalKind = goal.kind;

  const projection = useResource(
    useCallback(() => (detailsOpen ? getGoalProjection(ws, goal.id) : Promise.resolve(null)), [ws, goal.id, detailsOpen]),
    [ws, goal.id, detailsOpen],
  );
  const path = projection.data?.path ?? [];
  const lastMonth = path.length ? path[path.length - 1].month : null;

  /* what-if (debt only) */
  const [extra, setExtra] = useState('');
  const [whatIfBusy, setWhatIfBusy] = useState(false);
  const [whatIf, setWhatIf] = useState<{ months: number; amount: Amount | null } | 'no_loan' | null>(null);
  const runWhatIf = async () => {
    if (v.decimal(extra, { positive: true })) return;
    setWhatIfBusy(true);
    try {
      const r = await goalWhatIf(ws, goal.id, extra.trim());
      if (r.error) setWhatIf('no_loan');
      else setWhatIf({ months: r.months_saved ?? 0, amount: r.interest_saved ?? null });
    } catch (e) {
      toast.error(errorMessage(e, t));
    } finally {
      setWhatIfBusy(false);
    }
  };

  const contribute = () => {
    addEntry.open({
      kind: 'transfer',
      prefill: {
        to_account_id: goal.account_id ?? undefined,
        amount: goal.monthly_required ?? undefined,
      },
      onSaved: onChanged,
    });
  };

  const status = goal.target_date_invalid ? (
    <p className="small err" data-testid="goal-status" data-status="date-invalid">
      {t('goal.date_invalid')}
    </p>
  ) : done ? (
    <p className="small" data-testid="goal-status" data-status="done">
      <Badge tone="pos">{t('goal.done')}</Badge>
    </p>
  ) : goal.monthly_required && goal.target_date ? (
    <p className="small" data-testid="goal-status" data-status="monthly">
      {t('goal.monthly_needed_by', { amount: fmt(goal.monthly_required), date: formatDate(goal.target_date, lang) })}
    </p>
  ) : (
    <p className="small muted" data-testid="goal-status" data-status="no-date">
      {t('goal.no_date')}
    </p>
  );

  return (
    <article className="card" data-testid="goal-card" data-goal-id={goal.id} data-pct={String(goal.pct ?? '')}>
      <div className="row">
        <Icon name={GOAL_ICON[kind] ?? 'target'} size={20} />
        <h2>{goal.name}</h2>
        <Badge tone="accent">{t(`goal.type.${kind}`)}</Badge>
        <span className="spacer" />
        <IconButton icon="more" ariaLabel={t('common.more_actions')} onClick={() => setMenu(true)} />
      </div>
      <div className={`bar ${done ? 'pos' : ''}`} aria-hidden="true">
        <span style={{ width: `${goalBarWidth(goal.pct)}%` }} />
      </div>
      <p>
        {t('goal.progress', { saved: fmt(goal.progress), target: fmt(goal.target) })}
        {goal.account_name && <span className="small muted"> · {t('goal.saved_in', { account: goal.account_name })}</span>}
      </p>
      {status}
      <div className="row">
        <Button variant="secondary" data-testid="goal-contribute" onClick={contribute}>
          {t('goal.contribute')}
        </Button>
      </div>

      <details onToggle={(e) => setDetailsOpen((e.currentTarget as HTMLDetailsElement).open)}>
        <summary className={tap.summary}>{t('goal.how')}</summary>
        {detailsOpen && (
          <div className="stack">
            {projection.loading || projection.refreshing ? (
              <p className="small muted">{t('common.loading')}</p>
            ) : path.length > 0 ? (
              <>
                <Sparkline
                  title={t('goal.projection')}
                  points={path.map((p) => ({ label: p.month, value: { amount: p.balance, currency: goal.currency } }))}
                />
                {lastMonth && mounted && <p className="small muted">{t('goal.pace', { month: formatPeriod(lastMonth, lang, 'long') })}</p>}
              </>
            ) : (
              <p className="small muted">{t('goal.pace.none')}</p>
            )}
            {kind === 'debt' && (
              <div className="stack">
                <Field label={t('goal.whatif.extra')}>
                  <MoneyInput value={extra} onChange={setExtra} currency={goal.currency} />
                </Field>
                <div className="row">
                  <Button variant="secondary" onClick={() => void runWhatIf()} loading={whatIfBusy} disabled={!extra.trim()}>
                    {t('goal.whatif.run')}
                  </Button>
                </div>
                {whatIf === 'no_loan' ? (
                  <p className="small muted">{t('goal.whatif.no_loan')}</p>
                ) : whatIf ? (
                  <p className="small">
                    {t('goal.whatif.result', { months: whatIf.months, amount: whatIf.amount ? fmt(whatIf.amount) : '—' })}
                  </p>
                ) : null}
              </div>
            )}
          </div>
        )}
      </details>

      <Sheet open={menu} onClose={() => setMenu(false)} title={goal.name}>
        <div className="ui-sheet-menu">
          <Button
            variant="ghost"
            onClick={() => {
              setMenu(false);
              onEdit();
            }}
          >
            {t('common.edit')}
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              setMenu(false);
              onDelete();
            }}
          >
            {t('goal.delete')}
          </Button>
        </div>
      </Sheet>
    </article>
  );
}
