/**
 * Strategy family evolution: the family's versions as a subway map (the baseline chain is
 * the trunk, every other version hangs off its parent; ringed = selected as baseline),
 * drawn horizontally (default) or vertically (newest first, one question per row), then the selected
 * version's ancestry back to the first version as a list of question → finding rows, and the
 * design-space dimensions the selected version decided. The selection lives in the `v` query
 * parameter (default: the latest version) and the layout in `layout`.
 *
 * USAGE:
 *   <StrategyEvolution strategyType="example"
 *                      dimensionHref={(anchor) => `/strategies/example/design-space#${anchor}`} />
 *   <StrategyEvolution strategyType={signalFamily} pkg="signals"
 *                      recordHref={(v) => `/signals/${signalFamily}/${v}`} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { LineageGraph, type LineageGraphOrientation } from '@quant-factory/qf-ui/charts/lineage';
import {
  type StrategyLineageRow,
  useStrategyFamilyVersions,
} from '@/lib/api/strategy-version-records';
import type { FamilyPackage } from '@/lib/strategy-docs';
import {
  Badge,
  Cluster,
  humanize,
  IndexBar,
  IndexList,
  Link,
  QueryState,
  Stack,
  statusTone,
  TerminalSection,
  Text,
  useSearchParamState,
} from '@/ui';
import { dimensionAnchor, useDesignDimensions } from './StrategyDesignSpace';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Selected version first, then each parent back to the root; stops on a missing or repeated parent. */
function ancestry(rows: Map<string, StrategyLineageRow>, selected: string): StrategyLineageRow[] {
  const path: StrategyLineageRow[] = [];
  let row = rows.get(selected);
  while (row && !path.includes(row)) {
    path.push(row);
    row = row.parent ? rows.get(row.parent) : undefined;
  }
  return path;
}

function signed(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(3)}`;
}

/** `Δ +0.120 [−0.300, +0.540] · sortino 365`, or null when the version records no difference. */
function headlineText(row: StrategyLineageRow): string | null {
  const { difference, interval, metric } = row.headline ?? {};
  if (typeof difference !== 'number') return null;
  const bounds =
    Array.isArray(interval) && interval.length === 2 && interval.every((x) => typeof x === 'number')
      ? ` [${signed(interval[0])}, ${signed(interval[1])}]`
      : '';
  const label = typeof metric === 'string' ? ` · ${humanize(metric)}` : '';
  return `Δ ${signed(difference)}${bounds}${label}`;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StrategyEvolution({
  strategyType,
  dimensionHref = (anchor) => `#${anchor}`,
  pkg = 'strategies',
  recordHref = (version) => `/strategies/${strategyType}/${version}?view=details`,
}: {
  strategyType: string;
  /** Link to a design-space dimension row; defaults to an anchor on the same page. */
  dimensionHref?: (anchor: string) => string;
  /** Package whose extensions hold the family; default strategies. */
  pkg?: FamilyPackage;
  /** Link to a version's record page; defaults to the strategy version's Details view. */
  recordHref?: (version: string) => string;
}) {
  const query = useStrategyFamilyVersions(strategyType, pkg);
  const dimensions = useDesignDimensions(strategyType, pkg);
  const [selectedParam, setSelected] = useSearchParamState('v', '', { replace: true });
  const [layoutParam, setLayout] = useSearchParamState('layout', 'horizontal', { replace: true });
  const orientation: LineageGraphOrientation =
    layoutParam === 'horizontal' ? 'horizontal' : 'vertical';
  const rows = query.data ?? [];
  const byVersion = new Map(rows.map((row) => [row.version, row]));
  const selected = byVersion.has(selectedParam) ? selectedParam : (rows.at(-1)?.version ?? '');
  const path = ancestry(byVersion, selected);
  const children = rows.filter((row) => row.parent === selected);
  const decided = dimensions.filter((dimension) => dimension.versions.includes(selected));
  const counts = new Map<string, number>();
  for (const row of rows)
    counts.set(row.status ?? 'unknown', (counts.get(row.status ?? 'unknown') ?? 0) + 1);
  // Relative, so the selection stays on whichever page hosts the view.
  const familyHref = (version: string) => `?v=${version}`;

  // The section frame stays put; only its body waits for the records.
  const loaded = rows.length > 0 && !query.isPlaceholderData;

  return (
    <>
      <TerminalSection
        title="evolution"
        right={
          <Cluster gap="stack">
            {[...counts].map(([status, count]) => (
              <Badge key={status} tone={statusTone(status)} size="sm">
                {`${count} ${humanize(status).toLowerCase()}`}
              </Badge>
            ))}
          </Cluster>
        }
      >
        <QueryState
          query={query}
          skeleton="table"
          count={3}
          isEmpty={rows.length === 0}
          emptyTitle="No version records"
          emptyHint="This family has no VERSION.toml records"
        >
          <Stack gap="heading">
            <LineageGraph
              label="Versions"
              orientation={orientation}
              onOrientationChange={setLayout}
              items={rows.map((row) => ({
                id: row.version,
                parentId: row.parent,
                label: row.version,
                tone: statusTone(row.status ?? 'unknown'),
                marked: Boolean(row.baseline_selected_at),
                description: row.question ?? undefined,
                title: `${row.version} · ${row.status ?? 'unknown'}${row.baseline_selected_at ? ' · ★ baseline' : ''}${row.question ? ` — ${row.question}` : ''}`,
              }))}
              selectedId={selected}
              onSelect={setSelected}
            />
            <Cluster gap="stack">
              <Text size="sm" tone="muted">
                {`${selected} · ${path.length - 1} ancestors · children:`}
              </Text>
              {children.length > 0 ? (
                children.map((child) => (
                  <Link key={child.version} to={familyHref(child.version)} variant="subtle">
                    {child.version}
                  </Link>
                ))
              ) : (
                <Text size="sm" tone="muted">
                  none
                </Text>
              )}
              <Link to={recordHref(selected)}>{`Open ${selected} record`}</Link>
            </Cluster>
            {decided.length > 0 ? (
              <Cluster gap="stack">
                <Text size="sm" tone="muted">
                  decided:
                </Text>
                {decided.map((dimension) => (
                  <Link
                    key={dimension.slug}
                    to={dimensionHref(dimensionAnchor(dimension.slug))}
                    variant="subtle"
                  >
                    {`${dimension.name} (${dimension.status})`}
                  </Link>
                ))}
              </Cluster>
            ) : null}
          </Stack>
        </QueryState>
      </TerminalSection>
      {loaded ? (
        <TerminalSection title={`lineage of ${selected}`}>
          <IndexList>
            {path.map((row) => (
              <IndexBar
                key={row.version}
                href={row.version === selected ? undefined : familyHref(row.version)}
                index={row.version.slice(1)}
                title={row.question ?? row.version}
                description={row.finding ?? 'No finding recorded'}
                wrap
                status={
                  <Badge tone={statusTone(row.status ?? 'unknown')} size="sm">
                    {row.status ?? 'unknown'}
                  </Badge>
                }
                metrics={headlineText(row) ?? undefined}
                tags={row.baseline_selected_at ? <Badge size="sm">★ baseline</Badge> : undefined}
              />
            ))}
          </IndexList>
        </TerminalSection>
      ) : null}
    </>
  );
}
