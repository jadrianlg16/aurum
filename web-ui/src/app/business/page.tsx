'use client';

/**
 * Negocio — the business-workspace screen.
 *
 * The rail only shows this entry when the current workspace is `kind === "business"`, but a
 * direct link is still possible (and the static export has no per-workspace routes), so the
 * page checks the workspace itself and explains rather than erroring. The constants tab is
 * workspace-independent — `GET /business/constants/mx-nl` is global — so it stays available.
 */
import { useState } from 'react';
import {
  BusinessConstantsPanel,
  BusinessInvoicesPanel,
  BusinessKpisPanel,
  BusinessPayrollPanel,
} from '@/components/Business';
import { TabPanel, Tabs, useToast } from '@/components/Ui3';
import { useI18n } from '@/lib/i18n';
import { closePeriod, periodsEndingAt } from '@/lib/period';
import { useQueryTab } from '@/lib/query';
import { useWorkspace } from '@/lib/workspace';

type Tab = 'kpis' | 'invoices' | 'payroll' | 'constants';

export default function BusinessPage() {
  const { t } = useI18n();
  const { ws, current } = useWorkspace();
  const [tab, setTab] = useQueryTab<Tab>(['kpis', 'invoices', 'payroll', 'constants'] as const, 'kpis');
  const [period, setPeriod] = useState(closePeriod());
  const toast = useToast();

  const isBusiness = current?.kind === 'business';

  return (
    <>
      <div className="page-head">
        <h1>{t('business.title')}</h1>
        <div className="spacer" />
        {(tab === 'kpis' || tab === 'payroll') && (
          <label className="field">
            {t('common.period')}
            <select value={period} onChange={(e) => setPeriod(e.target.value)}>
              {periodsEndingAt(closePeriod(), 12).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <Tabs<Tab>
        label={t('business.title')}
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'kpis', label: t('business.tab.kpis') },
          { id: 'invoices', label: t('business.tab.invoices') },
          { id: 'payroll', label: t('business.tab.payroll') },
          { id: 'constants', label: t('business.tab.constants') },
        ]}
      />

      {!isBusiness && tab !== 'constants' ? (
        <div className="card" style={{ marginTop: 14 }}>
          <p>{t('business.only')}</p>
        </div>
      ) : (
        <div style={{ marginTop: 14 }}>
          {tab === 'kpis' && (
            <TabPanel id="kpis">
              <BusinessKpisPanel ws={ws} period={period} />
            </TabPanel>
          )}
          {tab === 'invoices' && (
            <TabPanel id="invoices">
              <BusinessInvoicesPanel ws={ws} toast={toast} />
            </TabPanel>
          )}
          {tab === 'payroll' && (
            <TabPanel id="payroll">
              <BusinessPayrollPanel ws={ws} period={period} />
            </TabPanel>
          )}
          {tab === 'constants' && (
            <TabPanel id="constants">
              <BusinessConstantsPanel />
            </TabPanel>
          )}
        </div>
      )}

      {toast.node}
    </>
  );
}
