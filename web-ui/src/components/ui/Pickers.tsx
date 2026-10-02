'use client';

/**
 * AccountPicker and CategoryPicker.
 *
 * Both are `<select>`s fed by the personal API, never by ledger strings: an account option reads
 * `name · institution · balance`, a category option reads its name. `ws` may be `null` while the
 * workspace resolves, so nothing is requested until it is a string.
 *
 * CategoryPicker filters by `label.kind`, falling back to the account prefix for rows written
 * before pf migration v1 (`Expenses:` → expense, `Income:` → income); `allowNew` reveals an
 * inline name input whose Crear calls `createLabel(ws, {name, kind})` — the request body is sent
 * through one locally typed cast because the legacy `LabelInput` type is wider than this body.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { createLabel, listLabels, listPfAccounts } from '@/lib/api';
import { useI18n, useMoney } from '@/lib/i18n';
import type { Label, LabelInput } from '@/lib/types';
import type { PfAccount, PfAccountType } from '@/lib/types-personal';
import { Button } from './Button';
import { Input, Select, useFieldIds } from './Fields';

export type LabelKind = 'expense' | 'income' | 'transfer';

/** `Label` plus the `kind`/`archived` fields (pf migration v1); optional for older servers. */
export type PickerLabel = Label & { kind?: LabelKind | null; archived?: boolean | null };

const GROUPS: { key: 'cash' | 'cards' | 'loans' | 'investments' | 'other'; types: PfAccountType[] }[] = [
  { key: 'cash', types: ['checking', 'savings', 'cash'] },
  { key: 'cards', types: ['credit_card'] },
  { key: 'loans', types: ['loan'] },
  { key: 'investments', types: ['investment'] },
  { key: 'other', types: ['other'] },
];

export interface AccountPickerProps {
  ws: string | null | undefined;
  value: string;
  onChange: (id: string, account: PfAccount | null) => void;
  filterTypes?: PfAccountType[];
  /** Adds a "+ nueva cuenta" option that calls `onCreateNew` instead of selecting. */
  allowNew?: boolean;
  onCreateNew?: () => void;
  disabled?: boolean;
  id?: string;
  /** Rendered first; defaults to a blank option so nothing is chosen silently. */
  placeholder?: string;
  /** Bump to refetch (after an account is created elsewhere). */
  version?: number;
  /**
   * With no value yet, pick the obvious account once the list loads — the only
   * one, else the first bank account, else the first cash one, else the first listed. The
   * select stays visible, so the choice is always on screen and changeable.
   */
  autoPick?: boolean;
}

const NEW = '__new__';

