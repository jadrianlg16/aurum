'use client';

/**
 * Lists: `ResponsiveTable` is a real `<table>` at ≥768px
 * inside a keyboard-reachable scroll region and a `ul.cardlist` below that width (both are in
 * the DOM; CSS shows one, so no page ever scrolls sideways at 320px). `DataTable` is the plain
 * table for advanced screens: sr-only caption, `th scope`, the same scroll region.
 *
 * Row actions render as a trailing ⋯ IconButton that opens a Sheet — the tap target is 44px
 * and the actions are reachable from the keyboard.
 */
import { useState, type KeyboardEvent, type ReactNode } from 'react';
import { useI18n } from '@/lib/i18n';
import { Button, IconButton } from './Button';
import { Sheet } from './Dialog';

export type MobileSlot = 'title' | 'subtitle' | 'value' | 'meta' | 'hidden';

export interface Column<T> {
  key: string;
  header: string;
  align?: 'left' | 'right' | 'center';
  /** Where the cell lands on a card below 768px. */
  mobile?: MobileSlot;
  render?: (row: T) => ReactNode;
  /** Mark money/number columns so they get tabular figures. */
  numeric?: boolean;
  /** Class for this column's `<col>` (widths, so stacked tables line up). */
  colClass?: string;
}

export interface RowAction<T> {
  label: string;
  onClick: (row: T) => void;
  destructive?: boolean;
}

export interface ResponsiveTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  actions?: (row: T) => RowAction<T>[];
  /** Accessible name of the scroll region / list. */
  label: string;
  className?: string;
  /** Class on the `<table>` itself (e.g. `table-layout: fixed` for stacked day tables). */
  tableClassName?: string;
  /** Keep the header for screen readers only — for the 2nd+ table of a stack under one visible header. */
  quietHeader?: boolean;
}

function cell<T>(col: Column<T>, row: T): ReactNode {
  if (col.render) return col.render(row);
  const v = (row as Record<string, unknown>)[col.key];
  return v === null || v === undefined ? '' : String(v);
}

function alignClass<T>(col: Column<T>): string {
  return [col.numeric || col.align === 'right' ? 'num' : '', col.align === 'center' ? 'center' : ''].filter(Boolean).join(' ');
}

