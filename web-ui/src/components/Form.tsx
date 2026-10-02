'use client';

/**
 * Form primitives shared by every write screen.
 *
 * `Dialog` is now a shim over `components/ui/Dialog` (native `<dialog>`, form mode), so the
 * keyboard contract is the browser's own: **Enter submits**, **Esc cancels**. Validation messages are `MsgKey`s from
 * lib/validate, rendered with `t()`, so every rule is bilingual without a second dictionary.
 *
 * Money never becomes a number here: `DecimalField` keeps the typed string and only strips
 * characters a decimal can never contain.
 */
import { useEffect, useId, useRef, type ReactNode } from 'react';
import { useI18n } from '@/lib/i18n';
import type { FieldError as FieldErr } from '@/lib/validate';
import { Dialog as UiDialog } from './ui/Dialog';

/**
 * Focus-on-mount as a ref instead of the JSX prop.
 *
 * `autoFocus` is what `jsx-a11y/no-autofocus` forbids, and rightly so on a page — but inside
 * a modal the first field *should* take focus, or a keyboard user lands nowhere. Focusing
 * explicitly on mount keeps that behaviour and keeps the rule honest, which is also why the
 * prop below is called `focusOnMount`: it never reaches the DOM as `autoFocus`.
 */
function useAutoFocus<T extends HTMLElement>(enabled?: boolean) {
  const ref = useRef<T | null>(null);
  useEffect(() => {
    if (enabled) ref.current?.focus();
  }, [enabled]);
  return ref;
}

export function FieldError({ error }: { error: FieldErr }) {
  const { t } = useI18n();
  if (!error) return null;
  return (
    <span className="err small" style={{ display: 'block', marginTop: 4 }}>
      {t(error)}
    </span>
  );
}

interface BaseProps {
  label: string;
  error?: FieldErr;
  hint?: string;
  required?: boolean;
  children?: ReactNode;
}

function Wrap({ label, error, hint, required, children }: BaseProps) {
  return (
    <label className="field" style={{ display: 'block', marginBottom: 12 }}>
      <span>
        {label}
        {required ? ' *' : ''}
      </span>
      {children}
      {hint && <span className="small muted" style={{ display: 'block', marginTop: 4 }}>{hint}</span>}
      <FieldError error={error ?? null} />
    </label>
  );
}

export function TextField({
  label,
  value,
  onChange,
  error,
  hint,
  required,
  placeholder,
  type = 'text',
  focusOnMount,
  disabled,
  list,
}: BaseProps & {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: 'text' | 'date' | 'month';
  focusOnMount?: boolean;
  disabled?: boolean;
  list?: string;
}) {
  return (
    <Wrap label={label} error={error} hint={hint} required={required}>
      <input
        type={type === 'month' ? 'text' : type}
        value={value}
        list={list}
        disabled={disabled}
        ref={useAutoFocus<HTMLInputElement>(focusOnMount)}
        placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        onChange={(e) => onChange(e.target.value)}
        style={{ width: '100%' }}
      />
    </Wrap>
  );
}

/**
 * A decimal *string* input. Keystrokes are filtered to digits, one dot and a leading minus;
 * the value is never parsed to a float, and is sent to the API exactly as typed.
 */
export function DecimalField({
  label,
  value,
  onChange,
  error,
  hint,
  required,
  placeholder = '0.00',
  allowNegative = false,
  focusOnMount,
}: BaseProps & {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  allowNegative?: boolean;
  focusOnMount?: boolean;
}) {
  const clean = (raw: string) => {
    let s = raw.replace(allowNegative ? /[^\d.-]/g : /[^\d.]/g, '');
    if (allowNegative) s = (s.startsWith('-') ? '-' : '') + s.replace(/-/g, '');
    const [int, ...rest] = s.replace(/^-/, '').split('.');
    const joined = rest.length ? `${int}.${rest.join('')}` : int;
    return (s.startsWith('-') ? '-' : '') + joined;
  };
  return (
    <Wrap label={label} error={error} hint={hint} required={required}>
      <input
        type="text"
        inputMode="decimal"
        value={value}
        ref={useAutoFocus<HTMLInputElement>(focusOnMount)}
        placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        onChange={(e) => onChange(clean(e.target.value))}
        style={{ width: '100%', fontFamily: 'var(--mono)' }}
      />
    </Wrap>
  );
}

