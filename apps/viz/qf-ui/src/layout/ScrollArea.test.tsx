/**
 * Structural tests for the shared ScrollArea primitive, plus the overflow-edge
 * attributes the fade mask keys off.
 *
 * USAGE:
 *   pnpm exec vitest run src/layout/ScrollArea.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ScrollArea, trackScrollEdges } from './ScrollArea';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ScrollArea', () => {
  it('defaults to a vertical region without a landmark role', () => {
    expect(renderToStaticMarkup(<ScrollArea>rows</ScrollArea>)).toBe(
      '<div class="ui-scroll-area is-y">rows</div>',
    );
  });

  it.each([
    ['x', 'is-x'],
    ['both', 'is-both'],
  ] as const)('renders axis %s as %s', (axis, className) => {
    expect(renderToStaticMarkup(<ScrollArea axis={axis}>x</ScrollArea>)).toContain(
      `class="ui-scroll-area ${className}"`,
    );
  });

  it('adds fill, merges className, names the region, and forwards attributes', () => {
    const markup = renderToStaticMarkup(
      <ScrollArea
        axis="both"
        fill
        label="Scrollable data table"
        className="data-table-scroll"
        aria-busy
      >
        x
      </ScrollArea>,
    );
    expect(markup).toContain('class="ui-scroll-area is-both is-fill data-table-scroll"');
    expect(markup).toContain('role="region"');
    expect(markup).toContain('aria-label="Scrollable data table"');
    expect(markup).toContain('aria-busy="true"');
  });

  it('bounds its height through maxHeight', () => {
    expect(renderToStaticMarkup(<ScrollArea maxHeight="32rem">x</ScrollArea>)).toContain(
      'style="max-height:32rem"',
    );
  });

  it('publishes overflow edges and flips them on scroll', () => {
    // jsdom reports every scroll metric as 0, so the geometry is stubbed.
    const node = document.createElement('div');
    const metric = (name: string, value: number) =>
      Object.defineProperty(node, name, { configurable: true, value });
    metric('scrollWidth', 1200);
    metric('clientWidth', 600);
    metric('scrollHeight', 400);
    metric('clientHeight', 400);

    const detach = trackScrollEdges(node);
    expect(node.dataset.edgeStart).toBe('');
    expect(node.dataset.edgeEnd).toBe('x');
    expect(node.dataset.edgeTop).toBe('');
    expect(node.dataset.edgeBottom).toBe('');

    node.scrollLeft = 600;
    node.dispatchEvent(new Event('scroll'));
    expect(node.dataset.edgeStart).toBe('x');
    expect(node.dataset.edgeEnd).toBe('');

    detach();
    node.scrollLeft = 0;
    node.dispatchEvent(new Event('scroll'));
    expect(node.dataset.edgeStart).toBe('x');
  });
});
