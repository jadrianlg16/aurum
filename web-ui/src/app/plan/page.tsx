'use client';

/**
 * `/plan/` — the advanced planning tabs.
 *
 * Budgets and goals moved to `/presupuesto/` and `/metas/`: `?tab=budgets|goals` is redirected
 * on mount (every other query param is kept). The remaining tabs render only when allowed —
 * holdings ⇐ `useModule('holdings')`, scenarios ⇐ `useAdvanced()`, credit ⇐ either — and a
 * simple workspace sees one EmptyState and fires **zero** requests: each tab is its own
 * component with its own `useResource`, mounted only while open (lazy). No `closePeriod`,
 * no `getLedgerAccounts`, no `listLabels` on this page. The EmptyState's button turns the
 * `holdings` module on (`PUT /workspaces/{ws} {modules}`), since `/avanzado/` links here from
 * a simple workspace — Inversiones and Crédito then appear; Escenarios stays advanced-only.
 */
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { useModeSave } from '@/components/AppMode';
import { CreditReportPanel } from '@/components/CreditReport';
import { Explain } from '@/components/Explain';
import { HoldingsPanel } from '@/components/Holdings';
import { ScenariosPanel } from '@/components/Scenarios';
import { ConfirmDelete } from '@/components/PfForms';
import { CardDialog, LoanDialog, MsiDialog, ScoreDialog } from '@/components/plan/CreditDialogs';
import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  ErrorBox,
  Field,
  Money,
  MoneyInput,
  PageHeader,
  ResponsiveTable,
  Skeleton,
  Stat,
  TabPanel,
  Tabs,
  type Column,
} from '@/components/ui';
import { getAmortization, getCards, getLoans, listPfAccounts, listScores } from '@/lib/api';
import { formatDate, formatPct } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { queryParam, queryTab } from '@/lib/query';
import { useResource } from '@/lib/useResource';
import { useAdvanced, useModule, useWorkspace } from '@/lib/workspace';
import type { AmortRow, CreditCard, CreditScore, Loan, MsiPlan } from '@/lib/types';

type Tab = 'holdings' | 'scenarios' | 'credit';
const ALL_TABS: readonly Tab[] = ['holdings', 'scenarios', 'credit'] as const;

/** `/plan/?tab=budgets&ws=x` → `/presupuesto/?ws=x` (the tab param dropped, the rest kept). */
function restOfQuery(): string {
  if (typeof window === 'undefined') return '';
  try {
    const params = new URLSearchParams(window.location.search);
    params.delete('tab');
    const s = params.toString();
    return s ? `?${s}` : '';
  } catch {
    return '';
  }
}

export default function PlanPage() {
  const { t } = useI18n();
  const router = useRouter();
  const { ws, loading: wsLoading } = useWorkspace();
  const holdingsOn = useModule('holdings');
  const advanced = useAdvanced();
  const creditOn = advanced || holdingsOn;
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<Tab>('credit');
  const { save: saveMode, busy: modeBusy, error: modeError, modules } = useModeSave();

  useEffect(() => {
    const wanted = queryParam('tab');
    if (wanted === 'budgets') {
      router.replace(`/presupuesto/${restOfQuery()}`);
      return;
    }
    if (wanted === 'goals') {
      router.replace(`/metas/${restOfQuery()}`);
      return;
    }
    const deep = queryTab(ALL_TABS);
    if (deep) setTab(deep);
    setReady(true);
  }, [router]);

  const allowed: Tab[] = ALL_TABS.filter((id) =>
    id === 'holdings' ? holdingsOn : id === 'scenarios' ? advanced : creditOn,
  );
  const active: Tab | null = allowed.includes(tab) ? tab : allowed[0] ?? null;

  const items = allowed.map((id) => ({ id, label: t(`plan.${id}`) }));

  return (
    <>
      <PageHeader title={t('plan.title')} />
      {!ready || wsLoading ? null : allowed.length === 0 ? (
        <>
          <EmptyState
            icon="grid"
            title={t('plan.advanced_only.title')}
            body={t('plan.advanced_only.body')}
            primary={{
              label: t('plan.advanced_only.cta'),
              onClick: modeBusy ? undefined : () => void saveMode({ modules: { ...modules, holdings: true } }),
            }}
          />
          {modeError && (
            <p className="err" role="alert">
              {modeError}
            </p>
          )}
        </>
      ) : (
        <div className="stack">
          <Tabs items={items} value={active ?? allowed[0]} onChange={setTab} queryKey="tab" label={t('plan.tabs')} />
          {active === 'holdings' && (
            <TabPanel id="holdings">
              <HoldingsPanel ws={ws} />
            </TabPanel>
          )}
          {active === 'scenarios' && (
            <TabPanel id="scenarios">
              <ScenariosPanel ws={ws} />
            </TabPanel>
          )}
          {active === 'credit' && (
            <TabPanel id="credit">
              <CreditTab ws={ws} />
            </TabPanel>
          )}
        </div>
      )}
    </>
  );
}

