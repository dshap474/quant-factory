/** Strategy Optimizer grouped history with research outcomes, backed by shared run telemetry.
 * USAGE: <OptimizerHistory />
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@quant-factory/qf-ui/tables';
// --------------------------------------------------------------------------- #
// Imports and presentation
// --------------------------------------------------------------------------- #
import { useLocation, useSearchParams } from 'react-router';
import { type OptimizerEntry, useOptimizerHistory } from '@/lib/api/optimizer';
import {
  Cluster,
  EmptyState,
  Field,
  formatDuration,
  formatShortDateTime,
  Input,
  isLoadingData,
  Link,
  LoadingSkeleton,
  liveStatusTone,
  Pagination,
  pluralize,
  ScrollArea,
  SelectControl,
  StateMessage,
  StatusBadge,
  Surface,
  TerminalSection,
} from '@/ui';
import { runState } from './runs';

export const optimizerStates: Record<string, string> = {
  succeeded: 'Completed',
  starting: 'Starting',
  running: 'Running',
  failed: 'Failed',
  cancelled: 'Cancelled',
  interrupted: 'Interrupted',
  unknown: 'Unknown',
  unresponsive: 'Unresponsive',
};
export function outcomeLabel(entry: OptimizerEntry) {
  if (!entry.research.status) return '—';
  return (
    { supported: 'Supported', falsified: 'Falsified', not_tested: 'Not tested' }[
      entry.research.status ?? ''
    ] ?? '—'
  );
}

// --------------------------------------------------------------------------- #
// Expanded target: ordinary research files and preserved attempt evidence
// --------------------------------------------------------------------------- #
function RunList({ entries }: { entries: OptimizerEntry[] }) {
  const location = useLocation();
  return (
    <Surface padding="none" clip>
      <ScrollArea axis="x">
        <Table density="dense" className="min-w-[680px]">
          <TableHeader>
            <TableRow>
              <TableHead>Target / version</TableHead>
              <TableHead>Execution</TableHead>
              <TableHead>Research outcome</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Started</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map((entry) => {
              const run = entry.detail.run;
              const href = `/agents/strategy-optimizer/runs/${encodeURIComponent(run.id)}`;
              const from = `${location.pathname}${location.search}`;
              return (
                <TableRow key={run.id}>
                  <TableCell
                    detail={`${entry.attempt_count} ${pluralize(entry.attempt_count, 'attempt')}`}
                  >
                    <Link to={href} state={{ from }} variant="subtle">
                      {run.target ?? run.legacy_source?.split('/').pop() ?? 'Historical run'}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <span title={run.health_detail ?? undefined}>
                      <StatusBadge tone={liveStatusTone(runState(run))}>
                        {optimizerStates[runState(run)]}
                      </StatusBadge>
                    </span>
                  </TableCell>
                  <TableCell>
                    <Link to={href} state={{ from }} variant="subtle">
                      {outcomeLabel(entry)}
                    </Link>
                  </TableCell>
                  <TableCell>{formatDuration(run.elapsed_seconds)}</TableCell>
                  <TableCell>{formatShortDateTime(run.started_at, 'Not recorded')}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </ScrollArea>
    </Surface>
  );
}

// --------------------------------------------------------------------------- #
// Workflow, running targets and paginated history
// --------------------------------------------------------------------------- #
/** Server-filtered, paged history with research outcomes: the optimizer's Runs extension. */
export function OptimizerHistory() {
  const [params, setParams] = useSearchParams();
  const filters = {
    query: params.get('query') ?? '',
    status: params.get('status') ?? '',
    since: params.get('since') ?? '',
    offset: Math.max(0, Number(params.get('offset')) || 0),
  };
  const setFilters = (values: typeof filters) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(values)) {
      if (value) next.set(key, String(value));
      else next.delete(key);
    }
    setParams(next, { replace: true });
  };
  const limit = 20;
  const query = useOptimizerHistory({ mode: 'all', limit, ...filters });
  // Placeholder data keeps the previous total, so Pagination stays mounted while the next page loads.
  const total = query.data?.total ?? null;
  const update = (name: 'query' | 'status' | 'since', value: string) =>
    setFilters({ ...filters, [name]: value, offset: 0 });
  return (
    <TerminalSection title="Search all runs">
      <Cluster gap="heading">
        <Input
          type="search"
          aria-label="Search target or version"
          placeholder="Search target or version…"
          value={filters.query}
          onChange={(event) => update('query', event.target.value)}
        />
        <SelectControl
          ariaLabel="Execution status"
          value={filters.status}
          onValueChange={(value) => update('status', value)}
          options={[
            { value: '', label: 'All statuses' },
            ...Object.entries(optimizerStates)
              .filter(([value]) => value !== 'unresponsive')
              .map(([value, label]) => ({ value, label })),
          ]}
        />
        <Field label="Since" htmlFor="optimizer-since" layout="inline">
          <Input
            id="optimizer-since"
            type="date"
            aria-label="Runs started since"
            title="Started on or after this date (UTC)"
            value={filters.since}
            onChange={(event) => update('since', event.target.value)}
          />
        </Field>
      </Cluster>
      {query.isError && (
        <StateMessage state="error" compact>
          History unavailable{query.data ? ' · stale data' : ''}.
        </StateMessage>
      )}
      {isLoadingData(query) ? (
        <LoadingSkeleton variant="table" count={5} />
      ) : query.data?.entries.length ? (
        <RunList entries={query.data.entries} />
      ) : query.data ? (
        <EmptyState title="No matching runs." />
      ) : null}
      {total !== null ? (
        <Pagination
          page={Math.floor(filters.offset / limit) + 1}
          pageCount={Math.max(1, Math.ceil(total / limit))}
          onPageChange={(next) => setFilters({ ...filters, offset: (next - 1) * limit })}
          label={
            total
              ? `${filters.offset + 1}–${Math.min(filters.offset + limit, total)} of ${total}`
              : '0 runs'
          }
        />
      ) : null}
    </TerminalSection>
  );
}