export function ResponsiveTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  actions,
  label,
  className,
  tableClassName,
  quietHeader,
}: ResponsiveTableProps<T>) {
  const { t } = useI18n();
  const [open, setOpen] = useState<T | null>(null);
  const openActions = open ? actions?.(open) ?? [] : [];

  const onRowKey = (row: T) => (e: KeyboardEvent<HTMLElement>) => {
    if (!onRowClick) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onRowClick(row);
    }
  };

  const actionCell = (row: T) =>
    actions ? (
      <IconButton
        icon="more"
        ariaLabel={t('common.more_actions')}
        onClick={(e) => {
          e.stopPropagation();
          setOpen(row);
        }}
      />
    ) : null;

  return (
    <div className={['ui-table-wrap', className].filter(Boolean).join(' ')}>
      {/* A focusable scroll region: keyboard users can reach and scroll a wide table (WCAG 2.1.1). */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <div className="table-scroll ui-table-region" tabIndex={0} role="region" aria-label={t('a11y.table_scroll', { caption: label })}>
        <table className={['ui-table', tableClassName].filter(Boolean).join(' ')}>
          <caption className="sr-only">{label}</caption>
          {columns.some((c) => c.colClass) && (
            <colgroup>
              {columns.map((c) => (
                <col key={c.key} className={c.colClass} />
              ))}
              {actions && <col className="ui-col-actions" />}
            </colgroup>
          )}
          <thead className={quietHeader ? 'sr-only' : undefined}>
            <tr>
              {columns.map((c) => (
                <th key={c.key} scope="col" className={alignClass(c)}>
                  {c.header}
                </th>
              ))}
              {actions && (
                <th scope="col" className="actions">
                  <span className="sr-only">{t('common.actions')}</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                className={onRowClick ? 'clickable' : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={onRowClick ? onRowKey(row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
              >
                {columns.map((c) => (
                  <td key={c.key} className={alignClass(c)}>
                    {cell(c, row)}
                  </td>
                ))}
                {actions && <td className="actions">{actionCell(row)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CardList
        rows={rows}
        rowKey={rowKey}
        label={label}
        onRowClick={onRowClick}
        trailing={actions ? actionCell : undefined}
        slots={(row) => {
          const s: Partial<Record<Exclude<MobileSlot, 'hidden'>, ReactNode[]>> = {};
          for (const c of columns) {
            const slot = c.mobile ?? 'subtitle';
            if (slot === 'hidden') continue;
            (s[slot] ??= []).push(<span key={c.key}>{cell(c, row)}</span>);
          }
          return s;
        }}
      />
      {actions && (
        <Sheet open={open !== null} onClose={() => setOpen(null)} title={t('common.actions')}>
          <div className="ui-sheet-menu">
            {openActions.map((a) => (
              <Button
                key={a.label}
                variant={a.destructive ? 'danger' : 'ghost'}
                onClick={() => {
                  const row = open as T;
                  setOpen(null);
                  a.onClick(row);
                }}
              >
                {a.label}
              </Button>
            ))}
          </div>
        </Sheet>
      )}
    </div>
  );
}

export interface CardListProps<T> {
  rows: T[];
  rowKey: (row: T) => string;
  label: string;
  onRowClick?: (row: T) => void;
  slots: (row: T) => Partial<Record<Exclude<MobileSlot, 'hidden'>, ReactNode[]>>;
  trailing?: (row: T) => ReactNode;
  className?: string;
}

/** `ul.cardlist`: title / subtitle on the left, value / meta on the right, actions trailing. */
export function CardList<T>({ rows, rowKey, label, onRowClick, slots, trailing, className }: CardListProps<T>) {
  return (
    <ul className={['cardlist', className].filter(Boolean).join(' ')} aria-label={label}>
      {rows.map((row) => {
        const s = slots(row);
        const clickable = Boolean(onRowClick);
        const inner = (
          <>
            {s.title && <span className="cl-title">{s.title}</span>}
            {s.subtitle && <span className="cl-subtitle">{s.subtitle}</span>}
            {s.value && <span className="cl-value">{s.value}</span>}
            {s.meta && <span className="cl-meta">{s.meta}</span>}
          </>
        );
        return (
          <li key={rowKey(row)} className={[trailing ? 'with-actions' : '', clickable ? 'clickable' : ''].filter(Boolean).join(' ') || undefined}>
            {clickable ? (
              <button type="button" className="cl-body cl-btn" onClick={() => onRowClick?.(row)}>
                {inner}
              </button>
            ) : (
              <div className="cl-body">{inner}</div>
            )}
            {trailing && <span className="cl-actions">{trailing(row)}</span>}
          </li>
        );
      })}
    </ul>
  );
}

export interface DataTableProps<T> {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey?: (row: T, index: number) => string;
  className?: string;
}

/** A plain table with an sr-only caption and scoped headers inside a scroll region. */
export function DataTable<T>({ caption, columns, rows, rowKey, className }: DataTableProps<T>) {
  const { t } = useI18n();
  return (
    // A focusable scroll region: keyboard users can reach and scroll a wide table (WCAG 2.1.1).
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
    <div className={['table-scroll ui-table-region', className].filter(Boolean).join(' ')} tabIndex={0} role="region" aria-label={t('a11y.table_scroll', { caption })}>
      <table className="ui-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={alignClass(c)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowKey ? rowKey(row, i) : i}>
              {columns.map((c) => (
                <td key={c.key} className={alignClass(c)}>
                  {cell(c, row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
