/**
 * Strategies API boundary tests — normalizers + research surface Zod parse.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/api/strategies.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  normalizeStrategyTypeSummary,
  normalizeVersionSummary,
  researchGridConfigurationSchema,
  researchGridSchema,
  researchSurfaceSchema,
} from './strategies';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const fixturesDir = path.join(path.dirname(fileURLToPath(import.meta.url)), '__fixtures__');

function loadJson(name: string): unknown {
  return JSON.parse(readFileSync(path.join(fixturesDir, name), 'utf8'));
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('strategies normalizers', () => {
  it('pairs supplement variant matrices with the selected research surface', () => {
    const surface = researchSurfaceSchema.parse(loadJson('research-surface.json'));
    const metrics = surface.metrics;
    if (!metrics) throw new Error('Fixture must contain metrics');
    const myMatrix = {
      run_id: surface.run_id,
      variants: ['first', 'second', 'third'].map((id) => ({
        id,
        label: `Variant ${id}`,
        metrics: metrics.strategy,
        gross_return: 0,
        gross_sharpe: 0,
        data: surface.data.map((row) => ({
          date: 'date' in row ? row.date : '',
          daily_return: 0,
          portfolio_value: 100,
        })),
      })),
    };
    const payload = { ...surface, supplements: { my_matrix: myMatrix } };
    const parsed = researchSurfaceSchema.safeParse(payload);
    expect(parsed.success).toBe(true);
    expect(parsed.data?.variant_matrices).toHaveLength(1);
    const otherRun = structuredClone(payload);
    otherRun.supplements.my_matrix.run_id = 'another-run';
    expect(researchSurfaceSchema.safeParse(otherRun).success).toBe(false);
    const wrongDates = structuredClone(payload);
    wrongDates.supplements.my_matrix.variants[1].data[0].date = '1900-01-01';
    expect(researchSurfaceSchema.safeParse(wrongDates).success).toBe(false);
  });

  it('normalizes live strategy-type list fixtures', () => {
    const raw = loadJson('strategy-types.json');
    expect(Array.isArray(raw)).toBe(true);
    const types = (raw as unknown[]).map(normalizeStrategyTypeSummary);
    expect(types.length).toBeGreaterThan(0);
    for (const item of types) {
      expect(item.strategy_type.length).toBeGreaterThan(0);
      expect(typeof item.total_runs).toBe('number');
      expect(Array.isArray(item.versions)).toBe(true);
    }
  });

  it('normalizes version summaries including surface flags', () => {
    const raw = loadJson('strategy-versions.json');
    const versions = (raw as unknown[]).map(normalizeVersionSummary);
    expect(versions.length).toBeGreaterThan(0);
    expect(versions.some((v) => v.memory_version === 'v003')).toBe(true);
    const v003 = versions.find((v) => v.memory_version === 'v003');
    expect(v003?.has_surface).toBe(true);
  });

  it('accepts bare version strings', () => {
    const version = normalizeVersionSummary('v001');
    expect(version).toEqual({
      memory_version: 'v001',
      run_count: 0,
      best_sharpe: null,
      best_return: null,
      latest_run: null,
      final_run_id: null,
      state: 'promoted',
      display_state: 'promoted',
      source: 'canonical',
      selected_run_id: null,
      experiment: null,
      has_surface: false,
      lifecycle_phase: null,
      lifecycle_status: null,
      invalidation_reason: null,
      scored_observations: null,
    });
  });

  it('preserves lifecycle metadata for registered versions without surfaces', () => {
    const version = normalizeVersionSummary({
      memory_version: 'v005',
      state: 'candidate',
      source: 'research',
      has_surface: false,
      lifecycle_phase: 'audited',
      lifecycle_status: 'active',
    });

    expect(version.has_surface).toBe(false);
    expect(version.lifecycle_phase).toBe('audited');
    expect(version.lifecycle_status).toBe('active');
  });

  it('preserves invalidated research metadata', () => {
    const version = normalizeVersionSummary({
      memory_version: 'v002',
      state: 'invalidated',
      source: 'research',
      selected_run_id: '20240101T000000Z-v002-check',
      invalidation_reason: 'Inputs changed.',
      scored_observations: 0,
    });

    expect(version.state).toBe('invalidated');
    expect(version.invalidation_reason).toBe('Inputs changed.');
    expect(version.scored_observations).toBe(0);
  });

  it('preserves an operator-selected research baseline', () => {
    const version = normalizeVersionSummary({
      memory_version: 'v003',
      state: 'rejected',
      display_state: 'baseline',
      source: 'research',
      selected_run_id: '20240102T000000Z-v003-variant',
    });

    expect(version.state).toBe('rejected');
    expect(version.display_state).toBe('baseline');
  });
});

describe('researchSurfaceSchema', () => {
  it('parses an operator-selected baseline without rewriting immutable lifecycle evidence', () => {
    const raw = loadJson('research-surface.json') as Record<string, unknown>;
    const surface = researchSurfaceSchema.parse({
      ...raw,
      display_state: 'baseline',
      operator_baseline: true,
    });

    expect(surface.state).toBe('rejected');
    expect(surface.display_state).toBe('baseline');
    expect(surface.operator_baseline).toBe(true);
  });

  it('parses a recorded research surface fixture', () => {
    const surface = researchSurfaceSchema.parse(loadJson('research-surface.json'));
    expect(surface.schema_version).toBe(1);
    expect(surface.strategy_type).toBe('example-strategy');
    expect(surface.memory_version).toBe('v003');
    expect(surface.data.length).toBeGreaterThan(0);
    expect(surface.metrics?.strategy.total_return).toEqual(expect.any(Number));
    expect(surface.gates.length).toBeGreaterThan(0);
    expect(surface.performance_unit).toBe('usd');
  });

  it('preserves a non-USD performance index unit', () => {
    const raw = loadJson('research-surface.json') as Record<string, unknown>;
    const surface = researchSurfaceSchema.parse({ ...raw, performance_unit: 'index' });

    expect(surface.performance_unit).toBe('index');
  });

  it('parses a text-only historical research record', () => {
    const raw = {
      schema_version: 1,
      strategy_type: 'example-alpha',
      memory_version: 'v002',
      state: 'rejected',
      display_state: 'rejected',
      experiment: 'example-plan',
      run_id: '20240101T000000Z-v002-record',
      published_at: '2024-01-01T00:00:00+00:00',
      title: 'Family A v002',
      summary: 'The plan was written but not run.',
      benchmark: null,
      metrics: null,
      diagnostics: [
        { key: 'classification', label: 'Outcome', value: 'NOT TESTED', format: 'text' },
      ],
      gates: [],
      disclosures: ['No returns recorded.'],
      data: [],
    };
    const surface = researchSurfaceSchema.parse(raw);

    expect(surface.data).toEqual([]);
    expect(surface.metrics).toBeNull();
    expect(surface.summary).toContain('not run');
    expect(() => researchSurfaceSchema.parse({ ...raw, performance_unit: 'index' })).toThrow(
      'research surface must contain complete performance, PnL, or a text-only record',
    );
  });

  it('parses a one-dollar PnL surface', () => {
    const raw = {
      schema_version: 1,
      strategy_type: 'example-research-strategy',
      memory_version: 'v001',
      state: 'rejected',
      display_state: 'rejected',
      experiment: 'gate-record',
      run_id: 'pnl-surface-v1',
      published_at: '2024-02-05T20:00:00+00:00',
      title: 'Family B v001',
      summary: 'Cumulative PnL on a $100 allocation.',
      benchmark: null,
      metrics: null,
      pnl: {
        path: 'surface/pnl.parquet',

        columns: ['timestamp', 'cumulative_pnl_usd'],
        row_count: 3,
        label: 'v001 cumulative PnL',
        allocation_usd: 100,
        interpretation: 'backtest',
      },
      diagnostics: [],
      gates: [],
      disclosures: [],
      data: [
        { timestamp: '2024-02-01T00:00:00Z', cumulative_pnl_usd: 0 },
        { timestamp: '2024-02-01T01:00:00Z', cumulative_pnl_usd: 2.5 },
        { timestamp: '2024-02-01T02:00:00Z', cumulative_pnl_usd: -1.25 },
      ],
    };
    const surface = researchSurfaceSchema.parse(raw);

    expect(surface.pnl?.allocation_usd).toBe(100);
    expect(surface.data).toHaveLength(3);
    expect(() => researchSurfaceSchema.parse({ ...raw, performance_unit: 'index' })).toThrow(
      'research surface must contain complete performance, PnL, or a text-only record',
    );
  });

  it('parses a display-sized sample without weakening artifact row-count validation', () => {
    const surface = researchSurfaceSchema.parse({
      schema_version: 1,
      strategy_type: 'example-research-strategy',
      memory_version: 'v004',
      state: 'candidate',
      experiment: 'example-runner',
      run_id: 'sampled-pnl-v1',
      published_at: '2024-02-20T00:00:00+00:00',
      title: 'Family B v004',
      summary: 'PnL sampled for chart delivery.',
      benchmark: null,
      metrics: null,
      pnl: {
        path: 'surface/pnl.parquet',

        columns: ['timestamp', 'cumulative_pnl_usd'],
        row_count: 100_000,
        label: 'v004 cumulative PnL',
        allocation_usd: 1000,
        interpretation: 'backtest',
      },
      diagnostics: [],
      gates: [],
      disclosures: [],
      points_total: 100_000,
      points_returned: 2,
      downsampled: true,
      data: [
        { timestamp: '2024-02-01T00:00:00Z', cumulative_pnl_usd: 0 },
        { timestamp: '2024-02-04T02:00:00Z', cumulative_pnl_usd: -1_000 },
      ],
    });

    expect(surface.points_total).toBe(100_000);
    expect(surface.points_returned).toBe(2);
    expect(surface.downsampled).toBe(true);
    expect(surface.pnl?.row_count).toBe(100_000);
  });

  it('rejects PnL metadata with a mismatched row count', () => {
    expect(() =>
      researchSurfaceSchema.parse({
        schema_version: 1,
        strategy_type: 'example-research-strategy',
        memory_version: 'v002',
        state: 'rejected',
        experiment: 'example-stop',
        run_id: 'pnl-surface-v1',
        published_at: '2024-02-05T20:00:00+00:00',
        title: 'Family B v002',
        summary: 'No result passed review.',
        benchmark: null,
        metrics: null,
        pnl: {
          path: 'surface/pnl.parquet',

          columns: ['timestamp', 'cumulative_pnl_usd'],
          row_count: 2,
          label: 'v002 stopped run',
          allocation_usd: 100,
          interpretation: 'protocol_stop',
        },
        diagnostics: [],
        gates: [],
        disclosures: [],
        data: [{ timestamp: '2024-02-01T00:00:00Z', cumulative_pnl_usd: 0 }],
      }),
    ).toThrow();
  });

  it('parses a PnL comparison surface', () => {
    const surface = researchSurfaceSchema.parse({
      schema_version: 1,
      strategy_type: 'example-research-strategy',
      memory_version: 'v003',
      state: 'rejected',
      experiment: 'signal-record',
      run_id: 'comparison-surface-v1',
      published_at: '2024-02-05T23:00:00+00:00',
      title: 'Family B v003',
      summary: 'Candidate and v001 cumulative PnL.',
      benchmark: { id: 'v001', label: 'v001' },
      metrics: null,
      pnl: {
        path: 'surface/pnl.parquet',

        columns: ['timestamp', 'cumulative_pnl_usd', 'benchmark_cumulative_pnl_usd'],
        row_count: 2,
        label: 'v003',
        allocation_usd: 100,
        interpretation: 'backtest',
      },
      diagnostics: [],
      gates: [],
      disclosures: [],
      data: [
        {
          timestamp: '2024-02-01T00:00:00Z',
          cumulative_pnl_usd: 0,
          benchmark_cumulative_pnl_usd: 0,
        },
        {
          timestamp: '2024-02-01T01:00:00Z',
          cumulative_pnl_usd: -1,
          benchmark_cumulative_pnl_usd: -5,
        },
      ],
    });

    expect(surface.benchmark?.label).toBe('v001');
    expect(surface.data[1]).toMatchObject({ benchmark_cumulative_pnl_usd: -5 });
  });

  it('rejects surfaces missing required trust fields', () => {
    expect(() => researchSurfaceSchema.parse({ schema_version: 1 })).toThrow();
  });
});

describe('research optimizer-grid schemas', () => {
  const metadata = {
    grid_schema_version: 1,
    dimensions: [
      { key: 'penalty', label: 'Penalty', format: 'bps', values: [0.001, 0.002] },
      { key: 'risk', label: 'Risk', format: 'percent', values: [0.01, 0.02] },
    ],
    metrics: [{ key: 'ir', label: 'IR', format: 'number', higher_is_better: true }],
    selected_config_id: 'selected',
    control_config_id: 'control',
    summary: { path: 'summary.parquet', row_count: 2, columns: ['rank'] },
    series: {
      path: 'series.parquet',

      row_count: 6,
      config_id_column: 'config_id',
      date_column: 'date',
      return_column: 'daily_return',
    },
  } as const;

  it('parses dynamic grid rows at the HTTP boundary', () => {
    const grid = researchGridSchema.parse({
      ...metadata,
      columns: ['rank', 'config_id', 'penalty', 'risk', 'ir'],
      data: [
        {
          rank: 1,
          config_id: 'selected',
          is_selected: true,
          is_control: false,
          penalty: 0.001,
          risk: 0.01,
          ir: 1.2,
        },
      ],
    });
    expect(grid.data[0]?.ir).toBe(1.2);
  });

  it('accepts categorical arm dimensions while keeping numeric dimensions numeric', () => {
    const grid = {
      ...metadata,
      dimensions: [
        { key: 'arm', label: 'Arm', format: 'text', values: ['candidate', 'control'] },
        { key: 'cost_bps', label: 'Cost', format: 'number', values: [0, 5] },
      ],
      columns: ['rank', 'config_id', 'arm', 'cost_bps', 'ir'],
      data: [
        {
          rank: 1,
          config_id: 'selected',
          is_selected: true,
          is_control: false,
          arm: 'candidate',
          cost_bps: 5,
          ir: 1.38,
        },
      ],
    };
    expect(researchGridSchema.parse(grid).data[0]?.arm).toBe('candidate');
    expect(() =>
      researchGridSchema.parse({
        ...grid,
        dimensions: [grid.dimensions[0], { ...grid.dimensions[1], values: ['5'] }],
      }),
    ).toThrow();
  });

  it('parses a selected, control, and benchmark comparison', () => {
    const standardMetrics = {
      total_return: 0.1,
      sharpe: 1.2,
      max_drawdown: -0.2,
      ending_value: 110,
      annualized_return: 0.1,
      annualized_volatility: 0.2,
      calmar: 0.5,
      positive_days: 0.55,
    };
    const comparison = researchGridConfigurationSchema.parse({
      config: { rank: 1, config_id: 'selected', is_selected: true, is_control: false },
      control: { rank: 2, config_id: 'control', is_selected: false, is_control: true },
      benchmark: { id: 'BTC', label: 'BTC buy & hold' },
      metrics: {
        selected: standardMetrics,
        control: standardMetrics,
        benchmark: standardMetrics,
      },
      columns: ['date'],
      data: [
        {
          date: '2024-01-01',
          selected_daily_return: 0.01,
          selected_portfolio_value: 101,
          control_daily_return: 0.005,
          control_portfolio_value: 100.5,
          benchmark_daily_return: 0,
          benchmark_portfolio_value: 100,
        },
      ],
    });
    expect(comparison.data).toHaveLength(1);
  });
});
