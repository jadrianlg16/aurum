/**
 * Workspace resolution: the four pick branches, stale-key fallback,
 * `?ws=` read once + stripped, refresh() keeping the id, and no fetch before resolution.
 * Rendered with react-dom/client + act (no testing-library).
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Workspace } from '@/lib/types';

vi.mock('@/lib/api', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/lib/api')>();
  return { ...mod, listWorkspaces: vi.fn() };
});

import { listWorkspaces } from '@/lib/api';
import { WorkspaceGate, WorkspaceProvider, pickWorkspace, useWorkspace, type WorkspaceValue } from '@/lib/workspace';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const ws = (id: string, extra: Partial<Workspace> = {}): Workspace => ({
  id,
  name: id,
  kind: 'personal',
  jurisdictions: ['MX'],
  base_currency: 'MXN',
  language: 'es',
  profile: {},
  created_at: '2026-09-01T00:00:00Z',
  ...extra,
});

const PERSONAL = ws('personal', { protected: true });
const DEMO = ws('demo-mx', { profile: { demo: true } });
const BIZ = ws('negocio', { kind: 'business' });

let root: Root;
let host: HTMLDivElement;
let last: WorkspaceValue | null = null;

function Probe() {
  last = useWorkspace();
  return <span data-testid="ws">{last.wsOrNull ?? 'null'}</span>;
}

async function mount(list: Workspace[] | Error) {
  const fn = listWorkspaces as unknown as ReturnType<typeof vi.fn>;
  fn.mockReset();
  if (list instanceof Error) fn.mockRejectedValue(list);
  else fn.mockResolvedValue(list);
  await act(async () => {
    root.render(
      <WorkspaceProvider>
        <Probe />
        <WorkspaceGate fallback={<i>gate</i>}>
          <b>inside</b>
        </WorkspaceGate>
      </WorkspaceProvider>,
    );
  });
  await act(async () => {
    await Promise.resolve();
  });
}

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, '', '/');
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  last = null;
});

afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
});

describe('pickWorkspace (pure)', () => {
  it('branch 1: the wanted id when listed', () => {
    expect(pickWorkspace([DEMO, PERSONAL], 'demo-mx')?.id).toBe('demo-mx');
  });
  it('branch 2: first personal, non-demo, non-hidden', () => {
    expect(pickWorkspace([DEMO, BIZ, PERSONAL], null)?.id).toBe('personal');
    expect(pickWorkspace([DEMO, ws('oculto', { hidden: true }), PERSONAL], null)?.id).toBe('personal');
  });
  it('branch 3: first non-demo when there is no personal', () => {
    expect(pickWorkspace([DEMO, BIZ], null)?.id).toBe('negocio');
  });
  it('branch 4: null when only demos exist (no silent demo-mx fallback)', () => {
    expect(pickWorkspace([DEMO], null)).toBeNull();
    expect(pickWorkspace([], 'anything')).toBeNull();
  });
  it('never auto-picks the synthetic business fixture (demo-biz) on a first run', () => {
    const DEMO_BIZ = ws('demo-biz', { kind: 'business', profile: { synthetic: true } });
    expect(pickWorkspace([DEMO_BIZ, DEMO], null)).toBeNull();
    expect(pickWorkspace([DEMO_BIZ, DEMO], 'demo-biz')?.id).toBe('demo-biz');
  });
});

describe('WorkspaceProvider', () => {
  it('starts unresolved (no id, gate closed) and resolves to the personal workspace', async () => {
    await mount([DEMO, PERSONAL]);
    expect(last?.wsOrNull).toBe('personal');
    expect(last?.ws).toBe('personal');
    expect(last?.resolved).toBe(true);
    expect(host.textContent).toContain('inside');
    expect(window.localStorage.getItem('aurum.ws')).toBe('personal');
  });

  it('uses the stored id when it is listed, and falls back when it is stale', async () => {
    window.localStorage.setItem('aurum.ws', 'demo-mx');
    await mount([PERSONAL, DEMO]);
    expect(last?.wsOrNull).toBe('demo-mx');
    await act(async () => root.unmount());
    root = createRoot(host);
    window.localStorage.setItem('aurum.ws', 'gone');
    await mount([DEMO, PERSONAL]);
    expect(last?.wsOrNull).toBe('personal');
    expect(window.localStorage.getItem('aurum.ws')).toBe('personal');
  });

  it('migrates the legacy aurum.workspace key once', async () => {
    window.localStorage.setItem('aurum.workspace', 'demo-mx');
    await mount([PERSONAL, DEMO]);
    expect(last?.wsOrNull).toBe('demo-mx');
    expect(window.localStorage.getItem('aurum.workspace')).toBeNull();
    expect(window.localStorage.getItem('aurum.ws')).toBe('demo-mx');
  });

  it('reads ?ws= once, persists it and strips it from the URL; refresh() keeps the id', async () => {
    window.history.replaceState(null, '', '/movimientos/?ws=demo-mx&tab=x');
    await mount([PERSONAL, DEMO]);
    expect(last?.wsOrNull).toBe('demo-mx');
    expect(window.location.search).toBe('?tab=x');
    expect(window.localStorage.getItem('aurum.ws')).toBe('demo-mx');
    // Put ?ws= back: refresh() must NOT re-apply it.
    window.history.replaceState(null, '', '/movimientos/?ws=personal');
    await act(async () => last?.refresh());
    await act(async () => {
      await Promise.resolve();
    });
    expect(last?.wsOrNull).toBe('demo-mx');
    expect((listWorkspaces as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(2);
  });

  it('rejects an invalid ?ws= (server id rule) and falls back to the default', async () => {
    window.history.replaceState(null, '', '/?ws=Bad%20Id');
    await mount([PERSONAL, DEMO]);
    expect(last?.wsOrNull).toBe('personal');
    expect(window.location.search).toBe('');
  });

  it('only demos → null id, gate closed, error ws.none', async () => {
    await mount([DEMO]);
    expect(last?.wsOrNull).toBeNull();
    expect(last?.ws).toBe('');
    expect(last?.error).toBe('ws.none');
    expect(host.textContent).toContain('gate');
    expect(host.textContent).not.toContain('inside');
  });

  it('a dead API → resolved with no id and error ws.resolve_failed (no guessed id)', async () => {
    await mount(new TypeError('Failed to fetch'));
    expect(last?.wsOrNull).toBeNull();
    expect(last?.resolved).toBe(true);
    expect(last?.error).toBe('ws.resolve_failed');
  });

  it('setWs persists and updates current', async () => {
    await mount([PERSONAL, DEMO]);
    await act(async () => last?.setWs('demo-mx'));
    expect(last?.wsOrNull).toBe('demo-mx');
    expect(last?.current?.id).toBe('demo-mx');
    expect(window.localStorage.getItem('aurum.ws')).toBe('demo-mx');
  });
});
