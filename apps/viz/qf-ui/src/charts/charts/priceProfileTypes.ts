/** Portable price, study, event, profile and market-pane composition contracts.
 * USAGE: import type { PriceProfileChartProps } from '@quant-factory/qf-ui/charts/renderers'.
 */
// --------------------------------------------------------------------------- #
// Imports and contracts
// --------------------------------------------------------------------------- #
import type { ReactNode } from 'react';
import type { QfValueFormat } from '../types/contracts';
import type { MarketCandle, MarketVolume } from './marketPriceLayers';

/** One observation: epoch milliseconds and a value (null breaks the line). */
export type PriceProfilePoint = readonly [time: number, value: number | null];

export interface PriceProfileLine {
  key: string;
  label: string;
  color?: string;
  points: readonly PriceProfilePoint[];
  interpolation?: 'linear' | 'step-end' | 'smooth';
}

export interface PriceProfileLevel extends PriceProfileLine {
  /** Opt into the shared study visibility controls. Existing profile levels stay annotation-only. */
  legend?: boolean;
  /** Stroke pattern, or cross marks at fixed screen spacing along the study. */
  style?: 'solid' | 'dashed' | 'dotted' | 'cross';
  /** Context guides use the thinner reference-rule width. */
  weight?: 'level' | 'guide';
  /** Text drawn at the line's last point. */
  endLabel?: string;
  /** Dashed up to and including this time, solid from it on; omit for solid throughout. */
  dashedUntil?: number;
}

export interface PriceProfileSegment {
  key: string;
  label: string;
  value: number;
  from: number;
  to: number;
  color: string;
  style: 'dotted' | 'dashed';
  /** `level` draws at the data line width, `guide` at the reference-rule width. */
  weight: 'level' | 'guide';
  /** Recede behind live levels (a carried-over reference). */
  muted?: boolean;
  text?: string;
  textPosition?: 'start' | 'end' | 'insideStartTop' | 'insideEndTop';
}

export interface PriceProfileTimeGuide {
  key: string;
  at: number;
  label: string;
  color?: string;
}

export interface PriceProfileMarker {
  key: string;
  time: number;
  value: number;
  label: string;
  color: string;
  labelPosition?: 'top' | 'bottom' | 'left' | 'right';
  /** Optional annotation color, independent of the event symbol's color. */
  labelColor?: string;
  /** Quiet chart-surface backing keeps the annotation legible over plotted lines. */
  labelBackdrop?: boolean;
  role?: 'signal' | 'entry' | 'exit_trigger' | 'exit';
  /** Execution action controls arrow direction independently of entry/exit lifecycle. */
  side?: 'buy' | 'sell';
}

/** One execution fill: a dot at its price whose area scales with `size`. */
export interface PriceProfileFill {
  time: number;
  price: number;
  /** Any positive measure (quantity, notional); the largest fill draws the largest dot. */
  size: number;
  /** Solid dot, or a hollow ring (e.g. maker vs taker). */
  solid: boolean;
}

/** A set of fills drawn as one legend series over the price. */
export interface PriceProfileFills {
  key: string;
  label: string;
  color: string;
  points: readonly PriceProfileFill[];
}

export interface PriceProfileDistribution {
  key: string;
  label: string;
  color: string;
  /** False keeps this profile always visible and omits its legend visibility control. */
  legend?: boolean;
  /** `[price, mass]` rows, each `rowSize` tall and centred on its price. */
  rows: readonly (readonly [number, number])[];
  rowSize: number;
  /** Value band `[low, high]`: its rows draw in `color`, the rest in the neutral tone. */
  band?: readonly [number, number];
  /** `filled` (default) draws solid rows; `outline` draws faint outlined rows, so a
   *  comparison profile reads through another one. */
  variant?: 'filled' | 'outline';
  /** Optional opacity multiplier (0–1), including value-band and outline rows. */
  opacity?: number;
}

export interface PriceProfileChartProps {
  ariaLabel: string;
  /** Full time range of the price panel, epoch milliseconds. */
  xDomain: readonly [number, number];
  price: PriceProfileLine;
  candles?: readonly MarketCandle[];
  volume?: MarketVolume;
  holding?: readonly [number, number];
  levels?: readonly PriceProfileLevel[];
  segments?: readonly PriceProfileSegment[];
  timeGuides?: readonly PriceProfileTimeGuide[];
  markers?: readonly PriceProfileMarker[];
  /** Execution fills as sized dots over the price; the tooltip shows each minute's fills. */
  fills?: PriceProfileFills;
  profiles?: readonly PriceProfileDistribution[];
  /** Overlay profiles on the left behind price; the default retains the separate right panel. */
  profilePlacement?: 'right' | 'overlay-left';
  /** Initial brushed window; changing it re-opens the brush on the new window. */
  focusWindow?: readonly [number, number];
  /** Break a line where consecutive points are further apart than this (ms). */
  maxGap?: number;
  valueFormat?: QfValueFormat;
  timeZone?: 'local' | 'utc';
  brush?: boolean;
  title?: string;
  headerRight?: ReactNode;
  footer?: ReactNode;
}

export interface PriceProfileModel extends Omit<PriceProfileChartProps, 'ariaLabel'> {
  hiddenSeries: ReadonlySet<string>;
  /** Visible time window; the full `xDomain` when omitted. */
  window?: readonly [number, number];
}
