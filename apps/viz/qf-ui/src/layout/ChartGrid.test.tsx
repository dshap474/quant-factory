/**
 * Class/style wiring and cell interaction tests for the shared ChartGrid.
 *
 * USAGE:
 *   pnpm exec vitest run src/layout/ChartGrid.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Button } from '../primitives/Button';
import { ChartGrid, ChartGridCell } from './ChartGrid';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ChartGrid', () => {
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

  it('renders auto-fit gapped columns with no inline style by default', () => {
    act(() => {
      root.render(
        <ChartGrid>
          <ChartGridCell>x</ChartGridCell>
        </ChartGrid>,
      );
    });
    const grid = container.querySelector('.ui-chart-grid') as HTMLElement;
    expect(grid.className).toBe('ui-chart-grid is-gapped');
    expect(grid.hasAttribute('style')).toBe(false);
  });

  it('applies the hairline, fixed-column and fill modifiers', () => {
    act(() => {
      root.render(
        <ChartGrid columns={2} variant="hairline" fill>
          <ChartGridCell>x</ChartGridCell>
        </ChartGrid>,
      );
    });
    const grid = container.querySelector('.ui-chart-grid') as HTMLElement;
    expect(grid.className).toContain('is-hairline');
    expect(grid.className).toContain('is-fixed');
    expect(grid.className).toContain('is-fill');
    expect(grid.getAttribute('style')).toContain('--ui-chart-grid-columns: 2');

    act(() => {
      root.render(
        <ChartGrid minColumnWidth="20rem">
          <ChartGridCell>x</ChartGridCell>
        </ChartGrid>,
      );
    });
    const auto = container.querySelector('.ui-chart-grid') as HTMLElement;
    expect(auto.className).not.toContain('is-fixed');
    expect(auto.getAttribute('style')).toContain('--ui-chart-grid-min: 20rem');
  });

  it('marks the target cell and forwards captured focus', () => {
    const spy = vi.fn();
    act(() => {
      root.render(
        <ChartGrid>
          <ChartGridCell target onFocusCapture={spy}>
            <Button>focus me</Button>
          </ChartGridCell>
        </ChartGrid>,
      );
    });
    const cell = container.querySelector('.ui-chart-grid-cell') as HTMLElement;
    expect(cell.className).toBe('ui-chart-grid-cell is-target');

    const button = container.querySelector('button') as HTMLButtonElement;
    act(() => button.focus());
    expect(spy).toHaveBeenCalled();
  });
});
