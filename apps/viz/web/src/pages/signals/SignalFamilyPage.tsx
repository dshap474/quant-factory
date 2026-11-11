/**
 * Signal research family detail: the family's design space (`optimization/DESIGN-SPACE.md`,
 * graph or table), its evolution (versions by parent, with each version's question and
 * finding), then the optimization lifecycle versions.
 *
 * USAGE:
 *   Routed at /signals/:family.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { DataTable } from '@quant-factory/qf-ui/tables';
import { useParams } from 'react-router';
import { useSignalResearchVersions } from '@/lib/api/signals';
import { StrategyDesignSpace } from '@/lib/components/strategies/StrategyDesignSpace';
import { StrategyEvolution } from '@/lib/components/strategies/StrategyEvolution';
import { hasFamilyDoc } from '@/lib/strategy-docs';
import {
  familyName,
  formatIsoDay,
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

export function SignalFamilyPage() {
  const { family = '' } = useParams();
  const query = useSignalResearchVersions(family);
  const versions = query.data ?? [];
  const name = familyName(family);
  const tableData = versions.map((version) => ({
    memory_version: version.memory_version,
    status: version.lifecycle_status ?? version.display_state,
    phase: version.lifecycle_phase ?? '-',
    runs: version.run_count,
    experiment: version.experiment ?? '-',
    latest: formatIsoDay(version.latest_run),
    link: `/signals/${family}/${version.memory_version}`,
  }));

  return (
    <TerminalPage
      kicker={name.sector ?? undefined}
      title={name.name}
      right={
        isLoadingData(query) ? (
          <LoadingSkeleton variant="line" announce={false} className="w-20" />
        ) : query.data ? (
          `${versions.length} ${pluralize(versions.length, 'version')}`
        ) : undefined
      }
    >
      {hasFamilyDoc(family, 'optimization/DESIGN-SPACE.md', 'signals') ? (
        <StrategyDesignSpace strategyType={family} pkg="signals" versionHref={(v) => `?v=${v}`} />
      ) : null}
      <StrategyEvolution
        strategyType={family}
        pkg="signals"
        recordHref={(version) => `/signals/${family}/${version}`}
      />
      <TerminalSection title="memory versions">
        <QueryState
          query={query}
          skeleton="table"
          isEmpty={versions.length === 0}
          emptyTitle="No optimization versions found"
          emptyHint="No research versions found for this signal family"
        >
          <DataTable
            data={tableData}
            columns={['memory_version', 'status', 'phase', 'runs', 'experiment', 'latest']}
            linkColumn="memory_version"
          />
        </QueryState>
      </TerminalSection>
    </TerminalPage>
  );
}
