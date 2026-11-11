/**
 * ML Engine run navigator: the API-filtered run index on the shared Navigator,
 * with the status and producer filters in the controls slot. Rows are buttons
 * (selection lives in the `?run=` search param), led by a StatusDot and
 * trailed by the run state.
 *
 * USAGE:
 *   <MlEngineNavigator runs={runs} selectedRunId={runId} onSelectRun={selectRun} … />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { MlEngineRun } from '@/lib/api/mlEngine';
import { liveStatusTone, Navigator, SegmentedControl, SelectControl, StatusDot } from '@/ui';

import { progressLabel, type RunFilter, relativeAge, shortRunId } from './model';

// --------------------------------------------------------------------------- #
// Types and constants
// --------------------------------------------------------------------------- #

export interface MlEngineNavigatorProps {
  runs: MlEngineRun[];
  totalRunCount: number;
  selectedRunId: string | null;
  filter: RunFilter;
  producers: string[];
  producerFilter: string;
  isLoading: boolean;
  hasError: boolean;
  onFilterChange: (filter: RunFilter) => void;
  onProducerChange: (producer: string) => void;
  onSelectRun: (runId: string) => void;
}

const FILTER_OPTIONS = [
  { value: 'all' as const, label: 'All' },
  { value: 'running' as const, label: 'Running' },
  { value: 'completed' as const, label: 'Completed' },
  { value: 'failed' as const, label: 'Failed' },
];

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function runState(run: MlEngineRun): string {
  if (run.status === 'running') return progressLabel(run);
  return run.inference_ready ? 'ready' : run.status;
}

function runAge(run: MlEngineRun): string {
  return run.status === 'completed' && run.completed_at
    ? `completed ${relativeAge(run.completed_at)}`
    : `updated ${relativeAge(run.updated_at)}`;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function MlEngineNavigator({
  runs,
  totalRunCount,
  selectedRunId,
  filter,
  producers,
  producerFilter,
  isLoading,
  hasError,
  onFilterChange,
  onProducerChange,
  onSelectRun,
}: MlEngineNavigatorProps) {
  const producerOptions = [
    { value: 'all', label: 'All producers' },
    ...[...new Set([...producers, producerFilter])]
      .filter((producer) => producer !== 'all')
      .sort()
      .map((producer) => ({ value: producer, label: producer })),
  ];

  return (
    <Navigator
      title="ML Engine"
      titleTo="/ml-engine"
      listLabel="Run index"
      mono
      controls={
        <>
          <SegmentedControl
            ariaLabel="Filter ML Engine runs"
            options={FILTER_OPTIONS}
            value={filter}
            onValueChange={onFilterChange}
            size="sm"
          />
          {producers.length > 1 || producerFilter !== 'all' ? (
            <SelectControl
              ariaLabel="Filter runs by producer"
              size="sm"
              className="w-full"
              value={producerFilter}
              onValueChange={onProducerChange}
              options={producerOptions}
            />
          ) : null}
        </>
      }
      loading={isLoading}
      error={hasError ? 'Runs unavailable.' : null}
      empty="No runs match this filter."
      groups={[
        {
          id: 'runs',
          label: 'Runs',
          meta: totalRunCount,
          items: runs.map((run) => ({
            id: run.run_id,
            label: run.producer,
            title: run.run_id,
            current: run.run_id === selectedRunId,
            leading: <StatusDot tone={liveStatusTone(run.status)} />,
            detail: (
              <>
                <span>{shortRunId(run.run_id)}</span>
                <span>{runAge(run)}</span>
              </>
            ),
            meta: runState(run),
            onSelect: () => onSelectRun(run.run_id),
          })),
        },
      ]}
    />
  );
}
