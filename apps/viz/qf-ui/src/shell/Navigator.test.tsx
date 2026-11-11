/**
 * Structural and interaction tests for the shared Navigator.
 *
 * USAGE:
 *   pnpm exec vitest run src/shell/Navigator.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LocationProbe, MemoryRouter } from '../../tests/memory-router';
import { Button } from '../primitives/Button';
import { Navigator } from './Navigator';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function markup(ui: ReactNode, path = '/signals'): string {
  return renderToStaticMarkup(<MemoryRouter initialPath={path}>{ui}</MemoryRouter>);
}

function stubMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: vi.fn(
      () =>
        ({
          matches,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        }) as unknown as MediaQueryList,
    ),
  });
}

function click(element: Element | null) {
  if (!element) throw new Error('element not found');
  act(() => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }));
  });
}

// --------------------------------------------------------------------------- #
// Structure
// --------------------------------------------------------------------------- #

describe('Navigator markup', () => {
  it('renders the section navigator chrome around a leaf list', () => {
    const html = markup(
      <Navigator
        title="Signals"
        items={[
          { id: 'alpha', label: 'alpha', to: '/signals/alpha', current: true },
          {
            id: 'beta',
            label: 'beta',
            to: '/signals/beta',
            tag: { label: 'supported', tone: 'success' },
          },
        ]}
      />,
    );

    expect(html).toContain('class="section-navigator ui-navigator"');
    expect(html).toContain('aria-label="Signals navigation"');
    expect(html).toContain('Collapse Signals navigation');
    expect(html).toContain('<nav class="ui-navigator-list" aria-label="Signals hierarchy">');
    expect(html).toContain('<ul class="ui-navigator-items">');
    expect(html).toContain('<li class="ui-navigator-item">');
    expect(html).toContain('class="ui-navigator-row is-leaf is-root is-current"');
    expect(html).toContain('aria-current="page"');
    expect(html).toContain('href="/signals/alpha"');
    expect(html).toContain('style="--ui-navigator-depth:0"');
    expect(html).toContain('<span class="ui-navigator-label">alpha</span>');
    expect(html).toContain('<span class="ui-navigator-tag" data-tone="success">supported</span>');
    expect(html).not.toContain('ui-navigator-chevron');
    expect(html).not.toContain('ui-navigator-group-label');
  });

  it('renders disclosure rows with trailing chevrons and nested children', () => {
    const html = markup(
      <Navigator
        title="Signals"
        items={[
          {
            id: 'family',
            label: 'family',
            to: '/signals/family',
            expanded: true,
            onToggle: () => {},
            children: [{ id: 'v001', label: 'v001', to: '/signals/family/v001' }],
          },
          { id: 'leaf', label: 'leaf', to: '/signals/leaf' },
          { id: 'closed', label: 'closed', children: [] },
        ]}
      />,
    );

    expect(html).toContain('<li class="ui-navigator-item is-expanded">');
    expect(html).toContain('class="ui-navigator-row is-disclosure is-root"');
    // nested rows read quieter than the top level
    expect(html).toContain('class="ui-navigator-row is-leaf" style="--ui-navigator-depth:1"');
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('<ul class="ui-navigator-children">');
    expect(html).toContain('style="--ui-navigator-depth:1"');
    expect(html).toContain('class="ui-navigator-chevron is-open"');
    expect(html).toContain('class="ui-navigator-chevron"');
    expect((html.match(/ui-navigator-chevron/g) ?? []).length).toBe(2);
    expect((html.match(/ui-navigator-children"/g) ?? []).length).toBe(1);
  });

  it('renders child loading, error and empty states', () => {
    const base = { id: 'family', label: 'family', expanded: true, children: [] };

    const loading = markup(<Navigator title="Signals" items={[{ ...base, loading: true }]} />);
    expect(loading).toContain('<div class="ui-navigator-children-state">');
    expect(loading).toContain('aria-hidden="true"');
    expect(loading).not.toContain('ui-state-message');

    const error = markup(<Navigator title="Signals" items={[{ ...base, error: 'boom' }]} />);
    expect(error).toContain('ui-state-message-error');
    expect(error).toContain('ui-state-message-compact');
    expect(error).toContain('ui-navigator-message');
    expect(error).toContain('role="alert"');
    expect(error).toContain('boom');

    const empty = markup(
      <Navigator title="Signals" items={[{ ...base, empty: 'No versions yet.' }]} />,
    );
    expect(empty).toContain('No versions yet.');

    const fallback = markup(<Navigator title="Signals" items={[base]} />);
    expect(fallback).toContain('Nothing here yet.');
  });

  it('renders root loading, error and empty states', () => {
    const loading = markup(<Navigator title="Signals" loading items={[{ id: 'a', label: 'a' }]} />);
    expect(loading).toContain('<div class="ui-navigator-loading">');
    expect(loading).toContain('role="status"');
    expect(loading).toContain('aria-label="Loading Signals"');
    expect(loading).not.toContain('ui-navigator-list');

    const error = markup(<Navigator title="Signals" error="Failed to load." />);
    expect(error).toContain('role="alert"');
    expect(error).toContain('Failed to load.');
    expect(error).not.toContain('ui-navigator-list');

    expect(markup(<Navigator title="Signals" items={[]} />)).toContain('Nothing here yet.');
    expect(markup(<Navigator title="Signals" empty="No signals match." />)).toContain(
      'No signals match.',
    );
  });

  it('renders groups, list label, variants and className', () => {
    const html = markup(
      <Navigator
        title="ML Engine"
        listLabel="Run index"
        mono
        density="compact"
        className="ml-nav"
        groups={[
          {
            id: 'runs',
            label: 'Runs',
            meta: 12,
            items: [{ id: 'r1', label: 'run-1', onSelect: () => {} }],
          },
          { id: 'more', items: [{ id: 'r2', label: 'run-2' }] },
        ]}
      />,
    );

    expect(html).toContain('class="section-navigator ui-navigator ml-nav"');
    expect(html).toContain('<nav class="ui-navigator-list" aria-label="Run index">');
    expect(html).toContain(
      '<div class="ui-navigator-group-label"><span>Runs</span><span class="ui-navigator-group-meta">12</span></div>',
    );
    expect((html.match(/ui-navigator-group"/g) ?? []).length).toBe(2);
    expect((html.match(/ui-navigator-group-label/g) ?? []).length).toBe(1);
    expect(html).toContain(
      '<button type="button" class="ui-navigator-row is-leaf is-root" style="--ui-navigator-depth:0">',
    );
  });

  it('renders glyph, leading, detail, meta and title slots', () => {
    const html = markup(
      <Navigator
        title="Dashboards"
        items={[
          {
            id: 'x',
            label: 'Dash',
            to: '/dashboards/x',
            glyph: '01',
            leading: <i data-x="dot" />,
            detail: <span>sub</span>,
            meta: 'ready',
            title: 'tip',
          },
        ]}
      />,
    );

    expect(html).toContain('<span class="ui-navigator-glyph" aria-hidden="true">01</span>');
    expect(html).toContain('<span class="ui-navigator-leading"><i data-x="dot"></i></span>');
    expect(html).toContain('<span class="ui-navigator-detail"><span>sub</span></span>');
    expect(html).toContain('<span class="ui-navigator-meta">ready</span>');
    expect(html).toContain('title="tip"');
  });

  it('renders search, controls and footer only while expanded', () => {
    const props = {
      title: 'Signals',
      search: {
        id: 'signal-search',
        label: 'Search signals',
        placeholder: 'Search signals',
        value: '',
        onChange: () => {},
      },
      controls: <b>ctl</b>,
      footer: <i data-x="foot" />,
      items: [{ id: 'a', label: 'a', to: '/signals/a' }],
    };

    const expanded = markup(<Navigator {...props} collapsed={false} />);
    expect(expanded).toContain('class="navigator-search"');
    expect(expanded).toContain('signal-search');
    expect(expanded).toContain('<div class="controls"><b>ctl</b></div>');
    expect(expanded).toContain('data-x="foot"');

    const collapsed = markup(<Navigator {...props} collapsed />);
    expect(collapsed).toContain('class="section-navigator collapsed ui-navigator"');
    expect(collapsed).toContain('Expand Signals navigation');
    expect(collapsed).not.toContain('navigator-search');
    expect(collapsed).not.toContain('ctl');
    expect(collapsed).not.toContain('data-x="foot"');
    expect(collapsed).not.toContain('ui-navigator-list');
  });
});

// --------------------------------------------------------------------------- #
// Interaction
// --------------------------------------------------------------------------- #

describe('Navigator interaction', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    Reflect.deleteProperty(window, 'matchMedia');
  });

  function render(ui: ReactNode, path = '/signals') {
    act(() => {
      root.render(
        <MemoryRouter initialPath={path}>
          <LocationProbe />
          {ui}
        </MemoryRouter>,
      );
    });
  }

  function location(): string {
    return container.querySelector('[data-testid="location"]')?.textContent ?? '';
  }

  function hover(element: Element | null) {
    if (!element) throw new Error('element not found');
    act(() => {
      element.dispatchEvent(new MouseEvent('pointerover', { bubbles: true }));
    });
  }

  function stubLabelWidth(scrollWidth: number) {
    const proto = HTMLElement.prototype;
    vi.spyOn(proto, 'scrollWidth', 'get').mockImplementation(function (this: HTMLElement) {
      return this.classList.contains('ui-navigator-label') ? scrollWidth : 0;
    });
    vi.spyOn(proto, 'clientWidth', 'get').mockReturnValue(100);
  }

  it('shows a popout with the full text only for truncated rows', () => {
    vi.useFakeTimers();
    try {
      stubLabelWidth(240);
      render(
        <Navigator
          title="Strategies"
          items={[
            {
              id: 'long',
              label: 'macro_yield-curve-long-flat',
              to: '/strategies/long',
              tag: { label: 'supported', tone: 'success' },
            },
          ]}
        />,
      );
      hover(container.querySelector('.ui-navigator-row'));
      expect(document.querySelector('.ui-navigator-popout')).toBeNull();
      act(() => vi.advanceTimersByTime(400));
      const popout = document.querySelector('.ui-navigator-popout');
      expect(popout?.getAttribute('aria-hidden')).toBe('true');
      expect(popout?.textContent).toContain('macro_yield-curve-long-flat');
      expect(popout?.textContent).toContain('supported');

      act(() => {
        container
          .querySelector('.ui-navigator-list')
          ?.dispatchEvent(new MouseEvent('pointerout', { bubbles: true }));
      });
      act(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })));
      expect(document.querySelector('.ui-navigator-popout')).toBeNull();
    } finally {
      vi.useRealTimers();
      vi.restoreAllMocks();
    }
  });

  it('never shows a popout for rows that fit', () => {
    vi.useFakeTimers();
    try {
      stubLabelWidth(80);
      render(<Navigator title="Strategies" items={[{ id: 'a', label: 'family-a', to: '/a' }]} />);
      hover(container.querySelector('.ui-navigator-row'));
      act(() => vi.advanceTimersByTime(400));
      expect(document.querySelector('.ui-navigator-popout')).toBeNull();
    } finally {
      vi.useRealTimers();
      vi.restoreAllMocks();
    }
  });

  it('toggles a disclosure and opens its route', () => {
    const onToggle = vi.fn();
    render(
      <Navigator
        title="Signals"
        items={[{ id: 'family', label: 'family', to: '/signals/family', children: [], onToggle }]}
      />,
    );

    click(container.querySelector('.ui-navigator-row.is-disclosure'));
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(location()).toBe('/signals/family');

    click(container.querySelector('.ui-navigator-row.is-disclosure'));
    expect(onToggle).toHaveBeenCalledTimes(2);
    expect(location()).toBe('/signals/family');
  });

  it('activates leaf buttons through onSelect and marks the current one', () => {
    const onSelect = vi.fn();
    render(<Navigator title="Runs" items={[{ id: 'r', label: 'run', onSelect, current: true }]} />);

    const row = container.querySelector('.ui-navigator-row.is-leaf');
    expect(row?.getAttribute('aria-current')).toBe('true');
    click(row);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('starts collapsed on compact viewports and toggles via the collapse button', () => {
    stubMatchMedia(true);
    render(<Navigator title="Signals" items={[{ id: 'a', label: 'a', to: '/signals/a' }]} />);

    const aside = container.querySelector('aside');
    expect(aside?.classList.contains('collapsed')).toBe(true);
    expect(container.querySelector('.ui-navigator-list')).toBeNull();

    click(container.querySelector('[aria-label="Expand Signals navigation"]'));
    expect(aside?.classList.contains('collapsed')).toBe(false);
    expect(container.querySelector('.ui-navigator-list')).not.toBeNull();
    expect(container.querySelector('[aria-label="Collapse Signals navigation"]')).not.toBeNull();
  });

  it('honours controlled collapse and reports changes', () => {
    stubMatchMedia(true);
    const onCollapsedChange = vi.fn();
    render(
      <Navigator
        title="Signals"
        collapsed={false}
        onCollapsedChange={onCollapsedChange}
        items={[{ id: 'a', label: 'a', to: '/signals/a' }]}
      />,
    );

    const aside = container.querySelector('aside');
    expect(aside?.classList.contains('collapsed')).toBe(false);
    click(container.querySelector('[aria-label="Collapse Signals navigation"]'));
    expect(onCollapsedChange).toHaveBeenCalledWith(true);
    expect(aside?.classList.contains('collapsed')).toBe(false);
  });

  it('collapses after a leaf selection on compact viewports unless disabled', () => {
    stubMatchMedia(true);
    const onCollapsedChange = vi.fn();
    render(
      <Navigator
        title="Signals"
        collapsed={false}
        onCollapsedChange={onCollapsedChange}
        items={[{ id: 'a', label: 'a', to: '/signals/a' }]}
      />,
    );
    click(container.querySelector('.ui-navigator-row.is-leaf'));
    expect(onCollapsedChange).toHaveBeenCalledWith(true);
    expect(location()).toBe('/signals/a');

    onCollapsedChange.mockClear();
    render(
      <Navigator
        title="Signals"
        collapsed={false}
        collapseOnSelect={false}
        onCollapsedChange={onCollapsedChange}
        items={[{ id: 'a', label: 'a', to: '/signals/a' }]}
      />,
    );
    click(container.querySelector('.ui-navigator-row.is-leaf'));
    expect(onCollapsedChange).not.toHaveBeenCalled();

    stubMatchMedia(false);
    render(
      <Navigator
        title="Signals"
        collapsed={false}
        onCollapsedChange={onCollapsedChange}
        items={[{ id: 'a', label: 'a', to: '/signals/a' }]}
      />,
    );
    click(container.querySelector('.ui-navigator-row.is-leaf'));
    expect(onCollapsedChange).not.toHaveBeenCalled();
  });
});

// --------------------------------------------------------------------------- #
// Row actions and header slot
// --------------------------------------------------------------------------- #

describe('Navigator row actions', () => {
  it('renders a pressed leaf row with trailing actions', () => {
    const html = markup(
      <Navigator
        title="Features"
        items={[
          {
            id: 'close',
            label: 'close',
            pressed: true,
            onSelect: () => {},
            actions: (
              <Button variant="nav" aria-label="x">
                R
              </Button>
            ),
          },
        ]}
      />,
    );
    const host = document.createElement('div');
    host.innerHTML = html;
    const item = host.querySelector('li.ui-navigator-item.has-actions');
    expect(item).not.toBeNull();
    expect(item?.firstElementChild?.classList.contains('ui-navigator-row')).toBe(true);
    expect(item?.firstElementChild?.getAttribute('aria-pressed')).toBe('true');
    const actions = item?.lastElementChild;
    expect(actions?.classList.contains('ui-navigator-actions')).toBe(true);
    expect(actions?.querySelector('button[aria-label="x"]')).not.toBeNull();
  });

  it('renders headerActions when no search is given', () => {
    const html = markup(
      <Navigator title="Features" headerActions={<span data-testid="count">12</span>} items={[]} />,
    );
    expect(html).toContain('data-testid="count"');
  });
});
