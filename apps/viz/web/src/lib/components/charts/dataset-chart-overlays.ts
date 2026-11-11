/**
 * Dataset chart overlay catalog: the registered benchmarks as overlay options and
 * conversion of benchmark rows into plot-ready points.
 *
 * USAGE:
 *   const options = priceOverlayOptions(useBenchmarks().data ?? []);
 *   const selected = resolvePriceOverlay(options, choice);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { MultiSeriesOverlay } from '@quant-factory/qf-ui/charts/renderers';
import type { BenchmarkData, BenchmarkOption } from '@/lib/api/benchmarks';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export const NO_PRICE_OVERLAY = 'none';

export interface DatasetPriceOverlayOption {
  value: string;
  label: string;
  ticker: string | null;
}

export type DatasetPriceOverlaySeries = MultiSeriesOverlay;

// --------------------------------------------------------------------------- #
// Catalog
// --------------------------------------------------------------------------- #

/** "None" followed by every registered benchmark, in registration order. */
export function priceOverlayOptions(
  benchmarks: readonly BenchmarkOption[],
): DatasetPriceOverlayOption[] {
  return [
    { value: NO_PRICE_OVERLAY, label: 'None', ticker: null },
    ...benchmarks.map((item) => ({ value: item.ticker, label: item.label, ticker: item.ticker })),
  ];
}

/** The chosen option, or the first registered benchmark when nothing has been chosen yet. */
export function resolvePriceOverlay(
  options: readonly DatasetPriceOverlayOption[],
  choice: string | null,
): DatasetPriceOverlayOption {
  return (
    options.find((option) => option.value === choice) ??
    (choice === null ? options[1] : undefined) ??
    options[0]
  );
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

export function parsePriceOverlayPoints(
  rows: BenchmarkData['data'],
): DatasetPriceOverlaySeries['points'] {
  const parsed: DatasetPriceOverlaySeries['points'] = [];
  for (const row of rows) {
    const point = { date: new Date(row.timestamp), value: row.close };
    if (!Number.isNaN(point.date.getTime()) && Number.isFinite(point.value)) parsed.push(point);
  }
  return parsed;
}
