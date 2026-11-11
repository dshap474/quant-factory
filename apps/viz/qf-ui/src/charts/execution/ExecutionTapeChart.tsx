/**
 * Execution tape: how one order worked against the market. Sampled depth sits behind a
 * bid-ask band, trades are bubbles sized by volume, our order is the one bold line, and a
 * study pane below shows how much has filled.
 *
 * USAGE:
 *   <ExecutionTapeChart title="Buying $1,000 of BTC" trades={trades} quotes={quotes}
 *     depth={books} order={order} fills={fills} progress={progress}
 *     arrivalPrice={arrival} averagePrice={average} formatPrice={format} />
 */

// --------------------------------------------------------------------------- #
// Imports and contracts
// --------------------------------------------------------------------------- #

import type { CustomSeriesRenderItem } from 'echarts';
import { useMemo } from 'react';
import { axisLabelWidth } from '../charts/axisLabelWidth';
import { ChartKey, type ChartKeyItem } from '../components/ChartKey';
import { TimeSeriesChart } from '../components/TimeSeriesChart';
import {
  multiPaneAspectRatio,
  QF_CHART_RULE_WIDTH,
  QF_CHART_TIME_AXIS_HEIGHT,
  valueGutterWidth,
} from '../core/geometry';
import { QfChart, type QfChartOption } from '../core/QfChart';
import { qfEChartsTooltip } from '../core/tooltip';
import { useChartTheme } from '../hooks/useChartTheme';
import { chartColor, chartPaletteColor } from '../theme/chartColor';
import { resolveCssColor } from '../theme/tokens';
import { escapeHtml } from '../utils/escapeHtml';
import {
  DEPTH_SHADES,
  depthCells,
  type ExecutionTapeBook,
  type ExecutionTapeQuote,
  type ExecutionTapeTrade,
  markDiameter,
  mergeTrades,
  placeTags,
  sizeCeiling,
  type TapeTag,
  tapeGrainMs,
} from './executionTapeModel';

import '../components/MultiPaneTimeSeriesChart.css';

export interface ExecutionTapeOrderPoint {
  time: number;
  /** Null while nothing is resting. */
  price: number | null;
}

export interface ExecutionTapeFill {
  time: number;
  price: number;
  size: number;
}

export interface ExecutionTapeProgressPoint {
  time: number;
  /** Share filled, 0 to 1. */
  value: number;
}

export interface ExecutionTapeChartProps {
  title: string;
  trades: readonly ExecutionTapeTrade[];
  quotes: readonly ExecutionTapeQuote[];
  depth: readonly ExecutionTapeBook[];
  order: readonly ExecutionTapeOrderPoint[];
  fills: readonly ExecutionTapeFill[];
  progress: readonly ExecutionTapeProgressPoint[];
  arrivalPrice?: number | null | undefined;
  averagePrice?: number | null | undefined;
  formatPrice?: ((value: number) => string) | undefined;
  formatSize?: ((value: number) => string) | undefined;
}

// --------------------------------------------------------------------------- #
// Geometry and marks
// --------------------------------------------------------------------------- #

const ASPECT_RATIO = multiPaneAspectRatio(['main', 'study']);
const GRID_TOP = 28;
const PANE_TITLE_TOP = 6;
/** Room a study pane's title takes above its plot. */
const PANE_TITLE_BAND = 22;
const TAG_GUTTER = 112;
const TAG_GAP = 16;
const MAIN_HEIGHT = '62%';
const STUDY_HEIGHT = '18%';
const TIME_PADDING = 0.015;
const TRADE_DIAMETER = [3, 24] as const;
const FILL_DIAMETER = [12, 26] as const;
const DEPTH_MAX_ALPHA = 0.62;

