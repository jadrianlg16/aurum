'use client';

/**
 * Ajustes › Modo. A real radiogroup — Simple / Avanzado — whose
 * checked state is exactly `current.ui_mode === 'advanced'` (the old switch showed the label
 * of the current mode next to a checkbox that meant "advanced", which read inverted). The
 * per-module switches sit in a collapsed `<details>` and only matter in simple mode; in
 * advanced mode everything is on anyway.
 */
import { useModeSave } from '@/components/AppMode';
import tap from '@/components/plan/tap.module.css';
import { useI18n } from '@/lib/i18n';
import { MODULE_KEYS, type ModuleKey, type UiMode } from '@/lib/types-personal';

export function ModeSection() {
  const { t } = useI18n();
  const { save, busy, error, mode, modules } = useModeSave();
  const pick = (next: UiMode) => {
    if (next !== mode) void save({ ui_mode: next });
  };
  const options: { id: UiMode; label: string; hint: string }[] = [
    { id: 'simple', label: t('settings.mode.simple'), hint: t('settings.mode.simple.hint') },
    { id: 'advanced', label: t('settings.mode.advanced'), hint: t('settings.mode.advanced.hint') },
  ];

  return (
    <div className="stack">
      <div role="radiogroup" aria-label={t('settings.section.mode')} className="stack">
        {options.map((o) => (
          <div key={o.id}>
            <label className={tap.choice} htmlFor={`ui-mode-${o.id}`}>
              <input
                id={`ui-mode-${o.id}`}
                type="radio"
                name="ui-mode"
                value={o.id}
                checked={mode === o.id}
                disabled={busy}
                data-testid={`mode-radio-${o.id}`}
                aria-describedby={`ui-mode-${o.id}-hint`}
                onChange={() => pick(o.id)}
              />
              <strong>{o.label}</strong>
            </label>
            <p className="small muted" id={`ui-mode-${o.id}-hint`}>
              {o.hint}
            </p>
          </div>
        ))}
      </div>
      {error && (
        <p className="err" role="alert">
          {error}
        </p>
      )}
      <details>
        <summary className={tap.summary}>{t('settings.mode.modules')}</summary>
        <div className="grid cols-2">
          {MODULE_KEYS.map((k: ModuleKey) => (
            <label className={tap.choice} key={k}>
              <input
                type="checkbox"
                checked={mode === 'advanced' || modules[k] === true}
                disabled={busy || mode === 'advanced'}
                onChange={(e) => void save({ modules: { ...modules, [k]: e.target.checked } })}
              />
              <span>{t(`mode.module.${k}`)}</span>
            </label>
          ))}
        </div>
      </details>
    </div>
  );
}
