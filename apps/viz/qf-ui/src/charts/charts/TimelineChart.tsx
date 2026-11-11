/**
 * Horizontal timeline (Gantt) of bars on a shared clock: one row per item, placed by
 * start and sized by duration, colored by tone. Rows keep the given order, top first.
 * Clicking a bar reports its id; the selected bar gets a focus outline.
 *
 * USAGE:
 *   <TimelineChart
 *     ariaLabel="Step timeline"
 *     rows={steps.map((s) => ({ id: s.id, label: s.name, start, end }))}
 *     selected={stepId}
 *     onSelect={setStepId}
 *   />
 *
 * Without `height` the chart grows by row (22px each) so labels never overlap.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMemo } from 'react';

import { chartTooltipHtml } from '../components/ChartTooltip';
import { QfChart, type QfChartOption } from '../core/QfChart';
import { qfEChartsTooltip } from '../core/tooltip';
import { useChartTheme } from '../hooks/useChartTheme';
import { resolveCssColor } from '../theme/tokens';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TimelineRow {
  id: string;
  label: string;
  /** Epoch ms. */
  start: number;
  /** Epoch ms; at or before `start` draws a minimum-width tick. */
  end: number;
  /** CSS colour; defaults to the first palette slot. */
  color?: string | undefined;
  /** Extra tooltip line. */
  detail?: string | undefined;
}

export interface TimelineChartProps {
  rows: readonly TimelineRow[];
  ariaLabel: string;
  selected?: string | null | undefined;
  onSelect?: ((id: string) => void) | undefined;
  /** Tooltip duration text for a row; defaults to seconds. */
  formatDuration?: ((seconds: number) => string) | undefined;
  height?: number | string | undefined;
  className?: string | undefined;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const ROW_HEIGHT = 22;
const AXIS_ROOM = 36;

interface RenderApi {
  value: (dimension: number) => number;
  coord: (point: [number, number]) => [number, number];
  size: (point: [number, number]) => [number, number];
}

interface RenderParams {
  dataIndex: number;
  coordSys: { x: number; y: number; width: number; height: number };
}

/** Clock time; with seconds when the whole span is under 15 minutes. */
function clockLabel(ms: number, seconds = true): string {
  return new Date(ms).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    ...(seconds ? { second: '2-digit' } : {}),
  });
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function TimelineChart({
  rows,
  ariaLabel,
  selected = null,
  onSelect,
  formatDuration = (seconds) => `${Math.round(seconds)}s`,
  height,
  className,
}: TimelineChartProps) {
  const theme = useChartTheme();
  const option = useMemo<QfChartOption>(() => {
    const colors = rows.map((row) =>
      row.color ? resolveCssColor(row.color) : (theme.palette[0] ?? theme.axis),
    );
    const start = Math.min(...rows.map((row) => row.start));
    const end = Math.max(...rows.map((row) => Math.max(row.end, row.start)));
    const span = Math.max(1, end - start);
    return {
      animation: false,
      grid: { top: 4, right: 12, bottom: 24, left: 8, containLabel: true },
      xAxis: {
        type: 'value',
        min: start,
        max: end + span * 0.01,
        axisLabel: {
          color: theme.axis,
          fontSize: 11,
          hideOverlap: true,
          formatter: (value: number) => clockLabel(value, span < 15 * 60_000),
        },
        axisLine: { lineStyle: { color: theme.frame, width: 1 } },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: theme.grid, opacity: theme.gridOpacity, width: 1 } },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: rows.map((row) => row.label),
        axisLabel: { color: theme.axis, fontSize: 11, width: 160, overflow: 'truncate' },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      tooltip: {
        ...qfEChartsTooltip(theme, 11),
        trigger: 'item',
        formatter: (params: unknown) => {
          const index = (params as { dataIndex?: number }).dataIndex;
          const row = index === undefined ? undefined : rows[index];
          if (!row) return '';
          return chartTooltipHtml({
            date: row.label,
            items: [
              { label: 'Started', value: clockLabel(row.start), swatch: colors[index ?? 0] ?? '' },
              {
                label: 'Duration',
                value: formatDuration(Math.max(0, (row.end - row.start) / 1000)),
              },
            ],
            ...(row.detail ? { detail: row.detail } : {}),
          });
        },
      },
      series: [
        {
          id: 'timeline',
          type: 'custom',
          encode: { x: [1, 2], y: 0 },
          data: rows.map((row, index) => [index, row.start, Math.max(row.end, row.start)]),
          cursor: onSelect ? 'pointer' : 'default',
          renderItem: (params: RenderParams, api: RenderApi) => {
            const index = api.value(0);
            const [x0, y] = api.coord([api.value(1), index]);
            const [x1] = api.coord([api.value(2), index]);
            const band = api.size([0, 1])[1];
            const barHeight = Math.max(4, Math.min(14, band * 0.6));
            const width = Math.max(3, x1 - x0);
            const isSelected = rows[params.dataIndex]?.id === selected;
            return {
              type: 'rect',
              shape: { x: x0, y: y - barHeight / 2, width, height: barHeight, r: 2 },
              style: {
                fill: colors[params.dataIndex],
                stroke: isSelected ? theme.focus : 'transparent',
                lineWidth: isSelected ? 2 : 0,
              },
            };
          },
        },
      ],
    };
  }, [rows, selected, onSelect, formatDuration, theme]);
  return (
    <QfChart
      option={option}
      ariaLabel={ariaLabel}
      height={height ?? rows.length * ROW_HEIGHT + AXIS_ROOM}
      className={className}
      onClick={(event) => {
        const row = event.dataIndex === undefined ? undefined : rows[event.dataIndex];
        if (row && onSelect) onSelect(row.id);
      }}
    />
  );
}
