/**
 * Interactive multi-cell chart workspace for catalog and feature parquet files.
 *
 * The feature rail runs the full height at the end edge; it is where metrics are put on a
 * chart's left or right axis. Beside it, inside the pane inset, the controls (entity,
 * overlay, grid) sit over the charts' one bordered card. Grids up to two rows fill the height; taller ones scroll.
 *
 * USAGE:
 *   <DatasetChartWorkspace
 *     path="raw/1d/btc.parquet"
 *     keyScope={[scope, selectedColumns ?? null]}
 *     previewChartBundle={fn}
 *     previewChartValues={fn}
 *     toolbarLead={<SegmentedControl … />}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  ChartTransformGroupProvider,
  ChartTransformMasterToolbar,
} from '@quant-factory/qf-ui/charts/chrome';
import { MultiSeriesTimeChart } from '@quant-factory/qf-ui/charts/renderers';
import { chartColor } from '@quant-factory/qf-ui/charts/theme';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { type ReactNode, useId, useState } from 'react';
import { useBenchmark, useBenchmarks } from '@/lib/api/benchmarks';
import type {
  DatasetChartAxis,
  DatasetChartBundleRequest,
  DatasetChartBundleResponse,
  DatasetChartValueResponse,
} from '@/lib/api/catalog';
import { ENTITY_VALUE_LIMIT, useEntityLabelOf } from '@/lib/api/dataset-queries';
import {
  ChartGrid,
  ChartGridCell,
  EmptyState,
  ErrorPanel,
  Field,
  Inset,
  isLoadingData,
  LoadingSkeleton,
  ScrollArea,
  SearchSelect,
  SelectControl,
  SplitRow,
  Stack,
  Surface,
  Toolbar,
} from '@/ui';
import { DatasetChartFeatureRail } from './DatasetChartFeatureRail';
import { DatasetPriceOverlayControl } from './DatasetPriceOverlayControl';
import {
  type DatasetPriceOverlaySeries,
  parsePriceOverlayPoints,
  priceOverlayOptions,
  resolvePriceOverlay,
} from './dataset-chart-overlays';

// --------------------------------------------------------------------------- #
// Types and constants
// --------------------------------------------------------------------------- #

type BundleFetcher = (
  path: string,
  request: DatasetChartBundleRequest,
  signal?: AbortSignal,
) => Promise<DatasetChartBundleResponse>;

type ValuesFetcher = (
  path: string,
  params: { entity_column: string; query?: string; limit?: number; offset?: number },
  signal?: AbortSignal,
) => Promise<DatasetChartValueResponse>;

interface ChartCell {
  id: string;
  leftMetric: string | null;
  rightMetric: string | null;
}

export interface DatasetChartWorkspaceProps {
  path: string;
  /** Everything the fetcher props close over; query keys cannot see it otherwise. */
  keyScope: readonly unknown[];
  previewChartBundle: BundleFetcher;
  previewChartValues: ValuesFetcher;
  /** Controls shown first in the toolbar band, e.g. the host's Chart/Table switch. */
  toolbarLead?: ReactNode;
}

const LAYOUTS = [
  { value: '1x1', rows: 1, cols: 1 },
  { value: '1x2', rows: 1, cols: 2 },
  { value: '2x1', rows: 2, cols: 1 },
  { value: '2x2', rows: 2, cols: 2 },
  { value: '2x3', rows: 2, cols: 3 },
  { value: '3x3', rows: 3, cols: 3 },
] as const;

const CHART_COLORS = [
  chartColor(1),
  chartColor(2),
  chartColor(3),
  chartColor(6),
  chartColor(7),
  chartColor(8),
];

// Trailing z-score and EMA windows come from qf-charts; a master toolbar drives every
// cell and each chart can override it. Daily panels stay under the API point cap so the
// transforms see every observation rather than a stride-sampled subset.
const DATASET_TRANSFORM_CONTROLS = { zScore: true, ema: true } as const;
const CHART_MAX_POINTS = 5_000;

function createCells(count: number, defaultMetric: string | null): ChartCell[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `cell-${index + 1}`,
    leftMetric: index === 0 ? defaultMetric : null,
    rightMetric: null,
  }));
}

