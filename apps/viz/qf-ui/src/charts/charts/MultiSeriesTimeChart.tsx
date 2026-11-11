/**
 * Complete multi-series time-chart experience with up to three axes, brush, legend,
 * benchmark overlay, downsampling, and responsive geometry.
 *
 * USAGE:
 *   <MultiSeriesTimeChart series={series} metricColors={colors} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react';

import { BrushBar } from '../components/BrushBar';
import { ChartLegend } from '../components/ChartLegend';
import { ChartNote } from '../components/ChartNote';
import type { ChartToolbarVariant } from '../components/ChartToggleGroup';
import { useChartTransformGroupMember } from '../components/ChartTransformGroup';
import { ChartTransformToolbar } from '../components/ChartTransformToolbar';
import { type MultiSeriesHoverAxes, MultiSeriesPlotHost } from '../components/MultiSeriesPlotHost';
import { TimeSeriesChart } from '../components/TimeSeriesChart';
import { QF_CHART_INSET, QF_CHART_TIME_AXIS_HEIGHT, valueGutterWidth } from '../core/geometry';
import { useChartBrush } from '../hooks/useChartBrush';
import { useChartTheme } from '../hooks/useChartTheme';
import { visibleAxisLabelWidth } from './axisLabelWidth';
import { type QfInterpolation, resolveInterpolation } from './interpolation';
import { MultiSeriesLinePlot } from './MultiSeriesLinePlot';
import {
  axisDomain,
  collectDomainPoints,
  dateDomain,
  formatYAxis,
  logAxisDomain,
  lttb,
  type MultiSeriesNullableSourceSeries,
  type MultiSeriesOverlay,
  type MultiSeriesPlotSeries,
  type MultiSeriesSourceSeries,
  type MultiSeriesValueFormat,
  paddedDomain,
  paletteMetricColors,
  parseMultiSeries,
} from './multiSeriesModel';
import {
  applyTimeSeriesTransforms,
  CHART_EMA_WINDOWS,
  CHART_Z_SCORE_WINDOWS,
  type ChartTransformControls,
  type ChartTransformState,
  DEFAULT_CHART_TRANSFORM_STATE,
  resolveChartTransformWindows,
  transformedValueFormat,
} from './timeSeriesTransforms';

import './MultiSeriesTimeChart.css';

// --------------------------------------------------------------------------- #
// Public contract
// --------------------------------------------------------------------------- #

export interface MultiSeriesTimeChartProps {
  title?: string;
  /** Heading element for the chart title; forwarded to ChartFrame (default 3). */
  headingLevel?: 2 | 3 | 4;
  /** Omit redundant legend chrome when controls already identify a single series. */
  showLegend?: boolean;
  titleAccessory?: ReactNode;
  series: readonly (MultiSeriesSourceSeries | MultiSeriesNullableSourceSeries)[];
  /** Colour per metric; omit it and series take palette slots in order (series 1 gold). */
  metricColors?: Readonly<Record<string, string>>;
  /** Disable width-dependent sampling for bounded series whose every extreme must remain visible. */
  downsample?: boolean;
  headerRight?: ReactNode;
  benchmark?: MultiSeriesOverlay | null;
  valueFormat?: MultiSeriesValueFormat;
  transformControls?: ChartTransformControls;
  transformState?: ChartTransformState;
  onTransformStateChange?: (value: ChartTransformState) => void;
  /** Transform toolbar style; defaults to the enclosing group's, else 'rail'. */
  transformToolbarVariant?: ChartToolbarVariant;
  tooltipMaxDistanceMs?: number;
  axisLabels?: { left?: string; right?: string; tertiary?: string };
  benchmarkValueFormat?: MultiSeriesValueFormat;
  /** Scale of the left (primary) value axis. Default 'linear'. */
  yScaleType?: 'linear' | 'log';
  /** How every line joins its points unless a series sets its own; linear by default. */
  interpolation?: QfInterpolation;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

