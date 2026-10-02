'use client';

/**
 * Spaces (workspaces): Ajustes › Perfil and Ajustes › Espacios.
 *
 * `ProfileForm` is Ajustes › Perfil: the current space's name and currency
 * (`PUT /api/workspaces/{ws}`), the app language (`useI18n().setLang`, a browser preference)
 * and the language of the notices Aurum generates (`{language}` on the workspace).
 *
 * `WorkspaceDialog` creates a space (`POST /api/workspaces`) or, in advanced mode, edits the
 * full profile (`PUT`). Simple mode asks only id / name / currency / language; kind,
 * jurisdictions, RFC, regime and state appear when `useAdvanced()`. The id is part of every
 * other endpoint's path, so it is immutable once created.
 *
 * **RFC stays masked.** The API returns `****1234`; the form shows that read-only and only sends
 * an `rfc` key when a *new* one is typed, so saving can never write a mask over the real value.
 */
import { useEffect, useState } from 'react';
import { Button, Dialog, Field, Input, Select, useToast } from '@/components/ui';
import { createWorkspace, errorMessage, updateWorkspace } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import * as v from '@/lib/validate';
import { useAdvanced, useWorkspace } from '@/lib/workspace';
import type { Jurisdiction, Lang, Workspace, WorkspaceKind } from '@/lib/types';

const KINDS: WorkspaceKind[] = ['personal', 'business', 'advisory'];
const LANGS: { value: Lang; label: string }[] = [
  { value: 'es', label: 'Español' },
  { value: 'en', label: 'English' },
];

/* ------------------------------------------------------------- Perfil ---- */