function defaultFormat(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

function clock(time: number): string {
  return new Date(time).toLocaleTimeString(undefined, { hour12: false });
}

interface TooltipEvent {
  seriesId?: string;
  value?: unknown;
}

// --------------------------------------------------------------------------- #
// Custom layers
// --------------------------------------------------------------------------- #

function depthLayer(alphaColors: readonly string[]): CustomSeriesRenderItem {
  return (_params, api) => {
    const [left, bottom] = api.coord([Number(api.value(0)), Number(api.value(2))]);
    const [right, top] = api.coord([Number(api.value(1)), Number(api.value(3))]);
    if (left === undefined || bottom === undefined || right === undefined || top === undefined)
      return;
    return {
      type: 'rect',
      shape: { x: left, y: top, width: right - left + 0.5, height: bottom - top + 0.5 },
      style: { fill: alphaColors[Number(api.value(4)) - 1] ?? 'transparent' },
    };
  };
}

/** The whole bid-ask band is one polygon, so a busy quote feed costs one shape. */
function bandLayer(quotes: readonly ExecutionTapeQuote[], fill: string): CustomSeriesRenderItem {
  return (_params, api) => {
    const upper: number[][] = [];
    const lower: number[][] = [];
    quotes.forEach((quote, index) => {
      const end = quotes[index + 1]?.time ?? quote.time;
      upper.push(api.coord([quote.time, quote.ask]), api.coord([end, quote.ask]));
      lower.push(api.coord([quote.time, quote.bid]), api.coord([end, quote.bid]));
    });
    return { type: 'polygon', shape: { points: [...upper, ...lower.reverse()] }, style: { fill } };
  };
}

function tagLayer(
  tags: readonly Omit<TapeTag, 'y'>[],
  time: number,
  font: string,
): CustomSeriesRenderItem {
  return (params, api) => {
    const plot = params.coordSys as unknown as {
      x: number;
      y: number;
      width: number;
      height: number;
    };
    const spread = placeTags(
      tags.map((tag) => ({ ...tag, y: api.coord([time, tag.value])[1] ?? plot.y })),
      TAG_GAP,
      plot.y + 6,
      plot.y + plot.height - 6,
    );
    return {
      type: 'group',
      children: spread.map((tag) => ({
        type: 'text',
        style: {
          x: plot.x + plot.width + 8,
          y: tag.y,
          text: tag.text,
          fill: tag.color,
          font,
          verticalAlign: 'middle',
        },
      })),
    };
  };
}

// --------------------------------------------------------------------------- #
// Pane titles
// --------------------------------------------------------------------------- #

/** Same label as a stacked chart's panes, placed over this chart's two plots. */
function PaneTitle({ left, top, children }: { left: number; top: string; children: string }) {
  return (
    <div
      className="qf-multi-pane-chart-pane-label"
      style={{ position: 'absolute', left, top, padding: 0, pointerEvents: 'none' }}
    >
      {children}
    </div>
  );
}

// --------------------------------------------------------------------------- #
// Chart
// --------------------------------------------------------------------------- #

export function ExecutionTapeChart({
  title,
  trades,
  quotes,
  depth,
  order,
  fills,
  progress,
  arrivalPrice,
  averagePrice,
  formatPrice = defaultFormat,
  formatSize = defaultFormat,
}: ExecutionTapeChartProps) {
  const theme = useChartTheme();
  const { option, plotLeft } = useMemo(() => {
    const times = [trades[0]?.time, quotes[0]?.time, quotes.at(-1)?.time].filter(
      (value): value is number => value !== undefined,
    );
    const first = Math.min(...times);
    const last = Math.max(...times, trades.at(-1)?.time ?? 0);
    const span = Math.max(1000, last - first);
    const axisMin = first;
    const axisMax = last + span * TIME_PADDING;
    const grain = tapeGrainMs(span);
    const bubbles = mergeTrades(trades, grain);
    const cells = depthCells(depth, grain, last);
    const tradeCeiling = sizeCeiling(bubbles.map((bubble) => bubble.size));
    const fillCeiling = Math.max(1e-12, ...fills.map((fill) => fill.size));

    const prices = [
      ...quotes.flatMap((quote) => [quote.bid, quote.ask]),
      ...trades.map((trade) => trade.price),
      ...cells.flatMap((cell) => [cell.low, cell.high]),
      ...fills.map((fill) => fill.price),
      ...(arrivalPrice != null ? [arrivalPrice] : []),
    ];
    const low = Math.min(...prices);
    const high = Math.max(...prices);
    const pad = (high - low || Math.abs(low) * 0.0005 || 1) * 0.06;
    const domain: [number, number] = [low - pad, high + pad];
    const labelWidth = axisLabelWidth({
      domain,
      scale: 'linear',
      splitNumber: 5,
      format: formatPrice,
      fontSize: theme.axisFontSize,
    });
    const left = valueGutterWidth(labelWidth);
    const font = `${theme.axisFontSize}px ${theme.fontFamily}`;
    const gold = theme.palette[0] ?? theme.axis;
    const buy = resolveCssColor(chartColor('positive', 0.62));
    const sell = resolveCssColor(chartColor('negative', 0.62));
    const depthAlpha = Array.from({ length: DEPTH_SHADES }, (_, index) =>
      resolveCssColor(chartColor('info', (DEPTH_MAX_ALPHA * (index + 1)) / DEPTH_SHADES)),
    );
    const latestQuote = quotes.at(-1);
    const startTime = quotes[0]?.time ?? first;
    const firstFill = fills[0]?.time;
    const lastProgress = progress.at(-1)?.value ?? 0;

    const priceTags: Omit<TapeTag, 'y'>[] = [
      ...(latestQuote
        ? [
            {
              value: latestQuote.ask,
              text: `Ask ${formatPrice(latestQuote.ask)}`,
              color: theme.axis,
            },
            {
              value: latestQuote.bid,
              text: `Bid ${formatPrice(latestQuote.bid)}`,
              color: theme.axis,
            },
          ]
        : []),
      ...(arrivalPrice != null
        ? [{ value: arrivalPrice, text: `Arrival ${formatPrice(arrivalPrice)}`, color: theme.axis }]
        : []),
      ...(averagePrice != null
        ? [{ value: averagePrice, text: `Avg ${formatPrice(averagePrice)}`, color: gold }]
        : []),
    ];

    const xAxisBase = {
      type: 'time',
      min: axisMin,
      max: axisMax,
      axisTick: { show: false },
      splitLine: { show: false },
      axisLine: { lineStyle: { color: theme.frame } },
      axisPointer: {
        show: true,
        // The tooltip describes one mark, so the crosshair alone must never open it.
        triggerTooltip: false,
        label: { show: false },
        lineStyle: { color: theme.crosshair, type: 'dotted', width: QF_CHART_RULE_WIDTH },
      },
    };
    const bubbleSize = (value: number[]) =>
      markDiameter(value[2] ?? 0, tradeCeiling, TRADE_DIAMETER[0], TRADE_DIAMETER[1]);
    const bubbleSeries = (id: string, side: 'buy' | 'sell', color: string) => ({
      id,
      type: 'scatter',
      z: 3,
      symbolSize: bubbleSize,
      itemStyle: { color },
      emphasis: { scale: false },
      data: bubbles
        .filter((bubble) => bubble.side === side)
        .map((bubble) => [bubble.time, bubble.price, bubble.size, bubble.count]),
    });
    const levelLine = (id: string, color: string, type: string, data: number[][]) => ({
      id,
      type: 'line',
      z: 4,
      silent: true,
      showSymbol: false,
      lineStyle: { color, type, width: QF_CHART_RULE_WIDTH },
      data,
    });

    const chartOption: QfChartOption = {
      animation: false,
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: [
        { left, right: TAG_GUTTER, top: GRID_TOP, height: MAIN_HEIGHT },
        { left, right: TAG_GUTTER, bottom: QF_CHART_TIME_AXIS_HEIGHT, height: STUDY_HEIGHT },
      ],
      xAxis: [
        { ...xAxisBase, gridIndex: 0, axisLabel: { show: false } },
        {
          ...xAxisBase,
          gridIndex: 1,
          axisLabel: {
            color: theme.axis,
            hideOverlap: true,
            // Ticks can be seconds apart on any run length, so minutes alone would repeat.
            formatter: (value: number) => clock(value),
          },
        },
      ],
      yAxis: [
        {
          type: 'value',
          gridIndex: 0,
          min: domain[0],
          max: domain[1],
          splitNumber: 5,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            color: theme.axis,
            formatter: formatPrice,
            showMinLabel: false,
            showMaxLabel: false,
          },
          splitLine: { lineStyle: { color: theme.grid, opacity: theme.gridOpacity } },
        },
        {
          type: 'value',
          gridIndex: 1,
          min: 0,
          max: 1,
          interval: 0.5,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            color: theme.axis,
            formatter: (value: number) => `${Math.round(value * 100)}%`,
          },
          splitLine: { lineStyle: { color: theme.grid, opacity: theme.gridOpacity } },
        },
      ],
      tooltip: {
        ...qfEChartsTooltip(theme),
        trigger: 'item',
        formatter: (event: TooltipEvent) => {
          // A formatter that throws leaves ECharts locked, and the chart stops updating.
          if (!Array.isArray(event.value)) return '';
          const [time = 0, price = 0, size = 0, count = 1] = event.value as number[];
          const name =
            event.seriesId === 'fills'
              ? 'Our fill'
              : event.seriesId === 'buys'
                ? 'Aggressive buy'
                : 'Aggressive sell';
          const merged = count > 1 ? ` · ${count} trades` : '';
          return [
            `<strong>${escapeHtml(name)}</strong>`,
            escapeHtml(clock(time)),
            `${escapeHtml(formatPrice(price))} · ${escapeHtml(formatSize(size))}${merged}`,
          ].join('<br/>');
        },
      },
      series: [
        {
          id: 'depth',
          type: 'custom',
          z: 1,
          silent: true,
          clip: true,
          renderItem: depthLayer(depthAlpha),
          encode: { x: [0, 1], y: [2, 3] },
          data: cells.map((cell) => [cell.start, cell.end, cell.low, cell.high, cell.shade]),
        },
        {
          id: 'band',
          type: 'custom',
          z: 2,
          silent: true,
          clip: true,
          renderItem: bandLayer(quotes, resolveCssColor(chartColor('foreground', 0.22))),
          encode: { x: 0, y: 1 },
          data: [[startTime, domain[0]]],
        },
        bubbleSeries('buys', 'buy', buy),
        bubbleSeries('sells', 'sell', sell),
        levelLine(
          'arrival',
          theme.axis,
          'dashed',
          arrivalPrice != null
            ? [
                [startTime, arrivalPrice],
                [axisMax, arrivalPrice],
              ]
            : [],
        ),
        levelLine(
          'average',
          gold,
          'dotted',
          averagePrice != null && firstFill !== undefined
            ? [
                [firstFill, averagePrice],
                [axisMax, averagePrice],
              ]
            : [],
        ),
        {
          id: 'order',
          type: 'line',
          z: 5,
          silent: true,
          step: 'end',
          showSymbol: false,
          lineStyle: { color: gold, width: theme.lineWidth },
          data: order.map((point) => [point.time, point.price]),
        },
        {
          id: 'fills',
          type: 'scatter',
          z: 6,
          symbol: 'diamond',
          symbolSize: (value: number[]) =>
            markDiameter(value[2] ?? 0, fillCeiling, FILL_DIAMETER[0], FILL_DIAMETER[1]),
          itemStyle: { color: gold, borderColor: theme.background, borderWidth: 1.5 },
          emphasis: { scale: false },
          data: fills.map((fill) => [fill.time, fill.price, fill.size, 1]),
        },
        {
          id: 'price-tags',
          type: 'custom',
          z: 7,
          silent: true,
          clip: false,
          renderItem: tagLayer(priceTags, startTime, font),
          encode: { x: 0, y: 1 },
          data: [[startTime, domain[0]]],
        },
        {
          id: 'progress',
          type: 'line',
          xAxisIndex: 1,
          yAxisIndex: 1,
          silent: true,
          step: 'end',
          showSymbol: false,
          lineStyle: { color: gold, width: theme.lineWidth },
          areaStyle: { color: gold, opacity: 0.22 },
          data: [
            ...progress.map((point) => [point.time, point.value]),
            ...(progress.length ? [[axisMax, lastProgress]] : []),
          ],
        },
        {
          id: 'progress-tag',
          type: 'custom',
          xAxisIndex: 1,
          yAxisIndex: 1,
          silent: true,
          clip: false,
          renderItem: tagLayer(
            [
              {
                value: lastProgress,
                text: `Filled ${Math.round(lastProgress * 100)}%`,
                color: theme.axis,
              },
            ],
            startTime,
            font,
          ),
          encode: { x: 0, y: 1 },
          data: [[startTime, 0]],
        },
      ],
      aria: { enabled: true },
    };
    return { option: chartOption, plotLeft: left };
  }, [
    arrivalPrice,
    averagePrice,
    depth,
    fills,
    formatPrice,
    formatSize,
    order,
    progress,
    quotes,
    theme,
    trades,
  ]);

  const legend = useMemo<ChartKeyItem[]>(
    () => [
      { id: 'buys', label: 'Aggressive buy', color: chartColor('positive') },
      { id: 'sells', label: 'Aggressive sell', color: chartColor('negative') },
      { id: 'band', label: 'Bid-ask spread', color: chartColor('foreground', 0.45) },
      { id: 'depth', label: 'Resting depth', color: chartColor('info', DEPTH_MAX_ALPHA) },
      { id: 'order', label: 'Our order and fills', color: chartPaletteColor(0) },
    ],
    [],
  );

  return (
    <TimeSeriesChart title={title} aspectRatio={ASPECT_RATIO} legend={<ChartKey items={legend} />}>
      <div style={{ position: 'relative', height: '100%' }}>
        <QfChart
          option={option}
          height="100%"
          ariaLabel={`${title}: trades, bid-ask spread and resting depth, with our order, fills and fill progress`}
        />
        <PaneTitle left={plotLeft} top={`${PANE_TITLE_TOP}px`}>
          Price and liquidity
        </PaneTitle>
        <PaneTitle
          left={plotLeft}
          top={`calc(100% - ${QF_CHART_TIME_AXIS_HEIGHT + PANE_TITLE_BAND}px - ${STUDY_HEIGHT})`}
        >
          Filled
        </PaneTitle>
      </div>
    </TimeSeriesChart>
  );
}
