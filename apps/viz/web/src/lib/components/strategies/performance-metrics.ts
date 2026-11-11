/** Shared strategy metric presentation.
 * USAGE: buildPerformanceMatrixRows(grid, metrics); attachMetricRanks(rows, rank).
 */

// --------------------------------------------------------------------------- #
// Metric display contract
// --------------------------------------------------------------------------- #

import type { MetricComparisonColumn, MetricComparisonRow } from '@quant-factory/qf-ui/tables';
import type { ResearchGrid, ResearchGridConfiguration, VersionRank } from '@/lib/api/strategies';

export const STANDARD_METRICS = [
  {
    key: 'total_return',
    label: 'Total return',
    group: 'Returns',
    format: 'percent',
    higherIsBetter: true,
    emphasis: true,
  },
  {
    key: 'annualized_return',
    label: 'Annualized return',
    group: 'Returns',
    format: 'percent',
    higherIsBetter: true,
  },
  {
    key: 'ending_value',
    label: 'Ending $100 value',
    group: 'Returns',
    format: 'money',
    higherIsBetter: true,
  },
  { key: 'positive_days', label: 'Positive days', group: 'Returns', format: 'percent' },
  {
    key: 'sortino',
    label: 'Sortino ratio',
    group: 'Risk-adjusted ratios',
    format: 'number',
    higherIsBetter: true,
    emphasis: true,
    description:
      'Primary ranking metric. Mean daily return divided by the root mean square of returns below zero, using all observed NAV intervals. Annualized with 365 days; target return 0%. Undefined without downside.',
  },
  {
    key: 'sharpe',
    label: 'Sharpe ratio',
    group: 'Risk-adjusted ratios',
    format: 'number',
    higherIsBetter: true,
    description:
      'Mean daily return divided by daily volatility, annualized with 365 days. Zero risk-free rate. Uses the recorded research convention.',
  },
  {
    key: 'calmar',
    label: 'Calmar ratio',
    group: 'Risk-adjusted ratios',
    format: 'number',
    higherIsBetter: true,
    description:
      'Compound annualized return divided by the magnitude of maximum drawdown. Undefined without drawdown.',
  },
  {
    key: 'martin',
    label: 'Martin ratio',
    group: 'Risk-adjusted ratios',
    format: 'number',
    higherIsBetter: true,
    description:
      'Calendar-day compound annualized return (365 days, zero cash rate) divided by the Ulcer Index: RMS drawdown over all full-resolution NAV observations, including the starting mark. Undefined without drawdown.',
  },
  {
    key: 'max_drawdown',
    label: 'Maximum drawdown',
    group: 'Drawdowns & volatility',
    format: 'percent',
    higherIsBetter: true,
  },
  {
    key: 'longest_drawdown_days',
    label: 'Longest time below peak',
    group: 'Drawdowns & volatility',
    format: 'days',
    higherIsBetter: false,
    description:
      'Calendar days from a peak to its recovery, or to the last observation if unrecovered. Includes the current episode; equality counts as recovery.',
  },
  {
    key: 'current_drawdown_days',
    label: 'Current time below peak',
    group: 'Drawdowns & volatility',
    format: 'days',
    higherIsBetter: false,
    description:
      'Calendar days since the latest high-water mark. Zero at a new or recovered peak. An unrecovered episode has no known recovery date.',
  },
  {
    key: 'annualized_volatility',
    label: 'Annualized volatility',
    group: 'Drawdowns & volatility',
    format: 'percent',
  },
] as const;

const ALIASES: Readonly<Record<string, string>> = {
  cagr: 'annualized_return',
  sharpe_365: 'sharpe',
  volatility_365: 'annualized_volatility',
};
const GROUP_ORDER = [
  'Returns',
  'Risk-adjusted ratios',
  'Drawdowns & volatility',
  'Exposure',
  'Trading costs',
  'Other metrics',
];
const EXTRA_PRESENTATION: Readonly<Record<string, Partial<MetricComparisonRow>>> = {
  final_equity: { group: 'Returns', format: 'money', higherIsBetter: true },
  mean_gross_exposure: { group: 'Exposure' },
  fee_dollars: { group: 'Trading costs', format: 'money', higherIsBetter: false },
  funding_pnl_dollars: { group: 'Trading costs', format: 'money', higherIsBetter: true },
};

