/**
 * Searchable feature profile atlas with sparklines and a detail inspector.
 *
 * The toolbar holds the name filter and one entity picker ("All" profiles the whole panel).
 * Block chips filter by feature block; the Feature, Coverage and Distribution headers sort.
 *
 * USAGE:
 *   <DatasetFeatureAtlas path="1d/example/data.parquet" profileFeatures={fn} … />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Histogram, Sparkline as QfSparkline } from '@quant-factory/qf-ui/charts/renderers';
import {
  SortHeader,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@quant-factory/qf-ui/tables';
import type { SortDirection, SortState } from '@quant-factory/qf-ui/tables/core';
import { type CSSProperties, type ReactNode, useDeferredValue, useState } from 'react';
import type { DatasetFeatureProfileDetail, DatasetFeatureSparkPoint } from '@/lib/api/catalog';
import {
  type DatasetScope,
  useDatasetEntityValues,
  useDatasetProfile,
  useDatasetProfileDetail,
  useEntityLabelOf,
} from '@/lib/api/dataset-queries';
import { useFeaturePanelMeta } from '@/lib/api/feature-publication';
import {
  Badge,
  Button,
  Cluster,
  Columns,
  cn,
  EMPTY,
  EmptyState,
  ErrorPanel,
  formatCompact,
  formatCount,
  formatIsoDay,
  formatPercent,
  Input,
  Inset,
  isLoadingData,
  LoadingSkeleton,
  Pagination,
  ScrollArea,
  SearchSelect,
  Stack,
  StatGrid,
  StatItem,
  Surface,
  Text,
  Toolbar,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Types and helpers
// --------------------------------------------------------------------------- #

export interface DatasetFeatureAtlasProps {
  path: string;
  scope: DatasetScope;
  preset?: string;
  /** Fill a bounded flex-column host: the list and inspector own their overflow. */
  fill?: boolean;
  /** Host control picking which family member is profiled; sits on the filter row. */
  memberSelect?: ReactNode;
  /** The path is every member at once: the member control is the only entity filter. */
  memberAll?: boolean;
}

// A filled host scrolls a long page (the API caps it at 250); a bounded one pages short.
const FILL_PAGE_SIZE = 200;
const PAGE_SIZE = 15;

// Header sorts and the API sort each maps to; a header with no key for a direction goes
// back to schema order (coverage ascending is the API's "most missing first").
const HEADER_SORTS: Record<string, Partial<Record<SortDirection, string>>> = {
  feature: { asc: 'name' },
  coverage: { desc: 'coverage_desc', asc: 'missing_desc' },
  distribution: { desc: 'std_desc' },
};

function headerSort(sort: string): SortState | null {
  for (const [column, keys] of Object.entries(HEADER_SORTS)) {
    for (const [direction, key] of Object.entries(keys)) {
      if (key === sort) return { column, direction: direction as SortDirection };
    }
  }
  return null;
}

const ALL_ENTITIES = 'All';

function compact(value: number | null): string {
  return formatCompact(value, { maximumSignificantDigits: 4 });
}

