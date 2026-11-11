/**
 * Legend hover emphasis: the row class helper mutes every row but the hovered one,
 * and ChartLegendItem renders the marker, label, and hover callbacks.
 *
 * USAGE:
 *   pnpm test -- chart-legend-item.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ChartLegendItem, legendItemClass } from '../../src/charts/components/ChartLegend';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('legendItemClass', () => {
  it('leaves every row unmuted when nothing is hovered', () => {
    expect(legendItemClass('ic', null)).toBe('chart-legend-item');
  });

  it('keeps the hovered row unmuted', () => {
    expect(legendItemClass('ic', 'ic')).toBe('chart-legend-item');
  });

  it('mutes the other rows', () => {
    expect(legendItemClass('SPY', 'ic')).toBe('chart-legend-item is-muted');
  });
});

describe('ChartLegendItem', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('renders a coloured marker and label and reports hover', async () => {
    const onHover = vi.fn();
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <ChartLegendItem
          seriesId="decision"
          swatch="var(--qf-chart-positive)"
          hoveredSeries="signal"
          onHoveredSeriesChange={onHover}
        >
          Decision
        </ChartLegendItem>,
      ),
    );
    const row = host.firstElementChild as HTMLElement;
    expect(row.className).toBe('chart-legend-item is-muted');
    const marker = row.querySelector<HTMLElement>('.chart-legend-marker.solid');
    expect(marker?.style.getPropertyValue('--legend-color')).toBe('var(--qf-chart-positive)');
    expect(row.textContent).toBe('Decision');
    await act(async () => {
      row.dispatchEvent(new PointerEvent('pointerover', { bubbles: true }));
    });
    await act(async () => {
      row.dispatchEvent(new PointerEvent('pointerout', { bubbles: true }));
    });
    expect(onHover.mock.calls).toEqual([['decision'], [null]]);
    await act(async () => root.unmount());
  });
});
