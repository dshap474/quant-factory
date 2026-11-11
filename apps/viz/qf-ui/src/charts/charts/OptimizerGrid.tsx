/**
 * Controlled optimizer heatmap with package-owned generic row contracts.
 *
 * USAGE:
 *   <OptimizerGrid dimensions={dimensions} metrics={metrics} rows={rows} selection={selection} onChange={setSelection} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { CSSProperties, ReactNode } from 'react';
import { GridSelect } from './GridSelect';
import { Heatmap, type HeatmapCell } from './Heatmap';
import { extent } from './multiSeriesModel';
import styles from './OptimizerGrid.module.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type OptimizerGridFormat = 'bps' | 'percent' | 'number' | 'money';

export interface OptimizerGridDimension {
  key: string;
  label: string;
  format: OptimizerGridFormat;
  values: readonly number[];
}
export interface OptimizerGridMetric {
  key: string;
  label: string;
  format: OptimizerGridFormat;
  higherIsBetter: boolean;
}
export interface OptimizerGridRow {
  id: string;
  rank: number;
  isControl?: boolean;
  values: Readonly<Record<string, number | null>>;
}
export interface OptimizerGridSelection {
  xKey: string;
  yKey: string;
  metricKey: string;
  rowId: string;
}
export interface OptimizerGridProps {
  dimensions: readonly OptimizerGridDimension[];
  metrics: readonly OptimizerGridMetric[];
  rows: readonly OptimizerGridRow[];
  selection: OptimizerGridSelection;
  onChange: (selection: OptimizerGridSelection) => void;
  ariaLabel?: string;
  className?: string;
  accentColor?: string;
  surfaceColor?: string;
  controlLabel?: string;
  intro?: ReactNode;
}

// --------------------------------------------------------------------------- #
// Model
// --------------------------------------------------------------------------- #

export function optimizerValue(row: OptimizerGridRow, key: string): number {
  const value = row.values[key];
  if (typeof value !== 'number' || !Number.isFinite(value))
    throw new Error(`Optimizer grid value “${key}” is not finite`);
  return value;
}

export function formatOptimizerValue(value: number | null, format: OptimizerGridFormat): string {
  if (value === null) return '—';
  if (format === 'bps') return `${(value * 10_000).toFixed(0)} bps`;
  if (format === 'percent') return `${(value * 100).toFixed(2)}%`;
  if (format === 'money') return `$${value.toFixed(2)}`;
  return value.toFixed(3);
}

function metricValue(row: OptimizerGridRow, key: string): number | null {
  return row.values[key] == null ? null : optimizerValue(row, key);
}

function metricPosition(
  value: number,
  range: readonly [number, number],
  higherIsBetter: boolean,
): number {
  const [minimum, maximum] = range;
  if (minimum === maximum) return 0.5;
  const position = (value - minimum) / (maximum - minimum);
  return higherIsBetter ? position : 1 - position;
}

function sliceRows(
  rows: readonly OptimizerGridRow[],
  dimensions: readonly OptimizerGridDimension[],
  xKey: string,
  yKey: string,
  selected: OptimizerGridRow,
): OptimizerGridRow[] {
  const fixed = dimensions.filter((dimension) => dimension.key !== xKey && dimension.key !== yKey);
  return rows.filter((row) =>
    fixed.every(
      (dimension) => optimizerValue(row, dimension.key) === optimizerValue(selected, dimension.key),
    ),
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function OptimizerGrid({
  dimensions,
  metrics,
  rows,
  selection,
  onChange,
  ariaLabel = 'Optimizer response surface',
  className = '',
  accentColor = 'var(--qf-chart-bitcoin-accent)',
  surfaceColor = 'var(--qf-chart-surface)',
  controlLabel = 'Control',
  intro = 'Each cell is a complete out-of-sample stream. Color rankings stay fixed across every slice.',
}: OptimizerGridProps) {
  const xDimension = dimensions.find((item) => item.key === selection.xKey);
  const yDimension = dimensions.find((item) => item.key === selection.yKey);
  const metric = metrics.find((item) => item.key === selection.metricKey);
  const selected =
    rows.find((row) => row.id === selection.rowId) ??
    [...rows].sort((left, right) => left.rank - right.rank)[0];
  if (!xDimension || !yDimension || !metric || !selected) return null;
  const emit = (next: Partial<OptimizerGridSelection>) => onChange({ ...selection, ...next });
  const fixed = dimensions.filter(
    (item) => item.key !== selection.xKey && item.key !== selection.yKey,
  );
  const visibleRows = sliceRows(rows, dimensions, selection.xKey, selection.yKey, selected);
  const metricRange = extent(
    rows.flatMap((row) => {
      const value = metricValue(row, metric.key);
      return value === null ? [] : [value];
    }),
  );
  const byPosition = new Map(
    visibleRows.map((row) => [
      [optimizerValue(row, selection.xKey), optimizerValue(row, selection.yKey)].join(':'),
      row,
    ]),
  );
  const cells: HeatmapCell[] = yDimension.values.flatMap((yValue, y) =>
    xDimension.values.flatMap((xValue, x) => {
      const row = byPosition.get([xValue, yValue].join(':'));
      if (!row) return [];
      const value = metricValue(row, metric.key);
      if (value === null) return [];
      const mix = 12 + metricPosition(value, metricRange, metric.higherIsBetter) * 70;
      return [
        {
          x,
          y,
          value,
          display: `${formatOptimizerValue(value, metric.format)}\nrank ${row.rank}`,
          tooltip: `${row.id} · rank ${row.rank} · ${metric.label}: ${formatOptimizerValue(value, metric.format)}`,
          color: `color-mix(in oklch, ${accentColor} ${mix}%, ${surfaceColor})`,
          selected: row.id === selected.id,
        },
      ];
    }),
  );
  const rootStyle = {
    '--optimizer-grid-accent': accentColor,
    '--optimizer-grid-surface': surfaceColor,
  } as CSSProperties;
  const dimensionSelect = (dimension: OptimizerGridDimension) => (
    <label className={styles.field} key={dimension.key} htmlFor={`optimizer-grid-${dimension.key}`}>
      <span className={styles.fieldLabel}>{dimension.label}</span>
      <GridSelect
        id={`optimizer-grid-${dimension.key}`}
        value={String(optimizerValue(selected, dimension.key))}
        options={dimension.values.map((value) => ({
          value: String(value),
          label: formatOptimizerValue(value, dimension.format),
        }))}
        onChange={(nextValue) => {
          const value = Number(nextValue);
          const leader = [...rows]
            .filter((row) =>
              fixed.every(
                (item) =>
                  optimizerValue(row, item.key) ===
                  (item.key === dimension.key ? value : optimizerValue(selected, item.key)),
              ),
            )
            .sort((left, right) => left.rank - right.rank)[0];
          if (leader) emit({ rowId: leader.id });
        }}
      />
    </label>
  );
  return (
    <div className={[styles.root, className].filter(Boolean).join(' ')} style={rootStyle}>
      <div className={styles.intro}>{intro}</div>
      {/* biome-ignore lint/a11y/useSemanticElements: preserving the established optimizer toolbar DOM avoids fieldset browser geometry. */}
      <div className={styles.toolbar} role="group" aria-label="Optimizer grid controls">
        <label className={styles.field} htmlFor="optimizer-grid-metric">
          <span className={styles.fieldLabel}>Metric</span>
          <GridSelect
            id="optimizer-grid-metric"
            value={selection.metricKey}
            options={metrics.map((item) => ({ value: item.key, label: item.label }))}
            onChange={(metricKey) => emit({ metricKey })}
          />
        </label>
        <label className={styles.field} htmlFor="optimizer-grid-x">
          <span className={styles.fieldLabel}>X axis</span>
          <GridSelect
            id="optimizer-grid-x"
            value={selection.xKey}
            options={dimensions
              .filter((item) => item.key !== selection.yKey)
              .map((item) => ({ value: item.key, label: item.label }))}
            onChange={(xKey) => emit({ xKey })}
          />
        </label>
        <label className={styles.field} htmlFor="optimizer-grid-y">
          <span className={styles.fieldLabel}>Y axis</span>
          <GridSelect
            id="optimizer-grid-y"
            value={selection.yKey}
            options={dimensions
              .filter((item) => item.key !== selection.xKey)
              .map((item) => ({ value: item.key, label: item.label }))}
            onChange={(yKey) => emit({ yKey })}
          />
        </label>
        {fixed.map(dimensionSelect)}
      </div>
      <div className={styles.scroll}>
        <Heatmap
          xLabels={xDimension.values.map((value) => formatOptimizerValue(value, xDimension.format))}
          yLabels={yDimension.values.map((value) => formatOptimizerValue(value, yDimension.format))}
          cells={cells}
          height={Math.max(330, yDimension.values.length * 84 + 80)}
          ariaLabel={`${ariaLabel}; ${metric.label}; ${yDimension.label} by ${xDimension.label}`}
          className={styles.chart}
          onCellClick={(cell) => {
            const row = byPosition.get(
              [xDimension.values[cell.x], yDimension.values[cell.y]].join(':'),
            );
            if (row) emit({ rowId: row.id });
          }}
        />
      </div>
      <div className={styles.legend}>
        <span>Worse</span>
        <span className={styles.gradient} aria-hidden="true" />
        <span>Better across all {rows.length} configurations</span>
      </div>
      <div className={styles.selection}>
        <strong>Selected #{selected.rank}</strong>
        <code>{selected.id}</code>
        <span>
          {metric.label}: {formatOptimizerValue(metricValue(selected, metric.key), metric.format)}
        </span>
        {selected.isControl ? <span>{controlLabel}</span> : null}
      </div>
    </div>
  );
}
