/**
 * Structural and interaction tests for the shared Pagination bar.
 *
 * USAGE:
 *   pnpm exec vitest run src/data/Pagination.test.tsx
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

import { Pagination } from './Pagination';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  act(() => {
    setter?.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

function pressEnter(target: Element) {
  act(() => {
    target.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }),
    );
  });
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Pagination', () => {
  it('renders the label and disables Previous on the first page', () => {
    const markup = renderToStaticMarkup(
      <Pagination
        page={1}
        pageCount={3}
        onPageChange={() => undefined}
        label="rows 1–50 of 120 · page 1/3"
      />,
    );
    expect(markup).toContain('<nav aria-label="Pagination" class="ui-pagination">');
    expect(markup).toContain('class="ui-pagination-label">rows 1–50 of 120 · page 1/3</span>');
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*>Previous<\/button>/);
    expect(markup).toMatch(/<button(?![^>]*disabled)[^>]*>Next<\/button>/);
    expect(markup).not.toContain('Go to page');
    expect(markup).not.toContain('>Rows<');
    expect(
      renderToStaticMarkup(
        <Pagination band page={1} pageCount={2} onPageChange={() => undefined} />,
      ),
    ).toContain('class="ui-pagination ui-pagination-band"');
  });

  it('disables Next on the last page and everything while disabled', () => {
    expect(
      renderToStaticMarkup(<Pagination page={3} pageCount={3} onPageChange={() => undefined} />),
    ).toMatch(/<button[^>]*disabled=""[^>]*>Next<\/button>/);
    const markup = renderToStaticMarkup(
      <Pagination page={2} pageCount={3} onPageChange={() => undefined} disabled />,
    );
    expect(markup.match(/disabled=""/g)).toHaveLength(2);
  });

  it('renders the jump field and page-size select when configured', () => {
    const markup = renderToStaticMarkup(
      <Pagination
        page={2}
        pageCount={5}
        onPageChange={() => undefined}
        jump
        pageSize={50}
        pageSizeOptions={[25, 50]}
        onPageSizeChange={() => undefined}
      />,
    );
    expect(markup).toContain('Go to page');
    expect(markup).toContain('class="ui-input ui-pagination-jump"');
    expect(markup).toContain('placeholder="2"');
    expect(markup).toContain('>Rows<');
  });

  describe('interaction', () => {
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

    function button(name: string): HTMLButtonElement {
      const match = Array.from(container.querySelectorAll('button')).find(
        (node) => node.textContent === name,
      );
      if (!match) throw new Error(`missing button ${name}`);
      return match;
    }

    it('steps pages and jumps only to valid targets', () => {
      const onPageChange = vi.fn();
      act(() => {
        root.render(<Pagination page={2} pageCount={5} onPageChange={onPageChange} jump />);
      });

      act(() => {
        button('Next').dispatchEvent(new MouseEvent('click', { bubbles: true }));
      });
      expect(onPageChange).toHaveBeenLastCalledWith(3);

      act(() => {
        button('Previous').dispatchEvent(new MouseEvent('click', { bubbles: true }));
      });
      expect(onPageChange).toHaveBeenLastCalledWith(1);

      const input = container.querySelector('input');
      if (!input) throw new Error('missing input');
      setInputValue(input, '9');
      pressEnter(input);
      expect(onPageChange).toHaveBeenCalledTimes(2);

      setInputValue(input, '4');
      pressEnter(input);
      expect(onPageChange).toHaveBeenLastCalledWith(4);
      expect(input.value).toBe('');
    });
  });
});
