/**
 * Price path beside a horizontal price-distribution profile.
 *
 * The left panel plots one price line, stepped level lines that switch from dashed to
 * solid at a declared time, horizontal reference segments, vertical time guides,
 * labelled event markers and execution fills (dots sized by quantity, solid or hollow).
 * Distributions (mass per price row) share the price scale in
 * a right panel, or a faint left overlay behind price, with optional highlighted bands.
 * The frame is the package TimeSeriesChart: right-rail legend, BrushBar under the plot.
 *
 * USAGE:
 *   <PriceProfileChart
 *     ariaLabel="Session"
 *     xDomain={[open, close]}
 *     price={{ key: 'close', label: 'Close', points }}
 *     levels={[{ key: 'mid', label: 'Developing mid', endLabel: 'MID', color, points, dashedUntil }]}
 *     profiles={[{ key: 'day', label: 'Day profile', color, rows, rowSize: 50, band: [lo, hi] }]}
 *     timeZone="utc"
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMemo, useState } from 'react';

import { BrushBar } from '../components/BrushBar';
import { ChartLegend } from '../components/ChartLegend';
import { ChartNote } from '../components/ChartNote';
import { type ChartTooltipItem, chartTooltipHtml } from '../components/ChartTooltip';
import { TimeSeriesChart } from '../components/TimeSeriesChart';
import {
  multiPaneAspectRatio,
  QF_CHART_INSET,
  QF_CHART_LINE_WIDTH,
  QF_CHART_RULE_WIDTH,
  QF_CHART_TIME_AXIS_HEIGHT,
  valueGutterWidth,
} from '../core/geometry';
import { QfChart, type QfChartOption } from '../core/QfChart';
import { qfAxisPointerLabel, qfEChartsTooltip } from '../core/tooltip';
import { type QfChartTheme, useChartTheme } from '../hooks/useChartTheme';
import { chartColor, withOpacity } from '../theme/chartColor';
import { resolveCssColor } from '../theme/tokens';
import { axisLabelWidth, extremeLabelVisibility } from './axisLabelWidth';
import { marketCandleSeries, marketVolumeSeries } from './marketPriceLayers';
import {
  fillSeries,
  guideMarkLines,
  LEVEL_ID,
  levelSeries,
  lineSeries,
  markerPoints,
  segmentMarkLines,
} from './priceProfileLayers';
import {
  breakLineGaps,
  clampWindow,
  formatPriceProfileTime,
  priceProfileExtent,
} from './priceProfileModel';

export { breakLineGaps, formatPriceProfileTime, priceProfileExtent } from './priceProfileModel';

import { profileLegendColor, profileSeries } from './priceProfileDistribution';
import type { PriceProfileChartProps, PriceProfileModel } from './priceProfileTypes';
import { formatQfValue } from './qfValueFormat';

export type {
  PriceProfileChartProps,
  PriceProfileDistribution,
  PriceProfileFill,
  PriceProfileFills,
  PriceProfileLevel,
  PriceProfileLine,
  PriceProfileMarker,
  PriceProfileModel,
  PriceProfilePoint,
  PriceProfileSegment,
  PriceProfileTimeGuide,
} from './priceProfileTypes';

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

const PROFILE_PANEL_LEFT = '78%';
const PRICE_PANEL_RIGHT = '22%';
const PLOT_TOP = 16;
const VALUE_SPLIT_NUMBER = 5;
const DASH: number[] = [4, 4];
const EMPTY_HIDDEN: ReadonlySet<string> = new Set();

// --------------------------------------------------------------------------- #
// Series builders
// --------------------------------------------------------------------------- #

interface TooltipParam {
  seriesId?: string;
  seriesName?: string;
  color?: string;
  axisValue?: number;
  value?: unknown;
}

// --------------------------------------------------------------------------- #
// Tooltip
// --------------------------------------------------------------------------- #

/** Rows for the hovered time: the price, then each level at its nearest drawn point. */
export function priceProfileTooltipItems(
  params: readonly TooltipParam[],
  model: Pick<PriceProfileModel, 'price' | 'levels' | 'valueFormat'> &
    Partial<Pick<PriceProfileModel, 'markers' | 'segments' | 'candles' | 'volume' | 'fills'>>,
): ChartTooltipItem[] {
  const axisValue = Number(params[0]?.axisValue);
  const best = new Map<string, { distance: number; value: number; color: string }>();
  for (const param of params) {
    const id = param.seriesId ?? '';
    const key = id.startsWith(LEVEL_ID)
      ? id.slice(LEVEL_ID.length).replace(/:(dashed|solid)$/, '')
      : id;
    const datum = Array.isArray(param.value) ? param.value : null;
    const value = datum?.[1];
    if (typeof value !== 'number' || !Number.isFinite(value)) continue;
    const distance = Math.abs(Number(datum?.[0]) - axisValue);
    const current = best.get(key);
    if (!current || distance < current.distance) {
      best.set(key, { distance, value, color: param.color ?? '' });
    }
  }
  const rows: ChartTooltipItem[] = [];
  for (const line of [model.price, ...(model.levels ?? [])]) {
    const hit = best.get(line.key === model.price.key ? 'price' : line.key);
    if (!hit) continue;
    rows.push({
      label: line.label,
      value: formatQfValue(hit.value, model.valueFormat),
      ...(hit.color ? { swatch: hit.color } : {}),
    });
  }
  const candle = params.find(
    (param) => param.seriesId === 'price' && Array.isArray(param.value) && param.value.length === 6,
  );
  if (candle && Array.isArray(candle.value)) {
    for (const [label, index] of [
      ['Open', 2],
      ['High', 3],
      ['Low', 4],
    ] as const)
      rows.push({ label, value: formatQfValue(Number(candle.value[index]), model.valueFormat) });
  }
  for (const segment of model.segments ?? []) {
    if (axisValue >= segment.from && axisValue <= segment.to)
      rows.push({
        label: segment.label,
        value: formatQfValue(segment.value, model.valueFormat),
        swatch: segment.color,
      });
  }
  const tolerance = model.candles?.[0]?.duration ?? model.volume?.bars[0]?.duration ?? 60_000;
  for (const marker of model.markers ?? []) {
    if (Math.abs(marker.time - axisValue) <= tolerance / 2)
      rows.push({
        label: `${marker.label} · ${formatPriceProfileTime(marker.time, 'utc')}`,
        value: formatQfValue(marker.value, model.valueFormat),
        swatch: marker.color,
      });
  }
  // Fills in the hovered minute: their total size and size-weighted price.
  const inMinute = (model.fills?.points ?? []).filter(
    (fill) => Math.abs(fill.time - axisValue) <= tolerance / 2,
  );
  const filledSize = inMinute.reduce((sum, fill) => sum + fill.size, 0);
  if (model.fills && filledSize > 0)
    rows.push({
      label: `${model.fills.label} · ${formatQfValue(filledSize, 'number')}`,
      value: formatQfValue(
        inMinute.reduce((sum, fill) => sum + fill.price * fill.size, 0) / filledSize,
        model.valueFormat,
      ),
      swatch: model.fills.color,
    });
  const volume = params.find((param) => param.seriesId === 'volume');
  if (volume && Array.isArray(volume.value))
    rows.push({
      label: model.volume?.label ?? 'Volume',
      value: formatQfValue(Number(volume.value[1]), 'number'),
    });
  return rows;
}

