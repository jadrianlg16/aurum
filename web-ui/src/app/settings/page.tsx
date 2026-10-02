'use client';

/**
 * Ajustes. One scrolling page with anchored
 * sections: Perfil · Apariencia · Categorías · Modo · Copia de seguridad · Espacios, then
 * "Empezar de nuevo" and "Restablecer preferencias", and — only when `useAdvanced()` — the
 * Avanzado group (API access / MCP, the models the server reports, the raw profile, the full
 * profile dialog). In simple mode nothing on this page mentions tokens, MCP, env names, tax
 * acronyms, ledger paths or "Espacio de trabajo".
 */
import { useState } from 'react';
import { ApiSecuritySection } from '@/components/Security';
import { ProfileForm, WorkspaceDialog } from '@/components/WorkspaceForm';
import { AppearanceSection } from '@/components/settings/AppearanceSection';
import { BackupSection } from '@/components/settings/BackupSection';
import { ModeSection } from '@/components/settings/ModeSection';
import { WorkspacesSection } from '@/components/settings/WorkspacesSection';
import { Badge, Button, ConfirmDialog, PageHeader, useToast } from '@/components/ui';
import { useHealth } from '@/lib/health';
import { useI18n } from '@/lib/i18n';
import { useAdvanced, useWorkspace } from '@/lib/workspace';

type Anchor = 'perfil' | 'apariencia' | 'categorias' | 'modo' | 'respaldo' | 'espacios' | 'avanzado';

function Section({ id, title, children }: { id: Anchor; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="card" data-testid={`settings-section-${id}`} aria-labelledby={`settings-${id}-h`}>
      <h2 id={`settings-${id}-h`}>{title}</h2>
      {children}
    </section>
  );
}

/** Every key the app stores in this browser starts with `aurum.`. */
function clearPreferences(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const k = window.localStorage.key(i);
      if (k && k.startsWith('aurum.')) keys.push(k);
    }
    for (const k of keys) window.localStorage.removeItem(k);
  } catch {
    /* storage blocked — nothing to clear */
  }
}

const PROFILE_KEYS: Record<string, 'settings.rfc' | 'settings.regime' | 'settings.state'> = {
  rfc: 'settings.rfc',
  regime: 'settings.regime',
  state: 'settings.state',
};

export default function SettingsPage() {
  const { t } = useI18n();
  const { ws, current, refresh } = useWorkspace();
  const advanced = useAdvanced();
  const { health } = useHealth();
  const toast = useToast();
  const [resetOpen, setResetOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  return (
    <>
      <PageHeader title={t('settings.title')} subtitle={t('settings.sub')} />
      <div className="stack">
        <Section id="perfil" title={t('settings.section.profile')}>
          <ProfileForm />
        </Section>

        <Section id="apariencia" title={t('settings.section.appearance')}>
          <AppearanceSection />
        </Section>

        {/* Categories have their own screen in the rail; Ajustes points there. */}
        <Section id="categorias" title={t('settings.section.categories')}>
          <p className="small muted">{t('cat.sub')}</p>
          <Button variant="secondary" href="/categorias/">
            {t('cat.open')}
          </Button>
        </Section>

        <Section id="modo" title={t('settings.section.mode')}>
          <ModeSection />
        </Section>

        <Section id="respaldo" title={t('settings.section.backup')}>
          <BackupSection ws={ws} />
        </Section>

        <Section id="espacios" title={t('settings.section.spaces')}>
          <WorkspacesSection />
        </Section>

        <section className="card stack">
          <div className="row">
            <Button variant="secondary" href="/empezar/">
              {t('settings.restart')}
            </Button>
            <span className="small muted">{t('settings.restart.hint')}</span>
          </div>
          <div className="row">
            <Button variant="ghost" onClick={() => setResetOpen(true)}>
              {t('settings.reset_prefs')}
            </Button>
            <span className="small muted">{t('settings.reset_prefs.hint')}</span>
          </div>
        </section>

        {advanced && (
          <Section id="avanzado" title={t('settings.section.advanced')}>
            <div className="stack">
              <ApiSecuritySection />

              <div className="stack">
                <h3>{t('adv.settings.models')}</h3>
                <p className="small muted">{t('adv.settings.models.hint')}</p>
                <div className="row">
                  <Badge tone="neutral">
                    {t('settings.provider')}: {health?.llm?.provider ?? '—'}
                  </Badge>
                  <Badge tone="neutral">
                    {t('settings.model')}: {health?.llm?.model ?? '—'}
                  </Badge>
                  <Badge tone={health?.llm?.cloud_opt_in ? 'warn' : 'pos'}>
                    {health?.llm?.cloud_opt_in ? t('adv.settings.cloud.on') : t('adv.settings.cloud.off')}
                  </Badge>
                </div>
              </div>

              <div className="stack">
                <div className="row">
                  <h3>{t('adv.settings.profile.raw')}</h3>
                  <Button variant="secondary" disabled={!current} onClick={() => setProfileOpen(true)}>
                    {t('ws.edit')}
                  </Button>
                </div>
                {current && (
                  <table className="ui-table">
                    <tbody>
                      <tr>
                        <td>{t('ws.id')}</td>
                        <td className="kbd">{current.id}</td>
                      </tr>
                      <tr>
                        <td>{t('ws.kind')}</td>
                        <td>{t(`ws.kind.${current.kind}`)}</td>
                      </tr>
                      <tr>
                        <td>{t('settings.jurisdictions')}</td>
                        <td>
                          {current.jurisdictions.map((j) => (
                            <Badge key={j} tone="info">
                              {j}
                            </Badge>
                          ))}
                        </td>
                      </tr>
                      <tr>
                        <td>{t('settings.currency')}</td>
                        <td className="num">{current.base_currency}</td>
                      </tr>
                      {Object.entries(current.profile ?? {}).map(([k, v]) => (
                        <tr key={k}>
                          <td>{PROFILE_KEYS[k] ? t(PROFILE_KEYS[k]) : k}</td>
                          <td className="num">
                            {String(v ?? '—')}
                            {typeof v === 'string' && v.includes('*') && (
                              <>
                                {' '}
                                <Badge tone="neutral">{t('settings.masked')}</Badge>
                              </>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </Section>
        )}
      </div>

      {resetOpen && (
        <ConfirmDialog
          title={t('settings.reset_prefs.title')}
          body={<p>{t('settings.reset_prefs.body')}</p>}
          confirmLabel={t('settings.reset_prefs.confirm')}
          destructive
          onConfirm={() => {
            clearPreferences();
            window.location.assign('/');
          }}
          onCancel={() => setResetOpen(false)}
        />
      )}
      {profileOpen && current && (
        <WorkspaceDialog
          workspace={current}
          onClose={(savedId) => {
            setProfileOpen(false);
            if (savedId) {
              toast.success(t('settings.space.saved'));
              refresh();
            }
          }}
        />
      )}
    </>
  );
}
