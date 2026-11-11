/**
 * Public data contracts shared by qf-charts primitives.
 *
 * USAGE:
 *   const series: QfSeries = { key: 'pnl', label: 'PnL', points: [] };
 */

// --------------------------------------------------------------------------- #
// Public contracts
// --------------------------------------------------------------------------- #

export type QfValueFormat =
  | 'number'
  | 'integer'
  | 'percent'
  | 'currency'
  | ((value: number) => string);

export interface QfPoint {
  date: Date;
  value: number | null;
  active?: boolean;
}

export interface QfSeries {
  key: string;
  label: string;
  color?: string;
  axis?: 'primary' | 'secondary' | 'tertiary';
  /** Dim semantic-grey dashed line, omitted from legends; hidden axis unless a shared scale is requested. */
  isBenchmark?: boolean;
  valueFormat?: QfValueFormat;
  points: readonly QfPoint[];
}

export interface QfPadding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}
