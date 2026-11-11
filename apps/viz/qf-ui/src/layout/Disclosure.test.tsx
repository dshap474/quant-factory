/**
 * Structural and toggle tests for the shared Disclosure primitive.
 *
 * USAGE:
 *   pnpm exec vitest run src/layout/Disclosure.test.tsx
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

import { Disclosure } from './Disclosure';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Disclosure', () => {
  it('renders a closed native details with the shared summary row', () => {
    const markup = renderToStaticMarkup(<Disclosure summary="config.json">body</Disclosure>);

    expect(markup).toContain('<details class="ui-disclosure">');
    expect(markup).not.toContain(' open');
    expect(markup).toContain('<summary class="ui-disclosure-summary">');
    expect(markup).toContain('ui-disclosure-chevron');
    expect(markup).toContain('<span class="ui-disclosure-title">config.json</span>');
    expect(markup).not.toContain('ui-disclosure-meta');
    expect(markup).toContain('<div class="ui-disclosure-content">body</div>');
  });

  it('opens by default, renders meta, applies the row variant, and merges className', () => {
    const markup = renderToStaticMarkup(
      <Disclosure summary="Structure" meta="12 markers" variant="row" defaultOpen className="mt-2">
        body
      </Disclosure>,
    );

    expect(markup).toContain('<details class="ui-disclosure is-row mt-2" open="">');
    expect(markup).toContain('<span class="ui-disclosure-meta">12 markers</span>');
  });

  it('mounts lazy content only while open', () => {
    expect(
      renderToStaticMarkup(
        <Disclosure summary="Advanced" lazy>
          body
        </Disclosure>,
      ),
    ).not.toContain('ui-disclosure-content');
    expect(
      renderToStaticMarkup(
        <Disclosure summary="Advanced" lazy open>
          body
        </Disclosure>,
      ),
    ).toContain('<div class="ui-disclosure-content">body</div>');
  });

  describe('toggle', () => {
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

    it('reports the native open state and mounts lazy content', () => {
      const onToggle = vi.fn();
      act(() => {
        root.render(
          <Disclosure summary="Advanced" lazy onToggle={onToggle}>
            body
          </Disclosure>,
        );
      });
      const details = container.querySelector('details');
      if (!details) throw new Error('missing details');
      expect(container.querySelector('.ui-disclosure-content')).toBeNull();

      act(() => {
        details.open = true;
        details.dispatchEvent(new Event('toggle'));
      });

      expect(onToggle).toHaveBeenCalledWith(true);
      expect(container.querySelector('.ui-disclosure-content')?.textContent).toBe('body');
    });
  });
});
