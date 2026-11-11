/**
 * Docked-side, collapsed-strip, header/bottom-bar and width-toggle tests for SectionNavigator,
 * SidebarShell's default footer placement, and the SectionWorkspace bounded
 * content-pane contract.
 *
 * USAGE:
 *   pnpm exec vitest run src/frame/SectionWorkspace.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { SidebarShell } from '../shell/SidebarShell';
import {
  SectionNavigator,
  SectionNavigatorWidthProvider,
  SectionWorkspace,
} from './SectionWorkspace';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function host(ui: ReactNode): HTMLDivElement {
  const node = document.createElement('div');
  node.innerHTML = renderToStaticMarkup(ui);
  return node;
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('SectionNavigator strip', () => {
  it('renders an end-docked collapsed strip with a vertical title and expand button', () => {
    const node = host(
      <SectionNavigator
        title="Features"
        side="end"
        collapsedVariant="strip"
        collapsed
        onToggleCollapse={() => {}}
      >
        <p>rows</p>
      </SectionNavigator>,
    );
    const aside = node.querySelector('aside.section-navigator');
    expect(aside?.getAttribute('aria-label')).toBe('Features navigation');
    expect(aside?.classList.contains('collapsed')).toBe(true);
    expect(aside?.classList.contains('is-end')).toBe(true);
    expect(aside?.classList.contains('is-strip')).toBe(true);
    expect(node.querySelector('.section-navigator-strip-label')?.textContent).toBe('Features');
    // The title reads from the top; the expand button sits at the strip's foot.
    expect(
      node.querySelector(
        '.section-navigator-strip > :last-child[aria-label="Expand Features navigation"]',
      ),
    ).not.toBeNull();
  });

  it('renders the normal shell when expanded', () => {
    const node = host(
      <SectionNavigator
        title="Features"
        side="end"
        collapsedVariant="strip"
        collapsed={false}
        onToggleCollapse={() => {}}
      >
        <p>rows</p>
      </SectionNavigator>,
    );
    expect(node.querySelector('.section-navigator-strip')).toBeNull();
    expect(node.textContent).toContain('rows');
  });
});

describe('SectionNavigator width toggle', () => {
  function SharedWidth({ onChange }: { onChange: (narrow: boolean) => void }) {
    const [narrow, setNarrow] = useState(false);
    return (
      <SectionNavigatorWidthProvider
        narrow={narrow}
        onNarrowChange={(next) => {
          setNarrow(next);
          onChange(next);
        }}
      >
        <SectionNavigator title="Strategies" collapsed={false} onToggleCollapse={() => {}}>
          <p>rows</p>
        </SectionNavigator>
        <SectionNavigator title="Signals" collapsed={false} onToggleCollapse={() => {}}>
          <p>rows</p>
        </SectionNavigator>
      </SectionNavigatorWidthProvider>
    );
  }

  it('toggles between wide and narrow through the shared width provider', () => {
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    const onChange = vi.fn();
    const node = document.createElement('div');
    const root = createRoot(node);
    act(() => {
      root.render(<SharedWidth onChange={onChange} />);
    });
    const [strategies, signals] = Array.from(node.querySelectorAll('aside.section-navigator'));
    expect(strategies?.classList.contains('is-narrow')).toBe(false);

    act(() => {
      node
        .querySelector<HTMLButtonElement>('button[aria-label="Narrow Strategies navigation"]')
        ?.click();
    });
    expect(strategies?.classList.contains('is-narrow')).toBe(true);
    expect(signals?.classList.contains('is-narrow')).toBe(true);
    expect(onChange).toHaveBeenLastCalledWith(true);

    act(() => {
      node
        .querySelector<HTMLButtonElement>('button[aria-label="Widen Strategies navigation"]')
        ?.click();
    });
    expect(strategies?.classList.contains('is-narrow')).toBe(false);
    act(() => root.unmount());
  });

  it('honours controlled narrow props over the provider', () => {
    const onNarrowChange = vi.fn();
    const node = document.createElement('div');
    const root = createRoot(node);
    act(() => {
      root.render(
        <SectionNavigatorWidthProvider narrow={false} onNarrowChange={() => {}}>
          <SectionNavigator
            title="Docs"
            collapsed={false}
            onToggleCollapse={() => {}}
            narrow
            onNarrowChange={onNarrowChange}
          >
            <p>rows</p>
          </SectionNavigator>
        </SectionNavigatorWidthProvider>,
      );
    });
    expect(node.querySelector('aside')?.classList.contains('is-narrow')).toBe(true);
    act(() => {
      node.querySelector<HTMLButtonElement>('button[aria-label="Widen Docs navigation"]')?.click();
    });
    expect(onNarrowChange).toHaveBeenCalledWith(false);
    act(() => root.unmount());
  });

  it('falls back to local state without a provider', () => {
    const node = document.createElement('div');
    const root = createRoot(node);
    act(() => {
      root.render(
        <SectionNavigator title="Docs" collapsed={false} onToggleCollapse={() => {}}>
          <p>rows</p>
        </SectionNavigator>,
      );
    });
    act(() => {
      node.querySelector<HTMLButtonElement>('button[aria-label="Narrow Docs navigation"]')?.click();
    });
    expect(node.querySelector('aside')?.classList.contains('is-narrow')).toBe(true);
    act(() => root.unmount());
  });

  it('hides the width toggle while collapsed', () => {
    const node = host(
      <SectionNavigator title="Strategies" collapsed onToggleCollapse={() => {}}>
        <p>rows</p>
      </SectionNavigator>,
    );
    expect(node.querySelector('.section-navigator-width-toggle')).toBeNull();
  });
});

describe('SectionWorkspace contentMode', () => {
  it('bounds the content pane only when contentMode is fill', () => {
    const filled = host(
      <SectionWorkspace contentMode="fill" navigator={null}>
        x
      </SectionWorkspace>,
    );
    expect(filled.querySelector('div.section-workspace.is-fill-content')).not.toBeNull();
    expect(
      filled.querySelector(
        'div.section-workspace.is-fill-content .section-workspace-content.is-fill',
      ),
    ).not.toBeNull();

    const scrolled = host(<SectionWorkspace navigator={null}>x</SectionWorkspace>);
    expect(scrolled.querySelector('.section-workspace.is-fill-content')).toBeNull();
    expect(scrolled.querySelector('.section-workspace-content.is-fill')).toBeNull();
  });
});

describe('SectionNavigator collapse direction', () => {
  it('points the expanded collapse glyph toward the docked edge', () => {
    const end = host(
      <SectionNavigator title="Features" side="end" collapsed={false} onToggleCollapse={() => {}}>
        <p>rows</p>
      </SectionNavigator>,
    );
    expect(
      end.querySelector('.shell-bottombar .sidebar-collapse-glyph[data-direction="right"]'),
    ).not.toBeNull();

    const start = host(
      <SectionNavigator title="Features" collapsed={false} onToggleCollapse={() => {}}>
        <p>rows</p>
      </SectionNavigator>,
    );
    expect(
      start.querySelector('.shell-bottombar .sidebar-collapse-glyph[data-direction="right"]'),
    ).toBeNull();
    expect(
      start.querySelector('.shell-bottombar .sidebar-collapse-glyph[data-direction="left"]'),
    ).not.toBeNull();
  });
});

describe('SectionNavigator header and bottom bar', () => {
  it('renders a title-only header and a bottom bar with collapse, search and width toggle in order', () => {
    const node = host(
      <SectionNavigator
        title="Strategies"
        collapsed={false}
        onToggleCollapse={() => {}}
        headerActions={<button type="button" aria-label="Search Strategies" />}
        footerControls={<i data-x="foot" />}
      >
        <p>rows</p>
      </SectionNavigator>,
    );
    const header = node.querySelector('.shell > .shell-header.shell-topbar');
    expect(header).not.toBeNull();
    expect(header?.textContent).toBe('Strategies');
    expect(header?.querySelectorAll('button')).toHaveLength(0);
    expect(node.querySelector('.brand-static')).toBeNull();
    expect(node.querySelector('.footer-bar')).toBeNull();
    expect(node.querySelector('.footer [data-x="foot"]')).not.toBeNull();
    // The bottom bar is the shell's last child, after the scrolling body and footer slot.
    const bottombar = node.querySelector('.shell > .shell-bottombar:last-child');
    expect(bottombar).not.toBeNull();
    const labels = Array.from(bottombar?.querySelectorAll('button') ?? []).map((button) =>
      button.getAttribute('aria-label'),
    );
    expect(labels).toEqual([
      'Collapse Strategies navigation',
      'Search Strategies',
      'Narrow Strategies navigation',
    ]);
    expect(bottombar?.querySelector(':scope > .sidebar-collapse-button.is-icon')).not.toBeNull();
    expect(
      bottombar?.querySelector(
        ':scope > .shell-bottombar-actions > .section-navigator-width-toggle',
      ),
    ).not.toBeNull();
  });

  it('keeps only the expand tile in the bottom bar while collapsed', () => {
    const node = host(
      <SectionNavigator title="Strategies" collapsed onToggleCollapse={() => {}}>
        <p>rows</p>
      </SectionNavigator>,
    );
    expect(node.querySelector('.shell-topbar')).toBeNull();
    const bottombar = node.querySelector('.shell-bottombar');
    expect(bottombar?.querySelectorAll('button')).toHaveLength(1);
    expect(
      bottombar?.querySelector(
        ':scope > .sidebar-collapse-button.is-tile[aria-label="Expand Strategies navigation"]',
      ),
    ).not.toBeNull();
    expect(node.querySelector('.footer')).toBeNull();
  });
});

describe('SidebarShell default footer placement', () => {
  it('keeps the title row and footer collapse button', () => {
    const withActions = host(
      <SidebarShell
        title="Panel"
        onToggleCollapse={() => {}}
        headerActions={<i data-x="act" />}
        footerActions={<i data-x="trail" />}
      >
        <p>rows</p>
      </SidebarShell>,
    );
    expect(withActions.querySelector('.shell-header > .brand.brand-static')).not.toBeNull();
    expect(withActions.querySelector('.shell-topbar')).toBeNull();
    expect(
      withActions.querySelector('.footer > .footer-bar > .sidebar-collapse-button'),
    ).not.toBeNull();
    expect(withActions.querySelector('.footer-bar-actions [data-x="trail"]')).not.toBeNull();

    const bare = host(
      <SidebarShell title="Panel" onToggleCollapse={() => {}}>
        <p>rows</p>
      </SidebarShell>,
    );
    expect(bare.querySelector('.shell > .brand.brand-static')).not.toBeNull();
    expect(bare.querySelector('.footer > .sidebar-collapse-button')).not.toBeNull();
  });
});
