'use client';

/**
 * Categorías (`/categorias/`). The category list used to live at the bottom of
 * Ajustes; making categories is one of the everyday jobs, so it gets its own screen in the
 * rail. The list, dialogs and actions are `CategoriesSection` unchanged (Ajustes links here).
 */
import { CategoriesSection } from '@/components/settings/CategoriesSection';
import { PageHeader, Skeleton } from '@/components/ui';
import { useI18n } from '@/lib/i18n';
import { WorkspaceGate, useWorkspace } from '@/lib/workspace';

export default function CategoriasPage() {
  const { t } = useI18n();
  return (
    <>
      <PageHeader title={t('cat.title')} subtitle={t('cat.page.sub')} />
      <WorkspaceGate fallback={<Skeleton variant="list" rows={6} what={t('cat.title')} />}>
        <CategoriesBody />
      </WorkspaceGate>
    </>
  );
}

function CategoriesBody() {
  const { ws } = useWorkspace();
  return (
    <section className="card">
      <CategoriesSection ws={ws} />
    </section>
  );
}
