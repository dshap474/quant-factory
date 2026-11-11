/**
 * Strategy family design space: the family's `optimization/DESIGN-SPACE.md` rendered from the
 * repository. The `## Dimensions` table becomes a filterable table with a status badge per
 * dimension and links from each deciding version to the Evolution view, or (`?view=graph`) a
 * network of dimensions linked to their deciding versions: clicking a node (`?node=`) focuses
 * it and opens its detail below. `## Open questions` and the intro render as Markdown.
 * `#dimension-<slug>` selects and scrolls to a dimension in the table.
 *
 * USAGE:
 *   <StrategyDesignSpace strategyType="example"
 *                        versionHref={(v) => `/strategies/example/evolution?v=${v}`} />
 *   <StrategyDesignSpace strategyType={signalFamily} pkg="signals" versionHref={(v) => `?v=${v}`} />
 *   const dimensions = useDesignDimensions('example');   // [] when none
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { NetworkGraph, type NetworkGraphNode } from '@quant-factory/qf-ui/charts/network';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@quant-factory/qf-ui/tables';
import { useEffect, useMemo } from 'react';
import { useLocation } from 'react-router';
import { type FamilyPackage, familyDocPath, hasFamilyDoc, useFamilyDoc } from '@/lib/strategy-docs';
import { SanitizedMarkdown } from '@/pages/docs/SanitizedMarkdown';
import {
  Badge,
  Button,
  Cluster,
  Link,
  LoadingSkeleton,
  pluralize,
  ScrollArea,
  SegmentedControl,
  Stack,
  Surface,
  TerminalSection,
  Text,
  type Tone,
  useSearchParamState,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Parsing
// --------------------------------------------------------------------------- #

const DOC = 'optimization/DESIGN-SPACE.md';
const STATUSES = ['locked', 'open', 'closed'] as const;
type Status = (typeof STATUSES)[number];
const STATUS_TONE: Record<Status, Tone> = { locked: 'success', open: 'warning', closed: 'neutral' };

export interface DesignDimension {
  slug: string;
  name: string;
  status: Status;
  /** The full status cell, e.g. `locked (Sunday), open why`. */
  statusText: string;
  choice: string;
  versions: string[];
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

export function dimensionAnchor(slug: string): string {
  return `dimension-${slug}`;
}

/** `v002–v004, v007` → v002, v003, v004, v007. */
function versionsIn(text: string): string[] {
  const found: string[] = [];
  for (const [, start = '', end] of text.matchAll(/v(\d{3})(?:\s*[–-]\s*v?(\d{3}))?/g)) {
    const last = Number(end ?? start);
    for (let n = Number(start); n <= last; n += 1) found.push(`v${String(n).padStart(3, '0')}`);
  }
  return found;
}

