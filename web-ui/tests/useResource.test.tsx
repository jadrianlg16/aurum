/**
 * useResource: stale-while-refresh, abort on deps change,
 * no call while the workspace is unresolved, reset on workspace change, localized errors.
 */
import { act, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Workspace } from '@/lib/types';

vi.mock('@/lib/api', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/lib/api')>();
  return { ...mod, listWorkspaces: vi.fn() };
});

import { ApiError, listWorkspaces } from '@/lib/api';
import { useResource, type Resource } from '@/lib/useResource';
import { WorkspaceProvider, useWorkspace } from '@/lib/workspace';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const WS = (id: string): Workspace => ({
  id,
  name: id,
  kind: 'personal',
  jurisdictions: ['MX'],
  base_currency: 'MXN',
  language: 'es',
  profile: {},
  created_at: '2026-09-01T00:00:00Z',
});

type Deferred<T> = { promise: Promise<T>; resolve: (v: T) => void; reject: (e: unknown) => void };
function deferred<T>(): Deferred<T> {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

let root: Root;
let host: HTMLDivElement;
let snapshot: Resource<string> | null = null;
const calls: { key: string; signal: AbortSignal; d: Deferred<string> }[] = [];

function Probe({ dep }: { dep: string }) {
  snapshot = useResource(
    (signal) => {
      const d = deferred<string>();
      calls.push({ key: dep, signal, d });
      return d.promise;
    },
    [dep],
  );
  return null;
}

function Harness({ initialDep = 'a', gated = false }: { initialDep?: string; gated?: boolean }) {
  const [dep, setDep] = useState(initialDep);
  (globalThis as unknown as { __setDep: (d: string) => void }).__setDep = setDep;
  const probe = <Probe dep={dep} />;
  return gated ? <WorkspaceProvider>{probe}<Switcher /></WorkspaceProvider> : probe;
}

function Switcher() {
  const w = useWorkspace();
  (globalThis as unknown as { __setWs: (id: string) => void }).__setWs = w.setWs;
  return null;
}

const setDep = (d: string) => (globalThis as unknown as { __setDep: (d: string) => void }).__setDep(d);
const flush = async () => {
  await act(async () => {
    await Promise.resolve();
  });
};

beforeEach(() => {
  calls.length = 0;
  snapshot = null;
  window.localStorage.clear();
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
});

describe('useResource', () => {
  it('first load: loading=true, data null; then data with loading=false', async () => {
    await act(async () => root.render(<Harness />));
    expect(snapshot?.loading).toBe(true);
    expect(snapshot?.data).toBeNull();
    expect(calls.length).toBe(1);
    await act(async () => calls[0].d.resolve('one'));
    expect(snapshot?.data).toBe('one');
    expect(snapshot?.loading).toBe(false);
    expect(snapshot?.refreshing).toBe(false);
  });

  it('reload keeps the previous data and toggles refreshing, not loading', async () => {
    await act(async () => root.render(<Harness />));
    await act(async () => calls[0].d.resolve('one'));
    await act(async () => snapshot?.reload());
    expect(snapshot?.data).toBe('one');
    expect(snapshot?.refreshing).toBe(true);
    expect(snapshot?.loading).toBe(false);
    await act(async () => calls[1].d.resolve('two'));
    expect(snapshot?.data).toBe('two');
    expect(snapshot?.refreshing).toBe(false);
  });

  it('a deps change aborts the in-flight loader and its late result never lands', async () => {
    await act(async () => root.render(<Harness />));
    const first = calls[0];
    await act(async () => setDep('b'));
    expect(first.signal.aborted).toBe(true);
    expect(calls.length).toBe(2);
    expect(calls[1].signal.aborted).toBe(false);
    await act(async () => first.d.resolve('stale'));
    expect(snapshot?.data).toBeNull();
    await act(async () => calls[1].d.resolve('fresh'));
    expect(snapshot?.data).toBe('fresh');
  });

  it('unmount aborts', async () => {
    await act(async () => root.render(<Harness />));
    const first = calls[0];
    await act(async () => root.unmount());
    root = createRoot(host);
    expect(first.signal.aborted).toBe(true);
  });

  it('errors are localized through errorMessage and exposed raw as problem', async () => {
    await act(async () => root.render(<Harness />));
    const err = new ApiError('entry e1 was already deleted', 409, { code: 'entry_already_deleted' });
    await act(async () => calls[0].d.reject(err));
    expect(snapshot?.error).toBe('Ese movimiento ya estaba borrado.');
    expect(snapshot?.problem).toBe(err);
    expect(snapshot?.loading).toBe(false);
  });

  it('never fires while the workspace is unresolved; resets data when the workspace changes', async () => {
    const list = deferred<Workspace[]>();
    (listWorkspaces as unknown as ReturnType<typeof vi.fn>).mockReturnValue(list.promise);
    await act(async () => root.render(<Harness gated />));
    await flush();
    expect(calls.length).toBe(0);
    expect(snapshot?.loading).toBe(true);
    await act(async () => list.resolve([WS('personal'), WS('otro')]));
    await flush();
    expect(calls.length).toBe(1);
    await act(async () => calls[0].d.resolve('personal-rows'));
    expect(snapshot?.data).toBe('personal-rows');
    await act(async () => (globalThis as unknown as { __setWs: (id: string) => void }).__setWs('otro'));
    await flush();
    expect(snapshot?.data).toBeNull();
    expect(snapshot?.loading).toBe(true);
    expect(calls.length).toBe(2);
    await act(async () => calls[1].d.resolve('otro-rows'));
    expect(snapshot?.data).toBe('otro-rows');
  });

  it('set() applies an optimistic local update', async () => {
    await act(async () => root.render(<Harness />));
    await act(async () => calls[0].d.resolve('one'));
    await act(async () => snapshot?.set((prev) => `${prev}!`));
    expect(snapshot?.data).toBe('one!');
  });
});