// --------------------------------------------------------------------------- #
// Option builder
// --------------------------------------------------------------------------- #

export function buildPriceProfileOption(
  model: PriceProfileModel,
  theme: QfChartTheme,
): QfChartOption {
  const hidden = model.hiddenSeries;
  const timeZone = model.timeZone ?? 'local';
  const format = (value: number) => formatQfValue(value, model.valueFormat);
  const [yMin, yMax] = priceProfileExtent(model);
  const [x0, x1] = clampWindow(model.window, model.xDomain);
  const formatTime = (value: number) =>
    x1 - x0 > 86_400_000
      ? formatPriceProfileTime(value, timeZone, true).slice(5, 16)
      : formatPriceProfileTime(value, timeZone);
  const profiles = model.profiles ?? [];
  const hasProfile = profiles.length > 0;
  const overlayProfile = model.profilePlacement === 'overlay-left';
  const hasVolume = model.volume != null;
  const volumeAxis = hasProfile ? 2 : 1;
  const priceRight = hasProfile && !overlayProfile ? PRICE_PANEL_RIGHT : QF_CHART_INSET;
  const priceBottom = hasVolume ? '28%' : QF_CHART_TIME_AXIS_HEIGHT;
  let maxMass = 1;
  for (const profile of profiles) {
    if (profile.legend !== false && hidden.has(profile.key)) continue;
    for (const [, mass] of profile.rows) maxMass = Math.max(maxMass, mass);
  }
  const left = valueGutterWidth(
    axisLabelWidth({
      domain: [yMin, yMax],
      scale: 'linear',
      splitNumber: VALUE_SPLIT_NUMBER,
      format,
      fontSize: theme.axisFontSize,
    }),
  );
  const priceColor = resolveCssColor(model.price.color ?? theme.benchmark);
  const pointer = { color: theme.crosshair, width: QF_CHART_RULE_WIDTH, type: DASH };
  const valueAxisBase = {
    type: 'value',
    min: yMin,
    max: yMax,
    splitNumber: VALUE_SPLIT_NUMBER,
    axisLine: { show: false },
    axisTick: { show: false },
  };

  return {
    animation: false,
    useUTC: timeZone === 'utc',
    tooltip: {
      ...qfEChartsTooltip(theme),
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        lineStyle: pointer,
        crossStyle: pointer,
        label: { show: false },
      },
      formatter: (raw: unknown) => {
        const params = (Array.isArray(raw) ? raw : [raw]) as TooltipParam[];
        const items = priceProfileTooltipItems(params, model);
        if (items.length === 0) return '';
        return chartTooltipHtml({
          date: formatPriceProfileTime(Number(params[0]?.axisValue), timeZone, true),
          items,
        });
      },
    },
    grid: [
      {
        left,
        right: priceRight,
        top: PLOT_TOP,
        bottom: priceBottom,
        containLabel: false,
      },
      ...(hasProfile
        ? [
            {
              left: overlayProfile ? left : PROFILE_PANEL_LEFT,
              ...(overlayProfile ? { width: '26%' } : { right: QF_CHART_INSET }),
              top: PLOT_TOP,
              bottom: priceBottom,
              containLabel: false,
            },
          ]
        : []),
      ...(hasVolume
        ? [
            {
              left,
              right: priceRight,
              top: '76%',
              bottom: QF_CHART_TIME_AXIS_HEIGHT,
              containLabel: false,
            },
          ]
        : []),
    ],
    axisPointer: { link: [{ xAxisIndex: hasVolume ? [0, volumeAxis] : [0] }] },
    xAxis: [
      {
        type: 'time',
        gridIndex: 0,
        min: x0,
        max: x1,
        axisLabel: {
          color: theme.axis,
          fontSize: theme.axisFontSize,
          hideOverlap: true,
          show: !hasVolume,
          formatter: formatTime,
        },
        axisLine: { lineStyle: { color: theme.frame, width: QF_CHART_RULE_WIDTH } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisPointer: { lineStyle: pointer, label: { show: false } },
      },
      ...(hasProfile
        ? [
            {
              type: 'value',
              gridIndex: 1,
              min: 0,
              max: maxMass * 1.05,
              axisLabel: { show: false },
              axisLine: { show: false },
              axisTick: { show: false },
              splitLine: { show: false },
              axisPointer: { show: false },
            },
          ]
        : []),
      ...(hasVolume
        ? [
            {
              type: 'time',
              gridIndex: volumeAxis,
              min: x0,
              max: x1,
              axisLabel: {
                color: theme.axis,
                fontSize: theme.axisFontSize,
                hideOverlap: true,
                formatter: formatTime,
              },
              axisLine: { lineStyle: { color: theme.frame } },
              axisTick: { show: false },
              splitLine: { show: false },
              axisPointer: { label: { show: false } },
            },
          ]
        : []),
    ],
    yAxis: [
      {
        ...valueAxisBase,
        gridIndex: 0,
        axisLabel: {
          color: theme.axis,
          fontSize: theme.axisFontSize,
          formatter: format,
          ...extremeLabelVisibility([yMin, yMax], 'linear', VALUE_SPLIT_NUMBER),
        },
        splitLine: {
          lineStyle: { color: theme.grid, opacity: theme.gridOpacity, width: QF_CHART_RULE_WIDTH },
        },
        // The price at the crosshair, on the value axis in the tooltip's chrome.
        axisPointer: { lineStyle: pointer, label: qfAxisPointerLabel(theme, format) },
      },
      ...(hasProfile
        ? [
            {
              ...valueAxisBase,
              gridIndex: 1,
              axisLabel: { show: false },
              splitLine: { show: false },
              axisPointer: { show: false },
            },
          ]
        : []),
      ...(hasVolume
        ? [
            {
              type: 'value',
              gridIndex: volumeAxis,
              min: 0,
              splitNumber: 2,
              axisLabel: {
                color: theme.axis,
                fontSize: theme.axisFontSize,
                formatter: (value: number) => formatQfValue(value, 'number'),
              },
              axisLine: { show: false },
              axisTick: { show: false },
              splitLine: { show: false },
            },
          ]
        : []),
    ],
    series: [
      model.candles
        ? marketCandleSeries(hidden.has(model.price.key) ? [] : model.candles)
        : {
            ...lineSeries(
              'price',
              model.price.label,
              priceColor,
              hidden.has(model.price.key) ? [] : breakLineGaps(model.price.points, model.maxGap),
            ),
          },
      ...(model.levels ?? []).flatMap((level) =>
        levelSeries(
          level,
          resolveCssColor(level.color ?? theme.axis),
          model.maxGap,
          hidden.has(level.key),
          theme,
        ),
      ),
      ...(model.fills
        ? [fillSeries(model.fills, resolveCssColor(model.fills.color), hidden.has(model.fills.key))]
        : []),
      {
        // Annotations ride an empty series so hiding the price line keeps them.
        id: 'annotations',
        name: 'annotations',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: [],
        silent: !(model.markers ?? []).some((marker) => marker.role != null),
        tooltip: { show: false },
        // Defaults for anything an annotation leaves unstyled, so no engine colour or
        // 2px default width can leak in.
        lineStyle: { color: theme.axis, width: QF_CHART_LINE_WIDTH },
        itemStyle: { color: theme.axis },
        markLine: {
          lineStyle: { color: theme.crosshair, width: QF_CHART_RULE_WIDTH },
          symbol: ['none', 'none'],
          animation: false,
          silent: true,
          emphasis: { disabled: true },
          data: [
            ...segmentMarkLines(model.segments ?? [], theme),
            ...guideMarkLines(model.timeGuides ?? [], theme),
          ],
        },
        markPoint: {
          animation: false,
          silent: false,
          data: markerPoints(model.markers ?? [], theme),
          tooltip: {
            show: true,
            trigger: 'item',
            formatter: (raw: unknown) => {
              const param = raw as { data?: { value?: string; coord?: [number, number] } };
              return chartTooltipHtml({
                date: formatPriceProfileTime(param.data?.coord?.[0] ?? 0, timeZone, true),
                items: [
                  {
                    label: param.data?.value ?? 'Event',
                    value: format(param.data?.coord?.[1] ?? 0),
                  },
                ],
              });
            },
          },
        },
        ...(model.holding
          ? {
              markArea: {
                silent: true,
                itemStyle: { color: resolveCssColor(withOpacity(chartColor('info'), 0.08)) },
                data: [[{ xAxis: model.holding[0] }, { xAxis: model.holding[1] }]],
              },
            }
          : {}),
      },
      ...profiles.map((profile) =>
        profileSeries(profile, profile.legend !== false && hidden.has(profile.key), overlayProfile),
      ),
      ...(model.volume
        ? [
            marketVolumeSeries(
              {
                ...model.volume,
                bars: model.volume.bars.filter(
                  (bar) => bar.availableTime >= x0 && bar.availableTime <= x1,
                ),
              },
              volumeAxis,
              theme.axis,
            ),
          ]
        : []),
    ],
  };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function PriceProfileChart({
  ariaLabel,
  brush = true,
  title,
  headerRight,
  footer,
  ...model
}: PriceProfileChartProps) {
  const theme = useChartTheme();
  const [hiddenSeries, setHiddenSeries] = useState<ReadonlySet<string>>(EMPTY_HIDDEN);
  const { xDomain, focusWindow } = model;
  // The brush belongs to one domain and focus window; a new one re-opens it there.
  const brushKey = `${xDomain[0]}:${xDomain[1]}:${focusWindow?.[0] ?? ''}:${focusWindow?.[1] ?? ''}`;
  // `window: null` is the full domain the user brushed back to.
  const [brushState, setBrushState] = useState<{
    key: string;
    window: [number, number] | null;
  } | null>(null);
  const visibleWindow =
    brushState?.key === brushKey
      ? (brushState.window ?? undefined)
      : focusWindow
        ? clampWindow(focusWindow, xDomain)
        : undefined;
  const brushData = useMemo(
    () => [{ date: new Date(xDomain[0]) }, { date: new Date(xDomain[1]) }],
    [xDomain[0], xDomain[1]],
  );
  // biome-ignore lint/correctness/useExhaustiveDependencies: the model fields are listed individually so a fresh props object does not rebuild the option.
  const option = useMemo(
    () =>
      buildPriceProfileOption(
        { ...model, hiddenSeries, ...(visibleWindow ? { window: visibleWindow } : {}) },
        theme,
      ),
    [
      hiddenSeries,
      theme,
      visibleWindow?.[0],
      visibleWindow?.[1],
      model.price,
      model.candles,
      model.volume,
      model.holding,
      model.levels,
      model.segments,
      model.timeGuides,
      model.markers,
      model.fills,
      model.profiles,
      model.profilePlacement,
      model.maxGap,
      model.valueFormat,
      model.timeZone,
      xDomain[0],
      xDomain[1],
    ],
  );
  const legendSeries = useMemo(
    () => [
      {
        key: model.price.key,
        label: model.price.label,
        color: model.candles ? 'var(--qf-chart-candle-up)' : (model.price.color ?? theme.benchmark),
        points: [],
      },
      ...(model.levels ?? [])
        .filter((level) => level.legend)
        .map((level) => ({
          key: level.key,
          label: level.label,
          color: level.color ?? theme.axis,
          points: [],
        })),
      ...(model.fills
        ? [{ key: model.fills.key, label: model.fills.label, color: model.fills.color, points: [] }]
        : []),
      ...(model.profiles ?? [])
        .filter((profile) => profile.legend !== false)
        .map((profile) => ({
          key: profile.key,
          label: profile.label,
          color: profileLegendColor(profile),
          points: [],
        })),
    ],
    [
      model.price,
      model.candles,
      model.levels,
      model.fills,
      model.profiles,
      theme.benchmark,
      theme.axis,
    ],
  );

  return (
    <TimeSeriesChart
      {...(model.volume ? { aspectRatio: multiPaneAspectRatio(['main', 'study']) } : {})}
      {...(title === undefined ? {} : { title })}
      {...(headerRight === undefined ? {} : { headerRight })}
      footer={
        model.levels?.some((level) => level.interpolation === 'smooth') ? (
          <>
            {footer}
            <ChartNote>Smoothed</ChartNote>
          </>
        ) : (
          footer
        )
      }
      legend={
        <ChartLegend
          series={legendSeries}
          hiddenSeries={hiddenSeries}
          onHiddenSeriesChange={setHiddenSeries}
        />
      }
      {...(brush
        ? {
            controls: (
              <BrushBar
                data={brushData}
                {...(visibleWindow
                  ? { domain: [new Date(visibleWindow[0]), new Date(visibleWindow[1])] as const }
                  : {})}
                onDomainChange={(next) =>
                  setBrushState({
                    key: brushKey,
                    window: next ? [next[0].getTime(), next[1].getTime()] : null,
                  })
                }
              />
            ),
          }
        : {})}
    >
      <QfChart option={option} ariaLabel={ariaLabel} height="100%" interactive />
    </TimeSeriesChart>
  );
}
