/**
 * The in-browser fake API serves every response shape: entries
 * envelope + keyset cursor + totals, void semantics, liability sign, label kinds, idempotent
 * budget copy, budget status, goals account_id, partial stream PUT + real history rows, the
 * onboarding step ids, workspaces ordered personal-first with hidden/protected, occurrences mark /
 * un-mark, safe_to_spend parts + step ids, quickadd, bank CSV, health auth/bind/schema,
 * `{error}` bodies for the security simulations, 422 arrays for bad limits.
 *
 * Driven through the real client (`lib/api.ts`) so the wire is exercised end to end.
 */
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import * as api from '@/lib/api';
import { installMockApi, setMockSimulation } from '@/lib/mock';
import { SAFE_TO_SPEND_STEPS } from '@/lib/types-organizer';

const WS = 'mock-personal';
const money = (amount: string) => ({ amount, currency: 'MXN' });

// The fake API seeds data relative to "today" (some of it when the module loads) and these cases
// use fixed periods (2026-08/09), so the clock is pinned before any import to the day the fixtures
// describe. Only Date is faked; timers stay real.
vi.hoisted(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-09-19T12:00:00'));
});

beforeAll(() => {
  installMockApi();
});

afterAll(() => {
  vi.useRealTimers();
});

describe('core', () => {
  it('health carries auth/bind/schema and no data_dir', async () => {
    const h = await api.getHealth();
    expect(h.auth).toEqual({ required: false, source: 'none' });
    expect(h.bind).toBe('127.0.0.1');
    expect(h.schema).toEqual({ pf: 4, organizer: 1 });
    expect('data_dir' in h).toBe(false);
  });

  it('workspaces are ordered personal-first with protected/hidden, hidden omitted unless asked', async () => {
    const list = await api.listWorkspaces();
    expect(list[0].id).toBe(WS);
    expect(list[0].profile.demo).toBe(false);
    expect(list[0].protected).toBe(true);
    expect(list.slice(1).every((w) => w.profile.demo === true)).toBe(true);
    const created = await api.createWorkspace({ id: 'ui-check-test', name: 'x', kind: 'personal', jurisdictions: ['MX'], base_currency: 'MXN', language: 'es', profile: {} });
    expect(created.id).toBe('ui-check-test');
    await api.updateWorkspace('ui-check-test', { hidden: true });
    expect((await api.listWorkspaces()).some((w) => w.id === 'ui-check-test')).toBe(false);
    expect((await api.listWorkspaces({ includeHidden: true })).some((w) => w.id === 'ui-check-test')).toBe(true);
    await expect(api.updateWorkspace(WS, { protected: false } as never)).rejects.toMatchObject({ status: 400 });
  });

  it('an invalid workspace id answers 400 {error: invalid_workspace_id}', async () => {
    const err = (await api.listPfAccounts('Bad Id').catch((e: unknown) => e)) as api.ApiError;
    expect(err.status).toBe(400);
    expect(err.code).toBe('invalid_workspace_id');
  });

  it('simulations answer middleware {error} bodies', async () => {
    setMockSimulation('unauthorized');
    const e401 = (await api.getHealth().catch((e: unknown) => e)) as api.ApiError;
    expect(e401.status).toBe(401);
    expect(e401.code).toBe('unauthorized');
    setMockSimulation('origin_not_allowed');
    const e403 = (await api.getHealth().catch((e: unknown) => e)) as api.ApiError;
    expect(e403.status).toBe(403);
    expect(api.errorKey(e403)).toBe('err.forbidden.origin');
    setMockSimulation(null);
    await expect(api.getHealth()).resolves.toMatchObject({ ok: true });
  });

  it('ledger health and backups answer the expected shapes', async () => {
    expect(await api.getLedgerHealth(WS)).toMatchObject({ errors: [], error_count: 0 });
    expect(await api.createBackup()).toMatchObject({ size: expect.any(Number), sha256: expect.any(String) });
    expect(await api.listBackups()).toEqual([]);
    expect(api.backupUrl(WS)).toBe(`/api/workspaces/${WS}/backup.zip`);
    expect(api.movimientosCsvUrl(WS, '2026-09-01', '2026-09-30')).toBe(`/api/workspaces/${WS}/movimientos.csv?from=2026-09-01&to=2026-09-30`);
  });
});

