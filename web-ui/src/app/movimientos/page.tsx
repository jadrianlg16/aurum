'use client';

/**
 * Movimientos (`/movimientos/`) — the month's movements.
 *
 * `?period=` month picker, a debounced search, filters (account / category / kind — inline
 * from 768px, in a Sheet below), Entró / Salió / Neto / count straight from the API's totals
 * (never summed here), rows grouped by day with a display-only subtotal, "Mostrando n de
 * total · Ver más" through the cursor, row click → edit in the Agregar dialog, ⋯ → Editar /
 * Duplicar / Eliminar (locked rows: Duplicar only), checkboxes → "Poner categoría" in bulk.
 * Reloads keep the rows on screen (stale-while-refresh); a write anywhere (`version`) reloads
 * exactly the rows that were showing. Advanced mode adds the Libros link.
 */
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAddEntry } from '@/components/AddEntry';
import { BulkBar } from '@/components/movimientos/BulkBar';
import { DayGroup } from '@/components/movimientos/DayGroup';
import { DeleteEntryDialog } from '@/components/movimientos/DeleteEntryDialog';
import { FilterBar, kindOfTab, type FilterState } from '@/components/movimientos/FilterBar';
import { FilterSheet } from '@/components/movimientos/FilterSheet';
import { useMovementActions, useMovementColumns } from '@/components/movimientos/MovementRow';
import { groupByDay } from '@/components/movimientos/dayGroups';
import styles from '@/components/movimientos/movimientos.module.css';
import { useIsNarrow } from '@/components/movimientos/useIsNarrow';
import { Button, EmptyState, ErrorBox, PageHeader, Skeleton, Stat, TabPanel, useToast } from '@/components/ui';
import { errorMessage, getLedgerHealth, listEntries, listPfAccounts, updateEntry } from '@/lib/api';
import { todayLocalIso } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import { monthBounds, periodLabel, shiftPeriod, usePeriodParam } from '@/lib/period';
import { queryParam, useQueryParam } from '@/lib/query';
import type { Entry } from '@/lib/types-personal';
import { useResource } from '@/lib/useResource';
import { useAdvanced, useWorkspace, WorkspaceGate } from '@/lib/workspace';

const PAGE = 100;
const MAX_LIMIT = 500;
const SEARCH_DEBOUNCE_MS = 250;

export default function MovimientosPage() {
  return (
    <WorkspaceGate>
      <MovimientosScreen />
    </WorkspaceGate>
  );
}

