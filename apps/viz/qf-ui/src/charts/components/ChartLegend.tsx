/**
 * Controlled legend for ordinary chart series (benchmark overlays never appear), plus
 * the hover-emphasis row and class helper for hosts that compose their own legend.
 *
 * USAGE:
 *   <ChartLegend series={series} hiddenSeries={hidden} onHiddenSeriesChange={setHidden}
 *     emphasizedSeries={hovered} onEmphasizedSeriesChange={setHovered} />
 *   <ChartLegendItem seriesId="signal" swatch={chartColor(1)} hoveredSeries={hovered}
 *     onHoveredSeriesChange={setHovered}>Signal</ChartLegendItem>
 *   <div className={legendItemClass('strategy', hovered)} …>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import type { QfSeries } from '../types/contracts';
import { ChartLegendLabel } from './ChartLegendLabel';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartLegendProps {
  series: readonly QfSeries[];
  hiddenSeries: ReadonlySet<string>;
  onHiddenSeriesChange(next: ReadonlySet<string>): void;
  emphasizedSeries?: string | null;
  onEmphasizedSeriesChange?(key: string | null): void;
  ariaLabel?: string;
}

export interface ChartLegendItemProps {
  /** Series key matched against `hoveredSeries`. */
  seriesId: string;
  /** CSS colour of the solid marker, e.g. `chartColor(1)`. */
  swatch: string;
  hoveredSeries?: string | null;
  onHoveredSeriesChange?(seriesId: string | null): void;
  /** Row label, rendered inside a `ChartLegendLabel`. */
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Legend row classes; every row but the hovered one is muted while hovering. */
export function legendItemClass(seriesId: string, hoveredSeries: string | null): string {
  return hoveredSeries != null && hoveredSeries !== seriesId
    ? 'chart-legend-item is-muted'
    : 'chart-legend-item';
}

/** Solid series marker coloured through the `--legend-color` custom property. */
function LegendMarker({ color }: { color: string | undefined }) {
  return (
    <span className="chart-legend-marker solid" style={{ ['--legend-color' as string]: color }} />
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ChartLegend({
  series,
  hiddenSeries,
  onHiddenSeriesChange,
  emphasizedSeries = null,
  onEmphasizedSeriesChange,
  ariaLabel = 'Chart series',
}: ChartLegendProps) {
  return (
    <fieldset className="qf-chart-legend-group" aria-label={ariaLabel}>
      {series
        .filter((item) => !item.isBenchmark)
        .map((item) => {
          const visible = !hiddenSeries.has(item.key);
          const emphasized = visible && emphasizedSeries === item.key;
          const muted = emphasizedSeries != null && emphasizedSeries !== item.key;
          return (
            <button
              className={[
                'chart-legend-item chart-legend-toggle',
                emphasized ? 'is-pinned' : '',
                muted ? 'is-muted' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              type="button"
              key={item.key}
              aria-label={`${visible ? 'Hide' : 'Show'} ${item.label}`}
              aria-pressed={visible}
              title={item.label}
              onPointerEnter={() => {
                if (visible) onEmphasizedSeriesChange?.(item.key);
              }}
              onPointerLeave={() => onEmphasizedSeriesChange?.(null)}
              onFocus={() => {
                if (visible) onEmphasizedSeriesChange?.(item.key);
              }}
              onBlur={() => onEmphasizedSeriesChange?.(null)}
              onClick={() => {
                const next = new Set(hiddenSeries);
                if (visible) {
                  next.add(item.key);
                  onEmphasizedSeriesChange?.(null);
                } else next.delete(item.key);
                onHiddenSeriesChange(next);
              }}
            >
              <LegendMarker color={item.color} />
              <ChartLegendLabel focusable={false}>{item.label}</ChartLegendLabel>
            </button>
          );
        })}
    </fieldset>
  );
}

/** Static legend row: marker plus label, muted while another series is hovered. */
export function ChartLegendItem({
  seriesId,
  swatch,
  hoveredSeries = null,
  onHoveredSeriesChange,
  children,
}: ChartLegendItemProps) {
  return (
    <div
      className={legendItemClass(seriesId, hoveredSeries)}
      onPointerEnter={() => onHoveredSeriesChange?.(seriesId)}
      onPointerLeave={() => onHoveredSeriesChange?.(null)}
    >
      <LegendMarker color={swatch} />
      <ChartLegendLabel>{children}</ChartLegendLabel>
    </div>
  );
}