describe('accounts (liability sign)', () => {
  it('the seed card shows balance positive-owed, balance_signed negative, owed:true, and net worth is signed', async () => {
    const accounts = await api.listPfAccounts(WS);
    const card = accounts.find((a) => a.type === 'credit_card')!;
    expect(card.owed).toBe(true);
    expect(card.balance!.amount.startsWith('-')).toBe(false);
    expect(card.balance_signed!.amount.startsWith('-')).toBe(true);
    expect(card.opening_balance!.amount).toBe('8420.00');
    expect(card.apr_percent).toBe('36.9');
    expect(card.apr).toBe('0.369');
    expect(card.account).toBe(card.ledger_account);
    const overview = await api.getAccountsOverview(WS);
    const sum = accounts.reduce((acc, a) => acc + BigInt(a.balance_signed!.amount.replace('.', '')), 0n);
    expect(BigInt(overview.net_worth.amount.replace('.', ''))).toBe(sum);
  });

  it('a loan typed as owed is negated on write; negative owed is a 422 array', async () => {
    const loan = await api.createPfAccount(WS, { name: 'Crédito auto', type: 'loan', currency: 'MXN', opening_balance: money('50000.00'), apr_percent: '14' });
    expect(loan.balance!.amount).toBe('50000.00');
    expect(loan.balance_signed!.amount).toBe('-50000.00');
    expect(loan.apr).toBe('0.14');
    const err = (await api.createPfAccount(WS, { name: 'Malo', type: 'credit_card', currency: 'MXN', opening_balance: money('-1.00') }).catch((e: unknown) => e)) as api.ApiError;
    expect(err.status).toBe(422);
    expect(err.code).toBe('validation');
    expect(err.field).toBe('opening_balance');
  });

  it('adjust on a liability takes the owed figure; duplicate names 409; archive via PUT and DELETE rules', async () => {
    const accounts = await api.listPfAccounts(WS);
    const card = accounts.find((a) => a.type === 'credit_card')!;
    const adjusted = await api.adjustPfAccount(WS, card.id, { balance: money('9000.00'), date: '2026-09-12' });
    expect(adjusted.balance!.amount).toBe('9000.00');
    expect(adjusted.balance_signed!.amount).toBe('-9000.00');
    await expect(api.createPfAccount(WS, { name: 'BBVA', type: 'checking', currency: 'MXN' })).rejects.toMatchObject({ status: 409 });
    const fresh = await api.createPfAccount(WS, { name: 'Alcancía', type: 'cash', currency: 'MXN', opening_balance: money('10.00') });
    const archived = await api.updatePfAccount(WS, fresh.id, { archived: true });
    expect(archived.archived).toBe(true);
    expect((await api.listPfAccounts(WS)).some((a) => a.id === fresh.id)).toBe(false);
    expect((await api.listPfAccounts(WS, { includeArchived: true })).some((a) => a.id === fresh.id)).toBe(true);
    const bbva = accounts.find((a) => a.name === 'BBVA')!;
    const err = (await api.deletePfAccount(WS, bbva.id).catch((e: unknown) => e)) as api.ApiError;
    expect(err.status).toBe(409);
    expect(err.code).toBe('account_has_movements');
  });
});

