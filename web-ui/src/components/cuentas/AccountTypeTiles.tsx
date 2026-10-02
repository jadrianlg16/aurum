'use client';

/**
 * `AccountTypeTiles` — step 1 of the account form: "¿Qué tipo de
 * cuenta es?" as a `role="radiogroup"` of seven tiles, one per `PfAccountType`, with a roving
 * tabindex (←/→ and ↑/↓ move, Home/End jump) and ≥44px targets (`Button size="lg"`). Every tile is
 * `variant="secondary"` — the selected one is styled through `aria-checked` (`choice.module.css`), so the
 * form's submit stays its only `.btn.primary` (design-system §6).
 *
 * The icon set (`ui/Icon.tsx`) has no card/cash/loan glyphs, so `accountIcon` maps each type
 * onto an existing name until dedicated glyphs exist.
 */
import { useRef, type KeyboardEvent } from 'react';
import { Button, Icon, type IconName } from '@/components/ui';
import { useI18n } from '@/lib/i18n';
import { PF_ACCOUNT_TYPES, type PfAccountType } from '@/lib/types-personal';
import styles from './choice.module.css';

const ICONS: Record<PfAccountType, IconName> = {
  checking: 'bank',
  savings: 'bank',
  cash: 'wallet',
  credit_card: 'grid',
  loan: 'list',
  investment: 'target',
  other: 'more',
};

/** The `Icon` name that stands in for an account type. */
export function accountIcon(type: PfAccountType | string | null | undefined): IconName {
  return ICONS[(type ?? 'other') as PfAccountType] ?? 'more';
}

export function AccountTypeTiles({
  value,
  onChange,
  disabled,
}: {
  value: PfAccountType;
  onChange: (type: PfAccountType) => void;
  disabled?: boolean;
}) {
  const { t } = useI18n();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const focusAt = (i: number) => {
    const n = PF_ACCOUNT_TYPES.length;
    const idx = ((i % n) + n) % n;
    onChange(PF_ACCOUNT_TYPES[idx]);
    refs.current[idx]?.focus();
  };

  const onKey = (i: number) => (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      focusAt(i + 1);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      focusAt(i - 1);
    } else if (e.key === 'Home') {
      e.preventDefault();
      focusAt(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      focusAt(PF_ACCOUNT_TYPES.length - 1);
    }
  };

  return (
    <div role="radiogroup" aria-label={t('acct.type.pick')} className="grid cols-4" data-testid="acct-type-tiles">
      {PF_ACCOUNT_TYPES.map((type, i) => {
        const selected = type === value;
        return (
          <Button
            key={type}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            variant="secondary"
            size="lg"
            className={styles.choice}
            disabled={disabled}
            onClick={() => onChange(type)}
            onKeyDown={onKey(i)}
            data-testid={`acct-type-${type}`}
          >
            <Icon name={ICONS[type]} size={18} />
            {t(`acct.type.${type}`)}
          </Button>
        );
      })}
    </div>
  );
}
