'use client';

/**
 * Welcome — the first-run screen. Shown by the Shell instead of the page when
 * the workspace list has no personal (non-sample) workspace, which used to leave every screen
 * on a skeleton forever (or, with the Docker demo seed, open the business tax demo).
 *
 * Two questions, both prefilled — a name and a currency — then `POST /workspaces` creates
 * `personal` (the env-protected id) and the person lands on Empezar. When the sample
 * `demo-personal` is on disk a secondary link opens it instead, labelled "(atajo)".
 */
import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';
import { Button, Field, Icon, Input, type IconName } from '@/components/ui';
import { createWorkspace, errorMessage } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useWorkspace } from '@/lib/workspace';
import type { MsgKey } from '@/lib/i18n';
import choice from './cuentas/choice.module.css';
import styles from './welcome.module.css';

const PERSONAL_ID = 'personal';
const SAMPLE_ID = 'demo-personal';
const CURRENCIES = ['MXN', 'USD'] as const;
type Currency = (typeof CURRENCIES)[number];

const POINTS: { icon: IconName; key: MsgKey }[] = [
  { icon: 'plus', key: 'welcome.point.add' },
  { icon: 'calendar', key: 'welcome.point.left' },
  { icon: 'flag', key: 'welcome.point.goals' },
];

export function Welcome() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { workspaces, setWs, refresh } = useWorkspace();
  const [name, setName] = useState(() => t('welcome.name.default'));
  const [currency, setCurrency] = useState<Currency>('MXN');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasSample = workspaces.some((w) => w.id === SAMPLE_ID);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await createWorkspace({
        id: PERSONAL_ID,
        name: name.trim() || t('welcome.name.default'),
        kind: 'personal',
        jurisdictions: [currency === 'USD' ? 'US' : 'MX'],
        base_currency: currency,
        language: lang,
        profile: {},
        ui_mode: 'simple',
      });
      setWs(PERSONAL_ID);
      refresh();
      router.push('/empezar/');
    } catch (err) {
      setError(t('welcome.failed', { message: errorMessage(err, t) }));
      setBusy(false);
    }
  };

  return (
    <section className={styles.wrap} aria-labelledby="welcome-title">
      <span className={styles.mark} aria-hidden="true">
        Au
      </span>
      <h1 id="welcome-title">{t('welcome.title')}</h1>
      <p className={styles.lead}>{t('welcome.lead')}</p>

      <ul className={styles.points}>
        {POINTS.map((p) => (
          <li key={p.key}>
            <Icon name={p.icon} size={18} />
            {t(p.key)}
          </li>
        ))}
      </ul>

      <form className={`card stack ${styles.form}`} onSubmit={(e) => void submit(e)} aria-busy={busy || undefined} noValidate>
        <Field label={t('welcome.name')} hint={t('welcome.name.hint')}>
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} autoComplete="off" disabled={busy} />
        </Field>
        <Field label={t('welcome.currency')} asGroup>
          <div className="row" role="radiogroup" aria-label={t('welcome.currency')}>
            {CURRENCIES.map((c) => (
              <Button
                key={c}
                role="radio"
                aria-checked={currency === c}
                variant="secondary"
                className={choice.choice}
                onClick={() => setCurrency(c)}
                disabled={busy}
              >
                {t(`welcome.currency.${c}`)}
              </Button>
            ))}
          </div>
        </Field>
        {error && (
          <p className="ui-dialog-error" role="alert">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" size="lg" loading={busy} className={styles.start} data-testid="welcome-start">
          {t('welcome.start')}
        </Button>
        {hasSample && (
          <button type="button" className={`ui-linkbtn ${styles.sample}`} onClick={() => setWs(SAMPLE_ID)} disabled={busy}>
            {t('welcome.sample')}
          </button>
        )}
      </form>
      <p className={styles.private}>{t('welcome.private')}</p>
    </section>
  );
}
