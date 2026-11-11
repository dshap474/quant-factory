/**
 * Public contract tests for qf-charts models, formatting, chrome, and primitives.
 *
 * USAGE:
 *   pnpm test -- contracts.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import {
  axisIndexForSeries,
  formatOptimizerValue,
  Heatmap,
  Histogram,
  MultiSeriesTimeChart,
  normalizeLineSeries,
  OptimizerGrid,
  type QfLineSeries,
  Sparkline,
  TransitionMatrix,
} from '../../src/charts/charts';
import {
  ChartFrame,
  ChartLegend,
  ChartTooltip,
  LegendCollapseButton,
  MultiPaneTimeSeriesChart,
} from '../../src/charts/components';
import { QF_DARK_THEME, QF_LIGHT_THEME } from '../../src/charts/theme';
import { escapeHtml } from '../../src/charts/utils/escapeHtml';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const firstDate = new Date('2026-01-01T00:00:00Z');
const secondDate = new Date('2026-01-02T00:00:00Z');
const primary: QfLineSeries = {
  key: 'strategy',
  label: '<Strategy>',
  color: '#fff',
  valueFormat: 'percent',
  points: [
    { date: firstDate, value: 1 },
    { date: secondDate, value: null },
  ],
};
const benchmark: QfLineSeries = {
  key: 'btc',
  label: 'BTC',
  color: '#fc0',
  isBenchmark: true,
  points: [{ date: firstDate, value: 100 }],
};

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('line contracts', () => {
  it('preserves dates, nulls, labels, colors, and value formats', () => {
    const model = normalizeLineSeries([primary, benchmark]);
    expect(model.plotted[0]).toBe(primary);
    expect(model.plotted[0]?.points).toEqual(primary.points);
    expect(model.plotted[0]).toMatchObject({
      label: '<Strategy>',
      color: '#fff',
      valueFormat: 'percent',
    });
  });

  it('keeps benchmarks on their own axis and available to the shared legend', () => {
    const model = normalizeLineSeries([primary, benchmark]);
    expect(axisIndexForSeries(primary)).toBe(0);
    expect(axisIndexForSeries(benchmark)).toBe(1);
    expect(axisIndexForSeries({ ...primary, axis: 'secondary' })).toBe(1);
    expect(axisIndexForSeries(benchmark, true)).toBe(2);
    expect(model.legend.map((item) => item.key)).toEqual(['strategy', 'btc']);
  });

  it('removes hidden series completely and restores them from the full input', () => {
    expect(
      normalizeLineSeries([primary, benchmark], new Set(['strategy'])).plotted.map(
        (item) => item.key,
      ),
    ).toEqual(['btc']);
    expect(
      normalizeLineSeries([primary, benchmark], new Set()).plotted.map((item) => item.key),
    ).toEqual(['strategy', 'btc']);
  });
});

describe('formatting and theme contracts', () => {
  it('escapes tooltip labels', () => {
    expect(escapeHtml(`<script>&"'</script>`)).toBe(
      '&lt;script&gt;&amp;&quot;&#39;&lt;/script&gt;',
    );
  });

  it('keeps the current dark semantic defaults and readable light defaults', () => {
    expect(QF_DARK_THEME).toMatchObject({
      surface: 'oklch(0.19 0.006 60)',
      grid: 'rgb(255 255 255 / 0.07)',
      gridOpacity: 1,
      axis: 'rgb(255 255 255 / 0.12)',
      crosshair: 'rgb(255 255 255 / 0.32)',
      axisLabel: 'oklch(0.71 0.004 90)',
      label: 'oklch(0.78 0.004 90)',
      benchmark: 'oklch(0.72 0.005 90)',
    });
    expect(QF_LIGHT_THEME.gridOpacity).toBe(1);
    expect(QF_LIGHT_THEME.tooltipText).not.toBe(QF_LIGHT_THEME.tooltipBackground);
    expect(QF_DARK_THEME.palette).toHaveLength(20);
  });
});

describe('chrome and specialized contracts', () => {
  it('preserves frame and collapsed legend geometry without Reset controls', () => {
    const markup = renderToStaticMarkup(
      <ChartFrame title="Chart">
        <div>Plot</div>
      </ChartFrame>,
    );
    const button = renderToStaticMarkup(
      <LegendCollapseButton collapsed onToggle={() => undefined} />,
    );
    expect(markup).toContain('class="qf-chart-frame"');
    expect(markup).toContain('class="qf-chart-frame-header"');
    expect(markup).toContain('class="qf-chart-frame-title"');
    expect(markup).toContain('class="qf-chart-frame-body"');
    expect(button).toContain('width:24px');
    expect(button).toContain('aria-label="Expand legend"');
    expect(`${markup}${button}`).not.toMatch(/Reset/i);
  });

  it('excludes benchmarks while retaining ordinary legend and tooltip accessibility', () => {
    const secondary = { ...primary, key: 'secondary', label: 'Secondary' };
    const legend = renderToStaticMarkup(
      <ChartLegend
        series={[primary, secondary, benchmark]}
        hiddenSeries={new Set()}
        onHiddenSeriesChange={() => undefined}
        emphasizedSeries="strategy"
        onEmphasizedSeriesChange={() => undefined}
      />,
    );
    const tooltip = renderToStaticMarkup(
      <ChartTooltip date={firstDate} items={[{ label: '<IC>', value: '0.12' }]} />,
    );
    expect(legend).toContain('Hide');
    expect(legend).not.toContain('BTC');
    expect(legend).toContain('is-pinned');
    expect(legend).toContain('is-muted');
    expect(legend).toContain('aria-pressed="true"');
    expect(tooltip).toContain('&lt;IC&gt;');
    expect(tooltip).toContain('role="status"');
  });

  it('omits benchmark labels and markers from the multi-series legend', () => {
    const chart = renderToStaticMarkup(
      <MultiSeriesTimeChart
        series={[
          {
            metric: 'strategy',
            axis: 'left',
            label: 'v002',
            points: [{ x: firstDate, y: 1 }],
          },
          {
            metric: 'control',
            axis: 'left',
            label: 'Frozen v001 candidate',
            isBenchmark: true,
            points: [{ x: firstDate, y: 1 }],
          },
        ]}
      />,
    );
    expect(chart).toContain('Hide v002');
    expect(chart).not.toContain('Hide Frozen v001 candidate');
    expect(chart).toContain('chart-legend-marker solid');
    expect(chart).not.toContain('chart-legend-marker dotted');
  });

  it('labels a smoothed multi-series chart and leaves the linear default unlabelled', () => {
    const strategy = {
      metric: 'strategy',
      axis: 'left' as const,
      label: 'v002',
      points: [{ x: firstDate, y: 1 }],
    };
    const linear = renderToStaticMarkup(<MultiSeriesTimeChart series={[strategy]} />);
    const smoothed = renderToStaticMarkup(
      <MultiSeriesTimeChart series={[{ ...strategy, interpolation: 'smooth' as const }]} />,
    );
    expect(linear).not.toContain('Smoothed');
    expect(smoothed).toContain('Smoothed');
  });

  it('keeps transition matrix and optimizer selection contracts renderable', () => {
    const transition = renderToStaticMarkup(
      <TransitionMatrix regimes={['A', 'B']} matrix={[[{ count: 1, probability: 1 }]]} />,
    );
    const optimizer = renderToStaticMarkup(
      <OptimizerGrid
        dimensions={[
          { key: 'x', label: 'X', format: 'number', values: [1] },
          { key: 'y', label: 'Y', format: 'number', values: [2] },
        ]}
        metrics={[{ key: 'score', label: 'Score', format: 'percent', higherIsBetter: true }]}
        rows={[{ id: 'one', rank: 1, values: { x: 1, y: 2, score: 0.5 } }]}
        selection={{ xKey: 'x', yKey: 'y', metricKey: 'score', rowId: 'one' }}
        onChange={() => undefined}
      />,
    );
    expect(transition).toContain('Transition Matrix');
    expect(optimizer).toContain('Selected #1');
    expect(formatOptimizerValue(0.001, 'bps')).toBe('10 bps');
  });

  it('shows an undefined optimizer metric without turning it into zero or rejecting the grid', () => {
    const markup = renderToStaticMarkup(
      <OptimizerGrid
        dimensions={[
          { key: 'x', label: 'X', format: 'number', values: [1] },
          { key: 'y', label: 'Y', format: 'number', values: [2] },
        ]}
        metrics={[{ key: 'ratio', label: 'Ratio', format: 'number', higherIsBetter: true }]}
        rows={[{ id: 'undefined', rank: 1, values: { x: 1, y: 2, ratio: null } }]}
        selection={{ xKey: 'x', yKey: 'y', metricKey: 'ratio', rowId: 'undefined' }}
        onChange={() => undefined}
      />,
    );
    expect(markup).toContain('Selected #1');
    expect(markup).toContain('Ratio: —');
    expect(formatOptimizerValue(null, 'number')).toBe('—');
  });

  it('keeps heatmap, sparkline, and histogram caller-sized contracts renderable', () => {
    const heatmap = renderToStaticMarkup(
      <Heatmap
        xLabels={['X']}
        yLabels={['Y']}
        cells={[{ x: 0, y: 0, value: 1, display: '1', tooltip: 'X/Y', color: '#fff' }]}
        ariaLabel="Heatmap"
        height={120}
      />,
    );
    const sparkline = renderToStaticMarkup(<Sparkline values={[1, null, 2]} height={32} />);
    const histogram = renderToStaticMarkup(
      <Histogram values={[2, 4]} labels={['A', 'B']} height={80} />,
    );
    expect(heatmap).toContain('height:120px');
    expect(sparkline).toContain('height:32px');
    expect(histogram).toContain('height:80px');
  });

  it('leaves the histogram option untouched unless axes is opted in', async () => {
    const captured: Record<string, unknown>[] = [];
    vi.resetModules();
    vi.doMock('../../src/charts/core/QfChart', () => ({
      QfChart: ({ option }: { option: Record<string, unknown> }) => {
        captured.push(option);
        return null;
      },
    }));
    const { Histogram: Isolated } = await import('../../src/charts/charts/Histogram');
    renderToStaticMarkup(<Isolated values={[2, 4]} labels={['A', 'B']} height={80} />);
    renderToStaticMarkup(
      <Isolated values={[2, 4]} labels={['A', 'B']} height={160} axes={false} />,
    );
    renderToStaticMarkup(<Isolated values={[2, 4]} labels={['A', 'B']} height={160} axes />);
    vi.doUnmock('../../src/charts/core/QfChart');
    vi.resetModules();

    const [defaultOption, explicitOff, withAxes] = captured;
    expect(defaultOption).toEqual(explicitOff);
    expect(defaultOption).toMatchObject({
      grid: { top: 3, right: 2, bottom: 3, left: 2 },
      xAxis: { type: 'category', show: false, data: ['A', 'B'] },
      yAxis: { type: 'value', show: false },
    });
    expect(withAxes).not.toEqual(defaultOption);
    expect(withAxes).toMatchObject({
      grid: { top: 8, right: 6, bottom: 6, left: 36 },
      xAxis: { show: false },
      yAxis: { show: true, splitNumber: 3, axisLine: { show: false }, axisTick: { show: false } },
    });
    expect({ ...(withAxes as { series: Record<string, unknown> }).series }).toEqual({
      ...(defaultOption as { series: Record<string, unknown> }).series,
    });
  });

  it('renders a multi-pane footer caption only when footer is given', () => {
    const pane = { id: 'only', label: 'Only', content: <div /> };
    const withFooter = renderToStaticMarkup(
      <MultiPaneTimeSeriesChart panes={[pane]} footer="note" />,
    );
    const withoutFooter = renderToStaticMarkup(<MultiPaneTimeSeriesChart panes={[pane]} />);

    expect(withFooter).toContain('qf-chart-frame-footer');
    expect(withFooter).toContain('note');
    expect(withoutFooter).not.toContain('qf-chart-frame-footer');
  });
});
