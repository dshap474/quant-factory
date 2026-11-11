/**
 * Grouping, filtering, axis-assignment, and collapse tests for the chart feature rail.
 *
 * USAGE:
 *   pnpm test -- src/lib/components/charts/DatasetChartFeatureRail.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetFeatureFamily } from '@/lib/api/catalog';

import {
  DatasetChartFeatureRail,
  type DatasetChartFeatureRailProps,
  filterMetrics,
  groupMetricsByFamily,
} from './DatasetChartFeatureRail';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const METRICS = ['close', 'ta_rsi_14', 'funding_rate', 'volume_usd', 'mystery'];
const FAMILIES: DatasetFeatureFamily[] = [
  { id: 'ta', label: 'TA', count: 1 },
  { id: 'carry_funding', label: 'Carry / funding', count: 1 },
  { id: 'flow_liquidity', label: 'Flow / liquidity', count: 1 },
  { id: 'price_volatility', label: 'Price / volatility', count: 1 },
];
const METRIC_FAMILIES: Record<string, string> = {
  close: 'price_volatility',
  ta_rsi_14: 'ta',
  funding_rate: 'carry_funding',
  volume_usd: 'flow_liquidity',
};

function baseProps(overrides: Partial<DatasetChartFeatureRailProps> = {}) {
  return {
    metrics: METRICS,
    families: FAMILIES,
    metricFamilies: METRIC_FAMILIES,
    cells: [
      { id: 'cell-1', label: 'Chart 1', leftMetric: 'close', rightMetric: null },
      { id: 'cell-2', label: 'Chart 2', leftMetric: null, rightMetric: 'volume_usd' },
    ],
    targetCellId: 'cell-1',
    collapsed: false,
    onTargetCellChange: vi.fn(),
    onToggleCollapse: vi.fn(),
    onAssign: vi.fn(),
    ...overrides,
  } satisfies DatasetChartFeatureRailProps;
}

function click(element: Element | null | undefined) {
  if (!element) throw new Error('missing element');
  act(() => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
}

// --------------------------------------------------------------------------- #
// Pure helpers
// --------------------------------------------------------------------------- #

describe('groupMetricsByFamily', () => {
  it('keeps the API family order and parks unknown metrics under Other', () => {
    const groups = groupMetricsByFamily(METRICS, FAMILIES, METRIC_FAMILIES);
    expect(groups.map((group) => group.id)).toEqual([
      'ta',
      'carry_funding',
      'flow_liquidity',
      'price_volatility',
      'other',
    ]);
    expect(groups.at(-1)).toEqual({ id: 'other', label: 'Other', metrics: ['mystery'] });
  });

  it('drops families that no visible metric belongs to', () => {
    const groups = groupMetricsByFamily(['close'], FAMILIES, METRIC_FAMILIES);
    expect(groups).toEqual([
      { id: 'price_volatility', label: 'Price / volatility', metrics: ['close'] },
    ]);
  });
});

describe('filterMetrics', () => {
  it('matches case-insensitive substrings and passes everything through for blank queries', () => {
    expect(filterMetrics(METRICS, ' RSI ')).toEqual(['ta_rsi_14']);
    expect(filterMetrics(METRICS, '')).toBe(METRICS);
  });
});

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

describe('DatasetChartFeatureRail', () => {
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

  function render(props: DatasetChartFeatureRailProps) {
    act(() => {
      root.render(
        <MemoryRouter>
          <DatasetChartFeatureRail {...props} />
        </MemoryRouter>,
      );
    });
  }

  function rows() {
    return [...container.querySelectorAll<HTMLElement>('button.ui-navigator-row')];
  }

  function rowFor(metric: string) {
    return rows().find((row) => row.textContent?.trim() === metric);
  }

  it('lists every metric under its family header and marks the target cell axes', () => {
    render(baseProps());
    const headers = [
      ...container.querySelectorAll('.ui-navigator-group-label > span:first-child'),
    ].map((node) => node.textContent);
    expect(headers).toEqual([
      'TA',
      'Carry / funding',
      'Flow / liquidity',
      'Price / volatility',
      'Other',
    ]);
    expect(rows()).toHaveLength(METRICS.length);

    const close = rowFor('close');
    expect(close?.getAttribute('aria-current')).toBe('true');
    expect(close?.getAttribute('aria-pressed')).toBe('true');
    expect(close?.parentElement?.classList.contains('has-actions')).toBe(true);
    // volume_usd sits on chart 2, which is not the target: it must read as unplotted here.
    const volume = rowFor('volume_usd');
    expect(volume?.getAttribute('aria-current')).toBeNull();
    expect(volume?.getAttribute('aria-pressed')).toBe('false');
  });

  it('assigns and clears the target cell axes through onAssign', () => {
    const onAssign = vi.fn();
    render(baseProps({ onAssign }));

    click(rowFor('ta_rsi_14'));
    expect(onAssign).toHaveBeenLastCalledWith('cell-1', 'leftMetric', 'ta_rsi_14');

    click(container.querySelector('button[aria-label="funding_rate on Chart 1 right axis"]'));
    expect(onAssign).toHaveBeenLastCalledWith('cell-1', 'rightMetric', 'funding_rate');

    // Clicking the metric already on the left axis removes it.
    click(rowFor('close'));
    expect(onAssign).toHaveBeenLastCalledWith('cell-1', 'leftMetric', null);
  });

  it('filters the list by the search box', () => {
    render(baseProps());
    const input = container.querySelector<HTMLInputElement>('input[type="search"]');
    if (!input) throw new Error('missing search input');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(input, 'fund');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(rows().map((row) => row.textContent?.trim())).toEqual(['funding_rate']);
  });

  it('collapses to the navigator strip and reports the toggle', () => {
    const onToggleCollapse = vi.fn();
    render(baseProps({ collapsed: true, onToggleCollapse }));
    const rail = container.querySelector('aside.section-navigator');
    expect(rail?.classList.contains('collapsed')).toBe(true);
    expect(rail?.classList.contains('is-strip')).toBe(true);
    expect(container.querySelector('input[type="search"]')).toBeNull();
    expect(container.querySelector('.ui-navigator-row')).toBeNull();

    click(container.querySelector('button[aria-label="Expand Features navigation"]'));
    expect(onToggleCollapse).toHaveBeenCalledTimes(1);
  });
});
