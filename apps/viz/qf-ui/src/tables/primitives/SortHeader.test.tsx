/**
 * Structural and click tests for the shared SortHeader.
 *
 * USAGE:
 *   pnpm exec vitest run src/tables/primitives/SortHeader.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SortState } from '../core/sort';
import { SortHeader } from './SortHeader';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function header(sort: SortState | null, onSortChange: (next: SortState) => void, extra = {}) {
  return (
    <table>
      <thead>
        <tr>
          <SortHeader column="close" sort={sort} onSortChange={onSortChange} {...extra}>
            close
          </SortHeader>
        </tr>
      </thead>
    </table>
  );
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('SortHeader', () => {
  it('renders an inactive header with aria-sort none and the neutral glyph', () => {
    const markup = renderToStaticMarkup(header(null, () => undefined));
    expect(markup).toContain('aria-sort="none"');
    expect(markup).toContain('class="ui-sort-button"');
    expect(markup).toContain('↕');
  });

  it('marks the active column with its direction and forwards th props', () => {
    const markup = renderToStaticMarkup(
      header({ column: 'close', direction: 'desc' }, () => undefined, { className: 'extra' }),
    );
    expect(markup).toContain('aria-sort="descending"');
    expect(markup).toContain('class="ui-sort-button is-active"');
    expect(markup).toContain('↓');
    expect(markup).toContain('extra');
  });

  describe('click', () => {
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
    });

    it('emits nextSort from the current state using the initial direction', () => {
      const onSortChange = vi.fn();
      act(() => {
        root.render(header(null, onSortChange, { initialDirection: 'desc' }));
      });
      const button = container.querySelector('button');
      if (!button) throw new Error('missing button');
      act(() => {
        button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      });
      expect(onSortChange).toHaveBeenCalledWith({ column: 'close', direction: 'desc' });
    });
  });
});
