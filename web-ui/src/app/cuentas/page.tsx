'use client';

/**
 * Cuentas (`/cuentas/`) — where the money is.
 *
 * One resource — `GET /pf/{ws}/accounts?include_archived=1` — filtered client-side; the
 * `version` counter from `useAddEntry()` is in the deps so a movement saved anywhere refreshes
 * the balances, and every write made on this page calls `reload()` only (never `bump()`, which
 * was the double fetch). Stats per currency over the non-archived rows: 'Tienes' = Σ
 * `balance_signed` of asset rows, 'Debes' = Σ `balance` of owed rows, 'Neto' = the difference;
 * currencies are never added together (`sumDecimals`, integer centavos — the one client-side
 * sum this screen makes). Groups by type render only when non-empty.
 *
 * Archiving is `PUT {archived:true}` with a Deshacer toast (DELETE answers 409 once an opening
 * movement exists); 'Ver archivadas' reveals the archived cards, each with Restaurar.
 */
import { useCallback, useMemo, useRef, useState } from 'react';
import { useAddEntry } from '@/components/AddEntry';
import { AccountCard } from '@/components/cuentas/AccountCard';
import { AccountForm } from '@/components/cuentas/AccountForm';
import { AdjustDialog } from '@/components/cuentas/AdjustDialog';
import { GROUPS, currencyStats } from '@/components/cuentas/stats';
import { Button, ConfirmDialog, Dialog, EmptyState, ErrorBox, Money, PageHeader, Skeleton, Stat, useToast } from '@/components/ui';
import { listPfAccounts, updatePfAccount, errorMessage } from '@/lib/api';
import { usePageTitle } from '@/lib/a11y';
import { useI18n, useMoney } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { PfAccount } from '@/lib/types-personal';