describe('entries', () => {
  it('lists an envelope with totals over the full set and pages with a keyset cursor', async () => {
    const all = await api.listEntries(WS, { limit: 500 });
    expect(all.next_cursor).toBeNull();
    expect(all.totals.count).toBe(all.entries.length);
    const p1 = await api.listEntries(WS, { limit: 2 });
    expect(p1.entries.length).toBe(2);
    expect(p1.next_cursor).toBe(`${p1.entries[1].date}|${p1.entries[1].id}`);
    expect(p1.totals.count).toBe(all.totals.count);
    const p2 = await api.listEntries(WS, { limit: 2, cursor: p1.next_cursor! });
    expect(p2.entries[0].id).toBe(all.entries[2].id);
    const inCents = BigInt(all.totals.in.amount.replace('.', ''));
    const outCents = BigInt(all.totals.out.amount.replace('.', ''));
    // server convention (aurum/pf/entries.py): out = Σ|amount| positive, net = in − out
    expect(BigInt(all.totals.net.amount.replace('.', ''))).toBe(inCents - outCents);
    expect(outCents > 0n).toBe(true);
  });

  it('limit > 500 is a pydantic 422 array', async () => {
    const err = (await api.listEntries(WS, { limit: 501 }).catch((e: unknown) => e)) as api.ApiError;
    expect(err.status).toBe(422);
    expect(err.code).toBe('validation');
    expect(err.field).toBe('limit');
    expect(api.errorMessage(err)).toContain('Revisa');
  });

  it('create → void → 409 on the second delete; voided rows leave lists, totals and balances', async () => {
    const [acct] = await api.listPfAccounts(WS);
    const before = await api.listEntries(WS, { account_id: acct.id, limit: 500 });
    const balBefore = (await api.listPfAccounts(WS)).find((a) => a.id === acct.id)!.balance!.amount;
    const e = await api.createEntry(WS, { kind: 'expense', date: '2026-09-10', amount: money('100.00'), account_id: acct.id, payee: 'Prueba' });
    expect(e.amount.amount).toBe('-100.00');
    expect(e.voided).toBe(false);
    expect(e.source).toBe('manual');
    expect((await api.listEntries(WS, { account_id: acct.id, limit: 500 })).totals.count).toBe(before.totals.count + 1);
    const res = await api.deleteEntry(WS, e.id);
    expect(res).toEqual({ id: e.id, voided: true });
    const again = (await api.deleteEntry(WS, e.id).catch((x: unknown) => x)) as api.ApiError;
    expect(again.status).toBe(409);
    expect(again.code).toBe('entry_already_deleted');
    const after = await api.listEntries(WS, { account_id: acct.id, limit: 500 });
    expect(after.totals.count).toBe(before.totals.count);
    expect(after.entries.some((x) => x.id === e.id)).toBe(false);
    expect((await api.listPfAccounts(WS)).find((a) => a.id === acct.id)!.balance!.amount).toBe(balBefore);
  });

  it('validation: amount > 0, transfer needs a different target, label kind must match, partial PUT', async () => {
    const accounts = await api.listPfAccounts(WS);
    const [a, b] = accounts;
    const zero = (await api.createEntry(WS, { kind: 'expense', date: '2026-09-10', amount: money('0'), account_id: a.id }).catch((e: unknown) => e)) as api.ApiError;
    expect(zero.status).toBe(422);
    const same = (await api.createEntry(WS, { kind: 'transfer', date: '2026-09-10', amount: money('5'), account_id: a.id, to_account_id: a.id }).catch((e: unknown) => e)) as api.ApiError;
    expect(same.code).toBe('transfer_same_account');
    const noTarget = (await api.createEntry(WS, { kind: 'transfer', date: '2026-09-10', amount: money('5'), account_id: a.id }).catch((e: unknown) => e)) as api.ApiError;
    expect(noTarget.code).toBe('transfer_needs_target');
    const income = (await api.listLabels(WS, { kind: 'income' }))[0];
    const wrongKind = (await api.createEntry(WS, { kind: 'expense', date: '2026-09-10', amount: money('5'), account_id: a.id, label_id: income.id }).catch((e: unknown) => e)) as api.ApiError;
    expect(wrongKind.status).toBe(400);
    expect(wrongKind.message).toBe('Esa categoría es de ingresos');
    const ok = await api.createEntry(WS, { kind: 'transfer', date: '2026-09-10', amount: money('5'), account_id: a.id, to_account_id: b.id });
    const edited = await api.updateEntry(WS, ok.id, { note: 'nota' });
    expect(edited.note).toBe('nota');
    expect(edited.amount.amount).toBe('-5.00');
    expect(edited.to_account_id).toBe(b.id);
    const bulk = await api.bulkCreateEntries(WS, [
      { kind: 'expense', date: '2026-09-01', amount: money('1'), account_id: a.id },
      { kind: 'expense', date: '2026-09-02', amount: money('2'), account_id: a.id },
    ]);
    expect(bulk.created.length).toBe(2);
    const bad = (await api.bulkCreateEntries(WS, [{ kind: 'expense', date: '2026-09-01', amount: money('1'), account_id: a.id }, { kind: 'expense', date: 'x', amount: money('1'), account_id: a.id }]).catch((e: unknown) => e)) as api.ApiError;
    expect(bad.status).toBe(400);
    expect(bad.field).toBe('entries.1');
  });
});

