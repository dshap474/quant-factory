/**
 * Linked portfolio values and full-history drawdowns with shared visibility and brush.
 * USAGE: <PortfolioDrawdownChart series={portfolios} metricColors={colors} />
 *        <PortfolioDrawdownChart series={portfolios} cursor={replayDate} />  // vertical rule in both panes
 *        <PortfolioDrawdownChart series={sampled} drawdowns={{ strategy: fullHistoryDrawdown }} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMemo, useState } from 'react';
import { BrushBar } from '../components/BrushBar';
import { ChartLegend } from '../components/ChartLegend';
import { ChartNote } from '../components/ChartNote';
import { MultiPaneTimeSeriesChart } from '../components/MultiPaneTimeSeriesChart';
import { useChartBrush } from '../hooks/useChartBrush';
import { useChartTheme } from '../hooks/useChartTheme';
import type { QfPoint } from '../types/contracts';
import { type QfInterpolation, resolveInterpolation } from './interpolation';
import { LineChart, type QfLineSeries } from './LineChart';
import {
  collectDomainPoints,
  dateDomain,
  findNearestPoint,
  formatTooltipValue,
  formatYAxis,
  type MultiSeriesNullableSourcePoint,
  type MultiSeriesNullableSourceSeries,
  paletteMetricColors,
  parseMultiSeries,
  parseSourcePoints,
} from './multiSeriesModel';

// --------------------------------------------------------------------------- #
// Drawdown model
// --------------------------------------------------------------------------- #

/** Chronological equity / running positive peak - 1; gaps never reset the peak. */
export function portfolioDrawdown(points: readonly QfPoint[]): QfPoint[] {
  let peak = 0;
  return points.map((point) => {
    if (point.value === null || !Number.isFinite(point.value)) return { ...point, value: null };
    peak = Math.max(peak, point.value);
    return { ...point, value: peak > 0 ? point.value / peak - 1 : null };
  });
}

const PRIMARY_SERIES_COLOR = 'var(--qf-chart-series-primary)';
const formatValue = (value: number) => formatYAxis(value, 'number');
const formatDrawdown = (value: number) => formatYAxis(value, 'percent');

