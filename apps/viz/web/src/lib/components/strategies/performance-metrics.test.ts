/** Published grid conventions must survive presentation enrichment.
 * USAGE: pnpm exec vitest run performance-metrics
 */

// --------------------------------------------------------------------------- #
// Fixtures and regression checks
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';
import type { ResearchGrid } from '@/lib/api/strategies';
import { buildPerformanceMatrixRows, sortColumnsBySortino } from './performance-metrics';

const grid: ResearchGrid = {
  grid_schema_version: 1,
  selected_config_id: 'a',
  control_config_id: 'a',
  dimensions: [],
  summary: { path: 'summary', row_count: 1, columns: [] },
  series: {
    path: 'series',
    row_count: 2,
    config_id_column: 'id',
    date_column: 'date',
    return_column: 'return',
  },
  columns: [],
  metrics: [
    { key: 'cagr', label: 'CAGR', format: 'percent', higher_is_better: true },
    { key: 'sharpe_365', label: 'Sharpe365', format: 'number', higher_is_better: true },
    { key: 'max_drawdown', label: 'DD', format: 'percent', higher_is_better: true },
    { key: 'fee_dollars', label: 'Fees', format: 'number', higher_is_better: false },
  ],
  data: [
    {
      config_id: 'a',
      rank: 1,
      is_selected: true,
      is_control: true,
      cagr: 0.3,
      sharpe_365: 1.7,
      max_drawdown: -0.2,
      fee_dollars: 42,
    },
  ],
};

describe('performance matrix', () => {
  it('keeps published values, derives Calmar from the published pair, and shows missing supplements honestly', () => {
    const rows = buildPerformanceMatrixRows(grid, {});
    expect(rows.find((row) => row.key === 'sharpe')?.values.a).toBe(1.7);
    expect(rows.find((row) => row.key === 'calmar')?.values.a).toBeCloseTo(1.5);
    expect(rows.find((row) => row.key === 'sortino')?.values.a).toBeUndefined();
    expect(rows.find((row) => row.key === 'martin')?.values.a).toBeUndefined();
    expect(rows.find((row) => row.key === 'fee_dollars')?.format).toBe('money');
    expect([...new Set(rows.map((row) => row.group))]).toEqual([
      'Returns',
      'Risk-adjusted ratios',
      'Drawdowns & volatility',
      'Trading costs',
    ]);
  });
  it('shows all four ratios with Sortino first and preserves the API Martin value', () => {
    const rows = buildPerformanceMatrixRows(grid, {
      a: { martin: 2.25, sortino: 3.5 },
    });
    expect(
      rows.filter((row) => row.group === 'Risk-adjusted ratios').map((row) => row.key),
    ).toEqual(['sortino', 'sharpe', 'calmar', 'martin']);
    expect(rows.find((row) => row.key === 'martin')?.values.a).toBe(2.25);
  });
  it('ranks columns only by Sortino, with negative values ahead of missing and stable ties', () => {
    const ids = ['missing', 'negative', 'high', 'tie', 'zero', 'infinite'];
    const columns = ids.map((id) => ({ id, label: id }));
    const ordered = sortColumnsBySortino(columns, [
      {
        key: 'sortino',
        label: 'Sortino',
        format: 'number',
        values: {
          negative: -2,
          high: 3,
          tie: 3,
          zero: 0,
          infinite: Number.POSITIVE_INFINITY,
        },
      },
      { key: 'martin', label: 'Martin', format: 'number', values: { negative: 1_000 } },
    ]);
    expect(ordered.map((column) => column.id)).toEqual([
      'high',
      'tie',
      'zero',
      'negative',
      'missing',
      'infinite',
    ]);
    expect(columns.map((column) => column.id)).toEqual(ids);
  });
  it('leaves Calmar undefined without a drawdown', () => {
    const rows = buildPerformanceMatrixRows(
      { ...grid, data: [{ ...grid.data[0], max_drawdown: 0 }] },
      {},
    );
    expect(rows.find((row) => row.key === 'calmar')?.values.a).toBeNull();
  });
});
