'use client';

/**
 * Ajustes › Avanzado › API access. Rendered only when
 * `useAdvanced()`.
 *
 *  - the API bearer token: a password field whose stored copy lives in this browser's
 *    localStorage (`aurum.token`) and is sent as `Authorization: Bearer` by `lib/api.ts`.
 *    It is read in an effect (state starts empty), so the server-rendered markup never differs
 *    from the first client render (no hydration warning with a stored token);
 *  - whether the server requires a key at all (`useHealth().authRequired`) and whether it is in
 *    demo mode (read-only);
 *  - the MCP client snippet, with the absolute API URL computed after mount
 *    (`window.location.origin + API_BASE`) and the HTTP bearer hint for the `/mcp` transport.
 *
 * The token is never logged and never sent anywhere but `API_BASE`.
 */
import { useEffect, useState } from 'react';
import { Badge, Button, Field, Input, useToast } from '@/components/ui';
import { API_BASE, getApiToken, setApiToken } from '@/lib/api';
import { useHealth } from '@/lib/health';
import { useI18n } from '@/lib/i18n';

const MCP_PORT = process.env.NEXT_PUBLIC_MCP_PORT ?? '5042';

export function mcpSnippet(apiUrl: string, bearerComment: string): string {
  const json = JSON.stringify(
    {
      mcpServers: {
        aurum: {
          command: 'uv',
          args: ['run', 'aurum-mcp'],
          env: { AURUM_API_URL: apiUrl, AURUM_MCP_PORT: MCP_PORT },
        },
      },
    },
    null,
    2,
  );
  return `${bearerComment}\n${json}`;
}

export function ApiSecuritySection() {
  const { t } = useI18n();
  const toast = useToast();
  const { health, demoMode, authRequired, refresh } = useHealth();
  const [token, setToken] = useState('');
  const [stored, setStored] = useState(false);
  const [apiUrl, setApiUrl] = useState(API_BASE);

  // localStorage and window are read after mount only (hydration-safe).
  useEffect(() => {
    const current = getApiToken();
    setToken(current);
    setStored(current !== '');
    try {
      setApiUrl(/^https?:\/\//.test(API_BASE) ? API_BASE : `${window.location.origin}${API_BASE}`);
    } catch {
      setApiUrl(API_BASE);
    }
  }, []);

  const snippet = mcpSnippet(apiUrl, t('adv.settings.mcp.bearer'));

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(snippet);
      toast.success(t('common.copied'));
    } catch {
      toast.error(t('common.error'));
    }
  };

  return (
    <div className="stack">
      {demoMode && (
        <div className="notice warn" role="status">
          {t('settings.demo.banner')}
        </div>
      )}

      <div className="stack">
        <h3>{t('settings.token')}</h3>
        <div className="row">
          <Badge tone={authRequired ? 'warn' : 'neutral'}>{authRequired ? t('adv.settings.auth.required') : t('adv.settings.auth.local')}</Badge>
          <Badge tone={stored ? 'pos' : 'neutral'}>{stored ? t('settings.token.set') : t('settings.token.unset')}</Badge>
        </div>
        <p className="small muted">{t('settings.token.help')}</p>
        <p className="small muted">{t('adv.settings.token.file')}</p>
        <Field label={t('settings.token')}>
          <Input type="password" value={token} autoComplete="off" spellCheck={false} onChange={(e) => setToken(e.target.value)} />
        </Field>
        <div className="row">
          <Button
            variant="secondary"
            onClick={() => {
              setApiToken(token.trim());
              setStored(token.trim() !== '');
              toast.success(t('common.saved'));
              refresh();
            }}
          >
            {t('common.save')}
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setApiToken('');
              setToken('');
              setStored(false);
              toast.success(t('settings.token.unset'));
              refresh();
            }}
          >
            {t('settings.token.clear')}
          </Button>
        </div>
      </div>

      <div className="stack">
        <h3>{t('adv.settings.api')}</h3>
        <table className="ui-table">
          <tbody>
            <tr>
              <td>{t('adv.settings.demo')}</td>
              <td>
                <Badge tone={demoMode ? 'warn' : 'neutral'}>{demoMode ? t('common.yes') : t('common.no')}</Badge>
              </td>
            </tr>
            <tr>
              <td>{t('adv.settings.api')}</td>
              <td className="kbd">{apiUrl}</td>
            </tr>
            <tr>
              <td>{t('adv.settings.version')}</td>
              <td className="kbd">{health?.version ?? '—'}</td>
            </tr>
          </tbody>
        </table>
        {demoMode && <p className="small muted">{t('settings.demo.tooltip')}</p>}
      </div>

      <div className="stack">
        <div className="row">
          <h3>{t('settings.mcp')}</h3>
          <Button variant="secondary" onClick={() => void copy()}>
            {t('common.copy')}
          </Button>
        </div>
        <p className="small muted">{t('settings.mcp.help')}</p>
        <pre className="yaml-preview">{snippet}</pre>
      </div>
    </div>
  );
}
