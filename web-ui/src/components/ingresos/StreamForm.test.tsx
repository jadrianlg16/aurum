/**
 * `StreamForm` wire contract against the in-browser mock API: a salary
 * defaults to semimonthly on the 15th and the last day (`anchor_days [15, 31]`) with the label
 * named exactly 'Sueldo/Nómina'; biweekly 'viernes' posts `weekday: 4` (Monday = 0) and an
 * empty `anchor_days` (never null); `next_expected` is only sent for annual/irregular.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { I18nProvider } from '@/lib/i18n';
import { installMockApi } from '@/lib/mock';
import type { IncomeStream } from '@/lib/types-personal';
import { WorkspaceProvider } from '@/lib/workspace';
import { resolveCommitmentId } from '@/components/IncomeStreams';
import { StreamForm, type StreamTemplate } from './StreamForm';

const WS = 'mock-personal';
let host: HTMLDivElement;
let root: Root;
const posts: { url: string; method: string; body: unknown }[] = [];

const tick = async () => {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 90));
  });
};

const type = (el: HTMLInputElement, value: string) => {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
  setter.call(el, value);
  el.dispatchEvent(new Event('input', { bubbles: true }));
};
const select = (el: HTMLSelectElement, value: string) => {
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!;
  setter.call(el, value);
  el.dispatchEvent(new Event('change', { bubbles: true }));
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

async function mount(props: { template?: StreamTemplate; onSaved: (s: IncomeStream) => void }) {
  await act(async () => {
    root.render(
      <I18nProvider>
        <WorkspaceProvider>
          <StreamForm ws={WS} inline template={props.template} onSaved={props.onSaved} />
        </WorkspaceProvider>
      </I18nProvider>,
    );
  });
  await tick();
  await tick();
}

/** The first real account in the AccountPicker (skips the placeholder / 'new' options). */
function pickFirstAccount() {
  const selects = [...host.querySelectorAll('select')];
  const picker = selects.find((s) => [...s.options].some((o) => o.value.startsWith('acc')));
  expect(picker).toBeDefined();
  const opt = [...picker!.options].find((o) => o.value.startsWith('acc'))!;
  select(picker!, opt.value);
  return opt.value;
}

describe('StreamForm', () => {
  it("keeps 'Guardar ingreso' as its only primary: the selected source chip is a checked secondary", async () => {
    await mount({ onSaved: () => {} });
    const primaries = [...host.querySelectorAll('.btn.primary')].map((b) => b.getAttribute('data-testid'));
    expect(primaries).toEqual(['inc-save']);
    const chip = byTestId<HTMLButtonElement>('inc-source-salary');
    expect(chip.getAttribute('role')).toBe('radio');
    expect(chip.getAttribute('aria-checked')).toBe('true');
    expect(chip.classList.contains('primary')).toBe(false);
  });

  it('salary: semimonthly [15, 31] by default with the Sueldo/Nómina label', async () => {
    const saved: IncomeStream[] = [];
    await mount({ onSaved: (s) => saved.push(s) });
    expect(byTestId<HTMLSelectElement>('inc-cadence').value).toBe('semimonthly');
    expect(byTestId<HTMLSelectElement>('inc-day-1').value).toBe('15');
    expect(byTestId<HTMLSelectElement>('inc-day-2').value).toBe('31');

    let accountId = '';
    await act(async () => {
      type(byTestId<HTMLInputElement>('inc-name'), 'Quincena');
      accountId = pickFirstAccount();
      type(byName('amount'), '12000');
    });
    await act(async () => {
      byTestId<HTMLFormElement>('inc-form').requestSubmit();
    });
    await tick();
    await tick();

    const post = posts.find((p) => p.method === 'POST' && p.url.includes('/income/streams'));
    expect(post).toBeDefined();
    const body = post!.body as Record<string, unknown>;
    expect(body.source_type).toBe('salary');
    expect(body.cadence).toBe('semimonthly');
    expect(body.anchor_days).toEqual([15, 31]);
    expect(body.weekday).toBeNull();
    expect(body.next_expected).toBeNull();
    expect(body.account_id).toBe(accountId);
    expect(body.label_id).toBe('lbl-inc-salary');
    expect(body.active).toBe(true);
    expect((body.amount as { amount: string }).amount).toBe('12000');
    expect(saved).toHaveLength(1);
    expect(saved[0].anchor_days).toEqual([15, 31]);
  });

  it("biweekly 'viernes' posts weekday 4 and an empty anchor_days", async () => {
    const saved: IncomeStream[] = [];
    await mount({ template: 'freelance', onSaved: (s) => saved.push(s) });
    expect(byTestId<HTMLSelectElement>('inc-cadence').value).toBe('irregular');

    await act(async () => {
      type(byTestId<HTMLInputElement>('inc-name'), 'Honorarios');
      pickFirstAccount();
      type(byName('amount'), '8000');
      select(byTestId<HTMLSelectElement>('inc-cadence'), 'biweekly');
    });
    const weekday = byTestId<HTMLSelectElement>('inc-weekday');
    const viernes = [...weekday.options].find((o) => /viernes|friday/i.test(o.textContent ?? ''))!;
    expect(viernes.value).toBe('4');
    await act(async () => {
      select(weekday, '4');
    });
    await act(async () => {
      byTestId<HTMLFormElement>('inc-form').requestSubmit();
    });
    await tick();
    await tick();

    const post = posts.find((p) => p.method === 'POST' && p.url.includes('/income/streams'));
    const body = post!.body as Record<string, unknown>;
    expect(body.source_type).toBe('freelance');
    expect(body.cadence).toBe('biweekly');
    expect(body.weekday).toBe(4);
    expect(body.anchor_days).toEqual([]);
    expect(saved).toHaveLength(1);
    expect(saved[0].weekday).toBe(4);
  });
});

describe('resolveCommitmentId', () => {
  const base = { id: 's', name: 'x', amount: { amount: '1.00', currency: 'MXN' }, cadence: 'monthly', source_type: 'salary', active: true } as unknown as IncomeStream;
  it('is undefined without ids and the single id when there is one', async () => {
    expect(await resolveCommitmentId(WS, { ...base, commitment_ids: [] })).toBeUndefined();
    expect(await resolveCommitmentId(WS, { ...base })).toBeUndefined();
    expect(await resolveCommitmentId(WS, { ...base, commitment_ids: ['cmt-1'] })).toBe('cmt-1');
  });
  it('is undefined when several ids match none of the commitments the API knows', async () => {
    expect(await resolveCommitmentId(WS, { ...base, commitment_ids: ['nope-1', 'nope-2'] })).toBeUndefined();
  });
});
