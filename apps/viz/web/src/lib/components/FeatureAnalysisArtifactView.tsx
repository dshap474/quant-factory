/**
 * Operator-focused summaries for physical feature-analysis parquet artifacts.
 *
 * USAGE:
 *   <FeatureAnalysisArtifactView preview={preview} scope="features" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Heatmap } from '@quant-factory/qf-ui/charts/renderers';
import { DataTable } from '@quant-factory/qf-ui/tables';
import { compactDtype } from '@quant-factory/qf-ui/tables/core';
import { useQuery } from '@tanstack/react-query';
import { type ParquetPreview, queryDataParquet } from '@/lib/api/catalog';
import { queryFeatureParquet } from '@/lib/api/features';
import { STALE } from '@/lib/api/stale-times';
import {
  Columns,
  divergingCellColor,
  EmptyState,
  ErrorPanel,
  formatNumber,
  formatPercent,
  isLoadingData,
  LoadingSkeleton,
  ProgressBar,
  Stack,
  StatGrid,
  StatItem,
  Surface,
  Text,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Types and helpers
// --------------------------------------------------------------------------- #

export interface FeatureAnalysisArtifactViewProps {
  preview: ParquetPreview;
  scope: 'data' | 'features';
}

type ArtifactKind = 'heatmap' | 'quality' | 'horizon' | 'pairs' | 'clusters' | 'table';

const META: Record<string, { title: string; description: string; kind: ArtifactKind }> = {
  analysis_correlation_heatmap: {
    title: 'Correlation Heatmap',
    description: 'Signed pairwise feature correlations.',
    kind: 'heatmap',
  },
  analysis_cluster_heatmap: {
    title: 'Cluster Heatmap',
    description: 'Correlation cells ordered by deterministic feature clusters.',
    kind: 'heatmap',
  },
  analysis_feature_quality: {
    title: 'Feature Quality and Missingness',
    description: 'Coverage and quality checks for every feature.',
    kind: 'quality',
  },
  analysis_horizon_ic_matrix: {
    title: 'Horizon IC Matrix',
    description: 'Feature evidence across configured return horizons.',
    kind: 'horizon',
  },
  analysis_correlation_pairs: {
    title: 'Correlation Pairs',
    description: 'Feature pairs above the configured correlation threshold.',
    kind: 'pairs',
  },
  analysis_correlation_clusters: {
    title: 'Correlation Clusters',
    description: 'Feature groups and their deterministic representatives.',
    kind: 'clusters',
  },
};

function numberValue(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function textValue(value: unknown): string {
  return value === null || value === undefined ? '' : String(value);
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function FeatureAnalysisArtifactView({ preview, scope }: FeatureAnalysisArtifactViewProps) {
  const stem = (preview.path.split('/').pop() ?? '').replace(/\.parquet$/, '');
  const meta = META[stem] ?? {
    title: 'Analysis Artifact',
    description: 'Feature-analysis parquet artifact.',
    kind: 'table' as const,
  };
  const shouldLoadAll = meta.kind !== 'table';
  const allRowsQuery = useQuery({
    queryKey: ['feature-analysis-artifact', scope, preview.path],
    queryFn: ({ signal }) => {
      const query = scope === 'features' ? queryFeatureParquet : queryDataParquet;
      return query(preview.path, { limit: 100_000 }, signal);
    },
    enabled: shouldLoadAll,
    staleTime: STALE.catalog,
  });

  const rows: Record<string, unknown>[] = shouldLoadAll
    ? (allRowsQuery.data?.data ?? [])
    : preview.rows;
  const loading = isLoadingData(allRowsQuery);
  const error =
    allRowsQuery.error && allRowsQuery.data === undefined ? allRowsQuery.error.message : null;

  const quality = (() => {
    const counts = new Map<string, number>();
    let coverage = 0;
    let coverageCount = 0;
    for (const row of rows) {
      const status = textValue(row.quality_status) || 'unknown';
      counts.set(status, (counts.get(status) ?? 0) + 1);
      const value = numberValue(row.coverage);
      if (value !== null) {
        coverage += value;
        coverageCount += 1;
      }
    }
    return {
      total: rows.length,
      ok: counts.get('ok') ?? 0,
      warn: counts.get('warn') ?? 0,
      bad: counts.get('bad') ?? 0,
      coverage: coverageCount ? coverage / coverageCount : null,
      weakest: [...rows]
        .sort((a, b) => (numberValue(a.coverage) ?? 1) - (numberValue(b.coverage) ?? 1))
        .slice(0, 20),
    };
  })();

  const heatmap = (() => {
    const cells = rows
      .map((row) => ({
        row: numberValue(row.row_index),
        column: numberValue(row.column_index),
        value: numberValue(row.correlation),
        rowFeature: textValue(row.row_feature),
        columnFeature: textValue(row.column_feature),
      }))
      .filter(
        (
          cell,
        ): cell is {
          row: number;
          column: number;
          value: number | null;
          rowFeature: string;
          columnFeature: string;
        } => cell.row !== null && cell.column !== null,
      );
    const dimension = cells.reduce((max, cell) => Math.max(max, cell.row + 1, cell.column + 1), 0);
    const rowLabelByIndex = new Map(cells.map((cell) => [cell.row, cell.rowFeature]));
    const columnLabelByIndex = new Map(cells.map((cell) => [cell.column, cell.columnFeature]));
    const rowLabels = Array.from({ length: dimension }, (_, index) => {
      return rowLabelByIndex.get(index) || String(index + 1);
    });
    const columnLabels = Array.from({ length: dimension }, (_, index) => {
      return columnLabelByIndex.get(index) || String(index + 1);
    });
    return { cells, dimension, rowLabels, columnLabels };
  })();

  if (loading) return <LoadingSkeleton variant="chart" />;
  if (error) return <ErrorPanel message={error} onRetry={() => void allRowsQuery.refetch()} />;

  return (
    <Stack as="section" gap="block">
      <header>
        <Text as="p" variant="label">
          Feature analysis
        </Text>
        <Text as="h2" size="lg" weight="semibold">
          {meta.title}
        </Text>
        <Text as="p" size="sm" tone="muted">
          {meta.description}
        </Text>
      </header>
      {meta.kind === 'heatmap' ? (
        heatmap.cells.length ? (
          <Surface padding="sm">
            <Heatmap
              xLabels={heatmap.columnLabels}
              yLabels={heatmap.rowLabels}
              cells={heatmap.cells.map((cell) => ({
                x: cell.column,
                y: cell.row,
                value: cell.value ?? 0,
                display: '',
                tooltip: `${cell.rowFeature} × ${cell.columnFeature}: ${formatNumber(cell.value, 4)}`,
                color: divergingCellColor(cell.value, {
                  magnitude: stem === 'analysis_cluster_heatmap',
                }),
              }))}
              ariaLabel={meta.title}
              showAxisLabels={false}
              showCellLabels={false}
            />
          </Surface>
        ) : (
          <EmptyState title="No heatmap cells available" />
        )
      ) : null}
      {meta.kind === 'quality' ? (
        <>
          <StatGrid variant="strip" boxed>
            {[
              ['Features', quality.total],
              ['OK', quality.ok],
              ['Warn', quality.warn],
              ['Bad', quality.bad],
              ['Avg coverage', formatPercent(quality.coverage)],
            ].map(([label, value]) => (
              <StatItem
                key={String(label)}
                label={String(label)}
                value={typeof value === 'number' ? value.toLocaleString() : value}
              />
            ))}
          </StatGrid>
          <Surface>
            <Stack gap="heading">
              <Text as="h3" weight="semibold">
                Lowest coverage
              </Text>
              <div className="space-y-2">
                {quality.weakest.map((row) => {
                  const value = numberValue(row.coverage) ?? 0;
                  return (
                    <Columns
                      key={textValue(row.feature)}
                      template="minmax(12rem,1fr) minmax(8rem,16rem) 4rem"
                      gap="heading"
                      className="items-center"
                    >
                      <span className="truncate">{textValue(row.feature)}</span>
                      <ProgressBar
                        value={Math.max(0, Math.min(1, value))}
                        max={1}
                        label={`${textValue(row.feature)} coverage`}
                      />
                      <Text as="strong" variant="data" className="text-right">
                        {formatPercent(value)}
                      </Text>
                    </Columns>
                  );
                })}
              </div>
            </Stack>
          </Surface>
        </>
      ) : null}
      {meta.kind !== 'heatmap' ? (
        <Surface padding="none">
          <DataTable
            dense
            rowOffset={0}
            data={rows}
            columns={preview.schema.map((column) => column.name)}
            columnTypes={Object.fromEntries(
              preview.schema.map((column) => [column.name, compactDtype(column.dtype)]),
            )}
            maxRows={Math.min(rows.length, 1_000)}
          />
        </Surface>
      ) : null}
    </Stack>
  );
}