export default function CuentasPage() {
  const { t } = useI18n();
  const { base } = useMoney();
  const { ws } = useWorkspace();
  const { version, open } = useAddEntry();
  const toast = useToast();
  usePageTitle(t('acct.title'));

  const [form, setForm] = useState<{ account: PfAccount | null } | null>(null);
  const [adjust, setAdjust] = useState<PfAccount | null>(null);
  const [archive, setArchive] = useState<PfAccount | null>(null);
  const lastArchive = useRef<string>('');
  if (archive) lastArchive.current = archive.name;
  const archiveName = archive?.name ?? lastArchive.current;
  const [busy, setBusy] = useState(false);
  const [showArchived, setShowArchived] = useState(false);

  const accounts = useResource(
    useCallback((signal: AbortSignal) => listPfAccounts(ws, { includeArchived: true }, { signal }), [ws]),
    [ws, version],
  );
  const reload = accounts.reload;
  const all = useMemo(() => accounts.data ?? [], [accounts.data]);
  const active = useMemo(() => all.filter((a) => !a.archived), [all]);
  const visible = showArchived ? all : active;
  const archivedCount = all.length - active.length;
  const stats = useMemo(() => currencyStats(active, base.toUpperCase()), [active, base]);

  const setArchived = async (a: PfAccount, archived: boolean) => {
    setBusy(true);
    try {
      await updatePfAccount(ws, a.id, { archived });
      return true;
    } catch (e) {
      toast.error(errorMessage(e, t));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const confirmArchive = async () => {
    if (!archive) return;
    const a = archive;
    const ok = await setArchived(a, true);
    setArchive(null);
    if (!ok) return;
    reload();
    toast.success(t('acct.archived.toast'), {
      action: {
        label: t('common.undo'),
        onClick: () => {
          void setArchived(a, false).then((undone) => {
            if (undone) reload();
          });
        },
      },
    });
  };

  const restore = async (a: PfAccount) => {
    const ok = await setArchived(a, false);
    if (!ok) return;
    reload();
    toast.success(t('acct.restored'));
  };

  const groups = GROUPS.map((g) => ({ ...g, rows: visible.filter((a) => g.types.includes(a.type)) })).filter((g) => g.rows.length > 0);

  const header = (
    <PageHeader
      title={t('acct.title')}
      subtitle={t('acct.sub')}
      actions={
        <Button variant="primary" icon="plus" onClick={() => setForm({ account: null })} data-testid="acct-new">
          {t('acct.new')}
        </Button>
      }
    />
  );

  let body;
  if (accounts.loading) {
    body = <Skeleton variant="card" rows={4} what={t('acct.title')} />;
  } else if (accounts.error && all.length === 0) {
    body = <ErrorBox error={accounts.problem ?? accounts.error} onRetry={reload} />;
  } else if (active.length === 0 && (!showArchived || all.length === 0)) {
    body = (
      <EmptyState
        icon="bank"
        title={t('acct.empty.title')}
        body={t('acct.empty.body')}
        primary={{ label: t('acct.empty.cta'), onClick: () => setForm({ account: null }) }}
        secondary={{ label: t('acct.empty.wizard'), href: '/empezar/?step=accounts' }}
      />
    );
  } else {
    body = (
      <>
        {stats.map((s) => (
          <section className="card" key={s.currency} aria-label={`${t('acct.stat.net')} ${s.currency}`}>
            <div className="grid cols-3">
              <Stat label={stats.length > 1 ? `${t('acct.stat.have')} · ${s.currency}` : t('acct.stat.have')} value={<Money amount={{ amount: s.have, currency: s.currency }} />} />
              <Stat label={t('acct.stat.owe')} value={<Money amount={{ amount: s.owe, currency: s.currency }} />} tone={s.owe !== '0.00' ? 'neg' : undefined} />
              <Stat label={t('acct.stat.net')} value={<Money amount={{ amount: s.net, currency: s.currency }} />} />
            </div>
          </section>
        ))}
        {groups.map((g) => (
          <section key={g.key} aria-labelledby={`acct-group-${g.key}`}>
            <h2 id={`acct-group-${g.key}`}>{t(`acct.group.${g.key}`)}</h2>
            <div className="grid cols-2">
              {g.rows.map((a) => (
                <AccountCard
                  key={a.id}
                  account={a}
                  onAdd={(acc) => open({ kind: 'expense', accountId: acc.id })}
                  onEdit={(acc) => setForm({ account: acc })}
                  onAdjust={setAdjust}
                  onArchive={setArchive}
                  onRestore={(acc) => void restore(acc)}
                />
              ))}
            </div>
          </section>
        ))}
      </>
    );
  }

  return (
    <>
      {header}
      <div className="stack">
        {accounts.error && all.length > 0 && <ErrorBox error={accounts.problem ?? accounts.error} onRetry={reload} />}
        {body}
        {archivedCount > 0 && !accounts.loading && (
          <div className="row">
            <Button
              variant="ghost"
              aria-pressed={showArchived}
              onClick={() => setShowArchived((v) => !v)}
              data-testid="acct-show-archived"
            >
              {t('acct.show_archived')} ({archivedCount})
            </Button>
          </div>
        )}
      </div>

      {/* The inline form supplies its own submit — the Dialog is NOT in form mode (no nested form). */}
      <Dialog
        open={form !== null}
        onClose={() => setForm(null)}
        title={form?.account ? t('acct.edit') : t('acct.new')}
        size="md"
      >
        {form && (
          <AccountForm
            ws={ws}
            account={form.account}
            onSaved={() => {
              setForm(null);
              reload();
              toast.success(t('acct.saved'));
            }}
            onCancel={() => setForm(null)}
          />
        )}
      </Dialog>

      {adjust && (
        <AdjustDialog
          ws={ws}
          account={adjust}
          open
          onClose={(saved) => {
            setAdjust(null);
            if (saved) {
              reload();
              toast.success(t('acct.adjusted'));
            }
          }}
        />
      )}

      {/* Mounted once and driven by `open`: a Dialog that mounts open closes itself under StrictMode (see useOpenAfterMount). */}
      <ConfirmDialog
        open={archive !== null}
        title={t('acct.archive.title', { name: archiveName })}
        body={<p>{t('acct.archive.body')}</p>}
        confirmLabel={t('acct.archive')}
        busy={busy}
        onConfirm={() => void confirmArchive()}
        onCancel={() => setArchive(null)}
      />
    </>
  );
}
