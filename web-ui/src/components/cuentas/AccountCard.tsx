'use client';

/**
 * `AccountCard` — one account on `/cuentas/`.
 *
 * Type icon, name, institution · type label, the balance through `<Money>`; a card or a loan
 * reads 'Debes $X' in the negative tone from `balance` (positive owed — never from the sign
 * of `balance_signed`). Cards add 'Corte día · Pago día · Límite' (each part only when set) and a
 * usage bar (`role=progressbar`, owed/limit — pixel geometry through `toChartNumber`, the one
 * named float exception); loans show the annual rate and the term.
 *
 * Actions: a secondary 'Agregar movimiento aquí' (the caller opens + Agregar preselected on this
 * account) and a ⋯ `IconButton` that opens a `Sheet` with Editar / Ajustar saldo / Archivar
 * (Restaurar when archived) — there is no menu primitive; design-system §5 assigns menus to
 * `Sheet`. The ledger account is never rendered (banned vocabulary).
 */
import { useState } from 'react';
import { Badge, Button, Icon, IconButton, Money, Sheet } from '@/components/ui';
import { toChartNumber } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import type { PfAccount } from '@/lib/types-personal';
import { accountIcon } from './AccountTypeTiles';

export interface AccountCardProps {
  account: PfAccount;
  onAdd: (account: PfAccount) => void;
  onEdit: (account: PfAccount) => void;
  onAdjust: (account: PfAccount) => void;
  onArchive: (account: PfAccount) => void;
  onRestore: (account: PfAccount) => void;
}

/** `owed / limit` as a whole percent for the bar; 0 when either side is missing. */
export function usagePercent(owed: PfAccount['balance'], limit: PfAccount['credit_limit']): number {
  const l = toChartNumber(limit);
  if (!(l > 0)) return 0;
  const o = Math.max(0, toChartNumber(owed));
  return Math.min(100, Math.round((o / l) * 100));
}

export function AccountCard({ account: a, onAdd, onEdit, onAdjust, onArchive, onRestore }: AccountCardProps) {
  const { t, tn } = useI18n();
  const { fmt, base } = useMoney();
  const [menu, setMenu] = useState(false);
  const currency = a.currency ?? base;
  const owed = Boolean(a.owed);
  const balance = a.balance ?? { amount: '0.00', currency };
  const archived = Boolean(a.archived);
  const isCard = a.type === 'credit_card';
  const isLoan = a.type === 'loan';

  const cardMeta = isCard
    ? [
        a.cut_day ? t('acct.card.cut', { day: a.cut_day }) : null,
        a.due_day ? t('acct.card.due', { day: a.due_day }) : null,
        a.credit_limit ? t('acct.card.limit', { amount: fmt(a.credit_limit) }) : null,
      ].filter(Boolean)
    : [];
  const pct = isCard && toChartNumber(a.credit_limit) > 0 ? usagePercent(a.balance, a.credit_limit) : null;
  const barTone = pct === null ? '' : pct >= 90 ? 'neg' : pct >= 70 ? 'warn' : 'pos';

  const loanMeta = isLoan
    ? [
        a.apr_percent ? t('acct.loan.rate', { rate: a.apr_percent }) : null,
        a.loan_months ? tn('acct.loan.term', a.loan_months, { n: a.loan_months }) : null,
      ].filter(Boolean)
    : [];

  const close = () => setMenu(false);
  const pick = (fn: (acc: PfAccount) => void) => () => {
    close();
    fn(a);
  };

  return (
    <article className="card stack" data-testid={`acct-card-${a.id}`} aria-label={a.name}>
      {/* `.page-head` is the one global header row with a growing `.spacer` (no new CSS here). */}
      <div className="page-head">
        <div className="row">
          <Icon name={accountIcon(a.type)} size={22} />
          <div>
            <strong>{a.name}</strong>
            <div className="small muted">
              {a.institution ? `${a.institution} · ` : ''}
              {t(`acct.type.${a.type}`)}
            </div>
          </div>
        </div>
        <span className="spacer" />
        {archived && <Badge tone="neutral">{t('acct.archived')}</Badge>}
        <IconButton icon="more" ariaLabel={t('acct.more', { name: a.name })} onClick={() => setMenu(true)} data-testid="acct-menu" />
      </div>

      <div>
        {owed ? (
          <div className="metric-value money neg" data-testid="acct-owes">
            {t('acct.owes', { amount: fmt(balance) })}
          </div>
        ) : (
          <div className="metric-value">
            <Money amount={balance} />
          </div>
        )}
        {cardMeta.length > 0 && <div className="small muted">{cardMeta.join(' · ')}</div>}
        {loanMeta.length > 0 && <div className="small muted">{loanMeta.join(' · ')}</div>}
      </div>

      {pct !== null && (
        <div
          className={['bar', barTone].filter(Boolean).join(' ')}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-label={t('acct.card.usage', { pct: `${pct} %` })}
        >
          {/* width is data, not spacing: the only inline style on this screen */}
          <span style={{ width: `${pct}%` }} />
        </div>
      )}

      {!archived && (
        <div className="row">
          <Button variant="secondary" onClick={() => onAdd(a)} data-testid="acct-add-here">
            {t('acct.add_here')}
          </Button>
        </div>
      )}

      <Sheet open={menu} onClose={close} title={a.name}>
        <div className="ui-sheet-menu">
          <Button variant="ghost" onClick={pick(onEdit)} data-testid="acct-edit">
            {t('common.edit')}
          </Button>
          <Button variant="ghost" onClick={pick(onAdjust)} data-testid="acct-adjust">
            {t('acct.adjust')}
          </Button>
          {archived ? (
            <Button variant="ghost" onClick={pick(onRestore)} data-testid="acct-restore">
              {t('acct.restore')}
            </Button>
          ) : (
            <Button variant="ghost" onClick={pick(onArchive)} data-testid="acct-archive">
              {t('acct.archive')}
            </Button>
          )}
        </div>
      </Sheet>
    </article>
  );
}
