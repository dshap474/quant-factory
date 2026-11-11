/** Strategy comparison identity regressions. USAGE: pnpm vitest run ResearchStrategySurface.test.tsx. */

// --------------------------------------------------------------------------- #
// Imports and mocks
// --------------------------------------------------------------------------- #

import { readFileSync } from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { researchSurfaceSchema } from '@/lib/api/strategies';
import { ResearchStrategySurface } from './ResearchStrategySurface';

const chart = vi.hoisted(() => ({
  props: {} as { series?: Array<{ metric: string; label: string; isBenchmark?: boolean }> },
}));
vi.mock('@quant-factory/qf-ui/charts/renderers', () => ({
  MultiSeriesTimeChart: (props: typeof chart.props) => {
    chart.props = props;
    return <div data-chart="shared" />;
  },
}));
vi.mock('@/lib/api/benchmarks', () => ({
  useBenchmark: () => ({ data: undefined, error: null }),
  useBenchmarks: () => ({ data: [{ ticker: 'IDX', label: 'IDX', description: 'Registered' }] }),
}));
vi.mock('@/extensions', () => ({
  strategyExtraMetrics: () => [],
  strategySuppressesBenchmarkOverlay: () => false,
  strategyBacktestBenchmark: () => null,
  opsPanels: () => [],
}));

