/**
 * Strategies overview — map the strategy pipeline with live and extension rows.
 *
 * USAGE:
 *   Routed at /strategies (the Overview tab; Backtesting is the other tab)
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { extensionStrategyRows } from '@/extensions';
import { useSignalResearchFamilies } from '@/lib/api/signals';
import { type StrategyTypeSummary, useStrategyTypes } from '@/lib/api/strategies';
import { formatIsoDay, PipelineArchitectureMap, type PipelineRow, pluralize, Section } from '@/ui';
import { StrategiesFrame } from './StrategiesFrame';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function strategyRow(type: StrategyTypeSummary): PipelineRow {
  const parts = [
    `${type.version_count} ${pluralize(type.version_count, 'version')}`,
    `${type.total_runs} ${pluralize(type.total_runs, 'run')}`,
  ];
  if (type.best_sharpe !== null) parts.push(`sharpe ${type.best_sharpe.toFixed(2)}`);
  parts.push(`latest ${formatIsoDay(type.latest_run)}`);
  return {
    key: type.strategy_type,
    detail: parts.join(' · '),
    href: `/strategies/${type.strategy_type}`,
  };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StrategiesPage() {
  const signalsQuery = useSignalResearchFamilies();
  const typesQuery = useStrategyTypes();
  const signalRows = (signalsQuery.data ?? []).map((family) => ({
    key: family.signal_family,
    detail: `${family.total_runs} ${pluralize(family.total_runs, 'run')} · latest ${formatIsoDay(family.latest_run)}`,
    href: `/signals/${family.signal_family}`,
  }));
  const pinnedRows = extensionStrategyRows();
  const pinnedKeys = new Set(pinnedRows.map((row) => row.key));
  const typeRows = [
    ...pinnedRows,
    ...(typesQuery.data ?? [])
      .filter((type) => !pinnedKeys.has(type.strategy_type))
      .map(strategyRow),
  ];

  return (
    <StrategiesFrame>
      <Section>
        <PipelineArchitectureMap
          scope="strategies"
          hideHeader
          laneRows={{
            IN: {
              rows: signalRows,
              loading: signalsQuery.isLoading,
              empty: signalsQuery.error ? 'signal index unavailable' : 'no signal runs yet',
            },
            '01': {
              rows: typesQuery.isLoading ? [] : typeRows,
              loading: typesQuery.isLoading,
              empty: typesQuery.error ? 'strategy index unavailable' : undefined,
            },
          }}
        />
      </Section>
    </StrategiesFrame>
  );
}
