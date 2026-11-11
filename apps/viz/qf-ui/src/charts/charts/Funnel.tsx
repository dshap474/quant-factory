/**
 * Horizontal step funnel: one bar per stage with its count and the drop from the stage above.
 *
 * USAGE:
 *   <Funnel
 *     ariaLabel="Pipeline funnel"
 *     stages={[{ id: 'listed', label: 'Listed', count: 100 }, { id: 'complete', label: 'Complete', count: 80, detail: [{ label: 'missing data', value: 20 }] }]}
 *     selected={selected}
 *     onSelect={setSelected}       // the clicked id, or null when the selected bar is clicked again
 *   />
 *
 * Bars keep the order given, first on top. `detail` rows (drop-off reasons and their counts)
 * follow the count and drop in the tooltip. While a stage is selected the other bars dim.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMemo } from 'react';

import { chartTooltipHtml } from '../components/ChartTooltip';
import { QF_CHART_INSET } from '../core/geometry';
import { QfChart, type QfChartOption } from '../core/QfChart';
import { qfEChartsTooltip } from '../core/tooltip';
import { useChartTheme } from '../hooks/useChartTheme';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface FunnelDetail {
  label: string;
  value: number;
}

export interface FunnelStage {
  id: string;
  label: string;
  count: number;
  /** Extra tooltip rows, such as drop-off reasons and their counts. */
  detail?: readonly FunnelDetail[] | undefined;
}

export interface FunnelProps {
  stages: readonly FunnelStage[];
  ariaLabel: string;
  /** Selected stage id; the other bars dim. */
  selected?: string | null | undefined;
  /** Clicked stage id, or null when the selected stage is clicked again. */
  onSelect?: ((id: string | null) => void) | undefined;
  formatValue?: ((value: number) => string) | undefined;
  /** Defaults to a package row height per stage. */
  height?: number | string | undefined;
  className?: string | undefined;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const ROW_HEIGHT = 34;
const LABEL_WIDTH = 112;
const DIM_OPACITY = 0.35;
const DEFAULT_FORMAT = (value: number) => value.toLocaleString('en-US');

function stageIndex(params: unknown): number | null {
  const index = (params as { dataIndex?: unknown } | null)?.dataIndex;
  return typeof index === 'number' ? index : null;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Funnel({
  stages,
  ariaLabel,
  selected = null,
  onSelect,
  formatValue = DEFAULT_FORMAT,
  height,
  className,
}: FunnelProps) {
  const theme = useChartTheme();
  const option = useMemo<QfChartOption>(() => {
    const drops = stages.map((stage, index) =>
      index === 0 ? null : (stages[index - 1]?.count ?? 0) - stage.count,
    );
    return {
      animation: false,
      grid: { top: 4, right: QF_CHART_INSET + 96, bottom: 4, left: LABEL_WIDTH },
      xAxis: {
        type: 'value',
        show: false,
        max: Math.max(1, ...stages.map((stage) => stage.count)),
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: stages.map((stage) => stage.label),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: theme.axis,
          fontSize: theme.axisFontSize,
          width: LABEL_WIDTH - QF_CHART_INSET,
          overflow: 'truncate',
          align: 'left',
          margin: LABEL_WIDTH - QF_CHART_INSET / 2,
        },
      },
      tooltip: {
        ...qfEChartsTooltip(theme, 11),
        trigger: 'item',
        formatter: (params: unknown) => {
          const index = stageIndex(params);
          const stage = index === null ? undefined : stages[index];
          if (!stage || index === null) return '';
          const drop = drops[index];
          return chartTooltipHtml({
            date: stage.label,
            items: [
              { label: 'Count', value: formatValue(stage.count) },
              ...(typeof drop === 'number'
                ? [{ label: 'Drop', value: `−${formatValue(drop)}` }]
                : []),
              ...(stage.detail ?? []).map((row) => ({
                label: row.label,
                value: formatValue(row.value),
              })),
            ],
          });
        },
      },
      series: [
        {
          type: 'bar',
          barCategoryGap: '28%',
          showBackground: true,
          backgroundStyle: { color: theme.grid, opacity: theme.gridOpacity },
          data: stages.map((stage) => ({
            value: stage.count,
            itemStyle: {
              color: theme.palette[0],
              opacity: selected === null || selected === stage.id ? 1 : DIM_OPACITY,
              borderRadius: [0, 2, 2, 0],
            },
          })),
          label: {
            show: true,
            position: 'right',
            color: theme.axis,
            fontSize: theme.axisFontSize,
            formatter: (params: unknown) => {
              const index = stageIndex(params);
              if (index === null) return '';
              const drop = drops[index];
              const count = formatValue(stages[index]?.count ?? 0);
              return drop ? `${count}  −${formatValue(drop)}` : count;
            },
          },
        },
      ],
      aria: { enabled: true, decal: { show: false } },
    };
  }, [formatValue, selected, stages, theme]);

  return (
    <QfChart
      option={option}
      ariaLabel={ariaLabel}
      height={height ?? stages.length * ROW_HEIGHT + 8}
      className={className}
      interactive={Boolean(onSelect)}
      onClick={(params) => {
        const index = stageIndex(params);
        const stage = index === null ? undefined : stages[index];
        if (stage) onSelect?.(stage.id === selected ? null : stage.id);
      }}
    />
  );
}
