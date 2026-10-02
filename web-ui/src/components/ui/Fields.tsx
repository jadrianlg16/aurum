'use client';

/**
 * Form fields.
 *
 * `Field` owns the ids: the label points at the control, `aria-describedby` lists the hint and
 * the error, `aria-invalid` is set only while an error exists, and a required field carries a
 * visual `*` plus an sr-only "obligatorio". `Input`/`Textarea`/`Select` are the bare controls
 * (36px with a mouse, 44px on coarse pointers via CSS). `MoneyInput` is string-only: it strips
 * to digits, one dot and an optional leading minus, groups on blur, unformats on focus, and
 * never turns the value into a float. `DateField` is the native date input with Hoy/Ayer chips
 * that use LOCAL dates.
 */
import {
  createContext,
  forwardRef,
  useCallback,
  useContext,
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';
import { todayLocalIso } from '@/lib/format';
import { useI18n } from '@/lib/i18n';

interface FieldIds {
  id: string;
  describedBy?: string;
  invalid?: true;
  required?: boolean;
}

const FieldContext = createContext<FieldIds | null>(null);

/** Bind a control to the surrounding `Field` (id + aria). Bare controls outside a Field get nothing. */
export function useFieldIds(explicitId?: string): {
  id?: string;
  'aria-describedby'?: string;
  'aria-invalid'?: true;
  required?: boolean;
} {
  const ctx = useContext(FieldContext);
  if (!ctx) return explicitId ? { id: explicitId } : {};
  return {
    id: explicitId ?? ctx.id,
    'aria-describedby': ctx.describedBy,
    'aria-invalid': ctx.invalid,
    required: ctx.required,
  };
}

export interface FieldProps {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  required?: boolean;
  /** Set when the child is not a single labelable control (a group of chips). */
  asGroup?: boolean;
  className?: string;
  children: ReactNode;
}

export function Field({ label, hint, error, required, asGroup, className, children }: FieldProps) {
  const { t } = useI18n();
  const base = useId();
  const id = `${base}-c`;
  const hintId = `${base}-h`;
  const errId = `${base}-e`;
  const describedBy = [hint ? hintId : null, error ? errId : null].filter(Boolean).join(' ') || undefined;
  const ctx: FieldIds = { id, describedBy, invalid: error ? true : undefined, required };
  const labelNode = (
    <>
      {label}
      {required && (
        <>
          <span aria-hidden="true"> *</span>
          <span className="sr-only"> ({t('a11y.required')})</span>
        </>
      )}
    </>
  );
  const cls = ['ui-field', className].filter(Boolean).join(' ');
  const tail = (
    <>
      {hint && (
        <span className="ui-field-hint" id={hintId}>
          {hint}
        </span>
      )}
      {error && (
        <span className="ui-field-error" id={errId}>
          {error}
        </span>
      )}
    </>
  );
  if (asGroup) {
    return (
      <div className={cls} role="group" aria-labelledby={`${base}-l`} aria-describedby={describedBy}>
        <span className="ui-field-label" id={`${base}-l`}>
          {labelNode}
        </span>
        <FieldContext.Provider value={ctx}>{children}</FieldContext.Provider>
        {tail}
      </div>
    );
  }
  return (
    <div className={cls}>
      <label htmlFor={id}>{labelNode}</label>
      <FieldContext.Provider value={ctx}>{children}</FieldContext.Provider>
      {tail}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, id, ...rest },
  ref,
) {
  const ids = useFieldIds(id);
  return <input ref={ref} className={['ui-input', className].filter(Boolean).join(' ')} {...ids} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, id, ...rest }, ref) {
    const ids = useFieldIds(id);
    return <textarea ref={ref} className={['ui-textarea', className].filter(Boolean).join(' ')} {...ids} {...rest} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, id, ...rest },
  ref,
) {
  const ids = useFieldIds(id);
  return <select ref={ref} className={['ui-select', className].filter(Boolean).join(' ')} {...ids} {...rest} />;
});

/* ------------------------------------------------------------- MoneyInput */

