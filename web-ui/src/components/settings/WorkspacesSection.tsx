'use client';

/**
 * Ajustes › Espacios. `GET /workspaces?include_hidden=1`
 * (the provider's list omits hidden ones), personal first, demos (`profile.demo === true`)
 * grouped under "Demos", a "Protegido" badge, and a hide/show toggle (`PUT {hidden}`) disabled
 * for the protected space and the current one. "Nuevo espacio" opens `WorkspaceDialog`; after a
 * create the app switches to it with `setWs(id)` and `refresh()` — no page reload. No delete,
 * no reset.
 */
import { useCallback, useState } from 'react';
import tap from '@/components/plan/tap.module.css';
import { WorkspaceDialog } from '@/components/WorkspaceForm';
import { Badge, Button, ErrorBox, Skeleton, useToast } from '@/components/ui';
import { errorMessage, listWorkspaces, updateWorkspace } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { Workspace } from '@/lib/types';

const isDemo = (w: Workspace) => w.profile?.demo === true;

export function WorkspacesSection() {
  const { t } = useI18n();
  const toast = useToast();
  const { ws, setWs, refresh } = useWorkspace();
  const list = useResource(useCallback(() => listWorkspaces({ includeHidden: true }), []), []);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const rows = list.data ?? [];
  const mine = rows.filter((w) => !isDemo(w));
  const demos = rows.filter(isDemo);

  const toggle = async (w: Workspace) => {
    setBusyId(w.id);
    try {
      await updateWorkspace(w.id, { hidden: !w.hidden });
      toast.success(t('settings.spaces.updated'));
      list.reload();
      refresh();
    } catch (e) {
      toast.error(errorMessage(e, t));
    } finally {
      setBusyId(null);
    }
  };

  const row = (w: Workspace) => {
    const current = w.id === ws;
    const locked = w.protected === true || current;
    return (
      <li key={w.id} className="row" data-testid="ws-row" data-ws-id={w.id} data-hidden={w.hidden ? 'true' : 'false'}>
        <span>
          <strong>{w.name}</strong> <span className="small muted">{w.id}</span>
        </span>
        {current && <Badge tone="accent">{t('settings.spaces.current')}</Badge>}
        {w.protected && <Badge tone="info">{t('settings.spaces.protected')}</Badge>}
        {w.hidden && <Badge tone="neutral">{t('settings.spaces.hidden')}</Badge>}
        {!current && !w.hidden && (
          <Button variant="ghost" onClick={() => setWs(w.id)}>
            {t('settings.spaces.use')}
          </Button>
        )}
        <Button variant="ghost" onClick={() => void toggle(w)} disabled={locked} loading={busyId === w.id}>
          {w.hidden ? t('settings.spaces.show') : t('settings.spaces.hide')}
        </Button>
      </li>
    );
  };

  return (
    <div className="stack">
      <p className="small muted">{t('settings.spaces.hint')}</p>
      {list.loading ? (
        <Skeleton variant="list" rows={3} what={t('settings.spaces.list')} />
      ) : list.error && !list.data ? (
        <ErrorBox error={list.problem ?? list.error} onRetry={list.reload} />
      ) : (
        <>
          <ul className="plain-list stack" aria-label={t('settings.spaces.list')}>
            {mine.map(row)}
          </ul>
          {demos.length > 0 && (
            <details>
              <summary className={tap.summary}>
                {t('settings.spaces.demos')} ({demos.length})
              </summary>
              <ul className="plain-list stack" aria-label={t('settings.spaces.demos')}>
                {demos.map(row)}
              </ul>
            </details>
          )}
        </>
      )}
      <div className="row">
        <Button variant="secondary" icon="plus" onClick={() => setCreating(true)}>
          {t('settings.spaces.new')}
        </Button>
      </div>
      {creating && (
        <WorkspaceDialog
          onClose={(savedId) => {
            setCreating(false);
            if (!savedId) return;
            toast.success(t('settings.spaces.created'));
            setWs(savedId);
            refresh();
            list.reload();
          }}
        />
      )}
    </div>
  );
}
