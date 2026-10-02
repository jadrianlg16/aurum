/**
 * `/presupuesto/` and `/metas/` building blocks:
 *  - `BudgetRow` renders the server's `state`/`pct` as-is (selectors + "Gastado … de … · queda …"),
 *    shows `carried` only when positive and the "Te pasaste" line only when `state === 'over'`;
 *  - `GoalCard` carries `data-goal-id`/`data-pct` and "Aportar" opens + Agregar as a transfer
 *    prefilled with the goal's account and monthly figure (the object form of `open`).
 * Driven against the in-browser mock API (jsdom).
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { AddEntryProvider } from '@/components/AddEntry';
import { BudgetRow, barWidth, budgetTone } from '@/components/plan/BudgetRow';
import { CardDialog, LoanDialog } from '@/components/plan/CreditDialogs';
import { GoalCard, goalBarWidth, goalTargetString } from '@/components/plan/GoalCard';
import * as api from '@/lib/api';
import { I18nProvider } from '@/lib/i18n';
import { installMockApi } from '@/lib/mock';
import type { BudgetStatusRow, Goal } from '@/lib/types';
import { WorkspaceProvider } from '@/lib/workspace';

const WS = 'mock-personal';
const mx = (amount: string) => ({ amount, currency: 'MXN' });

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;

const tick = async () => {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 90));
  });
};

beforeAll(() => {
  installMockApi();
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { close?: () => void; showModal?: () => void };
  if (typeof proto.showModal !== 'function') proto.showModal = function () { this.setAttribute('open', ''); };
  if (typeof proto.close !== 'function') proto.close = function () { this.removeAttribute('open'); };
});

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, '', `/?ws=${WS}`);
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
});

describe('budget helpers', () => {
  it('maps state → tone and clamps the bar to the track without recomputing pct', () => {
    expect(budgetTone('ok')).toBe('pos');
    expect(budgetTone('warn')).toBe('warn');
    expect(budgetTone('over')).toBe('neg');
    expect(budgetTone(undefined)).toBe('pos');
    expect(barWidth(85)).toBe(85);
    expect(barWidth('85.0')).toBe(85);
    expect(barWidth(105)).toBe(100);
    expect(barWidth(-3)).toBe(0);
    expect(barWidth('x')).toBe(0);
  });
});

describe('goal helpers', () => {
  it('reads target whatever the wire shape (Amount or string) and clamps the bar', () => {
    const base = { target: '30000.00' } as unknown as Goal;
    expect(goalTargetString(base)).toBe('30000.00');
    expect(goalTargetString({ target: { amount: '30000.00', currency: 'MXN' } } as unknown as Goal)).toBe('30000.00');
    expect(goalTargetString({ target: null } as unknown as Goal)).toBe('');
    expect(goalBarWidth(40)).toBe(40);
    expect(goalBarWidth(140)).toBe(100);
    expect(goalBarWidth(undefined)).toBe(0);
  });
});

describe('BudgetRow', () => {
  const row = (over: Partial<BudgetStatusRow>): BudgetStatusRow => ({
    budget_id: 'bud-1',
    label_id: 'lbl-1',
    label_name: 'Comida',
    icon: '🍔',
    budget: mx('1500.00'),
    carried: mx('0.00'),
    effective: mx('1500.00'),
    spent: mx('1275.00'),
    remaining: mx('225.00'),
    pct: 85,
    state: 'warn',
    rollover: false,
    ...over,
  });

  const render = async (r: BudgetStatusRow) => {
    await act(async () => {
      root.render(
        <I18nProvider>
          <WorkspaceProvider>
            <BudgetRow row={r} />
          </WorkspaceProvider>
        </I18nProvider>,
      );
    });
    return host.querySelector('[data-testid="budget-row"]') as HTMLElement;
  };

  it('85 % → data-state="warn", data-pct="85", "Gastado … de … · queda …", no carried line', async () => {
    const el = await render(row({}));
    expect(el.dataset.state).toBe('warn');
    expect(el.dataset.pct).toBe('85');
    expect(el.dataset.labelId).toBe('lbl-1');
    expect(el.textContent).toMatch(/Gastado .*1,275.* de .*1,500.* · queda .*225/);
    expect(el.textContent).not.toMatch(/sobró del mes pasado/);
    expect(el.textContent).not.toMatch(/Te pasaste/);
    expect((el.querySelector('.bar > span') as HTMLElement).style.width).toBe('85%');
  });

  it('105 % → data-state="over", the bar stops at 100 % and "Te pasaste por" shows the overrun', async () => {
    const el = await render(row({ spent: mx('1575.00'), remaining: mx('-75.00'), pct: 105, state: 'over' }));
    expect(el.dataset.state).toBe('over');
    expect(el.dataset.pct).toBe('105');
    expect((el.querySelector('.bar > span') as HTMLElement).style.width).toBe('100%');
    expect(el.textContent).toMatch(/Te pasaste por .*75/);
  });

  it('a positive carried amount is displayed (display only) and "de" is the effective figure', async () => {
    const el = await render(row({ carried: mx('200.00'), effective: mx('1700.00'), pct: 75, state: 'ok' }));
    expect(el.dataset.state).toBe('ok');
    expect(el.textContent).toMatch(/de .*1,700/);
    expect(el.textContent).toMatch(/200.* que sobró del mes pasado/);
  });
});

describe('GoalCard', () => {
  it('carries data-goal-id/data-pct and "Aportar" opens a transfer prefilled with the goal account and monthly figure', async () => {
    const accounts = await api.listPfAccounts(WS);
    const savings = accounts.find((a) => !a.archived && (a.type === 'savings' || a.type === 'checking'))!;
    expect(savings).toBeTruthy();
    const goal: Goal = {
      id: 'goal-test-1',
      ws_id: WS,
      kind: 'savings',
      name: 'Viaje',
      target: '30000.00',
      currency: 'MXN',
      target_date: '2027-06-30',
      account: savings.ledger_account ?? 'Assets:Bank:Test',
      account_id: savings.id,
      account_name: savings.name,
      created_at: '2026-09-01T00:00:00+00:00',
      progress: mx('12000.00'),
      remaining: mx('18000.00'),
      pct: 40,
      monthly_required: mx('2000.00'),
      explain: { summary: '', steps: [], assumptions: [], sources: [] } as unknown as Goal['explain'],
    };
    await act(async () => {
      root.render(
        <I18nProvider>
          <WorkspaceProvider>
            <AddEntryProvider>
              <GoalCard ws={WS} goal={goal} onEdit={() => {}} onDelete={() => {}} onChanged={() => {}} />
            </AddEntryProvider>
          </WorkspaceProvider>
        </I18nProvider>,
      );
    });
    await tick();
    await tick();

    const card = host.querySelector('[data-testid="goal-card"]') as HTMLElement;
    expect(card.dataset.goalId).toBe('goal-test-1');
    expect(card.dataset.pct).toBe('40');
    expect(card.textContent).toMatch(/Llevas .*12,000.* de .*30,000/);
    expect(card.textContent).toMatch(/Necesitas ahorrar .*2,000.* al mes para el/);
    expect(card.querySelector('[data-testid="goal-status"]')?.getAttribute('data-status')).toBe('monthly');
    // The account is a name, never a ledger path with ':'
    expect(card.textContent).not.toMatch(/Assets:/);

    const btn = card.querySelector('[data-testid="goal-contribute"]') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    await act(async () => {
      btn.click();
    });
    await tick();
    await tick();

    // the card's own ⋯ Sheet is a closed <dialog>; + Agregar is the open one
    const dialog = [...document.querySelectorAll('dialog')].find((d) => d.hasAttribute('open') && d.querySelector('[role="tab"]'));
    expect(dialog).toBeTruthy();
    expect(dialog!.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toMatch(/Transferencia|Transfer/);
    const inputs = [...dialog!.querySelectorAll('input')];
    expect(inputs.some((i) => i.value === '2000.00')).toBe(true);
    const selects = [...dialog!.querySelectorAll('select')];
    const toSelect = selects.filter((sel) => sel.value === savings.id);
    expect(toSelect.length).toBeGreaterThan(0);
  });
});

describe('CardDialog / LoanDialog edit terms', () => {
  const byLabel = (scope: ParentNode, text: RegExp): HTMLInputElement | HTMLSelectElement => {
    const label = [...scope.querySelectorAll('label')].find((l) => text.test(l.textContent ?? ''));
    expect(label, `label ${text}`).toBeTruthy();
    const el = document.getElementById(label!.htmlFor);
    expect(el, `control for ${text}`).toBeTruthy();
    return el as HTMLInputElement | HTMLSelectElement;
  };
  const typeInto = (el: HTMLInputElement, value: string) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
    setter.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  };
  const openDialog = () => [...document.querySelectorAll('dialog')].find((d) => d.hasAttribute('open'))!;

  let puts: { path: string; body: unknown }[];
  let realFetch: typeof window.fetch;
  beforeEach(() => {
    puts = [];
    realFetch = window.fetch;
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const href = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if ((init?.method ?? 'GET').toUpperCase() === 'PUT') {
        puts.push({ path: new URL(href, window.location.origin).pathname, body: JSON.parse(String(init?.body ?? 'null')) });
      }
      return realFetch(input, init);
    };
  });
  afterEach(() => {
    window.fetch = realFetch;
  });

  it('a preselected card shows its own cut/due/limit/apr and an untouched save sends nothing', async () => {
    const card = (await api.listPfAccounts(WS)).find((a) => a.type === 'credit_card')!;
    expect(card.cut_day).toBe(4);
    expect(card.due_day).toBe(22);
    let closed: boolean | null = null;
    await act(async () => {
      root.render(
        <I18nProvider>
          <WorkspaceProvider>
            <CardDialog ws={WS} mode="edit" accountId={card.id} onClose={(saved) => (closed = saved)} />
          </WorkspaceProvider>
        </I18nProvider>,
      );
    });
    await tick();
    await tick();
    const dialog = openDialog();
    expect((byLabel(dialog, /^Tarjeta/) as HTMLSelectElement).value).toBe(card.id);
    expect(byLabel(dialog, /Día de corte/).value).toBe('4');
    expect(byLabel(dialog, /Día de pago/).value).toBe('22');
    expect(byLabel(dialog, /Tasa anual/).value).toBe('36.9');
    expect(byLabel(dialog, /Límite/).value).toBe('60,000.00');

    await act(async () => {
      (dialog.querySelector('button[type="submit"]') as HTMLButtonElement).click();
    });
    await tick();
    expect(puts).toEqual([]);
    expect(closed).toBe(false);
  });

  it('changing only the limit PUTs only credit_limit (cut/due days survive)', async () => {
    const card = (await api.listPfAccounts(WS)).find((a) => a.type === 'credit_card')!;
    await act(async () => {
      root.render(
        <I18nProvider>
          <WorkspaceProvider>
            <CardDialog ws={WS} mode="edit" accountId={card.id} onClose={() => {}} />
          </WorkspaceProvider>
        </I18nProvider>,
      );
    });
    await tick();
    await tick();
    const dialog = openDialog();
    const limit = byLabel(dialog, /Límite/) as HTMLInputElement;
    await act(async () => {
      limit.focus();
      typeInto(limit, '45000');
    });
    await act(async () => {
      (dialog.querySelector('button[type="submit"]') as HTMLButtonElement).click();
    });
    await tick();
    await tick();
    expect(puts).toHaveLength(1);
    expect(puts[0].path).toMatch(new RegExp(`/pf/${WS}/accounts/${card.id}$`));
    expect(puts[0].body).toEqual({ credit_limit: { amount: '45000', currency: 'MXN' } });
    const after = (await api.listPfAccounts(WS)).find((a) => a.id === card.id)!;
    expect(after.cut_day).toBe(4);
    expect(after.due_day).toBe(22);
    expect(after.apr_percent).toBe('36.9');
    expect(after.credit_limit?.amount).toBe('45000');
  });

  it('a preselected loan shows its apr/months; changing the months PUTs only loan_months', async () => {
    const loan = await api.createPfAccount(WS, {
      type: 'loan',
      name: 'Auto',
      currency: 'MXN',
      opening_balance: mx('120000.00'),
      apr_percent: '12',
      loan_months: 36,
    });
    await act(async () => {
      root.render(
        <I18nProvider>
          <WorkspaceProvider>
            <LoanDialog ws={WS} mode="edit" accountId={loan.id} onClose={() => {}} />
          </WorkspaceProvider>
        </I18nProvider>,
      );
    });
    await tick();
    await tick();
    const dialog = openDialog();
    expect(byLabel(dialog, /Tasa anual/).value).toBe('12');
    expect(byLabel(dialog, /Plazo|meses/i).value).toBe('36');
    const months = byLabel(dialog, /Plazo|meses/i) as HTMLInputElement;
    await act(async () => {
      typeInto(months, '48');
    });
    await act(async () => {
      (dialog.querySelector('button[type="submit"]') as HTMLButtonElement).click();
    });
    await tick();
    await tick();
    expect(puts).toHaveLength(1);
    expect(puts[0].body).toEqual({ loan_months: 48 });
  });
});