export function SelectField<T extends string>({
  label,
  value,
  onChange,
  options,
  error,
  hint,
  required,
  focusOnMount,
  disabled,
}: BaseProps & {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  focusOnMount?: boolean;
  disabled?: boolean;
}) {
  return (
    <Wrap label={label} error={error} hint={hint} required={required}>
      <select
        value={value}
        disabled={disabled}
        ref={useAutoFocus<HTMLSelectElement>(focusOnMount)}
        aria-invalid={error ? true : undefined}
        onChange={(e) => onChange(e.target.value as T)}
        style={{ width: '100%' }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Wrap>
  );
}

export function CheckField({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
}) {
  return (
    <label className="row" style={{ gap: 8, marginBottom: 8, alignItems: 'flex-start' }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>
        {label}
        {hint && <span className="small muted" style={{ display: 'block' }}>{hint}</span>}
      </span>
    </label>
  );
}

/**
 * Beancount account picker: a free-text input backed by a `<datalist>` of the workspace's real
 * accounts (`GET /ledger/{ws}/accounts`). Free text is allowed on purpose — Beancount creates
 * an account the first time it is used, and the format is validated client-side.
 */
export function AccountField({
  label,
  value,
  onChange,
  accounts,
  error,
  required,
  hint,
  focusOnMount,
  filter,
}: BaseProps & {
  value: string;
  onChange: (v: string) => void;
  accounts: string[];
  focusOnMount?: boolean;
  filter?: string;
}) {
  const id = useId();
  const options = filter ? accounts.filter((a) => a.startsWith(filter)) : accounts;
  return (
    <Wrap label={label} error={error} hint={hint} required={required}>
      <input
        type="text"
        list={id}
        value={value}
        ref={useAutoFocus<HTMLInputElement>(focusOnMount)}
        placeholder="Expenses:Food:DiningOut"
        aria-invalid={error ? true : undefined}
        onChange={(e) => onChange(e.target.value)}
        style={{ width: '100%', fontFamily: 'var(--mono)' }}
      />
      <datalist id={id}>
        {options.map((a) => (
          <option key={a} value={a} />
        ))}
      </datalist>
    </Wrap>
  );
}

/**
 * Modal form — a shim over `ui/Dialog` in form mode. The props are exactly
 * what the seven older callers pass; `open` is always true because those callers mount
 * the component conditionally. Enter submits, Esc cancels, focus returns to the opener, and at
 * ≤640px it is a bottom sheet — all inherited from the primitive. New screens use
 * `ui/Dialog` directly; this shim goes once the last older caller migrates.
 */
export function Dialog({
  title,
  onCancel,
  onSubmit,
  busy,
  error,
  submitLabel,
  destructive,
  wide,
  children,
}: {
  title: string;
  onCancel: () => void;
  onSubmit: () => void;
  busy?: boolean;
  error?: string | null;
  submitLabel?: string;
  destructive?: boolean;
  wide?: boolean;
  children: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <UiDialog
      open
      onClose={onCancel}
      title={title}
      description={t('form.keys')}
      size={wide ? 'lg' : 'md'}
      form={{ onSubmit, busy, submitLabel }}
      destructive={destructive}
      error={error}
    >
      {children}
    </UiDialog>
  );
}

/** The `New` / `Edit` / `Delete` button trio used on every list row. */
export function RowActions({
  onEdit,
  onDelete,
  busy,
}: {
  onEdit?: () => void;
  onDelete?: () => void;
  busy?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
      {onEdit && (
        <button type="button" className="btn ghost" onClick={onEdit} disabled={busy}>
          {t('form.edit')}
        </button>
      )}
      {onDelete && (
        <button type="button" className="btn ghost" onClick={onDelete} disabled={busy}>
          {t('form.delete')}
        </button>
      )}
    </div>
  );
}
