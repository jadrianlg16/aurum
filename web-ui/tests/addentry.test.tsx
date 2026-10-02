/**
 * `useAddEntry().open(...)` object form: the
 * dialog is seeded from `prefill`/`accountId`, `commitment_id` travels verbatim in the POST, and
 * `onSaved` receives the row the API returned. Driven against the in-browser mock API.
 */
import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { AddEntryProvider, useAddEntry, type OpenAddEntryOptions } from '@/components/AddEntry';
import * as api from '@/lib/api';
import { I18nProvider } from '@/lib/i18n';
import { installMockApi } from '@/lib/mock';
import type { Entry } from '@/lib/types-personal';
import { WorkspaceProvider } from '@/lib/workspace';

const WS = 'mock-personal';
let host: HTMLDivElement;
let root: Root;
let opener: ((o: OpenAddEntryOptions) => void) | null = null;

function Opener() {
  const { open } = useAddEntry();
  useEffect(() => {
    opener = (o) => open(o);
  }, [open]);
  return null;
}

// the mock API answers after a visible 60 ms latency (lib/mock/index.ts), so a tick waits it out
const tick = async () => {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 90));
  });
};

beforeAll(() => {
  installMockApi();
  // jsdom has no <dialog> methods; the component guards showModal() but its cleanup calls close().
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
  opener = null;
});

afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
});

describe('useAddEntry().open object form', () => {
  it('seeds the dialog from prefill, sends commitment_id and hands the saved row to onSaved', async () => {
    const accounts = await api.listPfAccounts(WS);
    const acct = accounts.find((a) => !a.archived)!;
    const saved: Entry[] = [];

    await act(async () => {
      root.render(
        <I18nProvider>
          <WorkspaceProvider>
            <AddEntryProvider>
              <Opener />
            </AddEntryProvider>
          </WorkspaceProvider>
        </I18nProvider>,
      );
    });
    await tick();
    await tick();
    expect(opener).toBeTypeOf('function');

    await act(async () => {
      opener!({
        kind: 'expense',
        accountId: acct.id,
        prefill: { amount: { amount: '250.00', currency: 'MXN' }, payee: 'Netflix', commitment_id: 'cmt-test-1' },
        onSaved: (e) => saved.push(e),
      });
    });
    await tick();
    await tick();

    const dialog = document.querySelector('dialog');
    expect(dialog).not.toBeNull();
    const inputs = [...dialog!.querySelectorAll('input')];
    expect(inputs.some((i) => i.value === '250.00')).toBe(true);
    expect(inputs.some((i) => i.value === 'Netflix')).toBe(true);
    // the category select comes first; the account select is the one listing this account
    const selects = [...dialog!.querySelectorAll('select')];
    const accountSelect = selects.find((sel) => [...sel.options].some((o) => o.value === acct.id));
    expect(accountSelect?.value).toBe(acct.id);

    const form = dialog!.querySelector('form') as HTMLFormElement;
    await act(async () => {
      form.requestSubmit();
    });
    await tick();
    await tick();

    expect(saved).toHaveLength(1);
    expect(saved[0].payee).toBe('Netflix');
    expect(saved[0].amount.amount).toBe('-250.00');
    expect(saved[0].commitment_id).toBe('cmt-test-1');
    expect(saved[0].account_id).toBe(acct.id);
  });

  it('keeps the string form', async () => {
    await act(async () => {
      root.render(
        <I18nProvider>
          <WorkspaceProvider>
            <AddEntryProvider>
              <Opener />
            </AddEntryProvider>
          </WorkspaceProvider>
        </I18nProvider>,
      );
    });
    await tick();
    await tick();
    await act(async () => {
      opener!({ kind: 'income' });
    });
    await tick();
    const dialog = document.querySelector('dialog');
    expect(dialog).not.toBeNull();
    expect(dialog!.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toMatch(/Ingreso|Income/);
  });
});
