/**
 * Compact correlation and information-coefficient analysis views for feature datasets.
 *
 * USAGE:
 *   <FeatureAnalysisView path="1d/example/data.parquet" mode="correlation" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  DataTable,
  type DataTableColumn,
  Table,
  TableBody,
  TableCell,
  TableRow,
} from '@quant-factory/qf-ui/tables';
import { useFeatureAnalysisCorrelation, useFeatureAnalysisIc } from '@/lib/api/features';
import {
  Badge,
  Cluster,
  Columns,
  EmptyState,
  ErrorPanel,
  extentBy,
  formatNumber,
  formatPercent,
  Inset,
  isLoadingData,
  LoadingSkeleton,
  ProgressBar,
  ScrollArea,
  Section,
  Stack,
  StatGrid,
  StatItem,
  Surface,
  Text,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Types and helpers
// --------------------------------------------------------------------------- #

/** One feature x horizon IC summary cell. */
interface IcCell {
  value: number | null;
  raw: number | null;
  positive: number | null;
  folds: number | null;
}

export interface FeatureAnalysisViewProps {
  path: string;
  mode: 'correlation' | 'ic';
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function FeatureAnalysisView({ path, mode }: FeatureAnalysisViewProps) {
  const correlationQuery = useFeatureAnalysisCorrelation(mode === 'correlation' ? path : '');
  const icQuery = useFeatureAnalysisIc(mode === 'ic' ? path : '');

  const ic = (() => {
    const source = icQuery.data;
    if (!source) return null;
    const horizonIndex = new Map(source.horizons.map((horizon, index) => [horizon, index]));
    const cells = new Map<string, IcCell>();
    for (let index = 0; index < source.feature_index.length; index += 1) {
      const row = source.feature_index[index];
      const horizon = source.horizon[index];
      const column = horizonIndex.get(horizon) ?? 0;
      cells.set(`${row}-${column}`, {
        value: source.mean_oriented_ic[index] ?? null,
        raw: source.mean_validation_ic[index] ?? null,
        positive: source.positive_fold_rate[index] ?? null,
        folds: source.valid_folds[index] ?? null,
      });
    }
    const orientedExt = extentBy(source.mean_oriented_ic, (value) => Math.abs(value ?? 0));
    return {
      ...source,
      cells,
      maxAbs: Math.max(orientedExt?.max ?? 0.01, 0.01),
    };
  })();

  if (mode === 'correlation') {
    if (isLoadingData(correlationQuery)) return <LoadingSkeleton variant="chart" />;
    if (correlationQuery.error && !correlationQuery.data) {
      return (
        <ErrorPanel
          message={correlationQuery.error.message}
          onRetry={() => void correlationQuery.refetch()}
        />
      );
    }
    const data = correlationQuery.data;
    if (!data?.distribution.length) return <EmptyState title="No correlation summary found" />;
    const maxBucket = Math.max(extentBy(data.distribution, (bucket) => bucket.count)?.max ?? 1, 1);
    return (
      <Stack as="section" gap="block" aria-label="Correlation structure">
        <StatGrid variant="strip" boxed columns={4}>
          {[
            ['Features', data.feature_count],
            ['Clusters', data.clusters],
            ['Representatives', data.representatives],
            ['Pairs shown', data.returned_cells],
          ].map(([label, value]) => (
            <StatItem
              key={String(label)}
              label={String(label)}
              value={Number(value).toLocaleString()}
            />
          ))}
        </StatGrid>
        <Columns template="0.9fr 1.1fr" from="xl" gap="block">
          <Section title="Distribution">
            <Stack gap="block">
              {data.distribution.map((bucket) => (
                <div key={bucket.key} className="space-y-1.5">
                  <div className="flex justify-between">
                    <Text variant="caption" tone="default">
                      {bucket.label}
                    </Text>
                    <Text as="strong" variant="data">
                      {formatPercent(bucket.share, 0)}
                    </Text>
                  </div>
                  <ProgressBar value={bucket.count} max={maxBucket} label={bucket.label} />
                  <Text as="div" variant="caption">
                    {bucket.count.toLocaleString()} pairs
                  </Text>
                </div>
              ))}
            </Stack>
          </Section>
          <Section title="Strongest representative pairs">
            <Surface padding="none" clip>
              <ScrollArea axis="both" maxHeight="30rem">
                <Table density="dense">
                  <TableBody>
                    {data.top_pairs.map((pair) => (
                      <TableRow key={`${pair.row_feature}-${pair.column_feature}`}>
                        <TableCell wrap className="max-w-[24rem]">
                          <Text
                            as="strong"
                            variant="caption"
                            tone="default"
                            weight="semibold"
                            className="block truncate"
                          >
                            {pair.row_feature}
                          </Text>
                          <Text as="span" variant="caption" className="block truncate">
                            {pair.column_feature}
                          </Text>
                        </TableCell>
                        <TableCell numeric>
                          <Badge tone={pair.correlation < 0 ? 'critical' : 'success'}>
                            {formatNumber(pair.correlation)}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            </Surface>
          </Section>
        </Columns>
      </Stack>
    );
  }

  if (isLoadingData(icQuery)) return <LoadingSkeleton variant="chart" />;
  if (icQuery.error && !icQuery.data) {
    return <ErrorPanel message={icQuery.error.message} onRetry={() => void icQuery.refetch()} />;
  }
  if (!ic?.features.length) return <EmptyState title="No IC rows found for this feature version" />;

  const icCell = (row: Record<string, unknown>, key: string) => row[key] as IcCell | undefined;
  const icRows = ic.features.map((feature, rowIndex) => {
    const row: Record<string, unknown> = { feature, label: `${rowIndex + 1}. ${feature}` };
    ic.horizons.forEach((_, columnIndex) => {
      row[`h${columnIndex}`] = ic.cells.get(`${rowIndex}-${columnIndex}`);
    });
    return row;
  });
  const icColumns: DataTableColumn[] = [
    { key: 'label', header: 'Feature', truncate: 'end', title: (_, row) => String(row.feature) },
    ...ic.horizons.map((horizon, columnIndex): DataTableColumn => {
      const key = `h${columnIndex}`;
      return {
        key,
        header: `${horizon}d`,
        kind: 'heat',
        heat: { maxAbs: Math.max(ic.maxAbs, 0.01) },
        value: (row) => icCell(row, key)?.value ?? null,
        title: (_, row) => {
          const cell = icCell(row, key);
          return `${String(row.feature)} / ${horizon}d: ${formatNumber(cell?.value ?? null)} oriented IC, ${formatPercent(cell?.positive ?? null, 0)} positive folds, ${formatNumber(cell?.raw ?? null)} raw IC, ${formatNumber(cell?.folds ?? null, 0)} folds`;
        },
      };
    }),
  ];

  return (
    <Surface as="section" padding="none" clip aria-label="IC matrix">
      <DataTable data={icRows} columns={icColumns} dense flush maxRows={icRows.length} />
      <Inset padding="sm">
        <Cluster gap="block">
          <Text variant="caption">{ic.total_features.toLocaleString()} features</Text>
          <Text variant="caption">{ic.horizons.length} horizons</Text>
          <Text variant="caption">color: mean oriented IC</Text>
        </Cluster>
      </Inset>
    </Surface>
  );
}
