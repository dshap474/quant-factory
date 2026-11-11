/**
 * Pure benchmark-overlay and value-unit presentation helpers for research strategy charts.
 *
 * Benchmarks come from `/api/benchmarks` (none by default); the strategy's own
 * `backtestBenchmark` presentation, when registered, is the preferred overlay.
 *
 * USAGE:
 *   const ticker = defaultOverlayTicker(strategyType, tickers);
 *   const series = buildBuyHoldSeries(strategyDates, rows, { ticker, label });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { strategyBacktestBenchmark, strategySuppressesBenchmarkOverlay } from '@/extensions';
import type { BenchmarkData } from '@/lib/api/benchmarks';
import type { DatasetChartBundleSeries } from '@/lib/api/catalog';

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

const INITIAL_PORTFOLIO_VALUE = 100;

/** One registered benchmark offered as a buy-and-hold overlay. */
export interface BuyHoldOverlay {
  ticker: string;
  label: string;
}

export function buyHoldMetric(ticker: string): string {
  return `${ticker.toLowerCase()}_buy_hold`;
}

export function buyHoldLabel(label: string): string {
  return `${label} buy & hold`;
}

/** True when a surface's own benchmark id names a registered benchmark (`spy-total-return` -> SPY). */
export function isRegisteredBenchmark(
  benchmark: { id: string },
  tickers: readonly string[],
): boolean {
  const lead =
    benchmark.id
      .trim()
      .split(/[^A-Za-z0-9]/)[0]
      ?.toUpperCase() ?? '';
  return lead !== '' && tickers.some((ticker) => ticker.toUpperCase() === lead);
}

export function shouldAddBuyHoldOverlay(
  strategyType: string,
  benchmark: { id: string },
  tickers: readonly string[],
): boolean {
  return (
    tickers.length > 0 &&
    !strategySuppressesBenchmarkOverlay(strategyType) &&
    !isRegisteredBenchmark(benchmark, tickers)
  );
}

/** The strategy's declared backtest benchmark when registered, else the first registered one. */
export function defaultOverlayTicker(
  strategyType: string,
  tickers: readonly string[],
): string | null {
  const preferred = strategyBacktestBenchmark(strategyType);
  return preferred && tickers.includes(preferred) ? preferred : (tickers[0] ?? null);
}

export function performanceValuePresentation(unit: 'usd' | 'index') {
  return unit === 'index'
    ? {
        chartPrefix: 'Index values (100 = initial capital)',
        endingValueLabel: 'Ending index value',
        endingValueFormat: 'number' as const,
      }
    : {
        chartPrefix: '$100 portfolios',
        endingValueLabel: 'Ending $100 value',
        endingValueFormat: 'money' as const,
      };
}

// --------------------------------------------------------------------------- #
// Model
// --------------------------------------------------------------------------- #

/**
 * Rebase a buy-and-hold close series to 100 at its first date on the strategy calendar.
 * `mainScale` plots it on the strategy's own axis (comparable levels) instead of the
 * hidden benchmark axis; either way it stays out of the legend.
 */
export function buildBuyHoldSeries(
  strategyDates: readonly string[],
  rows: BenchmarkData['data'],
  overlay: BuyHoldOverlay,
  { mainScale = false }: { mainScale?: boolean } = {},
): DatasetChartBundleSeries | null {
  const closeByDate = new Map(
    rows
      .filter((row) => Number.isFinite(row.close) && row.close > 0)
      .map((row) => [row.timestamp.slice(0, 10), row.close]),
  );
  const aligned = strategyDates.flatMap((date) => {
    const day = date.slice(0, 10);
    const close = closeByDate.get(day);
    return close == null ? [] : [{ day, close }];
  });
  const initialClose = aligned[0]?.close;
  if (initialClose == null) return null;

  return {
    metric: buyHoldMetric(overlay.ticker),
    axis: 'left',
    label: buyHoldLabel(overlay.label),
    ...(mainScale ? { hideFromLegend: true } : { isBenchmark: true }),
    points_total: aligned.length,
    points_returned: aligned.length,
    points: aligned.map(({ day, close }) => ({
      x: `${day}T00:00:00`,
      y: INITIAL_PORTFOLIO_VALUE * (close / initialClose),
    })),
  };
}

/** A charted point whose value may be a coverage gap. */
export interface NullableChartPoint {
  x: string | Date;
  y: number | null;
}

/**
 * True when ``baseline`` repeats a series already on the chart (same dates, values within
 * 1e-9 relative), e.g. the page's own selected account or a control that reproduces it.
 * A gap (null) never matches: it is not evidence of equality to an observed value.
 */
export function duplicatesSeries(
  baseline: DatasetChartBundleSeries,
  series: readonly { points: readonly NullableChartPoint[] }[],
): boolean {
  const target = baseline.points;
  return series.some(
    (candidate) =>
      candidate.points.length === target.length &&
      candidate.points.every((point, index) => {
        const other = target[index];
        if (point.y === null || other === undefined) return false;
        const [a, b] = [point.y, other.y];
        return (
          point.x === other.x &&
          Number.isFinite(a) &&
          Number.isFinite(b) &&
          Math.abs(a - b) <= 1e-9 * Math.max(Math.abs(a), Math.abs(b), 1)
        );
      }),
  );
}
