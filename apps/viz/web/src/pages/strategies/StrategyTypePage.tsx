/**
 * Strategy type detail — the family's baseline architecture (docs/ARCHITECTURE.md) and design
 * space (optimization/DESIGN-SPACE.md) when it has them, its evolution (version lineage), then
 * its memory versions.
 *
 * USAGE:
 *   Routed at /strategies/:type
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { DataTable } from '@quant-factory/qf-ui/tables';
import { useParams } from 'react-router';
import { useStrategyVersions } from '@/lib/api/strategies';
import { StrategyArchitecture } from '@/lib/components/strategies/StrategyArchitecture';
import { StrategyDesignSpace } from '@/lib/components/strategies/StrategyDesignSpace';
import { StrategyEvolution } from '@/lib/components/strategies/StrategyEvolution';
import { hasFamilyDoc } from '@/lib/strategy-docs';
import {
  familyName,
  formatIsoDay,
  formatNumber,
  formatPercent,
  isLoadingData,
  LoadingSkeleton,
  pluralize,
  QueryState,
  TerminalPage,
  TerminalSection,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StrategyTypePage() {
  const { type: strategyType = '' } = useParams();
  const query = useStrategyVersions(strategyType);
  const versions = query.data ?? [];
  const family = familyName(strategyType);

  const tableData = versions.map((version) => ({
    memory_version: version.memory_version,
    status: version.lifecycle_status ?? version.display_state,
    runs: version.run_count,
    best_sharpe: formatNumber(version.best_sharpe, 3),
    best_return: formatPercent(version.best_return),
    latest: formatIsoDay(version.latest_run),
    final_run: version.final_run_id ?? '-',
    link: `/strategies/${strategyType}/${version.memory_version}`,
  }));

  return (
    <TerminalPage
      kicker={family.sector ?? undefined}
      title={family.name}
      right={
        isLoadingData(query) ? (
          <LoadingSkeleton variant="line" announce={false} className="w-20" />
        ) : query.data ? (
          `${versions.length} ${pluralize(versions.length, 'version')}`
        ) : undefined
      }
    >
      {hasFamilyDoc(strategyType, 'docs/ARCHITECTURE.md') ? (
        <TerminalSection title="architecture">
          <StrategyArchitecture strategyType={strategyType} />
        </TerminalSection>
      ) : null}
      {hasFamilyDoc(strategyType, 'optimization/DESIGN-SPACE.md') ? (
        <StrategyDesignSpace
          strategyType={strategyType}
          versionHref={(version) => `?v=${version}`}
        />
      ) : null}
      <StrategyEvolution strategyType={strategyType} />
      <TerminalSection title="memory versions">
        <QueryState
          query={query}
          skeleton="table"
          isEmpty={versions.length === 0}
          emptyTitle="No memory versions found"
          emptyHint="No versions found for this strategy type"
        >
          <DataTable
            data={tableData}
            columns={[
              'memory_version',
              'status',
              'runs',
              'best_sharpe',
              'best_return',
              'latest',
              'final_run',
            ]}
            linkColumn="memory_version"
          />
        </QueryState>
      </TerminalSection>
    </TerminalPage>
  );
}
