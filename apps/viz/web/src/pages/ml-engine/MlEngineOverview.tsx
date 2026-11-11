/**
 * ML Engine landing overview using the shared architecture-map workspace.
 *
 * USAGE:
 *   <MlEngineOverview runs={runs} totalCount={count} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { isActivelyRunning, type MlEngineRun } from '@/lib/api/mlEngine';
import { PageHeader, PipelineArchitectureMap, type PipelineRow } from '@/ui';

import { progressLabel, relativeAge, shortRunId } from './model';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function runRow(run: MlEngineRun): PipelineRow {
  const state = isActivelyRunning(run)
    ? `running · ${progressLabel(run)} fits`
    : run.inference_ready
      ? 'completed · inference ready'
      : run.final_refit === false
        ? 'completed · OOS only'
        : run.status;
  return {
    key: shortRunId(run.run_id),
    detail: `${run.producer} · ${state} · updated ${relativeAge(run.updated_at)}`,
    href: `/ml-engine?run=${encodeURIComponent(run.run_id)}`,
  };
}

function readinessRows(
  runs: readonly MlEngineRun[],
  totalCount: number,
  invalidCount: number,
): PipelineRow[] {
  const rows: PipelineRow[] = [
    { key: 'matched runs', detail: String(totalCount) },
    {
      key: 'active now',
      detail: String(runs.filter((run) => isActivelyRunning(run)).length),
    },
    {
      key: 'inference ready',
      detail: String(runs.filter((run) => run.inference_ready).length),
    },
    {
      key: 'failed in view',
      detail: String(runs.filter((run) => run.status === 'failed').length),
    },
    {
      key: 'producers in view',
      detail: String(new Set(runs.map((run) => run.producer)).size),
    },
  ];
  if (invalidCount > 0) rows.push({ key: 'malformed omitted', detail: String(invalidCount) });
  return rows;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

interface MlEngineOverviewProps {
  runs: readonly MlEngineRun[];
  totalCount: number;
  invalidCount: number;
  loading: boolean;
  error: boolean;
  filtersActive: boolean;
}

export function MlEngineOverview({
  runs,
  totalCount,
  invalidCount,
  loading,
  error,
  filtersActive,
}: MlEngineOverviewProps) {
  return (
    <>
      <PageHeader title="ML Engine" subtitle="fit → evaluate → artifact" />
      <PipelineArchitectureMap
        scope="ml-engine"
        hideHeader
        laneRows={{
          '01': {
            rows: runs.map(runRow),
            loading,
            empty: error
              ? 'run index unavailable'
              : filtersActive
                ? 'no runs match the current filters'
                : 'no ML Engine runs yet',
          },
          '02': {
            rows: readinessRows(runs, totalCount, invalidCount),
            loading,
          },
        }}
      />
    </>
  );
}
