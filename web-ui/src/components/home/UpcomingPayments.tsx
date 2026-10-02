'use client';

/**
 * Próximos pagos · 7 días.
 *
 * Rows come from `GET /organizer/{ws}/calendar?from=today&to=today+7`: items with status
 * due / upcoming / missed, never tax, at most six, then "Ver todos" → the Mi dinero calendar.
 *   - `kind === 'income'` → "Te llega", `+` amount, no button;
 *   - `card_due | card_cut | loan` → the row links to /cuentas/, no button;
 *   - `kind === 'commitment'` with `amount_variable === false` → one-tap "Pagado":
 *     `POST /occurrences/mark {status: paid, log_entry: true}`; the row flips to paid at once
 *     (the one optimistic exception), a toast offers "Deshacer" (`DELETE /occurrences/mark`, which voids
 *     the auto-created entry); an error reverts the row, and a 400 (a commitment without an
 *     account) falls through to the Registrar path;
 *   - `amount_variable === true` **or absent** → "Registrar": the shared + Agregar dialog opens
 *     prefilled (date, amount, payee, commitment_id) and, once saved, the occurrence is marked
 *     paid with that `entry_id`.
 * `reloadAll` (summary + calendar + entries + review + budgets + accounts) runs after every write.
 */
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useAddEntry } from '@/components/AddEntry';
import { Badge, Button, EmptyState, Money, useToast } from '@/components/ui';
import { ApiError, errorMessage, markOccurrence, unmarkOccurrence } from '@/lib/api';
import { relativeDay } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import type { CalendarItem, OrganizerCalendar, OrganizerSummary } from '@/lib/types-organizer';
import { HomeSection, negated } from './shared';
import styles from './home.module.css';

const SHOWN = new Set<CalendarItem['status']>(['due', 'upcoming', 'missed']);
const MAX_ROWS = 6;
const LINKS_TO_ACCOUNTS = new Set<CalendarItem['kind']>(['card_due', 'card_cut', 'loan']);

export function upcomingRows(calendar: OrganizerCalendar | null): CalendarItem[] {
  const rows: CalendarItem[] = [];
  for (const day of calendar?.days ?? []) {
    for (const item of day.items) {
      if (item.kind === 'tax' || !SHOWN.has(item.status)) continue;
      rows.push(item);
    }
  }
  return rows;
}

const keyOf = (item: CalendarItem) => `${item.id}|${item.date}`;

export function UpcomingPayments({
  ws,
  today,
  summary,
  calendar,
  reloadAll,
}: {
  ws: string;
  today: string;
  summary: OrganizerSummary | null;
  calendar: OrganizerCalendar | null;
  reloadAll: () => void;
}) {
  const { t, tn, lang } = useI18n();
  const { fmt } = useMoney();
  const toast = useToast();
  const { open } = useAddEntry();
  /** Occurrences flipped to paid locally (the optimistic exception) until the calendar reloads. */
  const [paid, setPaid] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState<string | null>(null);
  // A fresh calendar is the truth again: drop the local flips once it lands.
  useEffect(() => {
    setPaid(new Set());
  }, [calendar]);

  const all = upcomingRows(calendar);
  const rows = all.slice(0, MAX_ROWS);
  const alerts = summary?.alerts_count ?? 0;

  const register = (item: CalendarItem) =>
    open({
      kind: item.commitment_kind === 'income' ? 'income' : 'expense',
      accountId: item.account_id ?? undefined,
      prefill: { date: item.date, amount: item.amount, payee: item.name, commitment_id: item.id },
      onSaved: (entry) => {
        markOccurrence(ws, { commitment_id: item.id, date: item.date, status: 'paid', entry_id: entry.id })
          .then(reloadAll)
          .catch((e: unknown) => toast.error(errorMessage(e, t)));
      },
    });

  const markPaid = async (item: CalendarItem) => {
    const key = keyOf(item);
    setBusy(key);
    setPaid((s) => new Set(s).add(key));
    try {
      await markOccurrence(ws, { commitment_id: item.id, date: item.date, status: 'paid', log_entry: true });
      toast.success(t('inicio.pagado_toast', { name: item.name, amount: fmt(item.amount) }), {
        action: {
          label: t('common.undo'),
          onClick: () => {
            unmarkOccurrence(ws, item.id, item.date)
              .then(reloadAll)
              .catch((e: unknown) => toast.error(errorMessage(e, t)));
          },
        },
      });
      reloadAll();
    } catch (e: unknown) {
      setPaid((s) => {
        const n = new Set(s);
        n.delete(key);
        return n;
      });
      if (e instanceof ApiError && e.status === 400) {
        // The commitment has no account: log it by hand instead (the dialog asks for one).
        register(item);
      } else {
        toast.error(errorMessage(e, t));
      }
    } finally {
      setBusy(null);
    }
  };

  const action = (item: CalendarItem) => {
    if (item.kind === 'income' || LINKS_TO_ACCOUNTS.has(item.kind) || item.kind !== 'commitment') return null;
    if (paid.has(keyOf(item))) return <Badge tone="pos">{t('inicio.pagado')}</Badge>;
    if (item.amount_variable === false) {
      return (
        <Button variant="secondary" loading={busy === keyOf(item)} onClick={() => void markPaid(item)}>
          {t('inicio.pagado')}
        </Button>
      );
    }
    return (
      <Button variant="secondary" onClick={() => register(item)}>
        {t('inicio.registrar')}
      </Button>
    );
  };

  return (
    <HomeSection
      title={`${t('inicio.proximos')} · ${t('inicio.dias7')}`}
      actions={
        alerts > 0 ? (
          <Link href="/money/" className={styles.tapLink}>
            <Badge tone="warn" dot>
              {tn('inicio.avisos', alerts, { n: alerts })}
            </Badge>
          </Link>
        ) : undefined
      }
    >
      {rows.length === 0 ? (
        <EmptyState compact title={t('inicio.nada_por_pagar')} />
      ) : (
        <ul className={styles.rows}>
          {rows.map((item) => {
            const income = item.kind === 'income';
            const toAccounts = LINKS_TO_ACCOUNTS.has(item.kind);
            const name = toAccounts ? <Link href="/cuentas/">{item.name}</Link> : item.name;
            return (
              <li key={`${item.kind}|${keyOf(item)}`} className={styles.rowItem}>
                <span className={styles.rowMain}>
                  <span className={styles.rowName}>{name}</span>
                  <span className={styles.rowMeta}>
                    <Badge tone="neutral">{relativeDay(item.date, lang, today)}</Badge>
                    {item.status === 'missed' && <Badge tone="neg">{t('inicio.atrasado')}</Badge>}
                    {income && <Badge tone="pos">{t('inicio.te_llega')}</Badge>}
                    {item.account_name && <span>{item.account_name}</span>}
                  </span>
                </span>
                <span className={styles.rowSide}>
                  <Money amount={income ? item.amount : negated(item.amount)} sign="always" />
                  {action(item)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {all.length > 0 && (
        <p className="small">
          <Link href="/money/?tab=calendar">{t('inicio.ver_todos')}</Link>
        </p>
      )}
    </HomeSection>
  );
}
