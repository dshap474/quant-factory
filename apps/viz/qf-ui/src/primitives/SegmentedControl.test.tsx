/**
 * Structural and keyboard-model tests for the shared segmented-control primitive.
 *
 * USAGE:
 *   pnpm test -- src/primitives/SegmentedControl.test.tsx
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

import { SegmentedControl } from './SegmentedControl';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function pressKey(target: Element, key: string) {
  act(() => {
    target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
  });
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('SegmentedControl', () => {
  it('renders one accessible shared-button group with the selected value', () => {
    const markup = renderToStaticMarkup(
      <SegmentedControl
        ariaLabel="Profile view"
        options={[
          { value: 'session', label: 'Session' },
          { value: 'prior', label: 'Prior' },
        ]}
        value="session"
        onValueChange={() => undefined}
      />,
    );

    expect(markup).toContain('class="ui-segmented-control"');
    expect(markup).toContain('role="radiogroup"');
    expect(markup).toContain('aria-label="Profile view"');
    expect(markup).toContain('class="ui-button ui-segmented-control-item"');
    expect(markup).toContain('aria-checked="true"');
    expect(markup).toContain('aria-checked="false"');
    expect(markup).not.toContain('<fieldset');
    expect(markup).not.toContain('is-sm');
  });

  it('tightens the group with size="sm"', () => {
    const markup = renderToStaticMarkup(
      <SegmentedControl
        ariaLabel="Profile view"
        size="sm"
        options={[{ value: 'session', label: 'Session' }]}
        value="session"
        onValueChange={() => undefined}
      />,
    );

    expect(markup).toContain('class="ui-segmented-control ui-size-sm is-sm"');
  });

  it('maps size="lg" to the scale class without tightening the type', () => {
    const markup = renderToStaticMarkup(
      <SegmentedControl
        ariaLabel="Profile view"
        size="lg"
        options={[{ value: 'session', label: 'Session' }]}
        value="session"
        onValueChange={() => undefined}
      />,
    );

    expect(markup).toContain('class="ui-segmented-control ui-size-lg"');
  });

  it('gives only the selected radio a tab stop', () => {
    const markup = renderToStaticMarkup(
      <SegmentedControl
        ariaLabel="Profile view"
        options={[
          { value: 'session', label: 'Session' },
          { value: 'prior', label: 'Prior' },
          { value: 'all', label: 'All' },
        ]}
        value="prior"
        onValueChange={() => undefined}
      />,
    );

    expect(markup.match(/tabindex="0"/g)).toHaveLength(1);
    expect(markup.match(/tabindex="-1"/g)).toHaveLength(2);
  });

  describe('keyboard model', () => {
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

    function renderControl(value: string, onValueChange: (next: string) => void) {
      act(() => {
        root.render(
          <SegmentedControl
            ariaLabel="Profile view"
            options={[
              { value: 'session', label: 'Session' },
              { value: 'prior', label: 'Prior', disabled: true },
              { value: 'all', label: 'All' },
            ]}
            value={value}
            onValueChange={onValueChange}
          />,
        );
      });
    }

    function radio(name: string): HTMLButtonElement {
      const match = Array.from(
        container.querySelectorAll<HTMLButtonElement>('[role="radio"]'),
      ).find((node) => node.textContent === name);
      if (!match) throw new Error(`missing radio ${name}`);
      return match;
    }

    it('selects and focuses the next enabled radio on ArrowRight, skipping disabled', () => {
      const onValueChange = vi.fn();
      renderControl('session', onValueChange);

      pressKey(radio('Session'), 'ArrowRight');

      expect(onValueChange).toHaveBeenCalledWith('all');
      expect(document.activeElement).toBe(radio('All'));
    });

    it('wraps to the last enabled radio on ArrowLeft from the first', () => {
      const onValueChange = vi.fn();
      renderControl('session', onValueChange);

      pressKey(radio('Session'), 'ArrowLeft');

      expect(onValueChange).toHaveBeenCalledWith('all');
      expect(document.activeElement).toBe(radio('All'));
    });

    it('jumps to the first and last enabled radios on Home and End', () => {
      const onValueChange = vi.fn();
      renderControl('all', onValueChange);

      pressKey(radio('All'), 'Home');
      expect(onValueChange).toHaveBeenLastCalledWith('session');

      pressKey(radio('Session'), 'End');
      expect(onValueChange).toHaveBeenLastCalledWith('all');
    });
  });
});
