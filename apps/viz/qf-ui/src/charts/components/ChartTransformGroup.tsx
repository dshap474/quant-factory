/**
 * Page-wide transform coordination: one master window selection every chart follows,
 * with per-chart overrides, and no state threading through the page.
 *
 * Wrap a dashboard in ChartTransformGroupProvider; every MultiSeriesTimeChart inside
 * with transformControls joins the group on its own. ChartTransformMasterToolbar drives
 * the master state and, unless given controls, offers the union of the windows the
 * member charts expose. Picking a master window clears the per-chart overrides.
 *
 * USAGE:
 *   <ChartTransformGroupProvider>
 *     <WorkspaceToolbar title="Chart controls"><ChartTransformMasterToolbar /></WorkspaceToolbar>
 *     <MultiSeriesTimeChart transformControls={{ zScore: true, ema: true }} ... />
 *   </ChartTransformGroupProvider>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useState,
} from 'react';

import {
  CHART_EMA_WINDOWS,
  CHART_Z_SCORE_WINDOWS,
  type ChartTransformControls,
  type ChartTransformState,
  type ChartTransformWindow,
  DEFAULT_CHART_TRANSFORM_STATE,
  resolveChartTransformWindows,
} from '../charts/timeSeriesTransforms';
import { type ChartTransformGroup, useChartTransformGroup } from '../hooks/useChartTransformGroup';
import type { ChartToolbarVariant } from './ChartToggleGroup';
import { ChartTransformToolbar } from './ChartTransformToolbar';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartTransformGroupProviderProps {
  initialState?: ChartTransformState;
  /** How member charts and the master draw their transform toolbars (default 'rail'). */
  toolbarVariant?: ChartToolbarVariant;
  children: ReactNode;
}

export interface ChartTransformMasterToolbarProps {
  /** Windows the master offers; defaults to the union of the member charts' windows. */
  controls?: ChartTransformControls;
  /** Overrides the provider's toolbarVariant for the master only. */
  variant?: ChartToolbarVariant;
}

/** What a member chart reads and writes while inside a group. */
export interface ChartTransformGroupMember {
  state: ChartTransformState;
  onChange: (value: ChartTransformState) => void;
  toolbarVariant: ChartToolbarVariant;
}

interface ChartTransformGroupContextValue extends ChartTransformGroup {
  memberControls: ChartTransformControls;
  toolbarVariant: ChartToolbarVariant;
  registerControls: (memberId: string, controls: ChartTransformControls) => () => void;
}

// --------------------------------------------------------------------------- #
// Context
// --------------------------------------------------------------------------- #

const ChartTransformGroupContext = createContext<ChartTransformGroupContextValue | null>(null);

function unionWindows(
  registered: readonly ChartTransformControls[],
  kind: keyof ChartTransformControls,
  defaults: readonly ChartTransformWindow[],
): ChartTransformWindow[] {
  const windows = new Set<ChartTransformWindow>();
  for (const controls of registered) {
    for (const window of resolveChartTransformWindows(controls[kind], defaults)) {
      windows.add(window);
    }
  }
  return [...windows].sort((a, b) => a - b);
}

export function ChartTransformGroupProvider({
  initialState = DEFAULT_CHART_TRANSFORM_STATE,
  toolbarVariant = 'rail',
  children,
}: ChartTransformGroupProviderProps) {
  const group = useChartTransformGroup(initialState);
  const [registry, setRegistry] = useState<Readonly<Record<string, ChartTransformControls>>>({});

  const registerControls = useCallback((memberId: string, controls: ChartTransformControls) => {
    setRegistry((current) => ({ ...current, [memberId]: controls }));
    return () =>
      setRegistry((current) => {
        const { [memberId]: _removed, ...rest } = current;
        return rest;
      });
  }, []);

  const memberControls = useMemo<ChartTransformControls>(() => {
    const registered = Object.values(registry);
    return {
      zScore: unionWindows(registered, 'zScore', CHART_Z_SCORE_WINDOWS),
      ema: unionWindows(registered, 'ema', CHART_EMA_WINDOWS),
    };
  }, [registry]);

  const value = useMemo(
    () => ({ ...group, memberControls, registerControls, toolbarVariant }),
    [group, memberControls, registerControls, toolbarVariant],
  );
  return (
    <ChartTransformGroupContext.Provider value={value}>
      {children}
    </ChartTransformGroupContext.Provider>
  );
}

// --------------------------------------------------------------------------- #
// Member hook
// --------------------------------------------------------------------------- #

/**
 * Joins the enclosing transform group, if any. Returns null outside a provider or when
 * the chart exposes no transform windows, so the caller falls back to local state.
 */
export function useChartTransformGroupMember(
  controls: ChartTransformControls | undefined,
): ChartTransformGroupMember | null {
  const context = useContext(ChartTransformGroupContext);
  const memberId = useId();
  const zScore = resolveChartTransformWindows(controls?.zScore, CHART_Z_SCORE_WINDOWS);
  const ema = resolveChartTransformWindows(controls?.ema, CHART_EMA_WINDOWS);
  const joins = context !== null && (zScore.length > 0 || ema.length > 0);
  // Keyed by content so an inline controls object does not re-register every render.
  const controlsKey = joins ? JSON.stringify({ zScore, ema }) : '';
  const registerControls = context?.registerControls;

  useEffect(() => {
    if (!registerControls || controlsKey === '') return undefined;
    return registerControls(memberId, JSON.parse(controlsKey) as ChartTransformControls);
  }, [controlsKey, memberId, registerControls]);

  if (!context || !joins) return null;
  return {
    state: context.stateFor(memberId),
    onChange: (value) => context.updateChartState(memberId, value),
    toolbarVariant: context.toolbarVariant,
  };
}

// --------------------------------------------------------------------------- #
// Master toolbar
// --------------------------------------------------------------------------- #

export function ChartTransformMasterToolbar({
  controls,
  variant,
}: ChartTransformMasterToolbarProps) {
  const context = useContext(ChartTransformGroupContext);
  if (!context) {
    throw new Error('ChartTransformMasterToolbar must render inside ChartTransformGroupProvider');
  }
  return (
    <ChartTransformToolbar
      controls={controls ?? context.memberControls}
      value={context.masterState}
      onChange={context.applyMasterState}
      variant={variant ?? context.toolbarVariant}
    />
  );
}