export interface PortfolioDrawdownChartProps {
  title?: string;
  series: readonly MultiSeriesNullableSourceSeries[];
  /** Colour per metric; omit it and series take palette slots in order (series 1 gold). */
  metricColors?: Readonly<Record<string, string>>;
  /** How every line joins its points unless a series sets its own; linear by default. */
  interpolation?: QfInterpolation;
  /** Dashed vertical rule at this time in both panes (a replay or selection cursor). */
  cursor?: Date | undefined;
  /**
   * Drawdown per metric computed upstream (e.g. on full history before display sampling, which
   * can drop a peak); metrics without one derive it from their plotted values.
   */
  drawdowns?: Readonly<Record<string, readonly MultiSeriesNullableSourcePoint[]>>;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function PortfolioDrawdownChart({
  title,
  series,
  metricColors,
  interpolation,
  cursor,
  drawdowns: givenDrawdowns,
}: PortfolioDrawdownChartProps) {
  const theme = useChartTheme();
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [emphasized, setEmphasized] = useState<string | null>(null);
  const parsed = useMemo(
    () =>
      parseMultiSeries(
        series,
        metricColors ?? paletteMetricColors(series, PRIMARY_SERIES_COLOR),
        PRIMARY_SERIES_COLOR,
      ),
    [series, metricColors],
  );
  // All portfolios, including a benchmark, use the same visible value scale.
  const equity = useMemo<QfLineSeries[]>(
    () =>
      parsed.map((item) => ({
        key: item.metric,
        label: item.label,
        color: item.isBenchmark ? theme.benchmark : item.color,
        ...(item.isBenchmark === undefined ? {} : { isBenchmark: item.isBenchmark }),
        points: item.points,
        valueFormat: 'number',
        ...(item.interpolation === undefined ? {} : { interpolation: item.interpolation }),
      })),
    [parsed, theme.benchmark],
  );
  const drawdowns = useMemo<QfLineSeries[]>(
    () =>
      equity.map((item) => {
        const given = givenDrawdowns?.[item.key];
        return {
          ...item,
          points: given ? parseSourcePoints(given) : portfolioDrawdown(item.points),
          valueFormat: 'percent',
        };
      }),
    [equity, givenDrawdowns],
  );
  const dates = useMemo(() => collectDomainPoints(parsed), [parsed]);
  const brush = useChartBrush(dates);
  // Hover only changes `emphasized`; every input a LineChart receives stays referentially
  // stable across it, so a hover never re-decimates or re-sends the series data.
  const domain = useMemo(() => dateDomain(dates, brush.xDomain), [dates, brush.xDomain]);
  // Compute drawdowns before slicing so a zoom never creates a new high-water mark.
  // biome-ignore lint/correctness/useExhaustiveDependencies: brush.filterToRange is recreated per render but reads only brush.xDomain.
  const visibleEquity = useMemo(
    () => equity.map((item) => ({ ...item, points: brush.filterToRange(item.points) })),
    [equity, brush.xDomain],
  );
  // biome-ignore lint/correctness/useExhaustiveDependencies: brush.filterToRange is recreated per render but reads only brush.xDomain.
  const visibleDrawdowns = useMemo(
    () => drawdowns.map((item) => ({ ...item, points: brush.filterToRange(item.points) })),
    [drawdowns, brush.xDomain],
  );
  const drawdownDomain = useMemo(() => {
    let minimum = 0;
    for (const item of visibleDrawdowns) {
      if (hidden.has(item.key)) continue;
      for (const point of item.points) minimum = Math.min(minimum, point.value ?? 0);
    }
    return [minimum < 0 ? minimum * 1.05 : -0.01, 0] as const;
  }, [visibleDrawdowns, hidden]);
  const panes = [
    {
      id: 'equity',
      label: 'Portfolio value',
      size: 'main' as const,
      series: equity,
      visible: visibleEquity,
      format: 'number' as const,
    },
    {
      id: 'drawdown',
      label: 'Drawdown from peak',
      size: 'study' as const,
      series: drawdowns,
      visible: visibleDrawdowns,
      format: 'percent' as const,
    },
  ];
  // Smoothing invents values between observations, so a smoothed line is always labelled.
  const isSmoothed = parsed.some(
    (item) =>
      !hidden.has(item.metric) &&
      resolveInterpolation(item.interpolation, interpolation) === 'smooth',
  );
  return (
    <MultiPaneTimeSeriesChart
      {...(title === undefined ? {} : { title })}
      {...(isSmoothed ? { headerRight: <ChartNote>Smoothed</ChartNote> } : {})}
      linked
      xDomain={domain}
      legend={
        <ChartLegend
          series={equity}
          hiddenSeries={hidden}
          onHiddenSeriesChange={setHidden}
          emphasizedSeries={emphasized}
          onEmphasizedSeriesChange={setEmphasized}
        />
      }
      panes={panes.map((pane) => {
        return {
          id: pane.id,
          label: pane.label,
          size: pane.size,
          content: (
            <LineChart
              series={pane.visible}
              benchmarkScale="shared"
              height="100%"
              hiddenSeries={hidden}
              emphasizedSeries={emphasized}
              ariaLabel={pane.label}
              {...(interpolation === undefined ? {} : { interpolation })}
              {...(cursor === undefined ? {} : { thresholdX: cursor })}
              yFormat={pane.id === 'drawdown' ? formatDrawdown : formatValue}
              {...(pane.id === 'drawdown' ? { yDomain: drawdownDomain, thresholdY: 0 } : {})}
            />
          ),
          tooltip: (date: Date) => {
            const sample = findNearestPoint(dates, date);
            if (!sample) return null;
            return {
              date: sample.date,
              detail: pane.label,
              items: pane.series.flatMap((item) => {
                if (hidden.has(item.key)) return [];
                const point = findNearestPoint(item.points, sample.date, 0);
                return point?.value == null
                  ? []
                  : [
                      {
                        label: item.label,
                        value: formatTooltipValue(point.value, pane.format),
                        ...(item.color === undefined ? {} : { swatch: item.color }),
                      },
                    ];
              }),
            };
          },
        };
      })}
      controls={
        <BrushBar
          data={dates}
          {...(brush.xDomain ? { domain: brush.xDomain } : {})}
          onDomainChange={brush.setDomain}
        />
      }
    />
  );
}
