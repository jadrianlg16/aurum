/**
 * The advanced screens, in one list: the Shell's collapsed Avanzado group and the `/avanzado/`
 * page both read it, so a screen added here shows up in both. Same routes as before — nothing
 * is gated at the route; this list only decides where a link to it is shown.
 *
 * `icon` is the text glyph the rail uses for the group; `group` and `desc` are for the
 * `/avanzado/` page, which explains each screen in one plain line.
 */
import type { MsgKey } from './i18n';
import type { ModuleKey } from './types-personal';

export type AdvancedGroup = 'understand' | 'documents' | 'taxes' | 'expert';

export interface AdvancedItem {
  href: string;
  key: MsgKey;
  icon: string;
  group: AdvancedGroup;
  desc: MsgKey;
  /** Only for a business workspace — the screen reads `/api/business/...`. */
  businessOnly?: boolean;
  /** Shown in the rail's Avanzado group when this module's flag is on, even in simple mode. */
  module?: ModuleKey;
}

export const ADVANCED_GROUPS: AdvancedGroup[] = ['understand', 'documents', 'taxes', 'expert'];

export const ADVANCED_ITEMS: AdvancedItem[] = [
  { href: '/avisos', key: 'nav.avisos', icon: '!', group: 'understand', desc: 'adv.hub.desc.avisos' },
  { href: '/inbox', key: 'nav.inbox', icon: '▤', group: 'documents', desc: 'adv.hub.desc.inbox' },
  { href: '/business', key: 'nav.business', icon: '⌂', group: 'expert', desc: 'adv.hub.desc.business', businessOnly: true, module: 'business' },
  { href: '/documents', key: 'nav.documents', icon: '❐', group: 'documents', desc: 'adv.hub.desc.documents' },
  { href: '/books', key: 'nav.books', icon: '≣', group: 'expert', desc: 'adv.hub.desc.books' },
  { href: '/reconcile', key: 'nav.reconcile', icon: '⇄', group: 'documents', desc: 'adv.hub.desc.reconcile' },
  { href: '/taxes', key: 'nav.taxes', icon: '§', group: 'taxes', desc: 'adv.hub.desc.taxes', module: 'tax' },
  { href: '/crossborder', key: 'nav.crossborder', icon: '⇔', group: 'taxes', desc: 'adv.hub.desc.crossborder', module: 'crossborder' },
  { href: '/research', key: 'nav.research', icon: '?', group: 'taxes', desc: 'adv.hub.desc.research', module: 'research' },
  { href: '/watch', key: 'nav.watch', icon: '◎', group: 'taxes', desc: 'adv.hub.desc.watch', module: 'watch' },
  { href: '/plan', key: 'nav.plan', icon: '◆', group: 'understand', desc: 'adv.hub.desc.plan', module: 'holdings' },
  { href: '/reports', key: 'nav.reports', icon: '▦', group: 'understand', desc: 'adv.hub.desc.reports', module: 'reports' },
  { href: '/workflows', key: 'nav.workflows', icon: '↻', group: 'expert', desc: 'adv.hub.desc.workflows', module: 'workflows' },
  { href: '/tools', key: 'nav.tools', icon: '⚙', group: 'expert', desc: 'adv.hub.desc.tools' },
];

/** The screens that exist for this workspace kind (Negocio needs a business workspace). */
export function advancedItemsFor(kind: string | undefined): AdvancedItem[] {
  return ADVANCED_ITEMS.filter((n) => !n.businessOnly || kind === 'business');
}
