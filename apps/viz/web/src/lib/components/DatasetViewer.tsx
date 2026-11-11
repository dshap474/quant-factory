/**
 * Full parquet reader with table, chart, feature-profile, correlation, and IC modes.
 *
 * USAGE:
 *   <DatasetViewer path="1d/example/data.parquet" scope="features" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { DataTable } from '@quant-factory/qf-ui/tables';
import { compactDtype } from '@quant-factory/qf-ui/tables/core';
import {
  lazy,
  type ReactNode,
  Suspense,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import { previewChartBundle, previewChartValues } from '@/lib/api/catalog';
import { selectDatasetColumns, showsColumnControls } from '@/lib/api/dataset-columns';
import {
  useDatasetEntityValues,
  useDatasetPreview,
  useDatasetRows,
  useDatasetSchema,
  useEntityLabelOf,
} from '@/lib/api/dataset-queries';
import { previewFeatureChartBundle, previewFeatureChartValues } from '@/lib/api/features';
import { PREVIEW_PAGE_SIZE_OPTIONS, useAppSettings } from '@/lib/shared/lib/app-settings';
import {
  Button,
  Cluster,
  cn,
  ErrorPanel,
  Field,
  formatRowRangeLabel,
  Input,
  Inset,
  isLoadingData,
  LoadingSkeleton,
  Pagination,
  SearchSelect,
  SegmentedControl,
  SelectControl,
  Stack,
  Surface,
  Text,
  Toolbar,
} from '@/ui';
import { isRawOrderbookPath } from './charts/orderbook-view-state';
import { FeatureAnalysisArtifactView } from './FeatureAnalysisArtifactView';

// --------------------------------------------------------------------------- #
// Deferred analysis bundles
// --------------------------------------------------------------------------- #

const DatasetChartWorkspace = lazy(() =>
  import('./charts/DatasetChartWorkspace').then((module) => ({
    default: module.DatasetChartWorkspace,
  })),
);
const OrderbookChartWorkspace = lazy(() =>
  import('./charts/OrderbookChartWorkspace').then((module) => ({
    default: module.OrderbookChartWorkspace,
  })),
);
const DatasetFeatureAtlas = lazy(() =>
  import('./DatasetFeatureAtlas').then((module) => ({ default: module.DatasetFeatureAtlas })),
);
const FeatureAnalysisView = lazy(() =>
  import('./FeatureAnalysisView').then((module) => ({ default: module.FeatureAnalysisView })),
);

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface DatasetViewerProps {
  compactChrome?: boolean;
  /** Fill a bounded flex-column host: the viewer and its table body own their overflow. */
  fill?: boolean;
  path: string;
  scope: 'data' | 'features';
  selectedColumns?: string[];
  preset?: string;
  mode?: ViewerMode;
  hideModeControl?: boolean;
  /** Controls shown first in the table and chart toolbar bands, e.g. the host's view switch. */
  toolbarLead?: ReactNode;
  /** Host control picking which family member this viewer shows; sits on the filter row. */
  memberSelect?: ReactNode;
  /** The path is every member at once: the member control is the only entity filter. */
  memberAll?: boolean;
  /** Header slot for the view tabs; null until the slot mounts. */
  modeControlTarget?: HTMLElement | null;
}

type ViewerMode = 'table' | 'chart' | 'features' | 'correlation' | 'ic';

/**
 * Columns Table mode offers as a row filter, in the same priority order the API
 * uses when it infers an entity column for charts and profiles. A name also matches
 * as an ID key in any spelling (`asset_id`, `assetId`, `marketId`).
 */
const ENTITY_COLUMN_CANDIDATES = [
  'asset',
  'symbol',
  'ticker',
  'instrument',
  'pair',
  'coin',
  'market',
];

/** Priority of a column as a row filter, or null when it is not an entity key. */
function entityColumnRank(column: string): number | null {
  const name = column.toLowerCase().replace(/[_-]/g, '');
  const rank = ENTITY_COLUMN_CANDIDATES.findIndex(
    (candidate) => name === candidate || name === `${candidate}id`,
  );
  return rank === -1 ? null : rank;
}

