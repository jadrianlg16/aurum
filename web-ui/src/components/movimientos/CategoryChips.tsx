'use client';

/**
 * "Frecuentes": up to six category chips ordered by how often the person saved each one
 * (`aurum.catUsage.<ws>`, +1 per save — see prefs.ts). It is the usage-ordering workaround for
 * a CategoryPicker that has no order/recent prop: the picker below
 * keeps the full alphabetical list, the chips put the likely answer one tap away.
 *
 * Only categories of the current kind (expense/income) that still exist and are not archived
 * are shown. Until six are in use, the row is topped up with the common seeded
 * categories (by name, so a renamed one simply drops out) and titled "Comunes", so a first
 * expense is one tap instead of a 22-item select.
 */
import { useEffect, useMemo, useState } from 'react';
import { useI18n } from '@/lib/i18n';
import type { Label } from '@/lib/types';
import styles from './movimientos.module.css';
import { readCatUsage, topCategories, type CatUsage } from './prefs';

/** Seeded names (aurum/pf/labels.py) offered before the person has any history. */
const STARTERS: Record<'expense' | 'income', string[]> = {
  expense: ['Súper', 'Comida fuera', 'Transporte/Gasolina', 'Uber/Taxi', 'Servicios (luz/agua/gas)', 'Entretenimiento'],
  income: ['Sueldo/Nómina', 'Ingreso freelance', 'Otros ingresos'],
};

export function CategoryChips({
  ws,
  kind,
  labels,
  value,
  onPick,
  /** Bump after a save so the order refreshes while the dialog stays open. */
  version = 0,
}: {
  ws: string;
  kind: 'expense' | 'income';
  labels: Label[];
  value: string;
  onPick: (id: string, label: Label) => void;
  version?: number;
}) {
  const { t } = useI18n();
  const [usage, setUsage] = useState<CatUsage>({});
  useEffect(() => {
    if (!ws) return;
    setUsage(readCatUsage(ws));
  }, [ws, version]);

  const { chips, used } = useMemo(() => {
    const byId = new Map(labels.map((l) => [l.id, l]));
    const kindOf = (l: Label) => l.kind ?? (l.account?.startsWith('Income:') ? 'income' : 'expense');
    const usable = (l: Label | undefined): l is Label => Boolean(l) && !l!.archived && kindOf(l!) === kind;
    const frequent = topCategories(usage, 12)
      .map((id) => byId.get(id))
      .filter(usable)
      .slice(0, 6);
    const seen = new Set(frequent.map((l) => l.id));
    const starters = STARTERS[kind]
      .map((name) => labels.find((l) => l.name === name))
      .filter((l): l is Label => usable(l) && !seen.has(l.id));
    return { chips: [...frequent, ...starters].slice(0, 6), used: frequent.length > 0 };
  }, [usage, labels, kind]);

  if (chips.length === 0) return null;
  const title = used ? t('add.category.frequent') : t('add.category.common');
  return (
    <div className="ui-field" role="group" aria-label={title}>
      <span className="ui-field-label small muted">{title}</span>
      <span className={`ui-chips ${styles.chips}`}>
        {chips.map((l) => (
          <button
            key={l.id}
            type="button"
            className="ui-chip"
            aria-pressed={l.id === value}
            onClick={() => onPick(l.id, l)}
          >
            {l.icon ? `${l.icon} ${l.name}` : l.name}
          </button>
        ))}
      </span>
    </div>
  );
}