describe('labels', () => {
  it('filters by kind, derives the ledger account, refuses to delete a used label', async () => {
    const expense = await api.listLabels(WS, { kind: 'expense' });
    const income = await api.listLabels(WS, { kind: 'income' });
    expect(expense.every((l) => l.kind === 'expense')).toBe(true);
    expect(income.map((l) => l.name)).toContain('Sueldo/Nómina');
    const created = await api.createLabel(WS, { name: 'Mascotas', kind: 'expense', icon: '🐶' });
    expect(created.account).toBe('Expenses:Mascotas');
    expect(created.kind).toBe('expense');
    expect(created.archived).toBe(false);
    const child = await api.createLabel(WS, { name: 'Veterinario', kind: 'expense', parent: created.id });
    expect(child.account).toBe('Expenses:Mascotas:Veterinario');
    const patched = await api.updateLabel(WS, created.id, { archived: true });
    expect(patched.archived).toBe(true);
    expect((await api.listLabels(WS)).some((l) => l.id === created.id)).toBe(false);
    expect((await api.listLabels(WS, { includeArchived: true })).some((l) => l.id === created.id)).toBe(true);
    const used = expense.find((l) => l.name === 'Súper')!;
    await expect(api.deleteLabel(WS, used.id)).rejects.toMatchObject({ status: 409 });
  });
});

describe('budgets', () => {
  it('status has the budget-status shape; copy is idempotent; duplicates are 409', async () => {
    const status = await api.getBudgetStatus(WS, '2026-09');
    expect(status.currency).toBe('MXN');
    expect(status.totals).toBeDefined();
    for (const row of status.budgets) {
      expect(typeof row.pct).toBe('number');
      expect(['ok', 'warn', 'over']).toContain(row.state);
      expect(row.carried).toBeDefined();
      expect(row.effective).toBeDefined();
    }
    const previous = status.previous_period!;
    expect(status.has_previous).toBe(true);
    const first = await api.copyBudgets(WS, previous, status.period);
    expect(first.created).toBeGreaterThanOrEqual(1);
    const second = await api.copyBudgets(WS, previous, status.period);
    expect(second).toEqual({ created: 0, skipped: first.created + first.skipped, period: status.period });
    const list = await api.listBudgets(WS, status.period);
    await expect(api.createBudget(WS, { label_id: list[0].label_id, period: status.period, amount: '1', currency: 'MXN', rollover: false })).rejects.toMatchObject({ code: 'budget_exists' });
    const bad = (await api.getBudgetStatus(WS, '2026-13').catch((e: unknown) => e)) as api.ApiError;
    expect(bad.status).toBe(422);
  });
});

