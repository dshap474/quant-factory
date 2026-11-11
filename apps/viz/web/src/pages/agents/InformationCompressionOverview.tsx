/** Information Compression grouped run history with preserved attempts.
 * USAGE: <InformationCompressionHistory />
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
// Imports and labels
// --------------------------------------------------------------------------- #
import { Fragment, useState } from 'react';
import {
  type InformationCompressionEntry,
  useInformationCompressionAttempts,
  useInformationCompressionHistory,
} from '@/lib/api/information-compression';
import {
  Button,
  Cluster,
  EmptyState,
  Field,
  formatDuration,
  formatShortDateTime,
  Input,
  isLoadingData,
  LoadingSkeleton,
  liveStatusTone,
  Pagination,
  pluralize,
  ScrollArea,
  SelectControl,
  Stack,
  StateMessage,
  StatusBadge,
  Surface,
  TerminalSection,
  Text,
  usePagination,
} from '@/ui';
import { RunExpansion } from './RunExpansion';
import { runState } from './runs';

const ATTEMPTS_PAGE_SIZE = 10;

const states: Record<string, string> = {
  succeeded: 'Completed',
  starting: 'Starting',
  running: 'Running',
  failed: 'Failed',
  cancelled: 'Cancelled',
  interrupted: 'Interrupted',
  unknown: 'Unknown',
  unresponsive: 'Unresponsive',
};

// --------------------------------------------------------------------------- #
// Preserved attempts and shared step evidence
// --------------------------------------------------------------------------- #
function Attempts({ entry }: { entry: InformationCompressionEntry }) {
  const [selected, setSelected] = useState<string | null>(null);
  // The server owns the total, so the page stays unclamped (count undefined).
  const pages = usePagination({ count: undefined, pageSize: ATTEMPTS_PAGE_SIZE });
  const query = useInformationCompressionAttempts(entry.run.id, pages.start);
  // Placeholder data keeps the previous total, so Pagination stays mounted while the next page loads.
  const total = query.data?.total ?? null;
  const runs = query.data?.runs ?? [];
  const run = runs.find((item) => item.id === selected) ?? runs[0];
  return (
    <Surface padding="md">
      <Text as="h3" variant="label">
        Attempts · {entry.attempt_count}
      </Text>
      {query.isError && (
        <StateMessage state="error" compact>
          Attempts unavailable{query.data ? ' · stale data' : ''}.
        </StateMessage>
      )}
      {isLoadingData(query) ? (
        <LoadingSkeleton variant="line" label="Loading attempts" />
      ) : (
        <Cluster gap="stack">
          {runs.map((item) => (
            <Button
              key={item.id}
              variant="control"
              aria-pressed={run?.id === item.id}
              onClick={() => setSelected(item.id)}
            >
              {states[runState(item)]} · {formatShortDateTime(item.started_at, 'Not recorded')} ·{' '}
              {formatDuration(item.elapsed_seconds)}
            </Button>
          ))}
        </Cluster>
      )}
      {total !== null && total > ATTEMPTS_PAGE_SIZE && (
        <Pagination
          page={pages.page}
          pageCount={Math.ceil(total / ATTEMPTS_PAGE_SIZE)}
          onPageChange={(next) => {
            pages.setPage(next);
            setSelected(null);
          }}
        />
      )}
      {!isLoadingData(query) && run && (
        <>
          <Text as="p" variant="data" tone="muted" className="break-all">
            Attempt {run.id}
            {run.resumed_from_run_id ? ` · resumed from ${run.resumed_from_run_id}` : ''}
          </Text>
          <ScrollArea maxHeight="28rem">
            <RunExpansion key={run.id} run={run} />
          </ScrollArea>
        </>
      )}
    </Surface>
  );
}

function RunList({ entries }: { entries: InformationCompressionEntry[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <Surface padding="none" clip>
      <ScrollArea axis="x">
        <Table density="dense" className="min-w-[680px]">
          <TableHeader>
            <TableRow>
              <TableHead>Extraction run</TableHead>
              <TableHead>Execution</TableHead>
              <TableHead>Latest activity</TableHead>
              <TableHead>Latest duration</TableHead>
              <TableHead>Started</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map((entry) => {
              const { run } = entry;
              const open = expanded === run.id;
              const activity =
                run.active_steps.find((step) => step.activity)?.activity ?? run.last_step?.activity;
              return (
                <Fragment key={run.id}>
                  <TableRow>
                    <TableCell
                      detail={`${entry.attempt_count} ${pluralize(entry.attempt_count, 'attempt')}`}
                    >
                      <Button
                        className="flex items-center gap-2 text-left"
                        aria-expanded={open}
                        onClick={() => setExpanded(open ? null : run.id)}
                      >
                        <span aria-hidden="true">{open ? '▾' : '▸'}</span>
                        {run.target ?? run.id}
                      </Button>
                    </TableCell>
                    <TableCell>
                      <StatusBadge tone={liveStatusTone(runState(run))}>
                        {states[runState(run)]}
                      </StatusBadge>
                    </TableCell>
                    <TableCell>
                      <span title={activity ?? undefined} className="block max-w-[28ch] truncate">
                        {activity ?? '—'}
                      </span>
                    </TableCell>
                    <TableCell>{formatDuration(run.elapsed_seconds)}</TableCell>
                    <TableCell>{formatShortDateTime(run.started_at, 'Not recorded')}</TableCell>
                  </TableRow>
                  {open && (
                    <TableRow data-table-group="">
                      <TableCell colSpan={5} fullBleed>
                        <Attempts entry={entry} />
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      </ScrollArea>
    </Surface>
  );
}

// --------------------------------------------------------------------------- #
// Paginated history
// --------------------------------------------------------------------------- #
/** Server-filtered, paged history grouped by target with preserved attempts: the IC Runs extension. */
export function InformationCompressionHistory() {
  const [filters, setFilters] = useState({ query: '', status: '', since: '', offset: 0 });
  const limit = 20;
  const query = useInformationCompressionHistory({ mode: 'all', limit, ...filters });
  const total = query.data?.total ?? null;
  const update = (name: 'query' | 'status' | 'since', value: string) =>
    setFilters((current) => ({ ...current, [name]: value, offset: 0 }));
  return (
    <TerminalSection title="Search all runs">
      <Cluster gap="heading">
        <Input
          type="search"
          aria-label="Search extraction runs"
          placeholder="Search extraction runs…"
          value={filters.query}
          onChange={(event) => update('query', event.target.value)}
        />
        <SelectControl
          ariaLabel="Execution status"
          value={filters.status}
          onValueChange={(value) => update('status', value)}
          options={[
            { value: '', label: 'All statuses' },
            ...Object.entries(states)
              .filter(([value]) => value !== 'unresponsive')
              .map(([value, label]) => ({ value, label })),
          ]}
        />
        <Field label="Since" htmlFor="information-compression-since" layout="inline">
          <Input
            id="information-compression-since"
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
      <Stack gap="block">
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
      </Stack>
    </TerminalSection>
  );
}
