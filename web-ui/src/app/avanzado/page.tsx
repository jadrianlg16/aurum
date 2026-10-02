'use client';

/**
 * Avanzado (`/avanzado/`) — the last item of the menu, for everyone. Every advanced screen in
 * one place, grouped, each with one plain line saying what it is for, so a person who wants
 * more can find it without it being the first thing anyone sees. The list is
 * `lib/advanced.ts` (the rail's Avanzado group reads the same one); the screens themselves are
 * unchanged and open at their usual routes. No request fires here.
 *
 * In simple mode a closing card points to Ajustes › Modo, where Modo avanzado puts these
 * screens straight into the menu.
 */
import Link from 'next/link';
import { Button, Icon, PageHeader } from '@/components/ui';
import { ADVANCED_GROUPS, advancedItemsFor } from '@/lib/advanced';
import { useI18n } from '@/lib/i18n';
import { useAdvanced, useWorkspace } from '@/lib/workspace';
import s from './avanzado.module.css';

export default function AvanzadoPage() {
  const { t } = useI18n();
  const { current } = useWorkspace();
  const advanced = useAdvanced();
  const items = advancedItemsFor(current?.kind);

  return (
    <>
      <PageHeader title={t('nav.advanced')} subtitle={t('adv.hub.sub')} />
      <div className="stack">
        {ADVANCED_GROUPS.map((g) => {
          const list = items.filter((n) => n.group === g);
          if (list.length === 0) return null;
          return (
            <section key={g} aria-labelledby={`adv-${g}`}>
              <h2 id={`adv-${g}`} className={s.heading}>
                {t(`adv.hub.group.${g}`)}
              </h2>
              <ul className={s.grid}>
                {list.map((n) => (
                  <li key={n.href}>
                    <Link href={n.href} className={s.card}>
                      <span className={s.title}>
                        {t(n.key)}
                        <Icon name="chevron-right" size={16} />
                      </span>
                      <span className={s.desc}>{t(n.desc)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}

        {!advanced && (
          <section className={`card ${s.menu}`} aria-labelledby="adv-menu">
            <h2 id="adv-menu" className={s.heading}>
              {t('adv.hub.menu.title')}
            </h2>
            <p>{t('adv.hub.menu.body')}</p>
            <Button variant="secondary" href="/settings/#modo">
              {t('adv.hub.menu.cta')}
            </Button>
          </section>
        )}
      </div>
    </>
  );
}
