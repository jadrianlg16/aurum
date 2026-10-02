/**
 * Request layer: encoded segments, `lang=`, timeout, error mapping,
 * the 401 registry, empty bodies. `fetch` is mocked; nothing touches a server.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  _resetAuthState,
  deleteEntry,
  errorKey,
  errorMessage,
  getApiToken,
  getHealth,
  listEntries,
  mapApiError,
  onRequestOk,
  onUnauthorized,
  setApiToken,
  setRequestLang,
} from '@/lib/api';

type FetchMock = ReturnType<typeof vi.fn>;

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  const text = body === undefined ? '' : typeof body === 'string' ? body : JSON.stringify(body);
  return new Response(text, { status, headers: { 'Content-Type': 'application/json', ...headers } });
}

let fetchMock: FetchMock;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  setRequestLang('es');
  _resetAuthState();
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('request URL', () => {
  it('encodes every path segment and query value and appends lang=', async () => {
    fetchMock.mockResolvedValueOnce(respond(200, { entries: [], next_cursor: null, totals: { in: { amount: '0.00', currency: 'MXN' }, out: { amount: '0.00', currency: 'MXN' }, net: { amount: '0.00', currency: 'MXN' }, count: 0 } }));
    await listEntries('a b', { q: 'x/y' });
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('/pf/a%20b/entries?q=x%2Fy&lang=es');
  });

  it('follows setRequestLang for later requests', async () => {
    setRequestLang('en');
    fetchMock.mockResolvedValueOnce(respond(200, { ok: true }));
    await getHealth();
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/health\?lang=en$/);
  });

  it('sends the bearer token from aurum.token and migrates the legacy key once', async () => {
    window.localStorage.setItem('aurum.api_token', 'legacy-secret');
    expect(getApiToken()).toBe('legacy-secret');
    expect(window.localStorage.getItem('aurum.token')).toBe('legacy-secret');
    expect(window.localStorage.getItem('aurum.api_token')).toBeNull();
    fetchMock.mockResolvedValueOnce(respond(200, { ok: true }));
    await getHealth();
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer legacy-secret');
    setApiToken('');
    expect(getApiToken()).toBe('');
  });
});

describe('empty bodies', () => {
  it('resolves undefined on a 204 delete instead of calling res.json()', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(deleteEntry('ws', 'e1')).resolves.toBeUndefined();
  });

  it('resolves undefined on a 200 with an empty body', async () => {
    fetchMock.mockResolvedValueOnce(new Response('', { status: 200 }));
    await expect(getHealth()).resolves.toBeUndefined();
  });
});

describe('error mapping', () => {
  it('turns a pydantic 422 array into code validation + field + Spanish copy', async () => {
    fetchMock.mockResolvedValueOnce(
      respond(422, { detail: [{ loc: ['query', 'months'], msg: 'Input should be a valid integer', type: 'int_parsing' }] }),
    );
    const err = await getHealth().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const e = err as ApiError;
    expect(e.status).toBe(422);
    expect(e.code).toBe('validation');
    expect(e.field).toBe('months');
    expect(errorMessage(e)).toBe('Revisa los meses: Input should be a valid integer');
  });

  it('maps middleware {error} bodies to that code', () => {
    expect(mapApiError(403, { error: 'origin_not_allowed' }).code).toBe('origin_not_allowed');
    expect(mapApiError(413, { error: 'payload_too_large' }).code).toBe('payload_too_large');
    expect(mapApiError(400, { error: 'invalid_workspace_id' }).code).toBe('invalid_workspace_id');
    expect(mapApiError(429, { error: 'rate_limited' }).code).toBe('rate_limited');
    expect(errorKey(mapApiError(403, { error: 'host_not_allowed' }))).toBe('err.forbidden.origin');
    expect(errorKey(mapApiError(403, { error: 'demo_mode_read_only' }))).toBe('err.forbidden.demo');
  });

  it('maps coded detail objects and string details by the regex table', () => {
    expect(mapApiError(409, { detail: { code: 'duplicate', existing_id: 'c1' } }).code).toBe('duplicate');
    expect(mapApiError(409, { detail: 'budget for label x in 2026-09 already exists' }).code).toBe('budget_exists');
    expect(mapApiError(409, { detail: 'account a1 has movements; archive it instead of deleting' }).code).toBe('account_has_movements');
    expect(mapApiError(409, { detail: 'entry e1 was already deleted' }).code).toBe('entry_already_deleted');
    expect(mapApiError(400, { detail: 'splits must sum to 100.00, got 90.00' }).code).toBe('splits_sum');
    expect(mapApiError(400, { detail: 'transfer requires to_account_id' }).code).toBe('transfer_needs_target');
    expect(mapApiError(400, { detail: 'transfer cannot use the same account twice' }).code).toBe('transfer_same_account');
    expect(mapApiError(400, { detail: 'account a1 is archived' }).code).toBe('account_archived');
    expect(mapApiError(422, { detail: 'amount must be greater than 0' }).code).toBe('amount_not_positive');
    expect(mapApiError(403, { detail: 'source:cfdi' }).code).toBe('entry_not_editable');
    expect(mapApiError(409, { detail: 'entry e1 was deleted' }).code).toBe('entry_already_deleted');
    expect(mapApiError(409, { detail: 'something else changed' }).code).toBe('conflict');
    expect(mapApiError(404, { detail: 'goal g1 not found' }).code).toBe('not_found');
    expect(mapApiError(500, { detail: 'Internal Server Error' }).code).toBe('server');
    expect(mapApiError(502, undefined, 'Bad Gateway').code).toBe('server');
    expect(mapApiError(400, { detail: { index: 2, msg: 'bad row' } }).field).toBe('entries.2');
  });

  it('errorMessage: Spanish table without t, interpolated vars, generic fallback', () => {
    expect(errorMessage(mapApiError(409, { detail: 'entry e1 was already deleted' }))).toBe('Ese movimiento ya estaba borrado.');
    expect(errorMessage(mapApiError(403, { detail: 'source:cfdi' }))).toContain('se capturó desde cfdi');
    expect(errorMessage(new Error('boom'))).toBe('No se pudo completar: boom');
    expect(errorMessage('plain')).toBe('No se pudo completar: plain');
    expect(errorMessage(mapApiError(418, { detail: 'teapot' }))).toBe('No se pudo completar: teapot');
  });

  it('errorMessage with t uses the key and vars', () => {
    const t = vi.fn((key: string, vars?: Record<string, string | number>) => `${key}|${JSON.stringify(vars ?? {})}`);
    const e = mapApiError(422, { detail: [{ loc: ['body', 'amount'], msg: 'bad', type: 'x' }] });
    const out = errorMessage(e, t);
    expect(t).toHaveBeenCalledWith('err.field.amount');
    expect(out).toContain('err.validation|');
    expect(out).toContain('"field":"err.field.amount|{}"');
    expect(out).toContain('"message":"bad"');
  });

  it('a stalled request becomes code timeout (fake timers, 20 s)', async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementationOnce(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
        }),
    );
    const p = getHealth().catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(20_000);
    const err = (await p) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe('timeout');
    expect(errorMessage(err)).toBe('Aurum tarda demasiado en responder. Inténtalo de nuevo.');
  });

  it('a fetch TypeError becomes code network', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const err = (await getHealth().catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe('network');
    expect(err.status).toBe(0);
    expect(errorMessage(err)).toBe('No hay conexión con Aurum. Revisa que el servidor esté encendido.');
  });
});

describe('401 registry', () => {
  it('fires onUnauthorized once for two 401s inside 2 s, then onRequestOk on the next 2xx', async () => {
    const unauthorized = vi.fn();
    const ok = vi.fn();
    const off1 = onUnauthorized(unauthorized);
    const off2 = onRequestOk(ok);
    fetchMock.mockImplementation(() => Promise.resolve(respond(401, { error: 'unauthorized', hint: 'Bearer' }, { 'WWW-Authenticate': 'Bearer' })));
    const e1 = (await getHealth().catch((e: unknown) => e)) as ApiError;
    await getHealth().catch(() => undefined);
    expect(e1.code).toBe('unauthorized');
    expect(errorMessage(e1)).toBe('Aurum pide una clave de acceso. Escríbela en Ajustes › Avanzado (Token de la API).');
    expect(unauthorized).toHaveBeenCalledTimes(1);
    expect(ok).not.toHaveBeenCalled();
    fetchMock.mockImplementation(() => Promise.resolve(respond(200, { ok: true })));
    await getHealth();
    expect(ok).toHaveBeenCalledTimes(1);
    await getHealth();
    expect(ok).toHaveBeenCalledTimes(1);
    off1();
    off2();
  });
});
