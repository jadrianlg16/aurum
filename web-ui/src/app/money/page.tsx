'use client';

/**
 * "Mi dinero" (`/money/`).
 *
 * `PageHeader` (claims the document title), then `Tabs`: Pagos fijos · Ingresos · Calendario in
 * simple mode, Resumen · … · Flujo · Plan · Configurar in advanced mode. Tab ids
 * stay `summary | subs | income | calendar | flow | plan | setup` (`/money/?tab=subs` is linked
 * from `/empezar`); `?tab=plan|setup` in simple mode falls back to `summary` because the gated
 * list is what `useQueryParam` validates against. Nothing but a Skeleton renders until the
 * workspace is resolved, so every date runs after mount and after `ws` is known.
 *
 * The three older panels (Ingresos, Plan, Configurar) still take the legacy `Ui3.useToast()`
 * toaster; one instance lives here for them. Every new panel uses `components/ui`.
 */
import { MoneySummaryPanel } from '@/components/Money';
import { MoneyCalendarPanel } from '@/components/MoneyCalendar';
import { MoneyFlowPanel } from '@/components/MoneyFlow';
import { MoneyPlanPanel } from '@/components/MoneyPlan';
import { MoneySetupPanel } from '@/components/MoneySetup';
import { MoneySubsPanel } from '@/components/MoneySubs';
import { IncomeStreamsPanel } from '@/components/IncomeStreams';
import { useToast as useLegacyToast } from '@/components/Ui3';
import { PageHeader, Skeleton, TabPanel, Tabs, type TabItem } from '@/components/ui';
import styles from '@/components/money/money.module.css';
import { useI18n, useMoney } from '@/lib/i18n';
import { useQueryParam } from '@/lib/query';
import { useAdvanced, useWorkspace } from '@/lib/workspace';

type Tab = 'summary' | 'subs' | 'income' | 'calendar' | 'flow' | 'plan' | 'setup';

// Simple mode is the three lists a person keeps by hand. Resumen repeated
// Inicio's Disponible and Flujo is a 90-day projection chart; both stay in advanced mode.
const SIMPLE: readonly Tab[] = ['subs', 'income', 'calendar'];
const ADVANCED: readonly Tab[] = ['summary', 'subs', 'income', 'calendar', 'flow', 'plan', 'setup'];

export default function MoneyPage() {
  const { t } = useI18n();
  const { wsOrNull, resolved } = useWorkspace();
  return (
    <>
      <PageHeader title={t('money.title')} subtitle={t('money.subtitle')} />
      {resolved && wsOrNull !== null ? <MoneyTabs ws={wsOrNull} /> : <Skeleton variant="stat" what={t('money.title')} />}
    </>
  );
}

/** Mounted only once the workspace is resolved, so `useAdvanced()` is final when `?tab=` is read. */
function MoneyTabs({ ws }: { ws: string }) {
  const { t } = useI18n();
  const { base: currency } = useMoney();
  const advanced = useAdvanced();
  const valid = advanced ? ADVANCED : SIMPLE;
  const fallback: Tab = advanced ? 'summary' : 'subs';
  const [tab, setTab] = useQueryParam<Tab>('tab', fallback, valid);
  const legacyToast = useLegacyToast();

  const labels: Record<Tab, string> = {
    summary: t('money.tab.summary'),
    subs: t('money.tab.fixed'),
    income: t('inc.title'),
    calendar: t('money.tab.calendar'),
    flow: t('money.tab.flow'),
    plan: t('money.tab.plan'),
    setup: t('money.tab.setup'),
  };
  const items: TabItem<Tab>[] = valid.map((id) => ({ id, label: labels[id] }));
  const active: Tab = valid.includes(tab) ? tab : fallback;

  return (
    <>
      <Tabs<Tab> items={items} value={active} onChange={setTab} queryKey="tab" label={t('money.title')} />

      {advanced && active === 'summary' && (
        <TabPanel className={styles.panel} id="summary">
          <MoneySummaryPanel ws={ws} />
        </TabPanel>
      )}
      {active === 'subs' && (
        <TabPanel className={styles.panel} id="subs">
          <MoneySubsPanel ws={ws} />
        </TabPanel>
      )}
      {active === 'income' && (
        <TabPanel className={styles.panel} id="income">
          <IncomeStreamsPanel ws={ws} toast={legacyToast} currency={currency} />
        </TabPanel>
      )}
      {active === 'calendar' && (
        <TabPanel className={styles.panel} id="calendar">
          <MoneyCalendarPanel ws={ws} />
        </TabPanel>
      )}
      {advanced && active === 'flow' && (
        <TabPanel className={styles.panel} id="flow">
          <MoneyFlowPanel ws={ws} onGoTo={setTab} />
        </TabPanel>
      )}
      {advanced && active === 'plan' && (
        <TabPanel className={styles.panel} id="plan">
          <MoneyPlanPanel ws={ws} toast={legacyToast} />
        </TabPanel>
      )}
      {advanced && active === 'setup' && (
        <TabPanel className={styles.panel} id="setup">
          <MoneySetupPanel ws={ws} toast={legacyToast} onDone={() => setTab(fallback)} />
        </TabPanel>
      )}
      {legacyToast.node}
    </>
  );
}