function Sparkline({
  points,
  tall = false,
}: {
  points: DatasetFeatureSparkPoint[];
  tall?: boolean;
}) {
  const sparkline = (
    <QfSparkline
      values={points.map((point) => point.y)}
      height={tall ? 'var(--feature-inspector-trend-height, 112px)' : 20}
      className="w-full"
      ariaLabel="Feature trend"
    />
  );
  // The chart sizes to its host, so a fixed-width host keeps row trends from widening the table.
  return tall ? sparkline : <div className="w-28">{sparkline}</div>;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

type FillStyle = CSSProperties & Record<string, string>;

export function DatasetFeatureAtlas({
  path,
  scope,
  preset,
  fill = false,
  memberSelect,
  memberAll = false,
}: DatasetFeatureAtlasProps) {
  const [query, setQuery] = useState('');
  const [family, setFamily] = useState('all');
  const [sort, setSort] = useState('schema');
  const [page, setPage] = useState(1);
  const [entityValue, setEntityValue] = useState('');
  const [selectedFeature, setSelectedFeature] = useState<string | null>(null);
  const deferredQuery = useDeferredValue(query);
  // The panel's entity column comes from the first profile response; '' until then.
  const [entityColumn, setEntityColumn] = useState('');
  const entityValuesQuery = useDatasetEntityValues(scope, path, memberAll ? '' : entityColumn);
  const entitySelection = entityColumn && entityValue && !memberAll ? entityColumn : null;
  const profileQuery = useDatasetProfile(scope, path, {
    query: deferredQuery,
    family,
    sort,
    page,
    page_size: fill ? FILL_PAGE_SIZE : PAGE_SIZE,
    entity_column: entitySelection,
    entity_value: entitySelection ? entityValue : null,
    max_spark_points: 36,
    preset,
  });
  const profile = profileQuery.data ?? null;
  const firstEntityColumn = profile?.entity_columns[0] ?? '';
  if (firstEntityColumn && !entityColumn) setEntityColumn(firstEntityColumn);
  const profileLoading = isLoadingData(profileQuery);
  const activeSelectedFeature =
    profile?.features.some((item) => item.name === selectedFeature) === true
      ? selectedFeature
      : (profile?.features[0]?.name ?? null);
  const detailQuery = useDatasetProfileDetail(
    scope,
    path,
    activeSelectedFeature
      ? {
          column: activeSelectedFeature,
          entity_column: entitySelection,
          entity_value: entitySelection ? entityValue : null,
          max_spark_points: 160,
        }
      : null,
  );
  const detail = detailQuery.data ?? null;
  // The per-column contract (formula, unit, dependencies) lives in the panel's
  // published meta.yaml, which only feature panels carry.
  const panelMetaQuery = useFeaturePanelMeta(scope === 'features' ? path : '');
  const columnMeta = panelMetaQuery.data?.present
    ? panelMetaQuery.data.columns.find((item) => item.name === activeSelectedFeature)
    : undefined;
  const entityItems = [ALL_ENTITIES, ...(entityValuesQuery.data?.values ?? [])];
  const entityLabelOf = useEntityLabelOf(entityValuesQuery.data?.labels);
  // Only a failure with nothing to show takes the panel; a failed refresh keeps the data.
  const error =
    [profileQuery, detailQuery, entityValuesQuery].find((q) => q.error && q.data === undefined)
      ?.error?.message ?? null;
  const detailLoading = isLoadingData(detailQuery);

  function sortBy(next: SortState) {
    setSort(HEADER_SORTS[next.column]?.[next.direction] ?? 'schema');
    setPage(1);
  }

  const totalPages = profile
    ? Math.max(1, Math.ceil(profile.total_features / profile.page_size))
    : 1;
  return (
    <Stack
      as="section"
      gap={fill ? 'none' : 'heading'}
      className={cn('dataset-feature-atlas', fill && 'min-h-0 min-w-0 flex-1')}
      aria-label="Dataset feature atlas"
    >
      <Toolbar band aria-label="Feature profile controls">
        <Input
          type="search"
          className="min-w-56 flex-1"
          placeholder="Filter features"
          aria-label="Filter features"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
        />
        {memberSelect}
        {entityColumn && !memberAll && (!memberSelect || entityItems.length > 2) ? (
          <SearchSelect
            label={entityColumn}
            items={entityItems}
            labelOf={entityLabelOf}
            value={entityValue || ALL_ENTITIES}
            placeholder={`search ${entityColumn}…`}
            onChange={(value) => {
              setEntityValue(!value || value === ALL_ENTITIES ? '' : value);
              setPage(1);
            }}
          />
        ) : null}
      </Toolbar>

      {profile?.families.length ? (
        <Toolbar band aria-label="Feature blocks">
          <fieldset className="flex min-w-0 flex-1 flex-wrap gap-2">
            <legend className="sr-only">Feature blocks</legend>
            {profile.families.map((item) => (
              <Button
                key={item.id}
                type="button"
                variant="control"
                className="shrink-0"
                aria-pressed={family === item.id}
                onClick={() => {
                  setFamily(item.id);
                  setPage(1);
                }}
              >
                {item.label}{' '}
                <Text variant="data" tone="muted">
                  {item.count}
                </Text>
              </Button>
            ))}
          </fieldset>
        </Toolbar>
      ) : null}

      {error ? (
        <div className="shrink-0">
          <ErrorPanel
            message={error}
            onRetry={() => {
              void profileQuery.refetch();
              if (activeSelectedFeature) void detailQuery.refetch();
              if (entityColumn) void entityValuesQuery.refetch();
            }}
          />
        </div>
      ) : null}
      {profileLoading ? (
        <div className="shrink-0">
          <LoadingSkeleton variant="table" count={12} />
        </div>
      ) : null}

      {!profileLoading && profile && profile.feature_columns === 0 ? (
        <EmptyState title="No numeric features" hint="This parquet has no profileable columns" />
      ) : null}

      {!profileLoading && profile?.feature_columns ? (
        <Inset
          padding={fill ? 'pane' : 'none'}
          className={cn(fill && 'flex min-h-0 flex-1 flex-col')}
        >
          <Columns
            template="minmax(0,1fr) 22rem"
            from="xl"
            gap={fill ? 'block' : 'heading'}
            className={cn(
              'dataset-feature-atlas-body',
              fill
                ? 'min-h-0 flex-1 grid-rows-[minmax(0,1fr)_minmax(0,1fr)] xl:grid-rows-[minmax(0,1fr)]'
                : 'min-h-[32rem]',
            )}
          >
            <Surface
              padding="none"
              clip
              className={cn(
                'dataset-feature-atlas-list min-w-0',
                fill && 'flex h-full min-h-0 flex-col',
              )}
            >
              <ScrollArea
                axis="both"
                fill={fill}
                maxHeight={fill ? undefined : '38rem'}
                label="Feature list"
                className={cn('dataset-feature-atlas-rows', fill && 'min-h-0 overscroll-none')}
              >
                <Table density="dense">
                  <TableHeader sticky>
                    <TableRow>
                      <SortHeader column="feature" sort={headerSort(sort)} onSortChange={sortBy}>
                        Feature
                      </SortHeader>
                      <TableHead>Trend</TableHead>
                      <SortHeader
                        column="coverage"
                        numeric
                        initialDirection="desc"
                        sort={headerSort(sort)}
                        onSortChange={sortBy}
                      >
                        Coverage
                      </SortHeader>
                      <TableHead numeric>First</TableHead>
                      <TableHead numeric>Last</TableHead>
                      <SortHeader
                        column="distribution"
                        numeric
                        initialDirection="desc"
                        sort={headerSort(sort)}
                        onSortChange={sortBy}
                      >
                        Distribution
                      </SortHeader>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {profile.features.map((feature) => (
                      <TableRow
                        key={feature.name}
                        aria-selected={activeSelectedFeature === feature.name}
                        onClick={() => setSelectedFeature(feature.name)}
                      >
                        <TableCell>
                          <Button
                            type="button"
                            variant="link"
                            onClick={() => setSelectedFeature(feature.name)}
                          >
                            <Text as="span" variant="data" weight="medium">
                              {feature.name}
                            </Text>
                          </Button>
                        </TableCell>
                        <TableCell>
                          <Sparkline points={feature.sparkline} />
                        </TableCell>
                        <TableCell numeric>{formatPercent(feature.coverage)}</TableCell>
                        <TableCell numeric>{formatIsoDay(feature.first_non_null)}</TableCell>
                        <TableCell numeric>{formatIsoDay(feature.last_non_null)}</TableCell>
                        <TableCell numeric>
                          μ {compact(feature.mean)} · σ {compact(feature.std)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
              <Pagination
                band
                className="shrink-0"
                page={page}
                pageCount={totalPages}
                onPageChange={setPage}
                label={`${profile.total_features.toLocaleString()} features`}
              />
            </Surface>

            <Surface
              as="aside"
              className={cn(
                'dataset-feature-atlas-inspector',
                fill && 'flex h-full min-h-0 flex-col overscroll-contain',
              )}
              aria-label="Feature inspector"
            >
              <ScrollArea axis="y" fill={fill}>
                {detailLoading ? <LoadingSkeleton variant="card" count={4} /> : null}
                {!detailLoading && detail ? (
                  <Stack
                    gap="block"
                    className={cn('dataset-feature-inspector-content', fill && 'h-full')}
                  >
                    <Cluster justify="between" align="start" wrap={false} className="shrink-0">
                      <div className="min-w-0">
                        <Text as="p" variant="eyebrow">
                          {detail.family_label}
                        </Text>
                        <Text
                          as="h3"
                          variant="data"
                          size="sm"
                          weight="semibold"
                          className="break-words"
                        >
                          {detail.column}
                        </Text>
                      </div>
                      <Badge>{detail.dtype}</Badge>
                    </Cluster>
                    <Surface
                      padding="sm"
                      className={cn(
                        'dataset-feature-inspector-trend',
                        fill && 'min-h-48 flex-[1_0_12rem]',
                      )}
                      style={
                        fill
                          ? ({ '--feature-inspector-trend-height': '100%' } as FillStyle)
                          : undefined
                      }
                    >
                      <Sparkline points={detail.sparkline} tall />
                    </Surface>
                    <StatGrid variant="strip" boxed columns={2} className="shrink-0">
                      {[
                        ['Coverage', formatPercent(detail.stats.coverage)],
                        ['Missing', detail.stats.null_count.toLocaleString()],
                        ['First', formatIsoDay(detail.stats.first_non_null)],
                        ['Last', formatIsoDay(detail.stats.last_non_null)],
                        ['Mean', compact(detail.stats.mean)],
                        ['Std', compact(detail.stats.std)],
                        ['P25', compact(detail.stats.p25)],
                        ['P75', compact(detail.stats.p75)],
                      ].map(([label, value]) => (
                        <StatItem key={label} label={label} value={value} />
                      ))}
                    </StatGrid>
                    {detail.histogram.length ? (
                      <div
                        className={cn(
                          'dataset-feature-inspector-histogram',
                          fill && 'min-h-28 flex-[0.5_0_7rem]',
                        )}
                        style={
                          fill
                            ? ({ '--feature-inspector-histogram-height': '100%' } as FillStyle)
                            : undefined
                        }
                      >
                        <Histogram
                          values={detail.histogram.map((bin) => bin.count)}
                          labels={detail.histogram.map(
                            (bin) => `${compact(bin.bin_start)}–${compact(bin.bin_end)}`,
                          )}
                          height="var(--feature-inspector-histogram-height, 80px)"
                        />
                      </div>
                    ) : null}
                    {columnMeta ? (
                      <div className="shrink-0">
                        <div className="mb-2 flex items-center gap-2">
                          <Text as="h4" variant="eyebrow">
                            Published definition
                          </Text>
                          {columnMeta.unit ? <Badge tone="info">{columnMeta.unit}</Badge> : null}
                        </div>
                        <Text as="p" variant="caption" size="2xs" className="max-w-[60ch]">
                          {columnMeta.formula ?? EMPTY}
                        </Text>
                        <Text as="p" variant="caption" size="2xs" className="mt-2">
                          Rows {formatCount(columnMeta.non_null_rows)} ·{' '}
                          {formatIsoDay(columnMeta.first_non_null)} →{' '}
                          {formatIsoDay(columnMeta.last_non_null)}
                        </Text>
                        {columnMeta.dependencies.map((dependency) => (
                          <Text
                            key={dependency}
                            as="p"
                            variant="data"
                            size="2xs"
                            className="mt-1 break-all"
                          >
                            {dependency}
                          </Text>
                        ))}
                      </div>
                    ) : null}
                    {detail.latest_top.length || detail.latest_bottom.length ? (
                      <Columns
                        template="repeat(2, minmax(0,1fr))"
                        gap="heading"
                        className="shrink-0"
                      >
                        {[
                          ['Top', detail.latest_top],
                          ['Bottom', detail.latest_bottom],
                        ].map(([label, rows]) => (
                          <div key={String(label)}>
                            <Text as="h4" variant="eyebrow" className="mb-2">
                              {String(label)}
                            </Text>
                            {(rows as DatasetFeatureProfileDetail['latest_top'])
                              .slice(0, 5)
                              .map((row) => (
                                <p key={row.entity} className="flex justify-between gap-2">
                                  <span className="truncate" title={row.entity}>
                                    {row.label ?? row.entity}
                                  </span>
                                  <Text as="span" variant="data">
                                    {compact(row.value)}
                                  </Text>
                                </p>
                              ))}
                          </div>
                        ))}
                      </Columns>
                    ) : null}
                  </Stack>
                ) : null}
                {!detailLoading && !detail ? <EmptyState title="Select a feature" /> : null}
              </ScrollArea>
            </Surface>
          </Columns>
        </Inset>
      ) : null}
    </Stack>
  );
}