const PRIMARY_COLOR = 'var(--qf-chart-series-primary)';
const EMPTY_TRANSFORM_CONTROLS: ChartTransformControls = {};
// Resize ticks land per pixel; quantizing the downsample width up to the next step
// keeps the memoized LTTB pass warm while never yielding fewer points than the
// unbucketed target for the same width.
const DOWNSAMPLE_WIDTH_STEP = 50;
/** ECharts' default value-axis interval count, which the plot leaves unset. */
const VALUE_AXIS_SPLIT_NUMBER = 5;
/** Gutter a named value axis keeps: the rotated name sits 50px off the plot edge. */
const NAMED_AXIS_GUTTER = 72;
/** Offset the tertiary axis keeps past the secondary one. */
const TERTIARY_AXIS_GUTTER = 72;

export function MultiSeriesTimeChart({
  title,
  headingLevel = 3,
  showLegend = true,
  titleAccessory,
  series,
  metricColors,
  downsample = true,
  headerRight,
  benchmark = null,
  valueFormat = 'number',
  transformControls,
  transformState,
  onTransformStateChange,
  transformToolbarVariant,
  tooltipMaxDistanceMs,
  axisLabels,
  benchmarkValueFormat = 'number',
  yScaleType = 'linear',
  interpolation,
}: MultiSeriesTimeChartProps) {
  // Benchmark appearance has one source: the semantic theme. The swatch in the
  // tooltip and the line in the plot read the same value.
  const theme = useChartTheme();
  const plotHostRef = useRef<HTMLDivElement | null>(null);
  const [plotWidth, setPlotWidth] = useState(0);
  const [plotHeight, setPlotHeight] = useState(0);
  const [hiddenMetrics, setHiddenMetrics] = useState<Set<string>>(() => new Set());
  const [emphasizedMetric, setEmphasizedMetric] = useState<string | null>(null);
  const [internalTransformState, setInternalTransformState] = useState<ChartTransformState>(
    DEFAULT_CHART_TRANSFORM_STATE,
  );
  const enabledTransformControls = transformControls ?? EMPTY_TRANSFORM_CONTROLS;
  // Explicit props win, then an enclosing ChartTransformGroupProvider, then local state.
  const transformGroup = useChartTransformGroupMember(
    transformState === undefined ? transformControls : undefined,
  );
  const currentTransformState = transformState ?? transformGroup?.state ?? internalTransformState;
  const zScoreWindows = resolveChartTransformWindows(
    enabledTransformControls.zScore,
    CHART_Z_SCORE_WINDOWS,
  );
  const emaWindows = resolveChartTransformWindows(enabledTransformControls.ema, CHART_EMA_WINDOWS);
  const activeZScore =
    currentTransformState.zScore != null && zScoreWindows.includes(currentTransformState.zScore)
      ? currentTransformState.zScore
      : null;
  const activeEma =
    currentTransformState.ema != null && emaWindows.includes(currentTransformState.ema)
      ? currentTransformState.ema
      : null;
  const changeTransformState = (next: ChartTransformState) => {
    if (transformState === undefined) {
      if (transformGroup) transformGroup.onChange(next);
      else setInternalTransformState(next);
    }
    onTransformStateChange?.(next);
  };

  const parsedSeries = useMemo(
    () =>
      parseMultiSeries(
        series,
        metricColors ?? paletteMetricColors(series, PRIMARY_COLOR),
        PRIMARY_COLOR,
      ),
    [metricColors, series],
  );
  const transformedSeries = useMemo(
    () => applyTimeSeriesTransforms(parsedSeries, { zScore: activeZScore, ema: activeEma }),
    [activeEma, activeZScore, parsedSeries],
  );
  const displayValueFormat = transformedValueFormat(valueFormat, {
    zScore: activeZScore,
    ema: activeEma,
  });
  const brushSource = useMemo(() => collectDomainPoints(parsedSeries), [parsedSeries]);
  const brush = useChartBrush(brushSource);
  const bucketedPlotWidth = Math.ceil(plotWidth / DOWNSAMPLE_WIDTH_STEP) * DOWNSAMPLE_WIDTH_STEP;
  const downsampleTarget = Math.max(Math.round(bucketedPlotWidth / 2), 400);
  // biome-ignore lint/correctness/useExhaustiveDependencies: brush.filterToRange is recreated per render but reads only brush.xDomain.
  const rangedSeries = useMemo<MultiSeriesPlotSeries[]>(
    () =>
      transformedSeries.map((item) => {
        const points = brush.filterToRange(item.points);
        return { ...item, points: downsample ? lttb(points, downsampleTarget) : points };
      }),
    [brush.xDomain, downsample, downsampleTarget, transformedSeries],
  );
  // Hover values stay full resolution and aligned even when geometry is reduced with LTTB.
  // biome-ignore lint/correctness/useExhaustiveDependencies: brush.filterToRange is recreated per render but reads only brush.xDomain.
  const rangedHoverSeries = useMemo<MultiSeriesPlotSeries[]>(
    () =>
      transformedSeries.map((item) => ({
        ...item,
        points: brush.filterToRange(item.points),
      })),
    [brush.xDomain, transformedSeries],
  );
  // biome-ignore lint/correctness/useExhaustiveDependencies: brush.filterToRange is recreated per render but reads only brush.xDomain.
  const hoverPoints = useMemo(() => brush.filterToRange(brushSource), [brush.xDomain, brushSource]);
  const visibleSeries = useMemo(
    () => rangedSeries.filter((item) => !hiddenMetrics.has(item.metric)),
    [hiddenMetrics, rangedSeries],
  );
  const visibleHoverSeries = useMemo(
    () => rangedHoverSeries.filter((item) => !hiddenMetrics.has(item.metric)),
    [hiddenMetrics, rangedHoverSeries],
  );
  const activeEmphasizedMetric = visibleSeries.some((item) => item.metric === emphasizedMetric)
    ? emphasizedMetric
    : null;

  const hasRightAxis = visibleSeries.some((item) => item.axis === 'right' && !item.isBenchmark);
  const hasTertiaryAxis = visibleSeries.some(
    (item) => item.axis === 'tertiary' && !item.isBenchmark,
  );
  const visibleDomain = useMemo(
    () => dateDomain(brushSource, brush.xDomain ?? undefined),
    [brush.xDomain, brushSource],
  );
  const visibleBenchmark = useMemo(
    () =>
      benchmark && hiddenMetrics.has(benchmark.id)
        ? null
        : filterBenchmark(benchmark, visibleDomain),
    [benchmark, hiddenMetrics, visibleDomain],
  );
  const benchmarkDomain = useMemo(
    () =>
      paddedDomain([
        ...visibleHoverSeries.flatMap((item) =>
          item.isBenchmark
            ? item.points.flatMap((point) => (point.value === null ? [] : [point.value]))
            : [],
        ),
        ...(visibleBenchmark?.points.flatMap((point) =>
          point.value === null ? [] : [point.value],
        ) ?? []),
      ]),
    [visibleBenchmark, visibleHoverSeries],
  );
  // Axis domains read the full-resolution points: LTTB keeps a width-dependent subset, so
  // domains from the reduced geometry would move every y label when the plot resizes.
  const leftDomain = useMemo(
    () =>
      yScaleType === 'log'
        ? logAxisDomain(visibleHoverSeries, 'left')
        : axisDomain(visibleHoverSeries, 'left', displayValueFormat),
    [displayValueFormat, visibleHoverSeries, yScaleType],
  );
  const rightDomain = useMemo(
    () => axisDomain(visibleHoverSeries, 'right', displayValueFormat),
    [displayValueFormat, visibleHoverSeries],
  );
  const tertiaryDomain = useMemo(
    () => axisDomain(visibleHoverSeries, 'tertiary', displayValueFormat),
    [displayValueFormat, visibleHoverSeries],
  );
  // Mirrors the axes MultiSeriesLinePlot hands the renderer, so hover dots sit on the lines.
  const hoverAxes = useMemo<MultiSeriesHoverAxes>(() => {
    const inverse = displayValueFormat === 'rank';
    return {
      left: { domain: leftDomain, scale: yScaleType, inverse },
      right: { domain: rightDomain, scale: 'linear', inverse },
      tertiary: { domain: tertiaryDomain, scale: 'linear', inverse: false },
      overlay: {
        domain: benchmarkDomain,
        scale: visibleBenchmark ? 'log' : 'linear',
        inverse: false,
      },
    };
  }, [
    benchmarkDomain,
    displayValueFormat,
    leftDomain,
    rightDomain,
    tertiaryDomain,
    visibleBenchmark,
    yScaleType,
  ]);
  const leftValueFormat =
    visibleSeries.find((item) => item.axis === 'left' && !item.isBenchmark)?.valueFormat ??
    displayValueFormat;
  const rightValueFormat =
    visibleSeries.find((item) => item.axis === 'right' && !item.isBenchmark)?.valueFormat ??
    displayValueFormat;
  const tertiaryValueFormat =
    visibleSeries.find((item) => item.axis === 'tertiary' && !item.isBenchmark)?.valueFormat ??
    displayValueFormat;
  // Gutters fit the labels the axes draw, so the widest label starts on the card inset.
  const leftLabelWidth = useMemo(
    () =>
      visibleAxisLabelWidth({
        domain: leftDomain,
        scale: yScaleType,
        splitNumber: VALUE_AXIS_SPLIT_NUMBER,
        format: (value) => formatYAxis(value, leftValueFormat),
        fontSize: theme.axisFontSize,
      }),
    [leftDomain, leftValueFormat, theme.axisFontSize, yScaleType],
  );
  const rightLabelWidth = useMemo(
    () =>
      hasRightAxis
        ? visibleAxisLabelWidth({
            domain: rightDomain,
            scale: 'linear',
            splitNumber: VALUE_AXIS_SPLIT_NUMBER,
            format: (value) => formatYAxis(value, rightValueFormat),
            fontSize: theme.axisFontSize,
          })
        : 0,
    [hasRightAxis, rightDomain, rightValueFormat, theme.axisFontSize],
  );
  const leftGutter = valueGutterWidth(leftLabelWidth);
  const marginLeft =
    axisLabels?.left === undefined ? leftGutter : Math.max(leftGutter, NAMED_AXIS_GUTTER);
  const rightGutter = hasRightAxis
    ? axisLabels?.right === undefined
      ? valueGutterWidth(rightLabelWidth)
      : Math.max(valueGutterWidth(rightLabelWidth), NAMED_AXIS_GUTTER)
    : QF_CHART_INSET;
  const marginRight = hasTertiaryAxis
    ? (hasRightAxis ? NAMED_AXIS_GUTTER : 0) + TERTIARY_AXIS_GUTTER
    : rightGutter;
  const marginTop = QF_CHART_INSET;
  const marginBottom = QF_CHART_TIME_AXIS_HEIGHT;
  const innerWidth = Math.max(plotWidth - marginLeft - marginRight, 1);
  const innerHeight = Math.max(plotHeight - marginTop - marginBottom, 1);
  const hasData = parsedSeries.length > 0;
  const hasTransformToolbar = zScoreWindows.length > 0 || emaWindows.length > 0;
  // Smoothing invents values between observations, so a smoothed line is always labelled.
  const isSmoothed = visibleSeries.some(
    (item) => resolveInterpolation(item.interpolation, interpolation) === 'smooth',
  );
  const chartHeaderRight =
    headerRight || hasTransformToolbar || isSmoothed ? (
      <>
        {isSmoothed ? <ChartNote>Smoothed</ChartNote> : null}
        {headerRight}
        {hasTransformToolbar ? (
          <ChartTransformToolbar
            controls={enabledTransformControls}
            value={currentTransformState}
            onChange={changeTransformState}
            variant={transformToolbarVariant ?? transformGroup?.toolbarVariant ?? 'rail'}
          />
        ) : null}
      </>
    ) : undefined;

  // biome-ignore lint/correctness/useExhaustiveDependencies: hasData re-attaches when the conditional plot host mounts.
  useEffect(() => {
    const host = plotHostRef.current;
    if (!host) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      setPlotWidth(entry.contentRect.width);
      setPlotHeight(entry.contentRect.height);
    });
    observer.observe(host);
    return () => observer.disconnect();
  }, [hasData]);

  const plotStack = (
    <div className="chart-stack">
      <MultiSeriesPlotHost
        plotHostRef={plotHostRef}
        plotWidth={plotWidth}
        plotHeight={plotHeight}
        marginLeft={marginLeft}
        marginTop={marginTop}
        innerWidth={innerWidth}
        innerHeight={innerHeight}
        xDomain={visibleDomain}
        hoverPoints={hoverPoints}
        series={visibleHoverSeries}
        {...(tooltipMaxDistanceMs === undefined ? {} : { tooltipMaxDistanceMs })}
        valueFormat={displayValueFormat}
        overlayValueFormat={benchmarkValueFormat}
        priceOverlay={visibleBenchmark}
        overlayColor={theme.benchmark}
        valueAxes={hoverAxes}
        geometry={
          plotWidth > 0 && plotHeight > 0 ? (
            <MultiSeriesLinePlot
              plotWidth={plotWidth}
              plotHeight={plotHeight}
              marginLeft={marginLeft}
              marginTop={marginTop}
              innerWidth={innerWidth}
              innerHeight={innerHeight}
              xDomain={visibleDomain}
              leftDomain={leftDomain}
              rightDomain={rightDomain}
              tertiaryDomain={tertiaryDomain}
              overlayDomain={benchmarkDomain}
              series={rangedSeries}
              hiddenSeries={hiddenMetrics}
              emphasizedSeries={activeEmphasizedMetric}
              visibleSeries={visibleSeries}
              visiblePriceOverlay={visibleBenchmark}
              valueFormat={displayValueFormat}
              leftValueFormat={leftValueFormat}
              rightValueFormat={rightValueFormat}
              tertiaryValueFormat={tertiaryValueFormat}
              yScaleType={yScaleType}
              {...(axisLabels === undefined ? {} : { axisLabels })}
              {...(interpolation === undefined ? {} : { interpolation })}
            />
          ) : null
        }
      />
      <BrushBar
        data={brushSource}
        insetLeft={marginLeft}
        insetRight={marginRight}
        {...(brush.xDomain === undefined ? {} : { domain: brush.xDomain })}
        onDomainChange={brush.setDomain}
      />
    </div>
  );

  const chart = (
    <TimeSeriesChart
      headingLevel={headingLevel}
      {...(title === undefined ? {} : { title })}
      {...(titleAccessory === undefined ? {} : { titleAccessory })}
      {...(chartHeaderRight === undefined ? {} : { headerRight: chartHeaderRight })}
      {...(hasData && showLegend
        ? {
            legend: (
              <ChartLegend
                series={[
                  ...parsedSeries
                    .filter((item) => !item.hideFromLegend)
                    .map((item) => ({
                      key: item.metric,
                      label: item.label,
                      color: item.color,
                      axis: item.axis === 'left' ? ('primary' as const) : ('secondary' as const),
                      ...(item.isBenchmark === undefined ? {} : { isBenchmark: item.isBenchmark }),
                      points: [],
                    })),
                  // The price overlay draws on its own log axis; list it so it can be named and hidden.
                  ...(benchmark
                    ? [
                        {
                          key: benchmark.id,
                          label: benchmark.label,
                          color: theme.benchmark,
                          axis: 'secondary' as const,
                          points: [],
                        },
                      ]
                    : []),
                ]}
                hiddenSeries={hiddenMetrics}
                onHiddenSeriesChange={(next) => setHiddenMetrics(new Set(next))}
                emphasizedSeries={activeEmphasizedMetric}
                onEmphasizedSeriesChange={setEmphasizedMetric}
              />
            ),
          }
        : {})}
    >
      {!hasData ? <div className="chart-no-data">No data</div> : plotStack}
    </TimeSeriesChart>
  );
  return !parsedSeries.some((item) => item.axis === 'tertiary') ? (
    chart
  ) : (
    <div className="multi-series-frame-scroll">
      <div style={{ minWidth: 720 }}>{chart}</div>
    </div>
  );
}

function filterBenchmark(
  benchmark: MultiSeriesOverlay | null,
  domain: readonly [Date, Date],
): MultiSeriesOverlay | null {
  if (!benchmark) return null;
  const [start, end] = domain;
  const points = benchmark.points
    .filter((point) => point.date >= start && point.date <= end)
    .sort((left, right) => left.date.getTime() - right.date.getTime());
  return points.length < 2 ? null : { ...benchmark, points };
}
