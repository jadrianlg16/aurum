'use client';

/**
 * Done screen: "Listo. Así se ve tu dinero" with the liquid balance —
 * Σ `balance_signed` of the non-archived cash / checking / savings rows in the base currency.
 * This is one of the few client-side sums the UI makes (docs/modules/web-ui.md, Gotchas): it is a
 * string sum through `sumDecimals` (BigInt cents), never a float, over rows the server already
 * balanced. The currency is the workspace's `base_currency` (no literal fallback): until the
 * workspace row is known the figure is a Skeleton, and a failed `GET /pf/{ws}/accounts` is an
 * ErrorBox with Reintentar — never a fabricated $0.00. Primary "Ir a Inicio", secondary
 * "Agregar mi primer gasto" (shared dialog), and the import shortcut card only in advanced
 * mode. No link to the documents screen, the inbox or subscriptions.
 */
import { useCallback } from 'react';
import { useAddEntry } from '@/components/AddEntry';
import { Button, ErrorBox, Money, Skeleton, Stat } from '@/components/ui';
import { listPfAccounts } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import { sumDecimals } from '@/lib/validate';
import type { PfAccount } from '@/lib/types-personal';
import { useAdvanced, useWorkspace } from '@/lib/workspace';
import styles from './onboarding.module.css';

const LIQUID = new Set<PfAccount['type']>(['cash', 'checking', 'savings']);

/** The one allowed client-side sum: liquid, non-archived, base-currency rows. */
export function liquidBalance(rows: PfAccount[], baseCurrency: string): string {
  const base = baseCurrency.toUpperCase();
  return sumDecimals(
    rows
      .filter((a) => !a.archived && LIQUID.has(a.type) && (a.currency ?? base).toUpperCase() === base)
      .map((a) => a.balance_signed?.amount ?? a.balance?.amount ?? '0'),
  );
}

export function DoneScreen({ ws, onSaved }: { ws: string; onSaved: () => void }) {
  const { t } = useI18n();
  const { current } = useWorkspace();
  const advanced = useAdvanced();
  const { open, version } = useAddEntry();
  const currency = current?.base_currency.toUpperCase() ?? null;
  const accounts = useResource(
    useCallback((signal: AbortSignal) => listPfAccounts(ws, {}, { signal }), [ws]),
    [ws, version],
  );

  return (
    <section className="card headline" aria-label={t('empezar.listo')}>
      <h2>{t('empezar.listo')}</h2>
      {accounts.error ? (
        <ErrorBox error={accounts.problem ?? accounts.error} onRetry={accounts.reload} />
      ) : accounts.loading || !accounts.data || currency === null ? (
        <Skeleton variant="stat" what={t('inicio.tienes_hoy')} />
      ) : (
        <Stat
          size="lg"
          label={t('inicio.tienes_hoy')}
          value={<Money amount={{ amount: liquidBalance(accounts.data, currency), currency }} sign="auto" />}
          sub={t('onb.done.msg')}
        />
      )}
      <div className={styles.doneActions}>
        <Button variant="primary" href="/">
          {t('empezar.ir_inicio')}
        </Button>
        <Button variant="secondary" onClick={() => open({ kind: 'expense', onSaved: () => onSaved() })}>
          {t('empezar.primer_gasto')}
        </Button>
      </div>
      {advanced && (
        <div className={['card', styles.shortcut].join(' ')}>
          <h3>{t('empezar.importar')}</h3>
          <p className="small muted">{t('empezar.importar.hint')}</p>
          <Button variant="secondary" href="/movimientos/?import=1">
            {t('empezar.importar')}
          </Button>
        </div>
      )}
    </section>
  );
}