/** Keep digits, one dot and (optionally) a leading minus. Pure string work. */
export function cleanDecimal(raw: string, allowNegative: boolean): string {
  let s = raw.replace(/,/g, '').replace(allowNegative ? /[^\d.-]/g : /[^\d.]/g, '');
  const neg = allowNegative && s.startsWith('-');
  s = s.replace(/-/g, '');
  const [int, ...rest] = s.split('.');
  const joined = rest.length ? `${int}.${rest.join('')}` : int;
  return (neg ? '-' : '') + joined;
}

/** `1234.5` → `1,234.50` for display while the field is not focused. */
export function groupDecimal(value: string): string {
  if (!/^-?\d+(\.\d*)?$/.test(value)) return value;
  const neg = value.startsWith('-');
  const [int, frac = ''] = value.replace(/^-/, '').split('.');
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const cents = (frac + '00').slice(0, 2);
  return `${neg ? '-' : ''}${grouped}.${cents}`;
}

export interface MoneyInputProps {
  value: string;
  onChange: (value: string) => void;
  currency: string;
  allowNegative?: boolean;
  /** Focus via a ref on mount (never the DOM `autoFocus` prop). */
  autoFocus?: boolean;
  /** Changing this value re-focuses the field (e.g. after "Guardar y agregar otro"). */
  focusKey?: string | number;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  name?: string;
  className?: string;
}

export const MoneyInput = forwardRef<HTMLInputElement, MoneyInputProps>(function MoneyInput(
  { value, onChange, currency, allowNegative = false, autoFocus, focusKey, placeholder = '0.00', disabled, id, name, className },
  ref,
) {
  const inner = useRef<HTMLInputElement>(null);
  useImperativeHandle(ref, () => inner.current as HTMLInputElement);
  const ids = useFieldIds(id);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (autoFocus) inner.current?.focus();
  }, [autoFocus]);
  useEffect(() => {
    if (focusKey !== undefined) inner.current?.focus();
  }, [focusKey]);

  const shown = focused ? value : value ? groupDecimal(value) : '';
  return (
    <span className={['ui-money', className].filter(Boolean).join(' ')}>
      <input
        ref={inner}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        enterKeyHint="done"
        name={name}
        value={shown}
        placeholder={placeholder}
        disabled={disabled}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onChange={(e) => onChange(cleanDecimal(e.target.value, allowNegative))}
        {...ids}
      />
      <span className="ui-money-cur" aria-hidden="true">
        {currency.toUpperCase()}
      </span>
    </span>
  );
});

/* -------------------------------------------------------------- DateField */

export function DateField({
  value,
  onChange,
  todayYesterdayChips = true,
  min,
  max,
  disabled,
  id,
}: {
  value: string;
  onChange: (iso: string) => void;
  todayYesterdayChips?: boolean;
  min?: string;
  max?: string;
  disabled?: boolean;
  id?: string;
}) {
  const { t } = useI18n();
  const ids = useFieldIds(id);
  // The chips compute their dates on click — never at render — so prerendering stays clock-free.
  const pick = useCallback(
    (daysBack: number) => {
      const d = new Date();
      d.setDate(d.getDate() - daysBack);
      onChange(todayLocalIso(d));
    },
    [onChange],
  );
  const [today, setToday] = useState<string | null>(null);
  useEffect(() => {
    setToday(todayLocalIso());
  }, [value]);
  const yesterday = today
    ? (() => {
        const d = new Date();
        d.setDate(d.getDate() - 1);
        return todayLocalIso(d);
      })()
    : null;
  return (
    <span className="ui-date">
      <input
        className="ui-input"
        type="date"
        value={value}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        {...ids}
      />
      {todayYesterdayChips && (
        <span className="ui-chips">
          <button type="button" className="ui-chip" aria-pressed={today !== null && value === today} onClick={() => pick(0)} disabled={disabled}>
            {t('form.today')}
          </button>
          <button
            type="button"
            className="ui-chip"
            aria-pressed={yesterday !== null && value === yesterday}
            onClick={() => pick(1)}
            disabled={disabled}
          >
            {t('form.yesterday')}
          </button>
        </span>
      )}
    </span>
  );
}
