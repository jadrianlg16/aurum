'use client';

/**
 * Ajustes › Categorías. `GET /labels?include_archived=1`,
 * `transfer` rows hidden, two groups (Gastos / Ingresos), a row per category with its icon,
 * name and an "Escondida" badge when archived. Row actions: Editar, Esconder / Mostrar
 * (`PUT {archived}`), Borrar (`DELETE`; a 409 — the category has movements — toasts the
 * "hide it instead" hint). Every write reloads the list.
 */
import { useCallback, useState } from 'react';
import { CategoryDialog, type CategoryKind } from '@/components/settings/CategoryDialog';
import { Badge, Button, ConfirmDialog, ErrorBox, ResponsiveTable, Skeleton, useToast, type Column } from '@/components/ui';
import { ApiError, deleteLabel, errorMessage, listLabels, updateLabel } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import type { Label } from '@/lib/types';

function kindOf(l: Label): CategoryKind | null {
  if (l.kind === 'expense' || l.kind === 'income') return l.kind;
  if (l.kind === 'transfer') return null;
  const acct = l.account ?? '';
  if (acct.startsWith('Expenses:')) return 'expense';
  if (acct.startsWith('Income:')) return 'income';
  return null;
}

export function CategoriesSection({ ws }: { ws: string }) {
  const { t } = useI18n();
  const toast = useToast();
  const labels = useResource(useCallback(() => listLabels(ws, { includeArchived: true }), [ws]), [ws]);
  const [form, setForm] = useState<{ label: Label | null; kind?: CategoryKind } | null>(null);
  const [confirm, setConfirm] = useState<Label | null>(null);
  const [busy, setBusy] = useState(false);

  const rows = (labels.data ?? []).filter((l) => kindOf(l) !== null);
  const groups: { kind: CategoryKind; rows: Label[] }[] = (['expense', 'income'] as CategoryKind[]).map((kind) => ({
    kind,
    rows: rows.filter((l) => kindOf(l) === kind),
  }));

  const toggle = async (l: Label) => {
    const hide = !l.archived;
    try {
      await updateLabel(ws, l.id, { archived: hide });
      toast.success(hide ? t('cat.hidden_toast') : t('cat.shown_toast'));
      labels.reload();
    } catch (e) {
      toast.error(errorMessage(e, t));
    }
  };

  const remove = async () => {
    if (!confirm) return;
    const l = confirm;
    setBusy(true);
    try {
      await deleteLabel(ws, l.id);
      setConfirm(null);
      toast.success(t('cat.deleted'));
      labels.reload();
    } catch (e) {
      setConfirm(null);
      if (e instanceof ApiError && e.status === 409) toast.error(t('cat.delete.blocked'));
      else toast.error(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const columns: Column<Label>[] = [
    {
      key: 'name',
      header: t('cat.name'),
      mobile: 'title',
      render: (l) => (
        <span data-testid="cat-row" data-kind={kindOf(l) ?? ''} data-archived={l.archived ? 'true' : 'false'}>
          {l.icon ? <span aria-hidden="true">{l.icon} </span> : null}
          {l.name}
          {l.archived && (
            <>
              {' '}
              <Badge tone="neutral">{t('cat.hidden')}</Badge>
            </>
          )}
        </span>
      ),
    },
  ];

  return (
    <div className="stack">
      <div className="row">
        <Button variant="secondary" icon="plus" data-testid="cat-new" onClick={() => setForm({ label: null })}>
          {t('cat.new')}
        </Button>
      </div>
      {labels.loading ? (
        <Skeleton variant="list" rows={4} what={t('cat.title')} />
      ) : labels.error && !labels.data ? (
        <ErrorBox error={labels.problem ?? labels.error} onRetry={labels.reload} />
      ) : (
        groups.map((g) => (
          <div key={g.kind} className="stack">
            <h3>{t(`cat.kind.${g.kind}`)}</h3>
            {g.rows.length === 0 ? (
              <p className="small muted">{t('cat.empty')}</p>
            ) : (
              <ResponsiveTable
                label={t('cat.list', { kind: t(`cat.kind.${g.kind}`) })}
                columns={columns}
                rows={g.rows}
                rowKey={(l) => l.id}
                actions={(l) => [
                  { label: t('common.edit'), onClick: () => setForm({ label: l }) },
                  { label: l.archived ? t('cat.show') : t('cat.hide'), onClick: () => void toggle(l) },
                  { label: t('cat.delete'), onClick: () => setConfirm(l), destructive: true },
                ]}
              />
            )}
          </div>
        ))
      )}

      {form && (
        <CategoryDialog
          ws={ws}
          label={form.label}
          kind={form.kind}
          onClose={(saved) => {
            setForm(null);
            if (saved) labels.reload();
          }}
        />
      )}
      {confirm && (
        <ConfirmDialog
          title={t('cat.delete.title', { name: confirm.name })}
          body={<p>{t('cat.delete.body')}</p>}
          confirmLabel={t('cat.delete')}
          destructive
          busy={busy}
          onConfirm={() => void remove()}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  );
}