function fixture() {
  return researchSurfaceSchema.parse(
    JSON.parse(
      readFileSync(
        new URL('../../api/__fixtures__/research-surface.json', import.meta.url),
        'utf8',
      ),
    ),
  );
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ResearchStrategySurface', () => {
  it('preserves categorical identity and shows every status and attribution diagnostic', () => {
    const base = fixture();
    const surface = researchSurfaceSchema.parse({
      ...base,
      title: 'v004 lookback comparison',
      summary: 'SUPPORTED: longer versus shorter lookback, costs included.',
      diagnostics: [
        ...Array.from({ length: 40 }, (_, index) => ({
          key: `status_${index}`,
          label: `Arm ${index} status`,
          value: index < 25 ? 'complete' : 'blocked: missing source coverage',
          format: 'text',
        })),
        {
          key: 'matched_price_effect',
          label: 'Price effect on a matched subset',
          value: -120.5,
          format: 'money',
        },
      ],
      grid: {
        grid_schema_version: 1,
        dimensions: [
          { key: 'arm', label: 'Arm', format: 'text', values: ['candidate', 'control'] },
          { key: 'cost', label: 'Cost', format: 'number', values: [0, 7] },
        ],
        metrics: [{ key: 'return', label: 'Return', format: 'percent', higher_is_better: true }],
        selected_config_id: 'candidate_cost',
        control_config_id: 'control_cost',
        summary: { path: 'summary.parquet', row_count: 4, columns: ['rank'] },
        series: {
          path: 'series.parquet',

          row_count: 8,
          config_id_column: 'id',
          date_column: 'date',
          return_column: 'return',
        },
      },
    });
    const markup = renderToStaticMarkup(
      <ResearchStrategySurface strategyType="example" memoryVersion="v002" surface={surface} />,
    );
    expect(markup).toContain('SUPPORTED: longer versus shorter lookback');
    expect(markup).not.toContain('control-arm');
    expect(markup).not.toContain('static OOS');
    expect(markup).toContain('Research diagnostics');
    for (let index = 0; index < 40; index += 1) {
      expect(markup).toContain(`Arm ${index} status`);
    }
    expect(markup).toContain('blocked: missing source coverage');
    expect(markup).toContain('Price effect on a matched subset');
    expect(markup).toContain('$-120.50');
  });
  it('uses same-run comparison for both solid chart series and table while IDX remains an overlay', () => {
    const base = fixture();
    const surface = researchSurfaceSchema.parse({
      ...base,
      benchmark: { id: 'IDX', label: 'IDX buy & hold' },
      comparison: {
        id: 'registered_control',
        label: 'v003 continuation',
        run_id: base.run_id,
        metrics: { ...base.metrics?.benchmark, sharpe: -0.215 },
        points_total: base.points_total,
        points_returned: base.points_returned,
        data: base.data.map((row) => ({
          date: 'date' in row ? row.date : '',
          daily_return: 0,
          portfolio_value: 100,
        })),
      },
    });
    const markup = renderToStaticMarkup(
      <ResearchStrategySurface
        strategyType="example"
        memoryVersion="v005"
        surface={surface}
        operatorBaselineSurface={{ ...base, memory_version: 'v002' }}
      />,
    );
    expect(chart.props.series?.map((row) => [row.metric, !!row.isBenchmark])).toEqual([
      ['strategy', false],
      ['comparison', false],
      ['benchmark', true],
    ]);
    expect(chart.props.series?.[1]?.label).toBe('v003 continuation');
    expect(markup).toContain('−0.215');
    expect(markup).toContain('Difference');
    expect(markup).not.toContain('v002 baseline');
  });
  it('treats a legacy named-control benchmark as a strategy comparison on the main scale', () => {
    const base = fixture();
    const markup = renderToStaticMarkup(
      <ResearchStrategySurface
        strategyType="example"
        memoryVersion="v003"
        surface={{ ...base, benchmark: { id: 'control', label: 'v002 exact control' } }}
      />,
    );
    expect(chart.props.series?.[1]).toMatchObject({
      metric: 'comparison',
      label: 'v002 exact control',
    });
    expect(chart.props.series?.[1]?.isBenchmark).not.toBe(true);
    expect(markup).toContain('Registered comparison');
  });
  it('shows an unavailable control without silently substituting a historical winner', () => {
    const base = fixture();
    const markup = renderToStaticMarkup(
      <ResearchStrategySurface
        strategyType="example"
        memoryVersion="v003"
        surface={{
          ...base,
          benchmark: { id: 'IDX', label: 'IDX' },
          comparison_issue: 'Verified comparison unavailable.',
        }}
        operatorBaselineSurface={{ ...base, memory_version: 'v001' }}
      />,
    );
    expect(chart.props.series?.map((row) => row.metric)).toEqual(['strategy', 'benchmark']);
    expect(markup).toContain('Verified comparison unavailable.');
    expect(markup).not.toContain('>Difference<');
  });
  it('rejects comparison data from another run or sampled date population', () => {
    const base = fixture();
    const comparison = {
      id: 'control',
      label: 'Control',
      run_id: 'another-run',
      metrics: base.metrics?.benchmark,
      points_total: base.points_total,
      points_returned: 1,
      data: [{ date: '1999-01-01', daily_return: 0, portfolio_value: 100 }],
    };
    expect(() => researchSurfaceSchema.parse({ ...base, comparison })).toThrow(
      'comparison must match',
    );
  });
  it('shows every variant curve and a titled variant matrix from a supplement', () => {
    const base = fixture();
    const variants = [10, 20, 30].map((length) => ({
      id: `variant_${length}`,
      label: `Variant ${length}`,
      metrics: base.metrics?.strategy,
      gross_return: 0.1,
      gross_sharpe: 0.5,
      data: base.data.map((row) => ({
        date: 'date' in row ? row.date : '',
        daily_return: 0,
        portfolio_value: 100,
      })),
    }));
    const surface = researchSurfaceSchema.parse({
      ...base,
      performance_unit: 'index',
      benchmark: { id: 'IDX', label: 'IDX buy and hold' },
      supplements: {
        my_matrix: { run_id: base.run_id, title: 'Variant matrix', variants },
      },
    });
    const markup = renderToStaticMarkup(
      <ResearchStrategySurface strategyType="example" memoryVersion="v002" surface={surface} />,
    );
    expect(chart.props.series?.filter((row) => !row.isBenchmark).map((row) => row.label)).toEqual(
      variants.map((row) => row.label),
    );
    expect(markup).toContain('Performance comparison');
    expect(markup).toContain('Variant matrix');
    for (const variant of variants) expect(markup).toContain(variant.label);
    expect(markup).toContain('Return before fees');
    expect(() =>
      researchSurfaceSchema.parse({
        ...surface,
        supplements: { my_matrix: { run_id: 'other', variants } },
      }),
    ).toThrow('my_matrix must match');
  });
});
