/**
 * `AccountForm` wire contract against the in-browser mock API:
 * a card's owed figure is typed positive and travels verbatim as `opening_balance`, the rate goes
 * out as `apr_percent` (never `apr`, never divided), the saved row comes back `owed:true` with a
 * positive `balance`, and a duplicate name (409) is an inline error on Nombre — decided by the
 * status, not by `ApiError.code`.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { I18nProvider } from '@/lib/i18n';
import { installMockApi } from '@/lib/mock';
import type { PfAccount } from '@/lib/types-personal';
import { WorkspaceProvider } from '@/lib/workspace';
import { AccountForm } from './AccountForm';

const WS = 'mock-personal';
let host: HTMLDivElement;
let root: Root;
const posts: { url: string; method: string; body: unknown }[] = [];

const tick = async () => {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 90));
  });
};

/** Type into a React-controlled input: native setter + `input` event. */
const type = (el: HTMLInputElement, value: string) => {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
  setter.call(el, value);
  el.dispatchEvent(new Event('input', { bubbles: true }));
};

const byName = (name: string) => host.querySelector<HTMLInputElement>(`input[name="${name}"]`)!;
const byTestId = <T extends HTMLElement = HTMLElement>(id: string) => host.querySelector<T>(`[data-testid="${id}"]`)!;

beforeAll(() => {
  installMockApi();
  const patched = window.fetch;
  window.fetch = async (input, init) => {
    const method = (init?.method ?? 'GET').toUpperCase();
    if (method !== 'GET') {
      let body: unknown = init?.body;
      try {
        body = typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body;
      } catch {
        /* keep raw */
      }
      posts.push({ url: String(input), method, body });
    }
    return patched(input, init);
  };
});

