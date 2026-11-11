/**
 * Strategy version Details tab — the record every version of every family carries. The
 * record documents are the reading column; a dense Record rail beside them holds the VERSION.toml
 * facts, the strategies AGENTS.md §5 core for newer versions (question, parent, run_id, [headline],
 * [checks]) when present, and the family-specific recorded fields behind a disclosure.
 *
 * USAGE:
 *   <StrategyVersionDetails strategyType="example" memoryVersion="v002" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useState } from 'react';
import { useStrategyVersionRecords } from '@/lib/api/strategy-version-records';
import { SanitizedMarkdown } from '@/pages/docs/SanitizedMarkdown';
import {
  Badge,
  Cluster,
  Disclosure,
  DocumentLayout,
  EmptyState,
  ErrorPanel,
  humanize,
  isLoadingData,
  Link,
  LoadingSkeleton,
  pluralize,
  RecordList,
  Section,
  SegmentedControl,
  Stack,
  StatGrid,
  StatItem,
  Text,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

/** Keys every version records (strategies AGENTS.md §5); shown as facts, not in the recorded-field list. */
const SHARED_KEYS = [
  'version',
  'phase',
  'status',
  'backtest_run_at',
  'parent',
  'question',
  'finding',
  'baseline_selected_at',
  'run_id',
  'headline',
  'checks',
];

const DAY_MS = 86_400_000;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function text(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null;
}

function forwardTestLabel(backtestRunAt: string | null): string {
  const start = backtestRunAt ? Date.parse(backtestRunAt) : Number.NaN;
  if (!Number.isFinite(start)) return 'None recorded';
  const days = Math.max(0, Math.floor((Date.now() - start) / DAY_MS));
  return `${days.toLocaleString()} ${pluralize(days, 'day')}`;
}

function table(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function reading(value: unknown): string {
  if (typeof value === 'number')
    return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  if (Array.isArray(value) && value.length === 2) return `[${value.map(reading).join(', ')}]`;
  return text(value) ?? '—';
}

function formatRunAt(value: string | null): string {
  return value ? value.replace('T', ' ').replace('Z', ' UTC') : 'Not recorded';
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StrategyVersionDetails({
  strategyType,
  memoryVersion,
}: {
  strategyType: string;
  memoryVersion: string;
}) {
  const query = useStrategyVersionRecords(strategyType, memoryVersion);
  const [documentName, setDocumentName] = useState<string | null>(null);

  if (isLoadingData(query)) return <LoadingSkeleton variant="line" count={6} />;
  if (query.error || !query.data) {
    return (
      <ErrorPanel
        message={query.error?.message ?? 'Version records are unavailable'}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const { record, documents, path } = query.data;
  const status = text(record.status);
  const phase = text(record.phase);
  const backtestRunAt = text(record.backtest_run_at);
  const question = text(record.question);
  const finding = text(record.finding);
  const baselineSelectedAt = text(record.baseline_selected_at);
  const parent = text(record.parent);
  const runId = text(record.run_id);
  const headline = table(record.headline);
  const checks = Object.entries(table(record.checks) ?? {}).filter(
    (entry): entry is [string, boolean] => typeof entry[1] === 'boolean',
  );
  const difference = typeof headline?.difference === 'number' ? headline.difference : null;
  const recordedKeys = Object.keys(record).filter((key) => !SHARED_KEYS.includes(key));
  const document = documents.find((item) => item.name === documentName) ?? documents[0] ?? null;

  const passed = checks.filter(([, ok]) => ok).length;
  // Failures lead so a broken check is never buried in a long passing row.
  const orderedChecks = [...checks].sort(([, a], [, b]) => Number(a) - Number(b));

  const recordSection = (
    <Section
      title="Record"
      actions={
        checks.length > 0 ? (
          <Badge tone={passed === checks.length ? 'success' : 'critical'} size="md">
            {`${passed} of ${checks.length} checks passed`}
          </Badge>
        ) : undefined
      }
    >
      <Stack gap="heading">
        {question ? (
          <Text as="p" size="sm" tone="muted">
            {question}
          </Text>
        ) : null}
        {finding ? (
          <Text as="p" size="sm">
            {finding}
          </Text>
        ) : null}
        <StatGrid variant="rows" aria-label="Version facts">
          <StatItem label="Status" value={status ? humanize(status) : '—'} />
          <StatItem label="Phase" value={phase ? humanize(phase) : '—'} />
          <StatItem
            label="Parent"
            value={
              parent && /^v\d{3}$/.test(parent) ? (
                <Link to={`/strategies/${strategyType}/${parent}?view=details`}>{parent}</Link>
              ) : (
                (parent ?? 'Not recorded')
              )
            }
          />
          {baselineSelectedAt ? (
            <StatItem label="Selected as baseline" value={formatRunAt(baselineSelectedAt)} />
          ) : null}
          <StatItem label="Backtest run" value={formatRunAt(backtestRunAt)} />
          <StatItem label="Forward test" value={forwardTestLabel(backtestRunAt)} />
          <StatItem label="Run" value={runId ?? path} title={runId ?? path} />
        </StatGrid>
        {headline ? (
          <StatGrid
            variant="rows"
            aria-label={`Headline result · ${humanize(text(headline.metric) ?? 'metric')}`}
          >
            <StatItem
              label={`${humanize(text(headline.metric) ?? 'Metric')} control`}
              value={reading(headline.control)}
            />
            <StatItem label="Candidate" value={reading(headline.candidate)} />
            <StatItem
              label="Difference"
              value={reading(headline.difference)}
              tone={difference == null ? 'default' : difference > 0 ? 'success' : 'critical'}
            />
            <StatItem label="Interval" value={reading(headline.interval)} />
          </StatGrid>
        ) : null}
        {checks.length > 0 ? (
          <Cluster gap="stack" aria-label="Checks">
            {orderedChecks.map(([name, ok]) => (
              <Badge key={name} tone={ok ? 'success' : 'critical'} size="sm">
                {`${ok ? '✓' : '✗'} ${humanize(name)}`}
              </Badge>
            ))}
          </Cluster>
        ) : null}
        {recordedKeys.length > 0 ? (
          <Disclosure
            summary="Recorded fields"
            meta={`${recordedKeys.length} fields`}
            variant="row"
          >
            <RecordList
              record={record}
              omit={SHARED_KEYS}
              aria-label="Recorded VERSION.toml fields"
            />
          </Disclosure>
        ) : null}
      </Stack>
    </Section>
  );

  return (
    <DocumentLayout aside={recordSection}>
      <Section
        title="Documents"
        actions={
          documents.length > 1 && document ? (
            <SegmentedControl
              ariaLabel="Version document"
              size="sm"
              options={documents.map((item) => ({
                value: item.name,
                label: humanize(item.name.replace(/\.md$/, '')),
              }))}
              value={document.name}
              onValueChange={setDocumentName}
            />
          ) : undefined
        }
      >
        {document ? (
          <SanitizedMarkdown
            page={{
              path: `${path}/${document.name}`,
              title: document.name,
              markdown: document.markdown,
              modified: null,
              generated: false,
            }}
          />
        ) : (
          <EmptyState title="No record documents" hint={`Nothing found in ${path}`} />
        )}
      </Section>
    </DocumentLayout>
  );
}
