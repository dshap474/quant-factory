/** Sortino ranking must not change the published selection. USAGE: pnpm vitest run OptimizerGridSurface. */

// --------------------------------------------------------------------------- #
// Controlled grid and chart boundary
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { researchGridSchema } from '@/lib/api/strategies';
import { OptimizerGridSurface } from './OptimizerGridSurface';

const captured = vi.hoisted(() => ({
  metric: '',
  rows: [] as Array<{ id: string; rank: number; values: Record<string, number | null> }>,
  selected: '',
}));
vi.mock('@quant-factory/qf-ui/charts/renderers', () => ({
  MultiSeriesTimeChart: () => null,
  OptimizerGrid: (props: {
    rows: typeof captured.rows;
    selection: { metricKey: string; rowId: string };
  }) => {
    captured.metric = props.selection.metricKey;
    captured.selected = props.selection.rowId;
    captured.rows = props.rows;
    return null;
  },
}));
vi.mock('@/lib/api/benchmarks', () => ({ useBenchmark: () => ({}), useBenchmarks: () => ({}) }));
vi.mock('@tanstack/react-query', () => ({ useQuery: vi.fn() }));

import { useQuery } from '@tanstack/react-query';

// --------------------------------------------------------------------------- #
// Default metric, numeric ordering and null context
// --------------------------------------------------------------------------- #

describe('OptimizerGridSurface', () => {
  it('defaults to Sortino and ranks only by it while preserving the selected configuration', () => {
    const grid = researchGridSchema.parse({
      grid_schema_version: 1,
      selected_config_id: 'published',
      control_config_id: 'published',
      dimensions: [
        { key: 'x', label: 'X', format: 'number', values: [1, 2] },
        { key: 'y', label: 'Y', format: 'number', values: [1] },
      ],
      metrics: [
        { key: 'ir', label: 'IR', format: 'number', higher_is_better: true },
        {
          key: 'sortino',
          label: 'Sortino',
          format: 'number',
          higher_is_better: true,
          nullable: true,
        },
        {
          key: 'martin',
          label: 'Martin',
          format: 'number',
          higher_is_better: true,
          nullable: true,
        },
      ],
      summary: { path: 'summary', row_count: 2, columns: [] },
      series: {
        path: 'series',
        row_count: 4,
        config_id_column: 'id',
        date_column: 'date',
        return_column: 'return',
      },
      columns: [],
      data: [
        {
          config_id: 'published',
          rank: 1,
          is_selected: true,
          is_control: true,
          x: 1,
          y: 1,
          ir: 10,
          sortino: -1,
          martin: 100,
        },
        {
          config_id: 'higher_sortino',
          rank: 2,
          is_selected: false,
          is_control: false,
          x: 2,
          y: 1,
          ir: 1,
          sortino: 2,
          martin: null,
        },
      ],
    });
    vi.mocked(useQuery)
      .mockReturnValueOnce({ data: grid } as ReturnType<typeof useQuery>)
      .mockReturnValueOnce({ isFetching: true } as ReturnType<typeof useQuery>);
    renderToStaticMarkup(
      <MemoryRouter>
        <OptimizerGridSurface
          strategyType="example"
          memoryVersion="v001"
          metadata={{ ...grid, metrics: grid.metrics.slice(0, 1) }}
        />
      </MemoryRouter>,
    );
    expect(captured.metric).toBe('sortino');
    expect(captured.selected).toBe('published');
    expect(captured.rows.map(({ id, rank }) => [id, rank])).toEqual([
      ['higher_sortino', 1],
      ['published', 2],
    ]);
    expect(captured.rows[0].values.martin).toBeNull();
    expect(grid.data[0].rank).toBe(1);
  });
});
