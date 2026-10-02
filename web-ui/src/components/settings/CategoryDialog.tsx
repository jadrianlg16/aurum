'use client';

/**
 * Create / edit a category. Create sends `{name, kind, icon}`
 * and the server derives the ledger account; edit sends `{name, icon}` (PUT has no `kind`).
 * No tax matrix, no account column, no aliases: management is name + icon + type only.
 */
import { useState } from 'react';
import { Dialog, Field, Input, useToast } from '@/components/ui';
import { createLabel, errorMessage, updateLabel } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import * as v from '@/lib/validate';
import type { Label, LabelCreate, LabelPatch } from '@/lib/types';

export type CategoryKind = 'expense' | 'income';

export interface CategoryDialogProps {
  ws: string;
  label?: Label | null;
  /** Preselects the type on create (the group the button lives in). */
  kind?: CategoryKind;
  onClose: (saved: boolean) => void;
}

export function CategoryDialog({ ws, label, kind: initialKind, onClose }: CategoryDialogProps) {
  const { t } = useI18n();
  const toast = useToast();
  const editing = Boolean(label);
  const [name, setName] = useState(label?.name ?? '');
  const [icon, setIcon] = useState(label?.icon ?? '');
  const [kind, setKind] = useState<CategoryKind>(initialKind ?? 'expense');
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const errors = { name: v.required(name) };
  const show = (k: keyof typeof errors) => (touched && errors[k] ? t(errors[k]) : null);

  const submit = async () => {
    setTouched(true);
    if (!v.isValid(errors)) return;
    setBusy(true);
    setError(null);
    try {
      if (label) {
        const body: LabelPatch = { name: name.trim(), icon: icon.trim() || null };
        await updateLabel(ws, label.id, body);
      } else {
        const body: LabelCreate = { name: name.trim(), kind, icon: icon.trim() || null };
        await createLabel(ws, body);
      }
      onClose(true);
      toast.success(t('cat.saved'));
    } catch (e) {
      setError(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open
      onClose={() => onClose(false)}
      title={editing ? t('cat.edit') : t('cat.new')}
      size="sm"
      form={{ onSubmit: () => void submit(), busy, submitLabel: t('common.save') }}
      error={error}
    >
      <Field label={t('cat.name')} required error={show('name')}>
        <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} data-autofocus />
      </Field>
      <Field label={t('cat.icon')} hint={t('form.optional')}>
        <Input value={icon} onChange={(e) => setIcon(e.target.value)} maxLength={8} />
      </Field>
      {!editing && (
        <Field label={t('cat.kind')} asGroup>
          <div role="radiogroup" aria-label={t('cat.kind')} className="row">
            {(['expense', 'income'] as CategoryKind[]).map((k) => (
              <label key={k} className="row">
                <input type="radio" name="cat-kind" value={k} checked={kind === k} onChange={() => setKind(k)} />
                <span>{t(`cat.kind.${k}`)}</span>
              </label>
            ))}
          </div>
        </Field>
      )}
    </Dialog>
  );
}
