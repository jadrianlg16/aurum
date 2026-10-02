'use client';

/**
 * Cross-border — residency, the treaty ladder, FBAR and FEIE-vs-FTC.
 *
 * Four blocks, each with its own `Explain`, because they answer four separate questions and a
 * person can be right about one and wrong about the next. Nothing here decides anything: the
 * API's own `disclaimer` closes the page and the flags are phrased as things to *explore* with
 * a preparer.
 */
import { useCallback, useState } from 'react';
import { Empty, ErrorBox, Loading, Money, Section } from '@/components/Bits';
import { Explain } from '@/components/Explain';
import { UnverifiedList } from '@/components/VerifyChips';
import { XbProfileWizard } from '@/components/XbProfileWizard';
import { ApiError, getCrossborder } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { CrossborderProfile } from '@/lib/types';

const EMPTY_PROFILE: CrossborderProfile = {
  days_mx: 0,
  days_us: 0,
  days_us_prior_1: 0,
  days_us_prior_2: 0,
  days_abroad_for_feie: 0,
  bona_fide_resident_abroad: false,
  home_mx: false,
  home_us: false,
  green_card: false,
  citizenship: [],
  filing_status: 'single',
  main_professional_center: null,
  mx_source_income_share: null,
  foreign_tax_paid_usd: '0',
  income_sources: [],
  foreign_accounts: [],
  treaty_permanent_home: null,
  treaty_center_of_vital_interests: null,
  treaty_habitual_abode: null,
  treaty_nationality: null,
};

function YesNo({ value, label }: { value: boolean; label: string }) {
  return (
    <span className={`badge ${value ? 'gold' : 'neutral'}`}>
      {label}: {value ? '✓' : '—'}
    </span>
  );
}

export default function CrossborderPage() {
  const { t } = useI18n();
  const { ws } = useWorkspace();
  const [editing, setEditing] = useState(false);
  const [savedNote, setSavedNote] = useState(false);

  // No profile yet is a 404, not an error: the page still renders so "Editar perfil" can
  // create the first one (before, a new workspace saw only an error box and no way forward).
  const assessment = useResource(
    useCallback(
      () =>
        getCrossborder(ws).catch((e: unknown) => {
          if (e instanceof ApiError && e.status === 404) return null;
          throw e;
        }),
      [ws],
    ),
    [ws],
  );

  if (assessment.loading) return <Loading />;
  if (assessment.error) return <ErrorBox message={assessment.error} onRetry={assessment.reload} />;
  const d = assessment.data;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t('xb.title')}</h1>
          <div className="sub">{ws}</div>
        </div>
        <div className="spacer" style={{ flex: 1 }} />
        {!editing && (
          <button type="button" className="btn primary" onClick={() => setEditing(true)}>
            {t('xb.edit_profile')}
          </button>
        )}
      </div>

      {savedNote && <div className="banner info">{t('xb.saved')}</div>}

      {editing && (
        <XbProfileWizard
          ws={ws}
          initial={d?.profile ?? EMPTY_PROFILE}
          onCancel={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            setSavedNote(true);
            assessment.reload();
          }}
        />
      )}

      {!d ? (
        <Empty text={t('xb.no_profile')} />
      ) : (
        <div className="stack">
          {d.flags.length > 0 && (
            <div className="banner warn">
              <strong>{t('xb.flags')}</strong>
              <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                {d.flags.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          )}

          <Section title={t('xb.residency')}>
            <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
              <YesNo value={d.residency.mx} label={t('xb.resident_mx')} />
              <YesNo value={d.residency.us} label={t('xb.resident_us')} />
              {d.residency.dual && <span className="badge warn">{t('xb.dual')}</span>}
              <div style={{ flex: 1 }} />
              <span className="small muted">{t('xb.weighted_days')}</span>
              <strong className="money">{d.residency.weighted_us_days.amount}</strong>
            </div>
            <Explain explain={d.residency.explain} />
          </Section>

          <Section title={t('xb.treaty')}>
            {!d.treaty.applies ? (
              <p className="small muted">{t('xb.treaty_na')}</p>
            ) : (
              <div className="row small" style={{ marginBottom: 8 }}>
                <span className="badge gold">{t('xb.treaty_applies')}</span>
                {typeof d.treaty.resolved_at_step === 'number' && (
                  <span className="badge info">
                    {t('xb.resolved_step')} {d.treaty.resolved_at_step}
                  </span>
                )}
              </div>
            )}
            <h3>{t('xb.checklist')}</h3>
            <ol style={{ margin: '6px 0 0', paddingLeft: 20 }}>
              {d.treaty.checklist.map((s) => (
                <li
                  key={s.key}
                  className={s.step === d.treaty.resolved_at_step ? 'strong' : 'muted'}
                  style={{ marginBottom: 4 }}
                >
                  {s.label}
                </li>
              ))}
            </ol>
            <Explain explain={d.treaty.explain} />
          </Section>

          <Section title={t('xb.fbar')}>
            <div className="row">
              <span className={`badge ${d.fbar.required ? 'warn' : 'pos'}`}>
                {d.fbar.required ? t('xb.fbar_required') : t('xb.fbar_not_required')}
              </span>
              <div style={{ flex: 1 }} />
              <span className="small muted">{t('xb.aggregate')}</span>
              <strong>
                <Money value={d.fbar.aggregate} />
              </strong>
              <span className="small muted">
                {t('xb.threshold')}: {d.fbar.threshold}
              </span>
            </div>
            <Explain explain={d.fbar.explain} />
          </Section>

          <Section title={t('xb.feie')}>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t('xb.option')}</th>
                    <th>{t('explain.citations')}</th>
                    <th className="num">{t('common.amount')}</th>
                  </tr>
                </thead>
                <tbody>
                  {d.feie_vs_ftc.options.map((o) => (
                    <tr key={o.option}>
                      <td>
                        <strong>{o.option}</strong>
                      </td>
                      <td className="small muted">{o.citation}</td>
                      <td className="num">
                        <Money value={o.value} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Explain explain={d.feie_vs_ftc.explain} />
          </Section>

          <UnverifiedList keys={d.unverified_constants} />

          <p className="notice">{d.disclaimer || t('xb.not_advice')}</p>
        </div>
      )}
    </>
  );
}
