/**
 * Structural tests for the shared Button primitive's size and icon contract.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/Button.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { Button } from './Button';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Button', () => {
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

  it('marks an icon button as a square at the requested size step', () => {
    act(() => {
      root.render(
        <Button variant="control" size="sm" icon aria-label="Copy">
          <svg aria-hidden="true" />
        </Button>,
      );
    });

    const button = container.querySelector('button');
    if (!button) throw new Error('missing button');
    expect(button.className).toBe('ui-button ui-button-control ui-size-sm ui-icon-only');
    expect(button.getAttribute('style')).toBeNull();
  });

  it('emits a size class for every step and none for the md default', () => {
    for (const size of ['xs', 'sm', 'md', 'lg', 'xl'] as const) {
      act(() => {
        root.render(<Button size={size}>x</Button>);
      });
      expect(container.querySelector('button')?.className).toBe(`ui-button ui-size-${size}`);
    }
    act(() => {
      root.render(<Button icon aria-label="x" />);
    });
    expect(container.querySelector('button')?.className).toBe('ui-button ui-icon-only');
  });

  it('leaves a default button unmarked and typed as a button', () => {
    act(() => {
      root.render(<Button>Refresh</Button>);
    });

    const button = container.querySelector('button');
    if (!button) throw new Error('missing button');
    expect(button.className).toBe('ui-button');
    expect(button.getAttribute('type')).toBe('button');
  });

  it('renders the optional primary and destructive variants', () => {
    act(() => {
      root.render(<Button variant="primary">Save</Button>);
    });
    expect(container.querySelector('button')?.className).toBe('ui-button ui-button-primary');

    act(() => {
      root.render(<Button variant="destructive">Delete</Button>);
    });
    expect(container.querySelector('button')?.className).toBe('ui-button ui-button-destructive');
  });
});