function cellLabel(cellId: string): string {
  return `Chart ${cellId.replace('cell-', '')}`;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DatasetChartWorkspace({
  path,
  keyScope,
  previewChartBundle,
  previewChartValues,
  toolbarLead,
}: DatasetChartWorkspaceProps) {
  const controlId = useId();
  const [layoutValue, setLayoutValue] = useState('1x1');
  const [cells, setCells] = useState<ChartCell[]>(() => createCells(1, null));
  // Entity selections are *user overrides*: '' means "let the API choose". What the UI
  // shows is derived from the override and the bundle's own choice, never written back.
  const [entityColumn, setEntityColumn] = useState('');
  const [entityValue, setEntityValue] = useState('');
  // null follows the first registered benchmark; 'none' or a ticker is the operator's choice.
  const [overlayChoice, setOverlayChoice] = useState<string | null>(null);
  // The feature rail assigns metrics to one "target" cell: the last cell the operator
  // touched, or whichever the rail's own selector names.
  const [targetCellId, setTargetCellId] = useState('cell-1');
  const [railCollapsed, setRailCollapsed] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 760px)').matches,
  );

  const layout = LAYOUTS.find((item) => item.value === layoutValue) ?? LAYOUTS[0];
  const cellCount = layout.rows * layout.cols;

  // The series-free bundle is the dataset's chart metadata; its default metric seeds an
  // empty grid by derivation (not setCells), and the seeded grid is what gets requested.
  const metaRequest: DatasetChartBundleRequest = {
    entity_column: null,
    entity_value: null,
    max_points: CHART_MAX_POINTS,
    charts: [],
  };
  const metaQuery = useQuery({
    queryKey: ['dataset-chart-bundle', ...keyScope, path, metaRequest],
    queryFn: ({ signal }) => previewChartBundle(path, metaRequest, signal),
  });
  const defaultMetric = metaQuery.data?.default_y_column ?? null;
  const shownCells = cells.slice(0, cellCount);
  const activeCells = shownCells.some((cell) => cell.leftMetric || cell.rightMetric)
    ? shownCells
    : createCells(cellCount, defaultMetric);
  const targetCell = activeCells.find((cell) => cell.id === targetCellId) ?? activeCells[0];

  const request: DatasetChartBundleRequest = {
    entity_column: entityColumn || null,
    entity_value: entityValue || null,
    max_points: CHART_MAX_POINTS,
    charts: [],
  };
  for (const cell of activeCells) {
    const series: { metric: string; axis: DatasetChartAxis }[] = [];
    if (cell.leftMetric) series.push({ metric: cell.leftMetric, axis: 'left' });
    if (cell.rightMetric) series.push({ metric: cell.rightMetric, axis: 'right' });
    if (series.length) request.charts.push({ chart_id: cell.id, series });
  }

  const bundleQuery = useQuery({
    queryKey: ['dataset-chart-bundle', ...keyScope, path, request],
    queryFn: ({ signal }) => previewChartBundle(path, request, signal),
    placeholderData: keepPreviousData,
    enabled: metaQuery.isSuccess,
  });
  const bundle: DatasetChartBundleResponse | null = bundleQuery.data ?? null;
  const isPlaceholder = bundleQuery.isPlaceholderData;

  const resolvedEntityColumn = entityColumn || bundle?.selected_entity_column || '';
  const valuesQuery = useQuery({
    queryKey: ['dataset-chart-values', ...keyScope, path, resolvedEntityColumn],
    queryFn: ({ signal }) =>
      previewChartValues(
        path,
        { entity_column: resolvedEntityColumn, limit: ENTITY_VALUE_LIMIT, offset: 0 },
        signal,
      ),
    enabled: Boolean(resolvedEntityColumn),
  });
  const entityValues = valuesQuery.data?.values ?? [];
  const entityLabelOf = useEntityLabelOf(valuesQuery.data?.labels);
  const resolvedEntityValue = entityValue || bundle?.selected_entity_value || entityValues[0] || '';

  const overlayOptions = priceOverlayOptions(useBenchmarks().data ?? []);
  const overlayOption = resolvePriceOverlay(overlayOptions, overlayChoice);
  // An empty ticker disables the shared benchmark query, so 'none' costs no request.
  const overlayQuery = useBenchmark(overlayOption.ticker ?? '');
  const overlay: DatasetPriceOverlaySeries | null =
    overlayOption.ticker && overlayQuery.data
      ? {
          id: overlayOption.value,
          label: overlayOption.label,
          points: parsePriceOverlayPoints(overlayQuery.data.data),
        }
      : null;
  const overlayLoading = isLoadingData(overlayQuery);
  const overlayError =
    overlayQuery.error && overlayQuery.data === undefined ? overlayQuery.error.message : null;

  // Only a failure with nothing to show is reported; a failed refresh keeps the data.
  const error =
    [metaQuery, bundleQuery, valuesQuery].find((q) => q.error && q.data === undefined)?.error
      ?.message ?? null;

  // A user edit materializes whatever the grid currently shows, seeded cells included.
  const materializedCells = [...activeCells, ...cells.slice(cellCount)];

  function updateLayout(value: string) {
    const next = LAYOUTS.find((item) => item.value === value) ?? LAYOUTS[0];
    setLayoutValue(next.value);
    const nextCells = [...materializedCells];
    while (nextCells.length < next.rows * next.cols) {
      nextCells.push({ id: `cell-${nextCells.length + 1}`, leftMetric: null, rightMetric: null });
    }
    setCells(nextCells);
  }

  function updateCell(cellId: string, side: 'leftMetric' | 'rightMetric', metric: string | null) {
    setCells(
      materializedCells.map((cell) => (cell.id === cellId ? { ...cell, [side]: metric } : cell)),
    );
  }

  const metricColors = Object.fromEntries(
    (bundle?.y_columns ?? []).map((metric, index) => [
      metric,
      CHART_COLORS[index % CHART_COLORS.length],
    ]),
  );

  // First load only: a parameter change keeps the toolbar and skeletons each cell instead.
  if (!bundle && (isLoadingData(metaQuery) || isLoadingData(bundleQuery))) {
    return <LoadingSkeleton variant="chart" />;
  }
  const retryLoad = () => {
    void metaQuery.refetch();
    void bundleQuery.refetch();
    void valuesQuery.refetch();
  };

  if (error && !bundle) return <ErrorPanel message={error} onRetry={retryLoad} />;
  if (bundle && !bundle.chartable) {
    return <EmptyState title="Dataset is not chartable" hint={bundle.reason ?? undefined} />;
  }

  const fillGrid = layout.rows <= 2;
  const grid = (
    <ChartGrid variant="hairline" columns={layout.cols} fill={fillGrid}>
      {activeCells.map((cell) => {
        const chart = bundle?.charts.find((item) => item.chart_id === cell.id);
        return (
          <ChartGridCell
            key={cell.id}
            target={activeCells.length > 1 && cell.id === targetCell?.id}
            onPointerDownCapture={() => setTargetCellId(cell.id)}
            onFocusCapture={() => setTargetCellId(cell.id)}
          >
            {isPlaceholder ? (
              <LoadingSkeleton variant="chart" label={`Loading ${cellLabel(cell.id)}`} />
            ) : (
              <MultiSeriesTimeChart
                {...(activeCells.length > 1 ? { title: cellLabel(cell.id) } : {})}
                series={chart?.series ?? []}
                metricColors={metricColors}
                benchmark={overlay}
                transformControls={DATASET_TRANSFORM_CONTROLS}
              />
            )}
          </ChartGridCell>
        );
      })}
    </ChartGrid>
  );

  return (
    <ChartTransformGroupProvider toolbarVariant="menu">
      <SplitRow
        as="section"
        fill
        aria-label="Dataset chart workspace"
        aside={
          <DatasetChartFeatureRail
            metrics={bundle?.y_columns ?? []}
            families={bundle?.families ?? []}
            metricFamilies={bundle?.y_column_families ?? {}}
            cells={activeCells.map((cell) => ({
              id: cell.id,
              label: cellLabel(cell.id),
              leftMetric: cell.leftMetric,
              rightMetric: cell.rightMetric,
            }))}
            targetCellId={targetCell?.id ?? 'cell-1'}
            collapsed={railCollapsed}
            onTargetCellChange={setTargetCellId}
            onToggleCollapse={() => setRailCollapsed((value) => !value)}
            onAssign={updateCell}
          />
        }
      >
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {/* The same full-width hairline band as Table mode, one shell bar tall so its
              rule continues the Features rail's header rule. */}
          <Toolbar band aria-label="Dataset chart controls" className="min-h-(--shell-bar-height)">
            {toolbarLead}
            {resolvedEntityColumn && (bundle?.entity_columns.length ?? 0) > 1 ? (
              <SelectControl
                ariaLabel="Entity column"
                value={resolvedEntityColumn}
                onValueChange={(value) => {
                  setEntityColumn(value);
                  setEntityValue('');
                }}
                options={
                  bundle?.entity_columns.map((column) => ({ value: column, label: column })) ?? []
                }
              />
            ) : null}
            {resolvedEntityColumn && entityValues.length > 1 ? (
              <SearchSelect
                label={resolvedEntityColumn}
                items={entityValues}
                labelOf={entityLabelOf}
                value={resolvedEntityValue || null}
                placeholder={`search ${resolvedEntityColumn}…`}
                onChange={(value) => setEntityValue(value ?? '')}
              />
            ) : null}
            <DatasetPriceOverlayControl
              options={overlayOptions}
              selection={overlayOption.value}
              loading={overlayLoading}
              error={overlayError}
              onChange={(value) => setOverlayChoice(value)}
            />
            <Field label="Grid" htmlFor={`${controlId}-grid`} layout="inline">
              <SelectControl
                id={`${controlId}-grid`}
                value={layoutValue}
                onValueChange={updateLayout}
                options={LAYOUTS.map((item) => ({ value: item.value, label: item.value }))}
              />
            </Field>
            {activeCells.length > 1 ? <ChartTransformMasterToolbar /> : null}
          </Toolbar>
          <Inset padding="pane" className="flex min-h-0 min-w-0 flex-1 flex-col">
            <Stack gap="block" className="min-h-0 flex-1">
              {error ? <ErrorPanel message={error} onRetry={retryLoad} /> : null}
              <Surface padding="none" clip className="flex min-h-0 flex-1 flex-col">
                {fillGrid ? (
                  grid
                ) : (
                  <ScrollArea axis="y" fill label="Dataset charts">
                    {grid}
                  </ScrollArea>
                )}
              </Surface>
            </Stack>
          </Inset>
        </div>
      </SplitRow>
    </ChartTransformGroupProvider>
  );
}