export function ProfileForm() {
  const { t, lang, setLang } = useI18n();
  const toast = useToast();
  const { ws, current, refresh } = useWorkspace();
  const [name, setName] = useState('');
  const [currency, setCurrency] = useState('');
  const [busy, setBusy] = useState(false);
  const [langBusy, setLangBusy] = useState(false);
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Seed from the workspace once it resolves (and again when the id changes).
  useEffect(() => {
    setName(current?.name ?? '');
    setCurrency(current?.base_currency ?? '');
    setTouched(false);
  }, [current?.id, current?.name, current?.base_currency]);

  const errors = { name: v.required(name), base_currency: v.currency(currency.trim().toUpperCase()) };
  const show = (k: keyof typeof errors) => (touched && errors[k] ? t(errors[k]) : null);
  const dirty = Boolean(current) && (name.trim() !== (current?.name ?? '') || currency.trim().toUpperCase() !== (current?.base_currency ?? ''));

  const save = async () => {
    setTouched(true);
    if (!v.isValid(errors) || !current) return;
    setBusy(true);
    setError(null);
    try {
      await updateWorkspace(ws, { name: name.trim(), base_currency: currency.trim().toUpperCase() });
      toast.success(t('settings.space.saved'));
      refresh();
    } catch (e) {
      setError(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const saveNoticesLang = async (next: Lang) => {
    if (!current || next === current.language) return;
    setLangBusy(true);
    try {
      await updateWorkspace(ws, { language: next });
      toast.success(t('settings.space.saved'));
      refresh();
    } catch (e) {
      toast.error(errorMessage(e, t));
    } finally {
      setLangBusy(false);
    }
  };

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <Field label={t('settings.space.name')} required error={show('name')}>
        <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} disabled={!current} />
      </Field>
      <Field label={t('settings.space.currency')} hint={t('settings.space.currency.hint')} required error={show('base_currency')}>
        <Input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={3} disabled={!current} />
      </Field>
      {error && (
        <p className="err" role="alert">
          {error}
        </p>
      )}
      <div className="row">
        <Button type="submit" variant="secondary" loading={busy} disabled={!dirty}>
          {t('common.save')}
        </Button>
      </div>
      {/* A Select, like the notices language below: `+ Agregar` stays the page's only primary. */}
      <Field label={t('settings.lang.app')}>
        <Select value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
          {LANGS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={t('settings.lang.notices')} hint={t('settings.lang.notices.hint')}>
        <Select value={current?.language ?? 'es'} disabled={!current || langBusy} onChange={(e) => void saveNoticesLang(e.target.value as Lang)}>
          {LANGS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </Select>
      </Field>
    </form>
  );
}

/* ------------------------------------------------------ WorkspaceDialog ---- */

export function WorkspaceDialog({
  workspace,
  onClose,
}: {
  /** Present when editing (advanced); absent for a create. */
  workspace?: Workspace | null;
  onClose: (savedId: string | null) => void;
}) {
  const { t } = useI18n();
  const advanced = useAdvanced();
  const editing = Boolean(workspace);
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const [id, setId] = useState(workspace?.id ?? '');
  const [name, setName] = useState(workspace?.name ?? '');
  const [kind, setKind] = useState<WorkspaceKind>(workspace?.kind ?? 'personal');
  const [mx, setMx] = useState((workspace?.jurisdictions ?? ['MX']).includes('MX'));
  const [us, setUs] = useState((workspace?.jurisdictions ?? []).includes('US'));
  const [currency, setCurrency] = useState(workspace?.base_currency ?? 'MXN');
  const [language, setLanguage] = useState<Lang>(workspace?.language ?? 'es');
  const [rfc, setRfc] = useState('');
  const [regime, setRegime] = useState(String(workspace?.profile?.regime ?? ''));
  const [state, setState] = useState(String(workspace?.profile?.state ?? ''));
  const [touched, setTouched] = useState(false);

  const maskedRfc = String(workspace?.profile?.rfc ?? '');

  const errors = {
    id: editing ? null : v.workspaceId(id),
    name: v.required(name),
    base_currency: v.currency(currency.trim().toUpperCase()),
    jurisdictions: !advanced || mx || us ? null : ('valid.required' as const),
  };
  const show = (k: keyof typeof errors) => (touched && errors[k] ? t(errors[k]) : null);

  const submit = () => {
    setTouched(true);
    if (!v.isValid(errors)) return;
    const jurisdictions: Jurisdiction[] = advanced
      ? [...(mx ? (['MX'] as const) : []), ...(us ? (['US'] as const) : [])]
      : (workspace?.jurisdictions ?? ['MX']);
    const profile: Record<string, string> = {};
    if (advanced) {
      if (rfc.trim()) profile.rfc = rfc.trim().toUpperCase();
      if (regime.trim()) profile.regime = regime.trim();
      if (state.trim()) profile.state = state.trim();
    }
    setBusy(true);
    setApiError(null);
    const common = {
      name: name.trim(),
      kind: advanced ? kind : (workspace?.kind ?? 'personal'),
      jurisdictions,
      base_currency: currency.trim().toUpperCase(),
      language,
      profile,
    };
    const call = editing ? updateWorkspace(workspace!.id, common) : createWorkspace({ id: id.trim(), ...common });
    call
      .then((w) => onClose(w?.id ?? id.trim()))
      .catch((e) => setApiError(errorMessage(e, t)))
      .finally(() => setBusy(false));
  };

  return (
    <Dialog
      open
      onClose={() => onClose(null)}
      title={editing ? t('ws.edit') : t('settings.spaces.new')}
      form={{ onSubmit: submit, busy, submitLabel: t('common.save') }}
      error={apiError}
    >
      <Field label={t('ws.id')} hint={editing ? t('ws.id_immutable') : t('settings.spaces.id.hint')} required={!editing} error={show('id')}>
        <Input value={id} onChange={(e) => setId(e.target.value.toLowerCase())} disabled={editing} maxLength={40} data-autofocus={!editing || undefined} />
      </Field>
      <Field label={t('ws.name')} required error={show('name')}>
        <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
      </Field>
      <Field label={t('ws.currency')} hint={t('settings.space.currency.hint')} required error={show('base_currency')}>
        <Input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={3} />
      </Field>
      <Field label={t('ws.language')}>
        <Select value={language} onChange={(e) => setLanguage(e.target.value as Lang)}>
          {LANGS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </Select>
      </Field>
      {advanced && (
        <>
          <Field label={t('ws.kind')}>
            <Select value={kind} onChange={(e) => setKind(e.target.value as WorkspaceKind)}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`ws.kind.${k}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('ws.jurisdictions')} asGroup required error={show('jurisdictions')}>
            <div className="row">
              <label className="row">
                <input type="checkbox" checked={mx} onChange={(e) => setMx(e.target.checked)} /> MX
              </label>
              <label className="row">
                <input type="checkbox" checked={us} onChange={(e) => setUs(e.target.checked)} /> US
              </label>
            </div>
          </Field>
          <Field label={t('ws.rfc')} hint={maskedRfc ? `${maskedRfc} — ${t('ws.rfc_note')}` : t('ws.rfc_note')}>
            <Input value={rfc} onChange={(e) => setRfc(e.target.value.toUpperCase())} maxLength={13} />
          </Field>
          <Field label={t('ws.regime')} hint={t('form.optional')}>
            <Input value={regime} onChange={(e) => setRegime(e.target.value)} maxLength={40} />
          </Field>
          <Field label={t('ws.state')} hint={t('form.optional')}>
            <Input value={state} onChange={(e) => setState(e.target.value)} maxLength={40} />
          </Field>
        </>
      )}
    </Dialog>
  );
}
