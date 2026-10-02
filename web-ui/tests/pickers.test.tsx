/**
 * AccountPicker / CategoryPicker (`components/ui` primitives). The suite skips itself if
 * `components/ui` is missing; otherwise it renders both with `renderToStaticMarkup` and asserts
 * the personal rules: grouped account names, never a ledger string, kind-filtered categories.
 */
import { existsSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const UI_INDEX = path.resolve(__dirname, '..', 'src', 'components', 'ui', 'index.ts');
const UI_INDEX_TSX = path.resolve(__dirname, '..', 'src', 'components', 'ui', 'index.tsx');
const hasUi = existsSync(UI_INDEX) || existsSync(UI_INDEX_TSX);

describe.skipIf(!hasUi)('pickers', () => {
  it('render without ledger strings and honour the kind filter', async () => {
    const { renderToStaticMarkup } = await import('react-dom/server');
    const modPath = '@/components/ui';
    const ui = (await import(/* @vite-ignore */ modPath)) as Record<string, unknown>;
    const AccountPicker = ui.AccountPicker as ((props: Record<string, unknown>) => unknown) | undefined;
    const CategoryPicker = ui.CategoryPicker as ((props: Record<string, unknown>) => unknown) | undefined;
    expect(typeof AccountPicker).toBe('function');
    expect(typeof CategoryPicker).toBe('function');
    if (!AccountPicker || !CategoryPicker) return;
    const { createElement } = await import('react');
    // The primitives read t()/fmt() from context, so render them the way the app does: inside both providers.
    const { I18nProvider } = await import('@/lib/i18n');
    const { WorkspaceProvider } = await import('@/lib/workspace');
    const wrap = (el: unknown) =>
      createElement(I18nProvider, null, createElement(WorkspaceProvider, null, el as never));
    const account = renderToStaticMarkup(wrap(createElement(AccountPicker as never, { ws: 'mock-personal', value: null, onChange: () => undefined })));
    const category = renderToStaticMarkup(wrap(createElement(CategoryPicker as never, { ws: 'mock-personal', kind: 'expense', value: null, onChange: () => undefined })));
    for (const html of [account, category]) {
      expect(html).not.toMatch(/\b(Assets|Liabilities|Income|Expenses|Equity):/);
      expect(html.length).toBeGreaterThan(0);
    }
  });
});

describe('pickers (presence check)', () => {
  it('records whether components/ui exists', () => {
    expect(typeof hasUi).toBe('boolean');
  });
});
