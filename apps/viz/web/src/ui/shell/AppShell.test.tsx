/**
 * Structural and interaction tests for the shared AppShell.
 *
 * USAGE:
 *   pnpm exec vitest run src/ui/shell/AppShell.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { AppSettingsProvider } from '@/lib/shared/lib/AppSettingsProvider';
import { SectionNavigator } from '@/ui';

import { AppShell } from './AppShell';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const SIDEBAR_KEY = 'qf-viz-sidebar-collapsed';
const SECTION_NAV_NARROW_KEY = 'qf-viz-section-nav-narrow';

let container: HTMLDivElement;
let root: Root;

async function mount(path = '/catalog', page: ReactNode = <p data-testid="page">Page body</p>) {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <AppSettingsProvider>
          <AppShell>{page}</AppShell>
        </AppSettingsProvider>
      </MemoryRouter>,
    );
  });
  // Let the lazily loaded settings button settle before assertions.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

function query<T extends Element>(selector: string): T {
  const element = container.querySelector<T>(selector);
  if (!element) throw new Error(`missing ${selector}`);
  return element;
}

async function click(element: Element) {
  await act(async () => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

beforeEach(() => {
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => {
    root.unmount();
  });
  container.remove();
  localStorage.clear();
});

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('AppShell', () => {
  it('renders the skip link, sidebar dock, header rail, and route content', async () => {
    await mount();
    expect(query<HTMLAnchorElement>('a.app-skip-link').getAttribute('href')).toBe('#main-content');
    expect(query('.app-theme.app-shell')).toBeTruthy();
    expect(query('aside.app-sidebar')).toBeTruthy();
    const main = query<HTMLElement>('main#main-content.app-main');
    expect(main.querySelector('.app-workspace-header')).toBeTruthy();
    expect(main.querySelector('.route-content [data-testid="page"]')?.textContent).toBe(
      'Page body',
    );
    expect(container.querySelector('.app-shell-overlay')).toBeNull();
  });

  it('starts collapsed by default', async () => {
    await mount();
    expect(query('aside.app-sidebar').classList.contains('collapsed')).toBe(true);
  });

  it('restores the persisted collapse state and persists toggles', async () => {
    localStorage.setItem(SIDEBAR_KEY, '0');
    await mount();
    const aside = query('aside.app-sidebar');
    expect(aside.classList.contains('collapsed')).toBe(false);

    await click(query('button[aria-label="Collapse quant-factory navigation"]'));
    expect(aside.classList.contains('collapsed')).toBe(true);
    expect(localStorage.getItem(SIDEBAR_KEY)).toBe('1');
  });

  it('opens the drawer from the menu button and closes it on Escape', async () => {
    await mount();
    const menuButton = query<HTMLButtonElement>('button[aria-label="Toggle sidebar"]');
    expect(menuButton.getAttribute('aria-expanded')).toBe('false');

    await click(menuButton);
    const aside = query('aside.app-sidebar');
    expect(aside.classList.contains('is-open')).toBe(true);
    expect(aside.classList.contains('collapsed')).toBe(false);
    expect(menuButton.getAttribute('aria-expanded')).toBe('true');
    expect(container.querySelector('.app-shell-overlay')).toBeTruthy();

    await act(async () => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(aside.classList.contains('is-open')).toBe(false);
    expect(container.querySelector('.app-shell-overlay')).toBeNull();
    expect(document.activeElement).toBe(menuButton);
  });

  it('shares the section-navigator width through app settings and persists it', async () => {
    localStorage.setItem(SECTION_NAV_NARROW_KEY, '1');
    await mount(
      '/docs',
      <>
        <SectionNavigator title="Docs" collapsed={false} onToggleCollapse={() => {}}>
          <p>rows</p>
        </SectionNavigator>
        <SectionNavigator title="Guides" collapsed={false} onToggleCollapse={() => {}}>
          <p>rows</p>
        </SectionNavigator>
      </>,
    );
    const navigators = [...container.querySelectorAll('aside.section-navigator')];
    expect(navigators.map((node) => node.classList.contains('is-narrow'))).toEqual([true, true]);

    await click(query('button[aria-label="Widen Docs navigation"]'));
    expect(navigators.map((node) => node.classList.contains('is-narrow'))).toEqual([false, false]);
    expect(localStorage.getItem(SECTION_NAV_NARROW_KEY)).toBe('0');
  });
});