function sections(markdown: string): { intro: string; byName: Map<string, string> } {
  const [head = '', ...blocks] = markdown.split(/^## /m);
  const byName = new Map<string, string>();
  for (const block of blocks) {
    const newline = block.indexOf('\n');
    byName.set(block.slice(0, newline).trim(), block.slice(newline + 1).trim());
  }
  return { intro: head.replace(/^# .+$/m, '').trim(), byName };
}

/** Rows of the `## Dimensions` table: Dimension | Status | Choice | Deciding versions. */
function parseDimensions(section: string): DesignDimension[] {
  const rows = section
    .split('\n')
    .filter((line) => line.startsWith('|'))
    .slice(2);
  return rows.flatMap((line) => {
    const [name = '', statusText = '', choice = '', versions = ''] = line
      .replace(/^\||\|$/g, '')
      .split(' | ')
      .map((cell) => cell.trim());
    const status = STATUSES.find((value) => statusText.startsWith(value));
    if (!name || !status) return [];
    return [
      {
        slug: slugify(name),
        name: name.replaceAll('`', ''),
        status,
        statusText,
        choice: choice.replaceAll('`', ''),
        versions: versionsIn(versions),
      },
    ];
  });
}

export function useDesignDimensions(
  strategyType: string,
  pkg: FamilyPackage = 'strategies',
): DesignDimension[] {
  const markdown = useFamilyDoc(strategyType, DOC, pkg);
  return markdown ? parseDimensions(sections(markdown).byName.get('Dimensions') ?? '') : [];
}

// --------------------------------------------------------------------------- #
// Graph
// --------------------------------------------------------------------------- #

/** Dimensions (circles toned by status) linked to their deciding versions (diamonds sized by how many they decided). */
function useDesignNetwork(dimensions: DesignDimension[]) {
  return useMemo(() => {
    const decided = new Map<string, number>();
    for (const row of dimensions)
      for (const version of new Set(row.versions))
        decided.set(version, (decided.get(version) ?? 0) + 1);
    const nodes: NetworkGraphNode[] = [
      ...dimensions.map((row) => ({
        id: row.slug,
        label: row.name,
        tone: STATUS_TONE[row.status],
        title: `${row.name} (${row.statusText})`,
      })),
      ...[...decided].sort().map(([version, count]) => ({
        id: version,
        label: version,
        kind: 'secondary' as const,
        weight: count,
        labeled: count >= 4,
        title: `${version}: decided ${count} ${pluralize(count, 'dimension')}`,
      })),
    ];
    const links = dimensions.flatMap((row) =>
      [...new Set(row.versions)].map((version) => ({ source: row.slug, target: version })),
    );
    return { nodes, links };
  }, [dimensions]);
}

function GraphDetail({
  dimensions,
  selected,
  onSelect,
  versionHref,
}: {
  dimensions: DesignDimension[];
  selected: string;
  onSelect: (id: string) => void;
  versionHref: (version: string) => string;
}) {
  const row = dimensions.find((dimension) => dimension.slug === selected);
  if (row)
    return (
      <Stack gap="stack">
        <Cluster gap="stack">
          <Text weight="medium">{row.name}</Text>
          <Badge tone={STATUS_TONE[row.status]} size="sm">
            {row.statusText}
          </Badge>
        </Cluster>
        <Text>{row.choice}</Text>
        <Cluster gap="stack">
          <Text tone="muted">deciding versions:</Text>
          {row.versions.map((version) => (
            <Link key={version} to={versionHref(version)} variant="subtle">
              {version}
            </Link>
          ))}
        </Cluster>
      </Stack>
    );
  const decided = dimensions.filter((dimension) => dimension.versions.includes(selected));
  return (
    <Stack gap="stack">
      <Cluster gap="stack">
        <Link to={versionHref(selected)}>{selected}</Link>
        <Text tone="muted">{`decided ${decided.length} ${pluralize(decided.length, 'dimension')}`}</Text>
      </Cluster>
      <Cluster gap="stack">
        {decided.map((dimension) => (
          <Button key={dimension.slug} size="sm" onClick={() => onSelect(dimension.slug)}>
            {`${dimension.name} (${dimension.status})`}
          </Button>
        ))}
      </Cluster>
    </Stack>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StrategyDesignSpace({
  strategyType,
  versionHref,
  pkg = 'strategies',
}: {
  strategyType: string;
  versionHref: (version: string) => string;
  /** Package whose extensions hold the family; default strategies. */
  pkg?: FamilyPackage;
}) {
  const markdown = useFamilyDoc(strategyType, DOC, pkg);
  const [statusParam, setStatus] = useSearchParamState('status', 'all', { replace: true });
  const [view, setView] = useSearchParamState('view', 'table', { replace: true });
  const [node, setNode] = useSearchParamState('node', '', { replace: true });
  const { hash } = useLocation();
  const selected = hash.slice(1);

  useEffect(() => {
    if (markdown && selected)
      document.getElementById(selected)?.scrollIntoView({ block: 'center' });
  }, [markdown, selected]);

  const dimensions = useMemo(
    () => (markdown ? parseDimensions(sections(markdown).byName.get('Dimensions') ?? '') : []),
    [markdown],
  );
  const shown = useMemo(
    () =>
      statusParam === 'all' ? dimensions : dimensions.filter((row) => row.status === statusParam),
    [dimensions, statusParam],
  );
  const network = useDesignNetwork(shown);

  if (!hasFamilyDoc(strategyType, DOC, pkg))
    return <Text tone="muted">{`No ${DOC} for ${strategyType}.`}</Text>;
  if (markdown === null) return <LoadingSkeleton variant="line" count={4} />;

  const { intro, byName } = sections(markdown);
  const questions = byName.get('Open questions') ?? '';
  const focusId = network.nodes.some((item) => item.id === node) ? node : '';
  const count = (status: Status) => dimensions.filter((row) => row.status === status).length;
  const page = (title: string, body: string) => ({
    path: familyDocPath(strategyType, DOC, pkg),
    title,
    markdown: body,
    modified: null,
    generated: false,
  });

  return (
    <>
      <TerminalSection
        title="dimensions"
        right={
          <Cluster gap="stack">
            <SegmentedControl
              ariaLabel="Design space view"
              size="sm"
              options={[
                { value: 'graph', label: 'Graph' },
                { value: 'table', label: 'Table' },
              ]}
              value={view}
              onValueChange={setView}
            />
            <SegmentedControl
              ariaLabel="Dimension status"
              size="sm"
              options={[
                { value: 'all', label: `All ${dimensions.length}` },
                ...STATUSES.map((status) => ({
                  value: status,
                  label: `${status} ${count(status)}`,
                })),
              ]}
              value={statusParam}
              onValueChange={setStatus}
            />
          </Cluster>
        }
      >
        {view === 'graph' ? (
          <Stack gap="heading">
            <Surface padding="sm">
              <NetworkGraph
                label="Design dimensions and their deciding versions"
                nodes={network.nodes}
                links={network.links}
                selectedId={focusId || null}
                onSelect={(id) => setNode(id ?? '')}
              />
            </Surface>
            {focusId ? (
              <GraphDetail
                dimensions={shown}
                selected={focusId}
                onSelect={setNode}
                versionHref={versionHref}
              />
            ) : (
              <Text tone="muted">
                Click a dimension or version to focus it. Larger diamonds decided more dimensions at
                once.
              </Text>
            )}
          </Stack>
        ) : (
          <Surface padding="none" clip>
            <ScrollArea axis="x" label="Design dimensions">
              <Table aria-label="Design dimensions">
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Dimension</TableHead>
                    <TableHead scope="col">Status</TableHead>
                    <TableHead scope="col">Current choice or what was ruled out</TableHead>
                    <TableHead scope="col">Deciding versions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shown.map((row) => (
                    <TableRow
                      key={row.slug}
                      id={dimensionAnchor(row.slug)}
                      aria-selected={selected === dimensionAnchor(row.slug) || undefined}
                    >
                      <TableCell wrap>{row.name}</TableCell>
                      <TableCell wrap>
                        <Badge tone={STATUS_TONE[row.status]} size="sm">
                          {row.statusText}
                        </Badge>
                      </TableCell>
                      <TableCell wrap>{row.choice}</TableCell>
                      <TableCell wrap>
                        <Cluster gap="stack">
                          {row.versions.map((version) => (
                            <Link key={version} to={versionHref(version)} variant="subtle">
                              {version}
                            </Link>
                          ))}
                        </Cluster>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ScrollArea>
          </Surface>
        )}
      </TerminalSection>
      {questions ? (
        <TerminalSection title="open questions">
          <SanitizedMarkdown page={page('Open questions', questions)} />
        </TerminalSection>
      ) : null}
      {intro ? (
        <TerminalSection title="about this map">
          <SanitizedMarkdown page={page('Design space', intro)} />
        </TerminalSection>
      ) : null}
    </>
  );
}