describe('goals', () => {
  it('a goal created with account_id derives account/currency and carries account_name + pct', async () => {
    const [acct] = await api.listPfAccounts(WS);
    const goal = await api.createGoal(WS, { kind: 'savings', name: 'Viaje', target: money('12000.00'), account_id: acct.id });
    expect(goal.account_id).toBe(acct.id);
    expect(goal.account_name).toBe(acct.name);
    expect(goal.account).toBe(acct.ledger_account);
    expect(typeof goal.pct).toBe('number');
    await expect(api.createGoal(WS, { kind: 'savings', name: 'x', target: money('1'), account_id: 'nope' })).rejects.toMatchObject({ status: 404 });
    await expect(api.createGoal(WS, { kind: 'savings', name: 'x', target: money('1'), account_id: acct.id, target_date: '2000-01-01' })).rejects.toMatchObject({ status: 422 });
    const goals = await api.listGoals(WS);
    expect(goals.every((g) => 'account_id' in g)).toBe(true);
  });
});

describe('income streams', () => {
  it('partial PUT keeps the id and untouched fields; history rows are real occurrences', async () => {
    const [s] = await api.listStreams(WS);
    expect(s.account_name).toBeTruthy();
    const updated = await api.updateStream(WS, s.id, { amount: money('23000.00') });
    expect(updated.id).toBe(s.id);
    expect(updated.name).toBe(s.name);
    expect(updated.cadence).toBe(s.cadence);
    expect(updated.amount.amount).toBe('23000.00');
    await expect(api.updateStream(WS, s.id, { account_id: 'nope' })).rejects.toMatchObject({ status: 404 });
    const history = await api.getStreamHistory(WS, s.id);
    expect(history.stream_id).toBe(s.id);
    expect(history.periods.length).toBeGreaterThan(0);
    for (const row of history.periods) {
      expect(row.due).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(row.period).toBe(row.due.slice(0, 7));
      expect(['received', 'late', 'pending', 'missed']).toContain(row.status);
      expect('expected' in row && 'received' in row).toBe(true);
    }
    expect(history.periods.some((r) => r.status === 'received')).toBe(true);
  });
});

describe('onboarding', () => {
  it('has exactly the four step ids and done = accounts && first_entries', async () => {
    const o = await api.getOnboarding(WS);
    expect(o.steps.map((s) => s.id)).toEqual(['accounts', 'income', 'recurring', 'first_entries']);
    const done = Object.fromEntries(o.steps.map((s) => [s.id, s.done]));
    expect(o.done).toBe(done.accounts && done.first_entries);
  });
});

