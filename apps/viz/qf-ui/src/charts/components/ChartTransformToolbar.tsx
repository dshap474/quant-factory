/**
 * Controlled toolbar for package-owned time-series display transformations.
 *
 * USAGE:
 *   <ChartTransformToolbar controls={{ zScore: true, ema: true }} value={state} onChange={setState} />
 *   <ChartTransformToolbar variant="menu" controls={...} value={state} onChange={setState} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  CHART_EMA_WINDOWS,
  CHART_Z_SCORE_WINDOWS,
  type ChartTransformControls,
  type ChartTransformState,
  type ChartTransformWindow,
  resolveChartTransformWindows,
} from '../charts/timeSeriesTransforms';
import { ChartToggleGroup, type ChartToolbarVariant } from './ChartToggleGroup';

import './ChartTransformToolbar.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartTransformToolbarProps {
  controls: ChartTransformControls;
  value: ChartTransformState;
  onChange: (value: ChartTransformState) => void;
  /** Joined rail per transform (default) or one dropdown chip per transform. */
  variant?: ChartToolbarVariant;
}

// --------------------------------------------------------------------------- #
// Options
// --------------------------------------------------------------------------- #

function windowOptions(windows: readonly ChartTransformWindow[], describe: (n: number) => string) {
  return windows.map((window) => ({
    value: window,
    label: (
      <>
        {window}
        <span className="qf-chart-toggle-unit">D</span>
      </>
    ),
    ariaLabel: describe(window),
  }));
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ChartTransformToolbar({
  controls,
  value,
  onChange,
  variant = 'rail',
}: ChartTransformToolbarProps) {
  const zScoreWindows = resolveChartTransformWindows(controls.zScore, CHART_Z_SCORE_WINDOWS);
  const emaWindows = resolveChartTransformWindows(controls.ema, CHART_EMA_WINDOWS);
  if (zScoreWindows.length === 0 && emaWindows.length === 0) return null;
  return (
    <div className="qf-chart-transform-toolbar" data-variant={variant}>
      {zScoreWindows.length > 0 ? (
        <ChartToggleGroup<ChartTransformWindow>
          variant={variant}
          allowDeselect
          label="Z"
          ariaLabel="Z-score window"
          options={windowOptions(zScoreWindows, (n) => `${n}-day trailing Z-score`)}
          value={value.zScore}
          onChange={(zScore) => onChange({ ...value, zScore })}
        />
      ) : null}
      {emaWindows.length > 0 ? (
        <ChartToggleGroup<ChartTransformWindow>
          variant={variant}
          allowDeselect
          label="EMA"
          ariaLabel="EMA smoothing window"
          options={windowOptions(emaWindows, (n) => `${n}-day EMA smoothing`)}
          value={value.ema}
          onChange={(ema) => onChange({ ...value, ema })}
        />
      ) : null}
    </div>
  );
}