/* ----------------------------------------------------------------- credit */

function CreditTab({ ws }: { ws: string }) {
  const { t, lang } = useI18n();
  const cards = useResource(useCallback(() => getCards(ws), [ws]), [ws]);
  const loans = useResource(useCallback(() => getLoans(ws), [ws]), [ws]);
  const scores = useResource(useCallback(() => listScores(ws), [ws]), [ws]);
  // Card/loan rows carry the ledger `account`; the pf account id (for "Editar términos") is
  // matched through `ledger_account`.
  const pfAccounts = useResource(useCallback(() => listPfAccounts(ws, { includeArchived: true }), [ws]), [ws]);
  const accountIdFor = (ledger: string): string | null =>
    pfAccounts.data?.find((a) => a.ledger_account === ledger || a.account === ledger)?.id ?? null;

  const [cardForm, setCardForm] = useState<{ mode: 'create' | 'edit'; accountId?: string | null } | null>(null);
  const [loanForm, setLoanForm] = useState<{ mode: 'create' | 'edit'; accountId?: string | null } | null>(null);
  const [msiForm, setMsiForm] = useState<{ cardId: string; currency: string } | null>(null);
  const [scoreForm, setScoreForm] = useState(false);
  const [confirm, setConfirm] = useState<CreditScore | null>(null);

  const reloadAccounts = () => {
    cards.reload();
    loans.reload();
    pfAccounts.reload();
  };

  const msiColumns: Column<MsiPlan>[] = [
    { key: 'description', header: t('common.description') },
    { key: 'months_total', header: t('plan.msi.months'), numeric: true },
    { key: 'months_left', header: t('plan.msi.left'), numeric: true },
    { key: 'monthly', header: t('plan.msi.monthly'), numeric: true, render: (m) => <Money amount={m.monthly} /> },
    { key: 'remaining', header: t('plan.budget.remaining'), numeric: true, render: (m) => <Money amount={m.remaining} /> },
  ];
  const scoreColumns: Column<CreditScore>[] = [
    { key: 'date', header: t('common.date'), mobile: 'subtitle', render: (s) => formatDate(s.date, lang) },
    { key: 'bureau', header: t('score.bureau'), mobile: 'title' },
    { key: 'score', header: t('score.score'), numeric: true, mobile: 'value' },
  ];

  return (
    <div className="stack">
      <section className="card">
        <div className="row">
          <h2>{t('plan.cards')}</h2>
          <Button variant="secondary" size="sm" onClick={() => setCardForm({ mode: 'edit' })}>
            {t('card.edit_terms')}
          </Button>
          <Button variant="secondary" size="sm" icon="plus" onClick={() => setCardForm({ mode: 'create' })}>
            {t('card.new')}
          </Button>
        </div>
        {cards.loading ? (
          <Skeleton variant="card" rows={1} what={t('plan.cards')} />
        ) : cards.error ? (
          <ErrorBox error={cards.problem ?? cards.error} onRetry={cards.reload} />
        ) : (cards.data?.length ?? 0) === 0 ? (
          <p className="muted small">{t('common.empty')}</p>
        ) : (
          <div className="stack">
            {cards.data!.map((c: CreditCard) => (
              <article key={c.id} className="card">
                <div className="row">
                  <h3>{c.name}</h3>
                  <Badge tone="neutral">
                    {t('plan.card.cut')} {formatDate(c.next_cut_date, lang)}
                  </Badge>
                  <Badge tone="warn">
                    {t('plan.card.due')} {formatDate(c.next_due_date, lang)}
                  </Badge>
                  <Button variant="ghost" size="sm" onClick={() => setMsiForm({ cardId: c.id, currency: c.balance.currency })}>
                    {t('msi.new')}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setCardForm({ mode: 'edit', accountId: accountIdFor(c.account) })}>
                    {t('card.edit_terms')}
                  </Button>
                </div>
                <div className="grid cols-4">
                  <Stat label={t('plan.card.balance')} value={<Money amount={c.balance} />} />
                  <Stat label={t('plan.card.no_interest')} value={<Money amount={c.pago_no_intereses} />} />
                  <Stat label={t('plan.card.limit')} value={<Money amount={c.limit} />} />
                  <Stat label={t('plan.card.utilization')} value={formatPct(c.utilization, lang, 1)} />
                </div>
                {c.msi.length > 0 && (
                  <>
                    <h3>{t('plan.card.msi')}</h3>
                    <DataTable caption={t('plan.card.msi')} columns={msiColumns} rows={c.msi} rowKey={(m, i) => `${m.description}-${i}`} />
                  </>
                )}
                <Explain explain={c.explain} />
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <div className="row">
          <h2>{t('score.title')}</h2>
          <Button variant="secondary" size="sm" icon="plus" onClick={() => setScoreForm(true)}>
            {t('score.new')}
          </Button>
        </div>
        {scores.loading ? (
          <Skeleton variant="list" rows={2} what={t('score.title')} />
        ) : scores.error ? (
          <ErrorBox error={scores.problem ?? scores.error} onRetry={scores.reload} />
        ) : (scores.data?.length ?? 0) === 0 ? (
          <p className="muted small">{t('common.empty')}</p>
        ) : (
          <ResponsiveTable
            label={t('score.title')}
            columns={scoreColumns}
            rows={scores.data!}
            rowKey={(s) => s.id}
            actions={(s) => [{ label: t('score.delete'), onClick: () => setConfirm(s), destructive: true }]}
          />
        )}
      </section>

      <LoansSection
        ws={ws}
        loans={loans}
        accountIdFor={accountIdFor}
        onNew={() => setLoanForm({ mode: 'create' })}
        onEdit={(id) => setLoanForm({ mode: 'edit', accountId: id })}
      />

      <CreditReportPanel ws={ws} />

      {cardForm && (
        <CardDialog
          ws={ws}
          mode={cardForm.mode}
          accountId={cardForm.accountId}
          onClose={(saved) => {
            setCardForm(null);
            if (saved) reloadAccounts();
          }}
        />
      )}
      {loanForm && (
        <LoanDialog
          ws={ws}
          mode={loanForm.mode}
          accountId={loanForm.accountId}
          onClose={(saved) => {
            setLoanForm(null);
            if (saved) reloadAccounts();
          }}
        />
      )}
      {msiForm && (
        <MsiDialog
          ws={ws}
          cardId={msiForm.cardId}
          currency={msiForm.currency}
          onClose={(saved) => {
            setMsiForm(null);
            if (saved) cards.reload();
          }}
        />
      )}
      {scoreForm && (
        <ScoreDialog
          ws={ws}
          onClose={(saved) => {
            setScoreForm(false);
            if (saved) scores.reload();
          }}
        />
      )}
      {confirm && (
        <ConfirmDelete
          ws={ws}
          kind="score"
          id={confirm.id}
          what={`${confirm.bureau} · ${confirm.score}`}
          onClose={(saved) => {
            setConfirm(null);
            if (saved) scores.reload();
          }}
        />
      )}
    </div>
  );
}

function LoansSection({
  ws,
  loans,
  accountIdFor,
  onNew,
  onEdit,
}: {
  ws: string;
  loans: ReturnType<typeof useResource<Loan[]>>;
  accountIdFor: (ledger: string) => string | null;
  onNew: () => void;
  onEdit: (accountId: string | null) => void;
}) {
  const { t, lang } = useI18n();
  // The extra payment is the string the user typed, passed through untouched (the API does the math).
  const [extra, setExtra] = useState('');
  const [appliedExtra, setAppliedExtra] = useState<string | null>(null);
  const [loanId, setLoanId] = useState<string | null>(null);
  const activeLoanId = loanId ?? loans.data?.[0]?.id ?? null;
  const activeLoan = loans.data?.find((l) => l.id === activeLoanId) ?? null;
  const amort = useResource(
    useCallback(
      () => (activeLoanId ? getAmortization(ws, activeLoanId, appliedExtra ?? undefined) : Promise.resolve(null)),
      [ws, activeLoanId, appliedExtra],
    ),
    [ws, activeLoanId, appliedExtra],
  );
  const cur = activeLoan?.currency ?? 'MXN';
  const amortColumns: Column<AmortRow>[] = [
    { key: 'month', header: '#', numeric: true },
    { key: 'payment', header: t('plan.loan.payment'), numeric: true, render: (r) => <Money amount={r.payment} currency={cur} /> },
    { key: 'interest', header: t('plan.loan.interest'), numeric: true, render: (r) => <Money amount={r.interest} currency={cur} /> },
    { key: 'principal', header: t('plan.loan.principal'), numeric: true, render: (r) => <Money amount={r.principal} currency={cur} /> },
    { key: 'balance', header: t('plan.card.balance'), numeric: true, render: (r) => <Money amount={r.balance} currency={cur} /> },
  ];

  return (
    <section className="card">
      <div className="row">
        <h2>{t('plan.loans')}</h2>
        <Button variant="secondary" size="sm" onClick={() => onEdit(null)}>
          {t('loan.edit_terms')}
        </Button>
        <Button variant="secondary" size="sm" icon="plus" onClick={onNew}>
          {t('loan.new')}
        </Button>
      </div>
      {loans.loading ? (
        <Skeleton variant="card" rows={1} what={t('plan.loans')} />
      ) : loans.error ? (
        <ErrorBox error={loans.problem ?? loans.error} onRetry={loans.reload} />
      ) : (loans.data?.length ?? 0) === 0 ? (
        <p className="muted small">{t('common.empty')}</p>
      ) : (
        <div className="stack">
          {loans.data!.map((l) => (
            <article key={l.id} className="card">
              <div className="row">
                <h3>{l.name}</h3>
                <Badge tone="neutral">
                  {t('plan.loan.rate')} {formatPct(l.annual_rate, lang, 1)}
                </Badge>
                <Badge tone="neutral">
                  {t('plan.loan.months')} {l.months}
                </Badge>
                <Button
                  variant={activeLoanId === l.id ? 'secondary' : 'ghost'}
                  size="sm"
                  aria-pressed={activeLoanId === l.id}
                  onClick={() => {
                    setLoanId(l.id);
                    setAppliedExtra(null);
                  }}
                >
                  {t('plan.loan.amortization')}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => onEdit(accountIdFor(l.account))}>
                  {t('loan.edit_terms')}
                </Button>
              </div>
              <div className="grid cols-3">
                <Stat label={t('plan.loan.principal')} value={<Money amount={{ amount: l.principal, currency: l.currency }} compactCents />} />
                <Stat label={t('loan.start')} value={formatDate(l.start, lang)} />
              </div>
            </article>
          ))}

          <article className="card">
            <h3>{t('plan.loan.amortization')}</h3>
            <div className="row">
              <Field label={t('plan.loan.extra')}>
                <MoneyInput value={extra} onChange={setExtra} currency={cur} placeholder="1000.00" />
              </Field>
              <Button variant="secondary" onClick={() => setAppliedExtra(extra.trim() ? extra.trim() : null)}>
                {t('plan.loan.whatif')}
              </Button>
            </div>
            {amort.loading ? (
              <Skeleton variant="table" rows={4} what={t('plan.loan.amortization')} />
            ) : amort.error ? (
              <ErrorBox error={amort.problem ?? amort.error} onRetry={amort.reload} />
            ) : !amort.data ? (
              <p className="muted small">{t('common.empty')}</p>
            ) : (
              <div className="stack">
                <div className="row">
                  <Badge tone="neutral">
                    {t('plan.loan.payment')} <Money amount={amort.data.payment} currency={cur} />
                  </Badge>
                  <Badge tone="neutral">
                    {t('plan.loan.total_interest')} <Money amount={amort.data.total_interest} currency={cur} />
                  </Badge>
                  <Badge tone="neutral">{amort.data.rows.length} ×</Badge>
                </div>
                <Explain explain={amort.data.explain} />
                <DataTable caption={t('plan.loan.amortization')} columns={amortColumns} rows={amort.data.rows} rowKey={(r) => String(r.month)} />
              </div>
            )}
          </article>
        </div>
      )}
    </section>
  );
}
