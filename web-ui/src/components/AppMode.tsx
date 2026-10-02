'use client';

/**
 * Simple / advanced mode — the write half.
 *
 * `useModeSave()` PUTs `ui_mode` / `modules` through `PUT /api/workspaces/{ws}` (a UI
 * preference only: hiding a module never disables its endpoints), toasts `mode.saved` and
 * refreshes the workspace list so the rail picks the change up. `refresh()` keeps the current
 * id and never re-applies `?ws=`. The radio itself lives in
 * `components/settings/ModeSection.tsx`; this file renders no JSX.
 */
import { useState } from 'react';
import { useToast } from '@/components/ui';
import { errorMessage, updateWorkspace } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useWorkspace } from '@/lib/workspace';
import type { Modules, UiMode } from '@/lib/types-personal';

export interface ModeSaveValue {
  save: (next: { ui_mode?: UiMode; modules?: Modules }) => Promise<boolean>;
  busy: boolean;
  error: string | null;
  mode: UiMode;
  modules: Modules;
}

export function useModeSave(): ModeSaveValue {
  const { t } = useI18n();
  const toast = useToast();
  const { ws, current, refresh } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mode: UiMode = current?.ui_mode === 'advanced' ? 'advanced' : 'simple';
  const modules: Modules = current?.modules ?? {};

  const save = async (next: { ui_mode?: UiMode; modules?: Modules }): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      await updateWorkspace(ws, next);
      toast.success(t('mode.saved'));
      refresh();
      return true;
    } catch (e) {
      setError(errorMessage(e, t));
      return false;
    } finally {
      setBusy(false);
    }
  };

  return { save, busy, error, mode, modules };
}
