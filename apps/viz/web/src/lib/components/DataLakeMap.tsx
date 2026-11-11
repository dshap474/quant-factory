/**
 * Data landing map: lake size by layer, timeframe and provider, plus totals and freshness.
 *
 * USAGE:
 *   <DataLakeMap />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Treemap, type TreemapNode } from '@quant-factory/qf-ui/charts/renderers';
import { chartColor } from '@quant-factory/qf-ui/charts/theme';
import { DataTable, type DataTableColumn } from '@quant-factory/qf-ui/tables';

import { type CatalogOverviewNode, useCatalogOverview } from '@/lib/api/catalog';
import { Inset, QueryState, ScrollArea, Section, Stack, StatGrid, StatItem, Timestamp } from '@/ui';
import { compareResolutions } from './catalog-tree';
import { isRawLike } from './logical-catalog-model';

// --------------------------------------------------------------------------- #
// Model
// --------------------------------------------------------------------------- #

// Muted fills keep the light tile labels legible.
const LAYER_COLOR: Record<string, string> = {
  raw: chartColor(2, 0.4),
  derived: chartColor(1, 0.4),
};

interface LakeRow {
  path: string;
  layer: string;
  timeframe: string;
  group: string;
  group_label: string;
  size_mb: number;
  files: number;
  updated_at: string | null;
}

/** `53.4 GB`, `412 MB`, `0.3 MB`, `<0.1 MB`. */
export function formatLakeSize(sizeMb: number): string {
  if (sizeMb >= 1024) return `${(sizeMb / 1024).toFixed(1)} GB`;
  if (sizeMb >= 10) return `${Math.round(sizeMb)} MB`;
  if (sizeMb >= 0.1) return `${sizeMb.toFixed(1)} MB`;
  return sizeMb > 0 ? '<0.1 MB' : '0 MB';
}

function toTreemap(node: CatalogOverviewNode, color?: string): TreemapNode {
  const children = node.children.filter((child) => child.size_mb > 0);
  return {
    id: node.path,
    name: node.label ?? node.name,
    value: node.size_mb,
    color,
    detail: `${node.parquet_files.toLocaleString('en-US')} files`,
    children: children.length ? children.map((child) => toTreemap(child)) : undefined,
  };
}

/** Provider-first raw trees and resolution-first trees keep the same presentation. */
function lakeRows(branches: readonly CatalogOverviewNode[]): LakeRow[] {
  const rows: LakeRow[] = [];
  const append = (
    layer: string,
    timeframe: string,
    group: CatalogOverviewNode,
    prefix?: CatalogOverviewNode,
  ) => {
    if (!group.parquet_files) return;
    rows.push({
      path: group.path,
      layer,
      timeframe,
      group: prefix ? `${prefix.name}/${group.name}` : group.name,
      group_label: prefix
        ? `${prefix.label ?? prefix.name} / ${group.label ?? group.name}`
        : (group.label ?? group.name),
      size_mb: group.size_mb,
      files: group.parquet_files,
      updated_at: group.updated_at,
    });
  };
  const isResolution = (name: string) => /^(\d+[smhdw]|tick)$/.test(name);
  for (const layer of branches) {
    for (const folder of [...layer.children].sort((a, b) => compareResolutions(a.name, b.name))) {
      if (!isRawLike(layer.name) || isResolution(folder.name)) {
        for (const group of folder.children) append(layer.name, folder.name, group);
      } else {
        const resolutions = folder.children.filter((child) => isResolution(child.name));
        if (resolutions.length || !folder.children.length) {
          append(layer.name, resolutions.map((child) => child.name).join(', ') || '—', folder);
        } else {
          for (const group of folder.children) append(layer.name, '—', group, folder);
        }
      }
    }
  }
  return rows;
}

const COLUMNS: readonly DataTableColumn<LakeRow>[] = [
  { key: 'group_label', header: 'Provider / group' },
  { key: 'layer', header: 'Layer' },
  { key: 'timeframe', header: 'Folder' },
  {
    key: 'size_mb',
    header: 'Size',
    kind: 'number',
    format: (value) => formatLakeSize(Number(value)),
  },
  { key: 'files', header: 'Files', kind: 'count' },
  {
    key: 'updated_at',
    header: 'Last write',
    render: (value) => (typeof value === 'string' ? <Timestamp value={value} /> : '—'),
  },
];

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DataLakeMap() {
  const query = useCatalogOverview();
  const overview = query.data;
  const branches = overview?.branches.filter((branch) => branch.size_mb > 0) ?? [];
  const layer = (name: string) => branches.find((branch) => branch.name === name);
  const rows = lakeRows(branches);
  const providers = new Set(rows.filter((row) => row.layer === 'raw').map((row) => row.group));

  return (
    <ScrollArea fill label="Data lake map">
      <QueryState
        query={query}
        isEmpty={!branches.length}
        emptyTitle="No parquet under db/data"
        skeleton="chart"
      >
        <Inset padding="pane">
          <Stack gap="section">
            <StatGrid variant="strip" aria-label="Lake totals">
              <StatItem
                label="On disk"
                value={formatLakeSize(overview?.summary.total_size_mb ?? 0)}
                delta={`${(overview?.summary.parquet_files ?? 0).toLocaleString('en-US')} files`}
                deltaTone="muted"
              />
              {['raw', 'corrected', 'derived'].map((name) => {
                const node = layer(name);
                return (
                  <StatItem
                    key={name}
                    label={name.charAt(0).toUpperCase() + name.slice(1)}
                    value={formatLakeSize(node?.size_mb ?? 0)}
                    delta={`${(node?.parquet_files ?? 0).toLocaleString('en-US')} files`}
                    deltaTone="muted"
                  />
                );
              })}
              <StatItem label="Raw providers" value={providers.size} />
              <StatItem
                label="Last write"
                value={
                  overview?.summary.updated_at ? (
                    <Timestamp value={overview.summary.updated_at} />
                  ) : (
                    '—'
                  )
                }
              />
            </StatGrid>

            <Section title="Size map">
              <Treemap
                ariaLabel="db/data size by layer, timeframe and provider"
                nodes={branches.map((branch) => toTreemap(branch, LAYER_COLOR[branch.name]))}
                formatValue={formatLakeSize}
              />
            </Section>

            <Section title="Providers and groups">
              <DataTable
                dense
                data={rows}
                columns={COLUMNS}
                rowKey={(row) => row.path}
                sortable
                defaultSort={{ column: 'size_mb', direction: 'desc' }}
              />
            </Section>
          </Stack>
        </Inset>
      </QueryState>
    </ScrollArea>
  );
}
