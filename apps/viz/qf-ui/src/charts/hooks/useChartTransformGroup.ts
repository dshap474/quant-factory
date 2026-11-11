/**
 * Coordinates one master transform state with optional per-chart overrides.
 *
 * USAGE:
 *   const transforms = useChartTransformGroup();
 *   transforms.applyMasterState({ zScore: 90, ema: null });
 *   transforms.updateChartState('volume', { zScore: 30, ema: null });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useCallback, useState } from 'react';
import {
  type ChartTransformState,
  DEFAULT_CHART_TRANSFORM_STATE,
} from '../charts/timeSeriesTransforms';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartTransformGroup {
  masterState: ChartTransformState;
  applyMasterState: (value: ChartTransformState) => void;
  stateFor: (chartId: string) => ChartTransformState;
  updateChartState: (chartId: string, value: ChartTransformState) => void;
}

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export function useChartTransformGroup(
  initialState: ChartTransformState = DEFAULT_CHART_TRANSFORM_STATE,
): ChartTransformGroup {
  const [masterState, setMasterState] = useState(initialState);
  const [overrides, setOverrides] = useState<Readonly<Record<string, ChartTransformState>>>({});

  const applyMasterState = useCallback((value: ChartTransformState) => {
    setMasterState(value);
    setOverrides({});
  }, []);

  const updateChartState = useCallback((chartId: string, value: ChartTransformState) => {
    setOverrides((current) => ({ ...current, [chartId]: value }));
  }, []);

  const stateFor = useCallback(
    (chartId: string) => overrides[chartId] ?? masterState,
    [masterState, overrides],
  );

  return { masterState, applyMasterState, stateFor, updateChartState };
}
