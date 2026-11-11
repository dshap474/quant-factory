/**
 * Accessible categorical heatmap rendered through QfChart.
 *
 * USAGE:
 *   <Heatmap xLabels={x} yLabels={y} cells={cells} ariaLabel="Correlation" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useEffect, useMemo, useState } from 'react';

import { QF_CHART_ASPECT_RATIO, QfChart, type QfChartOption } from '../core/QfChart';
import { qfEChartsTooltip } from '../core/tooltip';
import { type QfChartTheme, useChartTheme } from '../hooks/useChartTheme';
import { resolveChartFont, resolveCssColor } from '../theme/tokens';
import { escapeHtml } from '../utils/escapeHtml';
import { extent } from './multiSeriesModel';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface HeatmapCell {
  x: number;
  y: number;
  value: number;
  display: string;
  tooltip: string;
  color: string;
  selected?: boolean;
}

export interface HeatmapProps {
  xLabels: readonly string[];
  yLabels: readonly string[];
  cells: readonly HeatmapCell[];
  ariaLabel: string;
  height?: number | string | undefined;
  className?: string | undefined;
  onCellClick?: ((cell: HeatmapCell) => void) | undefined;
  showAxisLabels?: boolean | undefined;
  showCellLabels?: boolean | undefined;
  /** Width of the y-axis label column in px; longer labels truncate. Default 92. */
  yLabelWidth?: number | undefined;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function datum(params: unknown): { display?: string; tooltip?: string } {
  if (!params || typeof params !== 'object') return {};
  const data = (params as { data?: unknown }).data;
  return data && typeof data === 'object' ? (data as { display?: string; tooltip?: string }) : {};
}

function dataIndex(params: unknown): number | null {
  if (!params || typeof params !== 'object') return null;
  const value = (params as { dataIndex?: unknown }).dataIndex;
  return typeof value === 'number' ? value : null;
}

// --------------------------------------------------------------------------- #
// Cell data
// --------------------------------------------------------------------------- #

// Takes the whole theme so React Compiler keys the memo on it: cell colours are caller
// tokens (tones, ramps) whose resolved values change with `data-theme` even when the
// neutrals this mapping reads stay the same.
function cellData(
  cells: readonly HeatmapCell[],
  activeIndex: number,
  onCellClick: HeatmapProps['onCellClick'],
  theme: QfChartTheme,
) {
  return cells.map((cell, index) => {
    const color = resolveCssColor(cell.color);
    const active = cell.selected || Boolean(onCellClick && index === activeIndex);
    return {
      value: [cell.x, cell.y, cell.value],
      display: cell.display,
      tooltip: cell.tooltip,
      itemStyle: {
        color,
        // Gutters in the surface colour separate cells without drawing a grid.
        borderColor: active ? theme.tooltipText : theme.background,
        borderWidth: active ? 3 : 1,
        borderRadius: 4,
      },
      emphasis: {
        itemStyle: {
          color,
          borderColor: active ? theme.tooltipText : theme.axis,
          borderWidth: active ? 3 : 1,
        },
      },
    };
  });
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Heatmap({
  xLabels,
  yLabels,
  cells,
  ariaLabel,
  height,
  className,
  onCellClick,
  showAxisLabels = true,
  showCellLabels = true,
  yLabelWidth = 92,
}: HeatmapProps) {
  const theme = useChartTheme();
  const selectedIndex = cells.findIndex((cell) => cell.selected);
  const [activeIndex, setActiveIndex] = useState(() => Math.max(0, selectedIndex));
  useEffect(() => {
    if (selectedIndex >= 0) setActiveIndex(selectedIndex);
    else if (activeIndex >= cells.length) setActiveIndex(Math.max(0, cells.length - 1));
  }, [activeIndex, cells.length, selectedIndex]);
  const activeCell = cells[activeIndex];
  const [minimum, maximum] =
    cells.length > 0 ? extent(cells.map((cell) => cell.value)) : ([0, 1] as const);
  const option = useMemo<QfChartOption>(
    () => ({
      animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      animationDuration: 150,
      stateAnimation: { duration: 0 },
      backgroundColor: 'transparent',
      grid: showAxisLabels
        ? { top: 16, right: 18, bottom: 54, left: yLabelWidth + 12, containLabel: false }
        : { top: 4, right: 4, bottom: 4, left: 4, containLabel: false },
      visualMap: {
        show: false,
        min: minimum,
        max: maximum === minimum ? minimum + 1 : maximum,
        dimension: 2,
        seriesIndex: 0,
      },
      xAxis: {
        type: 'category',
        data: xLabels,
        axisLabel: {
          show: showAxisLabels,
          color: theme.axis,
          fontSize: 11,
          interval: 0,
          hideOverlap: true,
        },
        axisLine: { show: showAxisLabels, lineStyle: { color: theme.frame } },
        axisTick: { show: false },
        splitArea: { show: false },
      },
      yAxis: {
        type: 'category',
        data: yLabels,
        inverse: true,
        axisLabel: {
          show: showAxisLabels,
          color: theme.axis,
          fontSize: 11,
          width: yLabelWidth,
          overflow: 'truncate',
        },
        axisLine: { show: showAxisLabels, lineStyle: { color: theme.frame } },
        axisTick: { show: false },
      },
      tooltip: {
        ...qfEChartsTooltip(theme),
        formatter: (params: unknown) => escapeHtml(datum(params).tooltip ?? ''),
      },
      series: [
        {
          type: 'heatmap',
          data: cellData(cells, activeIndex, onCellClick, theme),
          label: {
            show: showCellLabels,
            color: theme.tooltipText,
            fontFamily: resolveChartFont(),
            fontSize: 11,
            formatter: (params: unknown) => datum(params).display ?? '',
          },
        },
      ],
      aria: { enabled: true, decal: { show: false } },
    }),
    [
      activeIndex,
      cells,
      maximum,
      minimum,
      onCellClick,
      showAxisLabels,
      showCellLabels,
      theme,
      yLabelWidth,
      xLabels,
      yLabels,
    ],
  );

  const interactiveLabel = activeCell
    ? `${ariaLabel}. ${activeCell.tooltip}. Use arrow keys to move and Enter to select.`
    : ariaLabel;
  const chart = (
    <QfChart
      option={option}
      ariaLabel={interactiveLabel}
      height={height ?? '100%'}
      className={className}
      interactive={Boolean(onCellClick)}
      onClick={(params) => {
        const index = dataIndex(params);
        if (index == null) return;
        const cell = cells[index];
        if (!cell) return;
        setActiveIndex(index);
        onCellClick?.(cell);
      }}
      onKeyDown={(event) => {
        if (!onCellClick || cells.length === 0) return;
        const columns = Math.max(1, xLabels.length);
        let next = activeIndex;
        if (event.key === 'ArrowLeft') next -= 1;
        else if (event.key === 'ArrowRight') next += 1;
        else if (event.key === 'ArrowUp') next -= columns;
        else if (event.key === 'ArrowDown') next += columns;
        else if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          if (activeCell) onCellClick(activeCell);
          return;
        } else return;
        event.preventDefault();
        setActiveIndex(Math.min(cells.length - 1, Math.max(0, next)));
      }}
    />
  );
  if (height != null) return chart;
  return <div style={{ aspectRatio: `${QF_CHART_ASPECT_RATIO} / 1` }}>{chart}</div>;
}