// --------------------------------------------------------------------------- #
// Published grid values plus full-resolution API supplements
// --------------------------------------------------------------------------- #

export function buildPerformanceMatrixRows(
  grid: ResearchGrid,
  supplements: Readonly<Record<string, Partial<ResearchGridConfiguration['metrics']['selected']>>>,
): MetricComparisonRow[] {
  const rows: MetricComparisonRow[] = grid.metrics.map((metric) => {
    const key = ALIASES[metric.key] ?? metric.key;
    const presentation = STANDARD_METRICS.find((item) => item.key === key);
    return {
      key: metric.key,
      label: presentation?.label ?? metric.label,
      format: metric.format,
      higherIsBetter: metric.higher_is_better,
      group: 'Other metrics',
      ...presentation,
      ...EXTRA_PRESENTATION[metric.key],
      values: Object.fromEntries(
        grid.data.map((row) => {
          const value = row[metric.key];
          return [row.config_id, typeof value === 'number' ? value : null];
        }),
      ),
    };
  });
  for (const key of [
    'sortino',
    'sharpe',
    'calmar',
    'martin',
    'longest_drawdown_days',
    'current_drawdown_days',
  ] as const) {
    if (rows.some((row) => row.key === key)) continue;
    const presentation = STANDARD_METRICS.find((item) => item.key === key);
    if (!presentation) continue;
    rows.push({
      ...presentation,
      values: Object.fromEntries(
        grid.data.map((row) => {
          const cagr = row.cagr ?? row.annualized_return;
          const drawdown = row.max_drawdown;
          // Derive Calmar from the recorded pair; never mix saved CAGR with a recomputed drawdown.
          const value =
            key === 'calmar' && typeof cagr === 'number' && typeof drawdown === 'number'
              ? drawdown < 0
                ? cagr / Math.abs(drawdown)
                : null
              : supplements[row.config_id]?.[key];
          return [row.config_id, value];
        }),
      ),
    });
  }
  return rows.sort(
    (a, b) =>
      GROUP_ORDER.indexOf(a.group ?? 'Other metrics') -
        GROUP_ORDER.indexOf(b.group ?? 'Other metrics') ||
      Number(b.key === 'sortino') - Number(a.key === 'sortino'),
  );
}

// --------------------------------------------------------------------------- #
// Family rank: API-emitted canonical keys, aliases and directions
// --------------------------------------------------------------------------- #

export function attachMetricRanks(
  rows: readonly MetricComparisonRow[],
  rank: VersionRank,
): MetricComparisonRow[] {
  return rows.map((row) => {
    const definition = rank.metrics.find(
      (metric) => metric.key === row.key || metric.aliases.includes(row.key),
    );
    if (!definition || definition.direction === 'unranked') return row;
    return {
      ...row,
      rank: {
        direction: definition.direction,
        cells: Object.fromEntries(
          rank.columns.map((column) => [column.config_id, column.ranks[definition.key] ?? null]),
        ),
        missingNote: 'Not ranked: undefined over the comparison window.',
      },
    };
  });
}

// --------------------------------------------------------------------------- #
// Default comparison ordering: finite Sortino values descending, missing last
// --------------------------------------------------------------------------- #

export function sortColumnsBySortino(
  columns: readonly MetricComparisonColumn[],
  rows: readonly MetricComparisonRow[],
): MetricComparisonColumn[] {
  const values = rows.find((row) => row.key === 'sortino')?.values ?? {};
  return [...columns].sort((a, b) => compareSortinoValues(values[a.id], values[b.id]));
}

export function compareSortinoValues(left: unknown, right: unknown): number {
  const leftValid = typeof left === 'number' && Number.isFinite(left);
  const rightValid = typeof right === 'number' && Number.isFinite(right);
  if (leftValid && rightValid) return right - left;
  return Number(rightValid) - Number(leftValid);
}