beforeEach(() => {
  posts.length = 0;
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

async function mount(props: { account?: PfAccount | null; onSaved: (a: PfAccount) => void }) {
  await act(async () => {
    root.render(
      <I18nProvider>
        <WorkspaceProvider>
          <AccountForm ws={WS} inline account={props.account} onSaved={props.onSaved} />
        </WorkspaceProvider>
      </I18nProvider>,
    );
  });
  await tick();
}

describe('AccountForm', () => {
  it("keeps 'Guardar cuenta' as its only primary: the selected type tile is a checked secondary", async () => {
    await mount({ onSaved: () => {} });
    await act(async () => {
      byTestId<HTMLButtonElement>('acct-type-credit_card').click();
    });
    const primaries = [...host.querySelectorAll('.btn.primary')].map((b) => b.getAttribute('data-testid'));
    expect(primaries).toEqual(['acct-save']);
    const tile = byTestId<HTMLButtonElement>('acct-type-credit_card');
    expect(tile.getAttribute('role')).toBe('radio');
    expect(tile.getAttribute('aria-checked')).toBe('true');
    expect(tile.classList.contains('primary')).toBe(false);
    expect(byTestId<HTMLButtonElement>('acct-type-checking').getAttribute('aria-checked')).toBe('false');
  });

  it('sends a card typed positive as opening_balance and the rate as apr_percent; the row comes back owed', async () => {
    const saved: PfAccount[] = [];
    await mount({ onSaved: (a) => saved.push(a) });

    await act(async () => {
      byTestId<HTMLButtonElement>('acct-type-credit_card').click();
    });
    await act(async () => {
      type(byTestId<HTMLInputElement>('acct-name'), `Tarjeta prueba ${Date.now()}`);
      type(byName('opening_balance'), '5000.00');
      type(byName('credit_limit'), '30000');
      type(byTestId<HTMLInputElement>('acct-apr'), '45');
    });
    // the liability field never shows a sign hint and refuses a minus
    expect(byName('opening_balance').value).not.toContain('-');

    await act(async () => {
      byTestId<HTMLFormElement>('acct-form').requestSubmit();
    });
    await tick();
    await tick();

    const post = posts.find((p) => p.method === 'POST' && p.url.includes('/accounts'));
    expect(post).toBeDefined();
    const body = post!.body as Record<string, unknown>;
    expect(body.type).toBe('credit_card');
    expect((body.opening_balance as { amount: string }).amount).toBe('5000.00');
    expect(body.apr_percent).toBe('45');
    expect(body).not.toHaveProperty('apr');
    expect(body.opening_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);

    expect(saved).toHaveLength(1);
    expect(saved[0].owed).toBe(true);
    expect(saved[0].balance?.amount).toBe('5000.00');
    expect(saved[0].balance_signed?.amount).toBe('-5000.00');
    expect(saved[0].apr_percent).toBe('45');
  });

  it('turns the duplicate-name 409 into an inline error on Nombre', async () => {
    const saved: PfAccount[] = [];
    await mount({ onSaved: (a) => saved.push(a) });
    // the mock personal workspace seeds an account named 'BBVA' (fixtures-personal:159)
    await act(async () => {
      type(byTestId<HTMLInputElement>('acct-name'), 'BBVA');
    });
    await act(async () => {
      byTestId<HTMLFormElement>('acct-form').requestSubmit();
    });
    await tick();
    await tick();
    expect(saved).toHaveLength(0);
    const nameInput = byTestId<HTMLInputElement>('acct-name');
    expect(nameInput.getAttribute('aria-invalid')).toBe('true');
    expect(host.textContent).toMatch(/Ya tienes una cuenta con ese nombre|already have an account/);
  });

  it('edit mode PUTs only the editable fields (no opening balance, currency or type)', async () => {
    const saved: PfAccount[] = [];
    const account = {
      id: 'acc-x',
      name: 'Nu',
      type: 'credit_card',
      currency: 'MXN',
      institution: 'Nu',
      balance: { amount: '2610.00', currency: 'MXN' },
      balance_signed: { amount: '-2610.00', currency: 'MXN' },
      owed: true,
      archived: false,
      credit_limit: { amount: '30000.00', currency: 'MXN' },
      cut_day: 15,
      due_day: 5,
      apr_percent: null,
      loan_months: null,
      loan_principal: null,
      opening_balance: null,
      opening_date: null,
    } as unknown as PfAccount;
    await mount({ account, onSaved: (a) => saved.push(a) });
    expect(host.querySelector('[data-testid="acct-type-tiles"]')).toBeNull();
    expect(byName('opening_balance').disabled).toBe(true);
    expect(byTestId<HTMLSelectElement>('acct-cut-day').value).toBe('15');

    await act(async () => {
      type(byTestId<HTMLInputElement>('acct-apr'), '39.9');
    });
    await act(async () => {
      byTestId<HTMLFormElement>('acct-form').requestSubmit();
    });
    await tick();
    await tick();
    const put = posts.find((p) => p.method === 'PUT');
    expect(put).toBeDefined();
    const body = put!.body as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(['apr_percent', 'credit_limit', 'cut_day', 'due_day', 'institution', 'name']);
    expect(body.apr_percent).toBe('39.9');
    expect(body.cut_day).toBe(15);
  });

  it("'Otra…' reveals a 3-letter code, upper-cased and validated, sent as currency", async () => {
    const saved: PfAccount[] = [];
    await mount({ onSaved: (a) => saved.push(a) });
    const currency = byTestId<HTMLSelectElement>('acct-currency');
    expect([...currency.options].map((o) => o.value).slice(0, 3)).toEqual(['MXN', 'USD', 'EUR']);
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!;
      setter.call(currency, '__other__');
      currency.dispatchEvent(new Event('change', { bubbles: true }));
    });
    const code = byTestId<HTMLInputElement>('acct-currency-code');
    await act(async () => {
      type(byTestId<HTMLInputElement>('acct-name'), `Libras ${Date.now()}`);
      type(code, 'gb1p');
    });
    expect(code.value).toBe('GBP');
    await act(async () => {
      type(code, 'GB');
      byTestId<HTMLFormElement>('acct-form').requestSubmit();
    });
    await tick();
    expect(posts.filter((p) => p.method === 'POST')).toHaveLength(0);
    expect(code.getAttribute('aria-invalid')).toBe('true');
    await act(async () => {
      type(code, 'GBP');
      byTestId<HTMLFormElement>('acct-form').requestSubmit();
    });
    await tick();
    await tick();
    const post = posts.find((p) => p.method === 'POST');
    expect((post!.body as Record<string, unknown>).currency).toBe('GBP');
    expect(saved[0]?.currency).toBe('GBP');
  });
});