function MovimientosScreen() {
  const { t, tn, lang } = useI18n();
  const { fmt } = useMoney();
  const { ws } = useWorkspace();
  const advanced = useAdvanced();
  const router = useRouter();
  const narrow = useIsNarrow();
  const toast = useToast();
  const { open, version, bump } = useAddEntry();

  /* ---- url state: period + category filter (Presupuesto links here with ?label_id=) */
  const [period, setPeriod] = usePeriodParam();
  const [labelParam, setLabelParam] = useQueryParam<string>('label_id', '');
  const [filters, setFilters] = useState<FilterState>({ q: '', accountId: '', labelId: '', kind: 'all' });
  useEffect(() => {
    setFilters((f) => (f.labelId === labelParam ? f : { ...f, labelId: labelParam }));
  }, [labelParam]);
  const changeFilters = (next: Partial<FilterState>) => {
    setFilters((f) => ({ ...f, ...next }));
    if (next.labelId !== undefined) setLabelParam(next.labelId);
  };
  const clearFilters = () => {
    setFilters({ q: '', accountId: '', labelId: '', kind: 'all' });
    setLabelParam('');
  };

  // `/movimientos/?add=1` opens the Agregar dialog straight away; `?import=1` is the done-screen
  // shortcut and only means something in advanced mode.
  useEffect(() => {
    if (queryParam('add') === '1') open('expense');
    // Once, on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (queryParam('import') === '1' && advanced) router.replace('/documents/');
  }, [advanced, router]);

  /* ---- search debounce (rows never unmount while it runs) */
  const [qDebounced, setQDebounced] = useState('');
  useEffect(() => {
    const id = window.setTimeout(() => setQDebounced(filters.q.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [filters.q]);

  /* ---- today, read after mount (no Date at prerender) */
  const [today, setToday] = useState<string | null>(null);
  useEffect(() => {
    setToday(todayLocalIso());
  }, []);

  /* ---- selection (cleared on every query change) + bulk categorize state */
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  // Checkboxes only after "Seleccionar varios" (desktop); phones use the ⋯ menu.
  const [selecting, setSelecting] = useState(false);
  const [bulkLabel, setBulkLabel] = useState('');
  const [bulkBusy, setBulkBusy] = useState(false);

  /* ---- paging: `limit` for the first page, `extra` for the pages behind "Ver más" */
  const { from, to } = monthBounds(period);
  const kind = kindOfTab(filters.kind);
  const [limit, setLimit] = useState(PAGE);
  const [extra, setExtra] = useState<Entry[]>([]);
  const [extraCursor, setExtraCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);
  const shownRef = useRef(0);

  const queryKey = `${ws}|${from}|${to}|${filters.accountId}|${filters.labelId}|${kind}|${qDebounced}`;
  const page = useResource(
    (signal) =>
      listEntries(ws, { from, to, account_id: filters.accountId, label_id: filters.labelId, kind, q: qDebounced, limit }, { signal }),
    [queryKey, limit, reloadNonce],
    { keepPrevious: true },
  );

  // A different query starts over at 100 rows; a write anywhere reloads exactly what was showing.
  const lastKey = useRef(queryKey);
  useEffect(() => {
    if (lastKey.current === queryKey) return;
    lastKey.current = queryKey;
    setExtra([]);
    setExtraCursor(null);
    setLimit(PAGE);
    setSelected(new Set());
  }, [queryKey]);
  const lastVersion = useRef(version);
  useEffect(() => {
    if (lastVersion.current === version) return;
    lastVersion.current = version;
    setExtra([]);
    setExtraCursor(null);
    setLimit(Math.min(MAX_LIMIT, Math.max(PAGE, shownRef.current)));
    setReloadNonce((n) => n + 1);
  }, [version]);

  const rows = useMemo(() => [...(page.data?.entries ?? []), ...extra], [page.data, extra]);
  useEffect(() => {
    shownRef.current = rows.length;
  }, [rows.length]);
  const totals = page.data?.totals ?? null;
  const nextCursor = extra.length > 0 ? extraCursor : page.data?.next_cursor ?? null;

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const more = await listEntries(ws, {
        from,
        to,
        account_id: filters.accountId,
        label_id: filters.labelId,
        kind,
        q: qDebounced,
        limit: PAGE,
        cursor: nextCursor,
      });
      setExtra((prev) => [...prev, ...more.entries]);
      setExtraCursor(more.next_cursor);
    } catch (e) {
      toast.error(errorMessage(e, t));
    } finally {
      setLoadingMore(false);
    }
  };

  /* ---- accounts (zero-accounts empty state) + ledger health (once per ws) */
  const accounts = useResource((signal) => listPfAccounts(ws, {}, { signal }), [ws, version]);
  const health = useResource(() => getLedgerHealth(ws).catch(() => null), [ws]);
  const noAccounts = accounts.data !== null && accounts.data.filter((a) => !a.archived).length === 0;

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id));
  const selectAll = (on: boolean) => setSelected(on ? new Set(rows.map((r) => r.id)) : new Set());

  const applyBulk = async () => {
    if (!bulkLabel || selected.size === 0) return;
    setBulkBusy(true);
    let done = 0;
    let skipped = 0;
    const total = selected.size;
    try {
      for (const id of selected) {
        const e = rows.find((r) => r.id === id);
        if (!e || e.kind === 'transfer' || e.editable === false) {
          skipped += 1;
          continue;
        }
        try {
          // Exactly {label_id}: the server merges the patch, so splits and everything else stay.
          await updateEntry(ws, id, { label_id: bulkLabel });
          done += 1;
        } catch {
          /* counted as not updated; the toast says how many landed */
        }
      }
    } finally {
      setBulkBusy(false);
      setSelected(new Set());
      setBulkLabel('');
      bump();
      const msg = t('txn.bulk.result', { done, total });
      toast.success(skipped > 0 ? `${msg} · ${t('txn.bulk.skipped', { n: skipped })}` : msg);
    }
  };

  /* ---- row handlers */
  const [confirm, setConfirm] = useState<Entry | null>(null);
  const onEdit = useCallback((row: Entry) => open({ mode: 'edit' }, row), [open]);
  const onDuplicate = useCallback((row: Entry) => open({ mode: 'duplicate' }, row), [open]);
  const onRowClick = useCallback(
    (row: Entry) => {
      if (row.editable === false) return;
      open({ mode: 'edit' }, row);
    },
    [open],
  );
  const showOrigin = advanced || rows.some((r) => (r.source ?? 'manual') !== 'manual' || r.editable === false);
  const rowOpts = {
    selected,
    onToggle: toggle,
    advanced,
    onEdit,
    onDuplicate,
    onDelete: setConfirm,
    narrow,
    selecting: selecting && !narrow,
    showOrigin,
  };
  const columns = useMovementColumns(rowOpts);
  const actions = useMovementActions(rowOpts);
  const groups = useMemo(() => groupByDay(rows), [rows]);

  const filtered = Boolean(qDebounced || filters.accountId || filters.labelId || kind);
  const filterProps = { ws, value: filters, onChange: changeFilters, onClear: clearFilters, version };

  return (
    <>
      <PageHeader
        title={t('txn.title')}
        subtitle={t('txn.sub')}
        month={{ value: period, onChange: setPeriod }}
        actions={
          advanced ? (
            <Button variant="secondary" href="/books/">
              {t('txn.books_link')}
            </Button>
          ) : undefined
        }
      />

      {health.data && health.data.error_count > 0 && (
        <p className="banner warn" role="status">
          {t('txn.health.warn', { n: health.data.error_count })}
        </p>
      )}

      <div className="stack">
        <div className="card">
          {narrow ? <FilterSheet {...filterProps} /> : <FilterBar {...filterProps} />}
        </div>

        <div className={styles.stats}>
          <Stat label={t('txn.total.income')} value={totals ? fmt(totals.in) : '—'} />
          <Stat label={t('txn.total.expense')} value={totals ? fmt(totals.out) : '—'} />
          <Stat label={t('txn.total.net')} value={totals ? fmt(totals.net, { sign: 'always' }) : '—'} />
          <Stat label={periodLabel(period, lang)} value={totals ? tn('txn.count', totals.count) : '—'} />
        </div>

        {selected.size > 0 && (
          <BulkBar
            ws={ws}
            count={selected.size}
            labelId={bulkLabel}
            onLabel={setBulkLabel}
            onApply={() => void applyBulk()}
            onClear={() => setSelected(new Set())}
            busy={bulkBusy}
            version={version}
          />
        )}

        <TabPanel id={filters.kind}>
          <div className={page.refreshing ? styles.progress : styles.progressSpacer} aria-hidden="true" />
          <section aria-busy={page.refreshing || undefined} aria-label={t('txn.title')} className={styles.list}>
            {page.loading && rows.length === 0 ? (
              <Skeleton variant="list" rows={6} what={t('txn.title')} />
            ) : page.error && rows.length === 0 ? (
              <ErrorBox error={page.problem ?? page.error} onRetry={page.reload} />
            ) : noAccounts && rows.length === 0 ? (
              <EmptyState
                icon="wallet"
                title={t('txn.empty.no_accounts')}
                primary={{ label: t('txn.empty.setup'), href: '/empezar/?step=accounts' }}
              />
            ) : rows.length === 0 && filtered ? (
              <EmptyState icon="search" title={t('txn.empty.filtered')} primary={{ label: t('txn.filters.clear'), onClick: clearFilters, variant: 'secondary' }} />
            ) : rows.length === 0 ? (
              <>
                <EmptyState
                  icon="list"
                  title={t('txn.empty.title', { period: periodLabel(period, lang) })}
                  body={t('txn.empty.body')}
                  primary={{ label: t('txn.empty.cta'), onClick: () => open('expense') }}
                />
                <div className={styles.emptyExtra}>
                  <Button variant="ghost" onClick={() => setPeriod(shiftPeriod(period, -1))}>
                    {t('txn.empty.prev')}
                  </Button>
                  {advanced && <Link href="/documents/">{t('txn.empty.import_adv')}</Link>}
                </div>
              </>
            ) : (
              <>
                {!narrow && (
                  <div className={styles.selectRow}>
                    {selecting && (
                      <label className={styles.selectAll}>
                        <input type="checkbox" className={styles.rowCheck} checked={allSelected} onChange={(e) => selectAll(e.target.checked)} />
                        {t('txn.select_all')}
                      </label>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (selecting) setSelected(new Set());
                        setSelecting((v) => !v);
                      }}
                    >
                      {selecting ? t('txn.select.done') : t('txn.select.many')}
                    </Button>
                  </div>
                )}
                {groups.map((g, i) => (
                  <DayGroup key={g.date} group={g} today={today} columns={columns} actions={actions} onRowClick={onRowClick} first={i === 0} />
                ))}
                <div className={styles.footer}>
                  <span>{t('txn.showing', { shown: rows.length, total: totals?.count ?? rows.length })}</span>
                  {nextCursor && (
                    <Button variant="secondary" onClick={() => void loadMore()} loading={loadingMore}>
                      {t('txn.load_more')}
                    </Button>
                  )}
                </div>
              </>
            )}
          </section>
        </TabPanel>
      </div>

      {confirm && (
        <DeleteEntryDialog ws={ws} entry={confirm} bump={bump} onDone={() => setConfirm(null)} onCancel={() => setConfirm(null)} />
      )}
    </>
  );
}
