'use client';

/**
 * The one "Disponible": `GET /organizer/{ws}/summary`
 * `safe_to_spend` as a large `Stat` — "Disponible hasta el 30 sep" — with one plain sentence
 * under it. The four parts (balance +, fixed payments −, budget left −,
 * cushion −; all server figures, signs made explicit) and the explain summary live behind
 * "¿Cómo se calcula?", so a first look is one number and one sentence, never a formula.
 *
 * `summary.setup.has_income === false` (no active income) → the figure is "Lo que tienes hoy"
 * (`parts.balance`) with a link to add the income on /empezar/?step=income; "Disponible" is
 * then absent, because without a payday there is no "until".
 */
import { Button, Money, Stat } from '@/components/ui';
import { decimalSign, formatDate } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import type { OrganizerSummary } from '@/lib/types-organizer';
import { negated } from './shared';
import styles from './home.module.css';

export function HeroDisponible({ summary }: { summary: OrganizerSummary }) {
  const { t, lang } = useI18n();
  const s = summary.safe_to_spend;
  const parts = s.parts;
  const noIncome = summary.setup?.has_income === false;

  if (noIncome) {
    return (
      <section className="card headline" aria-label={t('inicio.tienes_hoy')}>
        <Stat
          size="lg"
          label={t('inicio.tienes_hoy')}
          value={<Money amount={parts?.balance ?? s.amount} sign="auto" />}
          sub={<Button variant="ghost" size="sm" href="/empezar/?step=income">{t('inicio.tienes_hoy.cta')}</Button>}
        />
      </section>
    );
  }

  const label = t('inicio.disponible_hasta', { date: formatDate(s.until, lang, 'short') });
  const negative = decimalSign(s.amount.amount) < 0;
  return (
    <section className="card headline" aria-label={label}>
      <Stat
        size="lg"
        label={label}
        value={<Money amount={s.amount} sign="auto" />}
        sub={negative ? t('inicio.disponible.neg') : t('inicio.disponible.sub')}
      />
      {parts && (
        <details className={styles.how}>
          <summary>{t('explain.steps')}</summary>
          {s.explain?.summary && <p className="explain-summary">{s.explain.summary}</p>}
          <dl className={styles.parts}>
            <dt>{t('inicio.parte.balance')}</dt>
            <dd>
              <Money amount={parts.balance} sign="always" />
            </dd>
            <dt>{t('inicio.parte.fijos')}</dt>
            <dd>
              <Money amount={negated(parts.fixed_pending)} sign="always" />
            </dd>
            <dt>{t('inicio.parte.presupuesto')}</dt>
            <dd>
              <Money amount={negated(parts.budgets_remaining)} sign="always" />
            </dd>
            <dt>{t('inicio.parte.colchon')}</dt>
            <dd>
              <Money amount={negated(parts.buffer)} sign="always" />
            </dd>
          </dl>
        </details>
      )}
    </section>
  );
}
