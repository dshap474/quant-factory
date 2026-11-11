/**
 * Signal prediction series with decision step-line and threshold.
 *
 * USAGE:
 *   <SignalChart data={predictions} threshold={0.5} label="p_long" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { BrushBar, ChartLegendItem, TimeSeriesChart } from '@quant-factory/qf-ui/charts/chrome';
import { useChartBrush } from '@quant-factory/qf-ui/charts/hooks';
import { type MultiSeriesPoint, TimeSeriesPlot } from '@quant-factory/qf-ui/charts/renderers';
import { chartColor } from '@quant-factory/qf-ui/charts/theme';
import { useState } from 'react';
import type { BenchmarkSeriesItem, IndexMode } from '@/lib/shared/lib/benchmark';
import { Button, extentBy } from '@/ui';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SignalChartProps {
  data: MultiSeriesPoint[];
  title?: string;
  label?: string;
  threshold?: number;
  benchmarkSeries?: BenchmarkSeriesItem[];
  indexMode?: IndexMode;
  onCycleIndex?: () => void;
  indexLoading?: boolean;
}

const EMPTY_BENCHMARK_SERIES: BenchmarkSeriesItem[] = [];

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SignalChart({
  data,
  title = 'Signal Predictions',
  label = 'prediction',
  threshold = 0.5,
  benchmarkSeries = EMPTY_BENCHMARK_SERIES,
  indexMode,
  onCycleIndex,
  indexLoading = false,
}: SignalChartProps) {
  const brush = useChartBrush(data);
  const [hoveredSeries, setHoveredSeries] = useState<string | null>(null);

  const decisionData = brush.visibleData.map((d) => ({
    date: d.date,
    value: d.value >= threshold ? 1 : 0,
  }));

  const series = (() => {
    const benches: Array<{
      id: string;
      data: MultiSeriesPoint[];
      color: string;
      isBenchmark: boolean;
      opacity: number;
    }> = [];
    for (const benchmark of benchmarkSeries) {
      if (benchmark.data.length === 0) continue;
      const visibleBench = brush.filterToRange(benchmark.data);
      const bExt = extentBy(visibleBench, (point) => point.value);
      if (!bExt) continue;
      const bRange = bExt.max - bExt.min || 1;
      benches.push({
        id: benchmark.ticker,
        data: visibleBench.map((point) => ({
          date: point.date,
          value: (point.value - bExt.min) / bRange,
        })),
        color: benchmark.color,
        isBenchmark: true,
        opacity: 0.48,
      });
    }
    return [
      ...benches,
      {
        id: 'decision',
        data: decisionData,
        color: chartColor('positive'),
        curve: 'stepAfter' as const,
        opacity: 0.72,
      },
      {
        id: 'signal',
        data: brush.visibleData,
        color: chartColor(1),
      },
    ];
  })();

  return (
    <TimeSeriesChart
      title={title}
      headerRight={
        onCycleIndex ? (
          <Button
            type="button"
            variant="control"
            aria-pressed={indexMode != null}
            onClick={onCycleIndex}
          >
            {indexMode ? `${indexMode}${indexLoading ? '…' : ''}` : 'Index'}
          </Button>
        ) : undefined
      }
      legend={
        <>
          <ChartLegendItem
            seriesId="signal"
            swatch={chartColor(1)}
            hoveredSeries={hoveredSeries}
            onHoveredSeriesChange={setHoveredSeries}
          >
            {label}
          </ChartLegendItem>
          <ChartLegendItem
            seriesId="decision"
            swatch={chartColor('positive')}
            hoveredSeries={hoveredSeries}
            onHoveredSeriesChange={setHoveredSeries}
          >
            Decision
          </ChartLegendItem>
        </>
      }
      controls={<BrushBar data={data} domain={brush.xDomain} onDomainChange={brush.setDomain} />}
    >
      <TimeSeriesPlot
        data={brush.visibleData}
        series={series}
        emphasizedSeries={hoveredSeries}
        xDomain={brush.xDomain}
        yDomain={[0, 1]}
        yFormat={(v) => v.toFixed(2)}
        thresholdY={threshold}
        tooltipItems={(point) => [
          {
            label,
            value: point.value.toFixed(4),
            swatch: chartColor(1),
          },
        ]}
      />
    </TimeSeriesChart>
  );
}
