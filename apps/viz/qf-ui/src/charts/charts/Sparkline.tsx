/**
 * Caller-sized compact line chart.
 *
 * USAGE:
 *   <Sparkline values={[1, 2, null]} height={32} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMemo } from 'react';

import { QfChart, type QfChartOption } from '../core/QfChart';
import { useChartTheme } from '../hooks/useChartTheme';
import { echartsInterpolation, type QfInterpolation } from './interpolation';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SparklineProps {
  values: readonly (number | null)[];
  height: number | string;
  className?: string | undefined;
  ariaLabel?: string | undefined;
  /** How the line joins its points; linear by default. A caller that smooths adds a "Smoothed" ChartNote. */
  interpolation?: QfInterpolation | undefined;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Sparkline({
  values,
  height,
  className,
  ariaLabel = 'Trend sparkline',
  interpolation = 'linear',
}: SparklineProps) {
  const theme = useChartTheme();
  const option = useMemo<QfChartOption>(() => {
    let lastIndex = values.length - 1;
    while (lastIndex >= 0 && !Number.isFinite(values[lastIndex] ?? Number.NaN)) lastIndex -= 1;
    return {
      animation: false,
      // Room on the right and vertically so the end dot is never clipped.
      grid: { top: 4, right: 4, bottom: 4, left: 2 },
      xAxis: { type: 'category', show: false, data: values.map((_, index) => index) },
      yAxis: { type: 'value', show: false, scale: true },
      tooltip: { show: false },
      series: [
        {
          type: 'line',
          data: values.map((value) => value ?? '-'),
          showSymbol: false,
          symbol: 'none',
          ...echartsInterpolation(interpolation),
          connectNulls: false,
          lineStyle: {
            color: theme.palette[0],
            width: theme.lineWidth,
            cap: 'round',
            join: 'round',
          },
          silent: true,
          // The end dot anchors the eye on the latest value, the reading a sparkline is for.
          markPoint:
            lastIndex < 0
              ? undefined
              : {
                  silent: true,
                  animation: false,
                  symbol: 'circle',
                  symbolSize: 5,
                  label: { show: false },
                  itemStyle: {
                    color: theme.palette[0],
                    borderColor: theme.background,
                    borderWidth: 1.5,
                  },
                  data: [{ coord: [lastIndex, values[lastIndex]] }],
                },
        },
      ],
    };
  }, [interpolation, theme.background, theme.lineWidth, theme.palette, values]);
  return <QfChart option={option} height={height} ariaLabel={ariaLabel} className={className} />;
}