export function AccountPicker({ ws, value, onChange, filterTypes, allowNew, onCreateNew, disabled, id, placeholder, version, autoPick }: AccountPickerProps) {
  const { t } = useI18n();
  const { fmt } = useMoney();
  const [accounts, setAccounts] = useState<PfAccount[]>([]);
  const ids = useFieldIds(id);

  useEffect(() => {
    if (!ws) return undefined;
    let alive = true;
    listPfAccounts(ws)
      .then((r) => {
        if (alive) setAccounts(r.filter((a) => !a.archived));
      })
      .catch(() => {
        if (alive) setAccounts([]);
      });
    return () => {
      alive = false;
    };
  }, [ws, version]);

  const visible = filterTypes ? accounts.filter((a) => filterTypes.includes(a.type)) : accounts;

  useEffect(() => {
    if (!autoPick || value || visible.length === 0) return;
    const pick =
      (visible.length === 1 ? visible[0] : null) ??
      visible.find((a) => a.type === 'checking') ??
      visible.find((a) => a.type === 'cash') ??
      visible[0];
    onChange(pick.id, pick);
    // Runs when the list lands (or the value is cleared); onChange identity is the caller's.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPick, value, accounts]);
  const label = (a: PfAccount) =>
    [a.name, a.institution, a.balance ? fmt(a.balance) : null].filter(Boolean).join(' · ');

  const groups: ReactNode[] = [];
  for (const g of GROUPS) {
    const rows = visible.filter((a) => g.types.includes(a.type));
    if (rows.length === 0) continue;
    groups.push(
      <optgroup key={g.key} label={t(`accounts.group.${g.key}`)}>
        {rows.map((a) => (
          <option key={a.id} value={a.id}>
            {label(a)}
          </option>
        ))}
      </optgroup>,
    );
  }

  return (
    <Select
      value={value}
      disabled={disabled || !ws}
      onChange={(e) => {
        const v = e.target.value;
        if (v === NEW) {
          onCreateNew?.();
          return;
        }
        onChange(v, accounts.find((a) => a.id === v) ?? null);
      }}
      {...ids}
    >
      <option value="">{placeholder ?? t('form.pick_account')}</option>
      {groups}
      {allowNew && <option value={NEW}>{t('accounts.new')}</option>}
    </Select>
  );
}

function kindOf(l: PickerLabel): LabelKind | null {
  if (l.kind) return l.kind;
  const acct = l.account ?? '';
  if (acct.startsWith('Expenses:')) return 'expense';
  if (acct.startsWith('Income:')) return 'income';
  return null;
}

export interface CategoryPickerProps {
  ws: string | null | undefined;
  /** `undefined` shows expense + income (+ unclassified); `transfer` labels are never shown. */
  kind?: 'expense' | 'income';
  value: string;
  onChange: (id: string, label: PickerLabel | null) => void;
  allowNew?: boolean;
  disabled?: boolean;
  id?: string;
  version?: number;
  /** Label of the blank first option; a filter passes "Todas" (the default says "Sin categoría"). */
  placeholder?: string;
}

export function CategoryPicker({ ws, kind, value, onChange, allowNew, disabled, id, version, placeholder }: CategoryPickerProps) {
  const { t } = useI18n();
  const [labels, setLabels] = useState<PickerLabel[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const ids = useFieldIds(id);

  useEffect(() => {
    if (!ws) return undefined;
    let alive = true;
    listLabels(ws)
      .then((r) => {
        if (alive) setLabels((r as PickerLabel[]).filter((l) => !l.archived));
      })
      .catch(() => {
        if (alive) setLabels([]);
      });
    return () => {
      alive = false;
    };
  }, [ws, version, nonce]);

  const visible = labels.filter((l) => {
    const k = kindOf(l);
    if (k === 'transfer') return false;
    if (kind) return k === kind;
    return true;
  });

  const create = async () => {
    const trimmed = name.trim();
    if (!ws || !trimmed || !kind) return;
    setBusy(true);
    setError(null);
    try {
      // `createLabel(ws, {name, kind, parent?, icon?})`: the wire body is exactly what
      // POST /labels accepts.
      const body = { name: trimmed, kind } as unknown as LabelInput;
      const created = (await createLabel(ws, body)) as PickerLabel;
      setName('');
      setCreating(false);
      setNonce((n) => n + 1);
      setLabels((cur) => [...cur, created]);
      onChange(created.id, created);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Select
        value={value}
        disabled={disabled || !ws}
        onChange={(e) => {
          const v = e.target.value;
          if (v === NEW) {
            setCreating(true);
            return;
          }
          onChange(v, labels.find((l) => l.id === v) ?? null);
        }}
        {...ids}
      >
        <option value="">{placeholder ?? t('common.no_category')}</option>
        {visible.map((l) => (
          <option key={l.id} value={l.id}>
            {l.name}
          </option>
        ))}
        {allowNew && kind && <option value={NEW}>{t('common.new_category')}</option>}
      </Select>
      {allowNew && kind && creating && (
        <span className="ui-inline-new">
          <Input
            id={`${ids.id ?? 'cat'}-new`}
            value={name}
            placeholder={t('common.name')}
            aria-label={t('common.new_category')}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void create();
              }
            }}
            disabled={busy}
          />
          <Button variant="primary" size="sm" onClick={() => void create()} loading={busy} disabled={!name.trim()}>
            {t('common.create')}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setCreating(false)} disabled={busy}>
            {t('common.cancel')}
          </Button>
        </span>
      )}
      {error && (
        <span className="ui-field-error" role="alert">
          {error}
        </span>
      )}
    </>
  );
}
