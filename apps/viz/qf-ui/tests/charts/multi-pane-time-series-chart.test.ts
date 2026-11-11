/**
 * Multi-pane chart row sizing and linked-pane geometry contracts.
 *
 * USAGE:
 *   pnpm test -- tests/charts/multi-pane-time-series-chart.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import {
  crosshairOffset,
  DEFAULT_PANE_GUTTER,
  dateAtOffset,
  leftInsetForLabelWidth,
  linkedPaneGrid,
  panePosition,
  showsSharedAxis,
} from '../../src/charts/components/MultiPaneContext';
import { buildMultiPaneRows } from '../../src/charts/components/MultiPaneTimeSeriesChart';
import { multiPaneAspectRatio, QF_CHART_ASPECT_RATIO } from '../../src/charts/core/geometry';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('buildMultiPaneRows', () => {
  it('shares unlinked rows by pane size', () => {
    expect(buildMultiPaneRows([undefined, 'study'])).toBe('minmax(0, 9fr) minmax(0, 3fr)');
    expect(buildMultiPaneRows(['main', 'main'], { controls: true })).toBe(
      'minmax(0, 9fr) minmax(0, 9fr) auto',
    );
  });

  it('keeps linked chrome fixed so the plots hold the size ratio', () => {
    // Top pane: label 32 + edge 12 + divider 1; bottom pane: label 32 + axis 26.
    expect(buildMultiPaneRows(['main', 'study'], { linked: true })).toBe(
      'calc(45px + (100% - 103px) * 0.75) calc(58px + (100% - 103px) * 0.25)',
    );
  });
});

// --------------------------------------------------------------------------- #
// Linked-pane geometry
// --------------------------------------------------------------------------- #

describe('linked pane geometry', () => {
  const gutter = { left: 64, right: 16 };

  it('positions panes so only the bottom one carries the shared axis', () => {
    expect([0, 1, 2].map((index) => panePosition(index, 3))).toEqual(['top', 'middle', 'bottom']);
    expect(panePosition(0, 1)).toBe('only');
    expect(showsSharedAxis('bottom')).toBe(true);
    expect(showsSharedAxis('only')).toBe(true);
    expect(showsSharedAxis('top')).toBe(false);
    expect(showsSharedAxis('middle')).toBe(false);
  });

  it('reserves axis height on the bottom pane and label height on every pane', () => {
    expect(linkedPaneGrid({ position: 'top', gutter, xDomain: null })).toEqual({
      top: 32,
      right: 16,
      bottom: 12,
      left: 64,
    });
    expect(linkedPaneGrid({ position: 'bottom', gutter, xDomain: null })).toEqual({
      top: 32,
      right: 16,
      bottom: 26,
      left: 64,
    });
  });

  it('tracks the crosshair only inside the shared plot area', () => {
    expect(crosshairOffset(100, 400, gutter)).toBe(100);
    expect(crosshairOffset(64, 400, gutter)).toBe(64);
    expect(crosshairOffset(384, 400, gutter)).toBe(384);
    expect(crosshairOffset(20, 400, gutter)).toBeNull();
    expect(crosshairOffset(390, 400, gutter)).toBeNull();
    expect(crosshairOffset(Number.NaN, 400, gutter)).toBeNull();
    expect(crosshairOffset(10, 60, gutter)).toBeNull();
  });

  it('maps a crosshair offset back to the time it sits over', () => {
    const domain: readonly [Date, Date] = [
      new Date('2026-01-01T00:00:00Z'),
      new Date('2026-01-03T00:00:00Z'),
    ];
    expect(dateAtOffset(64, 400, gutter, domain)?.toISOString()).toBe('2026-01-01T00:00:00.000Z');
    expect(dateAtOffset(224, 400, gutter, domain)?.toISOString()).toBe('2026-01-02T00:00:00.000Z');
    expect(dateAtOffset(384, 400, gutter, domain)?.toISOString()).toBe('2026-01-03T00:00:00.000Z');
    // Gutter pointers clamp to the domain ends instead of extrapolating past the plot.
    expect(dateAtOffset(10, 400, gutter, domain)?.toISOString()).toBe('2026-01-01T00:00:00.000Z');
    expect(dateAtOffset(Number.NaN, 400, gutter, domain)).toBeNull();
    expect(dateAtOffset(100, 60, gutter, domain)).toBeNull();
  });

  it('sizes the shared left gutter from the widest reported label', () => {
    expect(leftInsetForLabelWidth(0)).toBe(DEFAULT_PANE_GUTTER.left);
    expect(leftInsetForLabelWidth(Number.NaN)).toBe(DEFAULT_PANE_GUTTER.left);
    // Card inset (16), the label rounded up, then the label gap (8).
    expect(leftInsetForLabelWidth(40.2)).toBe(65);
    expect(leftInsetForLabelWidth(72)).toBe(96);
  });
});

// --------------------------------------------------------------------------- #
// Stack frame
// --------------------------------------------------------------------------- #

describe('multiPaneAspectRatio', () => {
  it('keeps one main pane on the shared chart frame', () => {
    expect(multiPaneAspectRatio(['main'])).toBe(QF_CHART_ASPECT_RATIO);
    expect(multiPaneAspectRatio([undefined])).toBe(QF_CHART_ASPECT_RATIO);
    expect(multiPaneAspectRatio([])).toBe(QF_CHART_ASPECT_RATIO);
  });

  it('adds a third of the main height per study and never grows taller than wide', () => {
    expect(multiPaneAspectRatio(['main', 'study'])).toBeCloseTo(4 / 3);
    expect(multiPaneAspectRatio(['main', 'study', 'study'])).toBeCloseTo(16 / 15);
    expect(multiPaneAspectRatio(['main', 'study', 'study', 'study'])).toBe(1);
    expect(multiPaneAspectRatio(['main', 'main'])).toBe(1);
  });
});