describe('organizer', () => {
  it('safe_to_spend carries currency, parts and the six step ids in order', async () => {
    const summary = await api.getOrganizerSummary(WS);
    const sts = summary.safe_to_spend;
    expect(sts.currency).toBe('MXN');
    expect(Object.keys(sts.parts!).sort()).toEqual(['balance', 'budgets_remaining', 'buffer', 'fixed_pending']);
    expect(sts.explain!.steps.map((s) => s.id)).toEqual([...SAFE_TO_SPEND_STEPS]);
    const c = (s: string) => BigInt(s.replace('.', ''));
    const p = sts.parts!;
    expect(c(sts.amount.amount)).toBe(c(p.balance.amount) - c(p.fixed_pending.amount) - c(p.budgets_remaining.amount) - c(p.buffer.amount));
  });

  it('commitments carry account_id/account_name; PUT is a patch-merge', async () => {
    const list = await api.listCommitments(WS);
    expect(list.every((c) => c.account_id && c.account_name)).toBe(true);
    const c = list[0];
    const patched = await api.patchCommitment(WS, c.id, { notes: 'hola' });
    expect(patched.notes).toBe('hola');
    expect(patched.name).toBe(c.name);
    expect(patched.amount).toEqual(c.amount);
    expect(await api.reviewCommitment(WS, c.id)).toMatchObject({ reviewed_at: expect.any(String) });
  });

  it('mark paid creates an entry stamped commitment_id when nothing matches; un-mark voids it', async () => {
    const list = await api.listCommitments(WS, { status: 'active' });
    const c = list.find((x) => x.kind !== 'income')!;
    const date = c.next_due;
    const res = await api.markOccurrence(WS, { commitment_id: c.id, date, status: 'paid', log_entry: true });
    expect(res.occurrence.status).toBe('paid');
    expect(res.occurrence.auto_created).toBe(true);
    expect(res.entry_id).toBeTruthy();
    const page = await api.listEntries(WS, { from: date, to: date, limit: 500 });
    const entry = page.entries.find((e) => e.id === res.entry_id)!;
    expect(entry.commitment_id).toBe(c.id);
    expect(entry.source).toBe('organizer');
    expect(entry.tags).toContain('pago-fijo');
    const again = await api.markOccurrence(WS, { commitment_id: c.id, date, status: 'paid', log_entry: true });
    expect(again.entry_id).toBe(res.entry_id);
    const cal = await api.getOrganizerCalendar(WS, date, date);
    const item = cal.days[0].items.find((i) => i.id === c.id)!;
    expect(item.status).toBe('paid');
    expect(item.entry_id).toBe(res.entry_id);
    expect(item.account_id).toBe(c.account_id);
    const un = await api.unmarkOccurrence(WS, c.id, date);
    expect(un).toEqual({ removed: true, voided_entry_id: res.entry_id });
    expect((await api.listEntries(WS, { from: date, to: date, limit: 500 })).entries.some((e) => e.id === res.entry_id)).toBe(false);
    const legacy = await api.markOccurrence(WS, c.id, date, 'skipped');
    expect(legacy.occurrence.status).toBe('skipped');
    await api.unmarkOccurrence(WS, c.id, date);
  });

  it('mark paid links an existing matching entry instead of creating one', async () => {
    const list = await api.listCommitments(WS, { status: 'active' });
    const c = list.find((x) => x.kind !== 'income')!;
    const [acct] = await api.listPfAccounts(WS);
    const date = '2026-08-20';
    const existing = await api.createEntry(WS, { kind: 'expense', date, amount: c.amount, account_id: acct.id, payee: c.name });
    const res = await api.markOccurrence(WS, { commitment_id: c.id, date, status: 'paid', log_entry: true });
    expect(res.entry_id).toBe(existing.id);
    expect(res.occurrence.auto_created).toBe(false);
    const un = await api.unmarkOccurrence(WS, c.id, date);
    expect(un.voided_entry_id).toBeNull();
  });
});

describe('quickadd + CSV', () => {
  it('quickadd answers preview/confidence/warnings/entry, needs an account, commits an editable entry', async () => {
    const [acct] = await api.listPfAccounts(WS);
    const preview = await api.quickAddPreview(WS, 'tacos 120 super', acct.id);
    expect(preview.preview.amount.amount).toBe('120.00');
    expect(preview.preview.account_id).toBe(acct.id);
    expect(preview.preview.label_name).toBe('Súper');
    expect(preview.entry).toBeNull();
    expect(Array.isArray(preview.warnings)).toBe(true);
    const committed = await api.quickAddCommit(WS, 'tacos 120 super', acct.id);
    expect(committed.entry!.source).toBe('quickadd');
    expect(committed.entry!.editable).toBe(true);
    const err = (await api.quickAddPreview(WS, 'cafe 40', 'nope').catch((e: unknown) => e)) as api.ApiError;
    expect(err.status).toBe(404);
  });

  it('bank CSV requires account_id (422 array) and answers created/skipped/errors', async () => {
    const [acct] = await api.listPfAccounts(WS);
    const file = new File(['Fecha,Monto\n'], 'edo.csv', { type: 'text/csv' });
    const ok = await api.importBankCsv(WS, file, acct.id, 'bbva');
    expect(ok.created.length).toBe(2);
    expect(ok).toMatchObject({ skipped_duplicates: 0, errors: [] });
    const err = (await api.uploadBankCsv(WS, file, 'bbva').catch((e: unknown) => e)) as api.ApiError;
    expect(err.status).toBe(422);
    expect(err.field).toBe('account_id');
  });
});