/** Row-filter value meaning "no filter"; the same sentinel the Features tab uses. */
const ALL_ENTITIES = 'All';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DatasetViewer({
  compactChrome = false,
  fill = false,
  path,
  scope,
  selectedColumns,
  preset,
  mode: controlledMode,
  hideModeControl = false,
  toolbarLead,
  memberSelect,
  memberAll = false,
  modeControlTarget,
}: DatasetViewerProps) {
  const controlId = useId();
  const tableGridRef = useRef<HTMLDivElement>(null);
  const [localMode, setMode] = useState<ViewerMode>(() =>
    scope === 'data' && isRawOrderbookPath(path) ? 'chart' : 'table',
  );
  const mode = controlledMode ?? localMode;
  const [page, setPage] = useState(1);
  const [columnPage, setColumnPage] = useState(1);
  const [columnSearch, setColumnSearch] = useState('');
  const [entityColumn, setEntityColumn] = useState('');
  const [entityValue, setEntityValue] = useState('');
  const { previewPageSize, setPreviewPageSize } = useAppSettings();
  const pageResetKey = `${scope}|${path}|${previewPageSize}`;
  const [initializedPageKey, setInitializedPageKey] = useState<string | null>(null);
  if (initializedPageKey !== pageResetKey) {
    setInitializedPageKey(pageResetKey);
    setPage(1);
  }
  const isAnalysisArtifact = /(^|\/)analysis_[^/]+\.parquet$/.test(path);
  const previewQuery = useDatasetPreview(
    scope,
    path,
    page,
    previewPageSize,
    isAnalysisArtifact && mode === 'table',
  );
  const schemaQuery = useDatasetSchema(scope, path, !isAnalysisArtifact && mode === 'table');
  const schemaColumns = (schemaQuery.data?.schema.map((column) => column.name) ?? []).filter(
    (column) =>
      !selectedColumns ||
      selectedColumns.includes(column) ||
      column === 'timestamp' ||
      column === 'asset',
  );
  const columns = selectDatasetColumns(schemaColumns, columnSearch, columnPage);
  const showColumnControls = showsColumnControls(compactChrome, columns.totalPages, columnSearch);
  const columnTypes = Object.fromEntries(
    (schemaQuery.data?.schema ?? []).map((column) => [column.name, compactDtype(column.dtype)]),
  );
  const entityCandidates = schemaColumns
    .map((column) => ({ column, rank: entityColumnRank(column) }))
    .filter((item): item is { column: string; rank: number } => item.rank !== null)
    .sort((a, b) => a.rank - b.rank)
    .map((item) => item.column);
  const resolvedEntityColumn = entityCandidates.includes(entityColumn) ? entityColumn : '';
  // A member that holds one entity (one file per asset) has nothing left to filter.
  const memberEntityQuery = useDatasetEntityValues(
    scope,
    path,
    memberSelect && !memberAll && mode === 'table' ? (entityCandidates[0] ?? '') : '',
    '',
  );
  const showEntityFilter =
    entityCandidates.length > 0 &&
    !memberAll &&
    (!memberSelect || (memberEntityQuery.data?.values.length ?? 0) > 1);
  // The full roster feeds a virtualized SearchSelect: tens of thousands of values stay cheap
  // because only the visible rows mount.
  const entityValuesQuery = useDatasetEntityValues(
    scope,
    path,
    mode === 'table' && !memberAll ? resolvedEntityColumn : '',
  );
  const entityItems = [ALL_ENTITIES, ...(entityValuesQuery.data?.values ?? [])];
  const entityLabelOf = useEntityLabelOf(entityValuesQuery.data?.labels);
  const appliedEntityValue = memberAll ? '' : entityValue;
  const [pagedEntityValue, setPagedEntityValue] = useState(appliedEntityValue);
  if (pagedEntityValue !== appliedEntityValue) {
    setPagedEntityValue(appliedEntityValue);
    setPage(1);
  }
  const rowsQuery = useDatasetRows(
    scope,
    path,
    page,
    previewPageSize,
    columns.selected,
    !isAnalysisArtifact && mode === 'table',
    {
      entityColumn: resolvedEntityColumn || null,
      entityValue: appliedEntityValue || null,
    },
  );
  // A labelled ID column (e.g. a UUID asset key) gets a read-only label column right after it.
  const rowLabels = rowsQuery.data?.labels ?? {};
  const labelColumnOf = (column: string) => `${column} · ${rowLabels[column]?.title ?? ''}`;
  const tableColumns = columns.selected.flatMap((column) =>
    rowLabels[column] ? [column, labelColumnOf(column)] : [column],
  );
  const tableRows = Object.keys(rowLabels).length
    ? (rowsQuery.data?.data ?? []).map((row) => {
        const labelled = { ...row };
        for (const [column, { values }] of Object.entries(rowLabels)) {
          const key = row[column];
          labelled[labelColumnOf(column)] = typeof key === 'string' ? (values[key] ?? null) : null;
        }
        return labelled;
      })
    : (rowsQuery.data?.data ?? []);
  const tableColumnTypes = Object.fromEntries([
    ...Object.entries(columnTypes),
    ...Object.keys(rowLabels).map((column) => [labelColumnOf(column), 'label']),
  ]);
  const preview = previewQuery.data ?? null;
  // Only a failure with nothing to show takes the panel; a failed refresh keeps the data.
  const failedQuery = [previewQuery, schemaQuery, rowsQuery].find(
    (q) => q.error && q.data === undefined,
  );
  const error = failedQuery?.error?.message ?? null;
  const previewLoading = isLoadingData(previewQuery);
  const rowsLoading = isLoadingData(rowsQuery);
  const entityValuesLoading = isLoadingData(entityValuesQuery);
  const loading =
    mode === 'table' && (isAnalysisArtifact ? previewLoading : isLoadingData(schemaQuery));
  const chartBundle = useCallback<typeof previewFeatureChartBundle>(
    async (chartPath, request, signal) => {
      const fetcher = scope === 'features' ? previewFeatureChartBundle : previewChartBundle;
      const scopedRequest =
        selectedColumns?.length && request.charts.length === 0
          ? {
              ...request,
              charts: [
                {
                  chart_id: 'cell-1',
                  series: [{ metric: selectedColumns[0], axis: 'left' as const }],
                },
              ],
            }
          : request;
      const response = await fetcher(chartPath, scopedRequest, signal);
      if (!selectedColumns) return response;
      const metrics = response.y_columns.filter((column) => selectedColumns.includes(column));
      return {
        ...response,
        y_columns: metrics,
        families: response.families
          .map((family) => ({
            ...family,
            count: metrics.filter((metric) => response.y_column_families[metric] === family.id)
              .length,
          }))
          .filter((family) => family.count > 0),
        default_y_column:
          response.default_y_column && metrics.includes(response.default_y_column)
            ? response.default_y_column
            : (metrics[0] ?? null),
      };
    },
    [scope, selectedColumns],
  );

  const modes: { value: ViewerMode; label: string }[] = [
    { value: 'table', label: 'Table' },
    { value: 'chart', label: 'Chart' },
    { value: 'features', label: 'Features' },
    ...(scope === 'features'
      ? ([
          { value: 'correlation', label: 'Correlation' },
          { value: 'ic', label: 'IC Matrix' },
        ] as const)
      : []),
  ];
  const entityFiltered = Boolean(resolvedEntityColumn && appliedEntityValue);
  const totalRows = isAnalysisArtifact
    ? preview?.total_rows
    : entityFiltered
      ? (rowsQuery.data?.matched_rows ?? schemaQuery.data?.total_rows)
      : schemaQuery.data?.total_rows;
  const totalColumns = isAnalysisArtifact ? preview?.columns : schemaColumns.length;
  const totalPages = Math.max(1, Math.ceil((totalRows ?? 0) / previewPageSize));

  // Terminal paging keys, live only while the grid is hovered or holds focus so
  // arrow keys keep their normal meaning everywhere else on the page.
  const columnPages = columns.totalPages;
  const gridPagingActive = mode === 'table' && !isAnalysisArtifact;
  useEffect(() => {
    if (!gridPagingActive) return;
    function onKeyDown(event: KeyboardEvent) {
      const grid = tableGridRef.current;
      const shell = grid?.closest('.dataset-table-shell');
      if (!grid || !shell) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest('input, select, textarea, [contenteditable="true"]')) return;
      if (!shell.matches(':hover') && !shell.contains(document.activeElement)) return;
      if (event.key === 'ArrowLeft') setPage((value) => Math.max(1, value - 1));
      else if (event.key === 'ArrowRight') setPage((value) => Math.min(totalPages, value + 1));
      else if (event.key === '[') setColumnPage((value) => Math.max(1, value - 1));
      else if (event.key === ']') setColumnPage((value) => Math.min(columnPages, value + 1));
      else return;
      event.preventDefault();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [gridPagingActive, totalPages, columnPages]);

  const modeControl = (
    <SegmentedControl
      variant="tabs"
      ariaLabel="Preview mode"
      options={modes}
      value={mode}
      onValueChange={setMode}
    />
  );
  const tableToolbar =
    compactChrome &&
    !toolbarLead &&
    !memberSelect &&
    !showEntityFilter &&
    !showColumnControls ? null : (
      <Toolbar band className="items-end justify-between">
        {toolbarLead}
        {showColumnControls ? (
          <Field
            label="Search columns"
            className="min-w-64 flex-1"
            htmlFor={`${controlId}-columns`}
          >
            <Input
              id={`${controlId}-columns`}
              type="search"
              className="w-full"
              value={columnSearch}
              placeholder={`Filter ${schemaColumns.length - columns.pinned.length} columns`}
              onChange={(event) => {
                setColumnSearch(event.target.value);
                setColumnPage(1);
              }}
            />
          </Field>
        ) : null}
        {showEntityFilter ? (
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Filter rows" className="min-w-40" htmlFor={`${controlId}-entity-column`}>
              <SelectControl
                id={`${controlId}-entity-column`}
                className="w-full"
                ariaLabel="Row filter column"
                value={resolvedEntityColumn}
                onValueChange={(value) => {
                  setEntityColumn(value);
                  setEntityValue('');
                  setPage(1);
                }}
                options={[
                  { value: '', label: 'All rows' },
                  ...entityCandidates.map((column) => ({ value: column, label: column })),
                ]}
              />
            </Field>
            {resolvedEntityColumn && !entityValuesLoading ? (
              <SearchSelect
                label={resolvedEntityColumn}
                items={entityItems}
                labelOf={entityLabelOf}
                value={appliedEntityValue || ALL_ENTITIES}
                placeholder={`search ${resolvedEntityColumn}…`}
                onChange={(value) => {
                  setEntityValue(!value || value === ALL_ENTITIES ? '' : value);
                  setPage(1);
                }}
              />
            ) : null}
            {resolvedEntityColumn && entityValuesLoading ? (
              <LoadingSkeleton announce={false} className="w-32" />
            ) : null}
          </div>
        ) : null}
        {memberSelect}
        {showColumnControls ? (
          <div className="flex flex-wrap items-center gap-2">
            <Text variant="data" tone="muted">
              Columns {columns.start}–{columns.end} of {columns.totalBrowsable}
              {columns.pinned.length ? ` · ${columns.pinned.length} pinned` : ''}
            </Text>
            <Button
              type="button"
              variant="control"
              disabled={columns.page <= 1}
              onClick={() => setColumnPage((value) => Math.max(1, value - 1))}
            >
              Previous columns
            </Button>
            <Button
              type="button"
              variant="control"
              disabled={columns.page >= columns.totalPages}
              onClick={() => setColumnPage((value) => value + 1)}
            >
              Next columns
            </Button>
          </div>
        ) : null}
      </Toolbar>
    );

  return (
    <Stack
      as="section"
      gap={fill ? 'none' : 'heading'}
      className={cn('dataset-viewer', fill && 'min-h-0 min-w-0 flex-1')}
    >
      {modeControlTarget && !hideModeControl ? createPortal(modeControl, modeControlTarget) : null}
      {compactChrome && (hideModeControl || modeControlTarget !== undefined) ? null : (
        <Cluster justify="between" className="dataset-viewer-contextbar">
          {compactChrome ? null : (
            <div className="dataset-viewer-metadata min-w-0">
              <Text as="p" variant="data" tone="muted" className="break-all">
                {scope}: {path}
              </Text>
              {totalRows !== undefined && totalColumns !== undefined ? (
                <Text as="p" variant="caption" className="mt-1">
                  {totalRows.toLocaleString()} rows · {totalColumns} columns
                </Text>
              ) : null}
            </div>
          )}
          {hideModeControl ? null : modeControl}
        </Cluster>
      )}

      {fill && mode === 'table' && !isAnalysisArtifact && (schemaQuery.data || memberSelect)
        ? tableToolbar
        : null}

      {error ? <ErrorPanel message={error} onRetry={() => void failedQuery?.refetch()} /> : null}
      {loading ? (
        <Inset padding={fill ? 'pane' : 'none'}>
          <LoadingSkeleton variant="table" count={8} />
        </Inset>
      ) : null}

      {mode === 'table' && preview && isAnalysisArtifact && !previewLoading ? (
        <FeatureAnalysisArtifactView preview={preview} scope={scope} />
      ) : null}

      {mode === 'table' && schemaQuery.data && !isAnalysisArtifact ? (
        <Inset
          padding={fill ? 'pane' : 'none'}
          className={cn(fill && 'flex min-h-0 flex-1 flex-col')}
        >
          <Surface
            padding="none"
            clip
            className={cn('dataset-table-shell', fill && 'flex min-h-0 flex-1 flex-col')}
          >
            {fill ? null : tableToolbar}
            <div
              ref={tableGridRef}
              className={cn('dataset-table-body', fill ? 'min-h-0 flex-1' : 'min-h-40')}
            >
              <DataTable
                dense
                flush
                fill={compactChrome}
                loading={rowsLoading}
                skeletonRows={Math.min(rowsQuery.data?.returned_rows || previewPageSize, 100)}
                data={tableRows}
                columns={tableColumns}
                columnTypes={tableColumnTypes}
                maxRows={rowsQuery.data?.returned_rows ?? 0}
                rowOffset={(page - 1) * previewPageSize}
                emptyTitle={
                  entityFiltered && totalRows === 0
                    ? `No rows where ${resolvedEntityColumn} is ${appliedEntityValue}`
                    : 'No rows on this page'
                }
                emptyHint={
                  entityFiltered && totalRows === 0
                    ? 'Clear the row filter or pick another value.'
                    : 'Adjust the page, page size, or column selection.'
                }
              />
            </div>
            <Pagination
              band
              page={page}
              pageCount={totalPages}
              onPageChange={setPage}
              label={
                rowsLoading ? (
                  <LoadingSkeleton announce={false} className="w-32" />
                ) : (
                  formatRowRangeLabel({
                    page,
                    pageSize: previewPageSize,
                    returnedRows: rowsQuery.data?.returned_rows ?? 0,
                    totalRows,
                    totalPages,
                  })
                )
              }
              jump
              pageSize={previewPageSize}
              pageSizeOptions={PREVIEW_PAGE_SIZE_OPTIONS}
              onPageSizeChange={(size) => {
                setPreviewPageSize(size);
                setPage(1);
              }}
              disabled={rowsLoading}
            />
          </Surface>
        </Inset>
      ) : null}

      <Suspense
        fallback={
          <LoadingSkeleton variant="chart" label="Loading analysis view" announce={!loading} />
        }
      >
        {mode === 'chart' ? (
          <div className="dataset-chart-content">
            {scope === 'data' && isRawOrderbookPath(path) ? (
              <Stack gap="none" className="min-h-0 min-w-0 flex-1">
                {memberSelect ? <Toolbar band>{memberSelect}</Toolbar> : null}
                <OrderbookChartWorkspace key={path} path={path} />
              </Stack>
            ) : (
              <DatasetChartWorkspace
                path={path}
                keyScope={[scope, selectedColumns ?? null]}
                previewChartBundle={chartBundle}
                previewChartValues={
                  scope === 'features' ? previewFeatureChartValues : previewChartValues
                }
                toolbarLead={
                  <>
                    {toolbarLead}
                    {/* A chart draws one asset: with All, its own asset control picks it. */}
                    {memberAll ? null : memberSelect}
                  </>
                }
              />
            )}
          </div>
        ) : null}
        {mode === 'features' ? (
          <DatasetFeatureAtlas
            path={path}
            scope={scope}
            preset={preset}
            fill={fill}
            memberSelect={memberSelect}
            memberAll={memberAll}
          />
        ) : null}
        {mode === 'correlation' || mode === 'ic' ? (
          <FeatureAnalysisView path={path} mode={mode} />
        ) : null}
      </Suspense>
    </Stack>
  );
}
