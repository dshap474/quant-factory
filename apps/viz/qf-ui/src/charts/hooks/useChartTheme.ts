/**
 * Reactive qf-charts semantic theme hook.
 *
 * USAGE:
 *   const theme = useChartTheme();
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMemo, useSyncExternalStore } from 'react';

import { QF_CHART_LINE_WIDTH } from '../core/geometry';
import { QF_DARK_THEME, QF_LIGHT_THEME } from '../theme/defaults';
import { resolveChartColor, resolveChartFont } from '../theme/tokens';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface QfChartTheme {
  axis: string;
  axisFontSize: number;
  background: string;
  benchmark: string;
  /** Hover crosshair rule colour. */
  crosshair: string;
  focus: string;
  /** Concrete canvas family list for chart text (the token sans). */
  fontFamily: string;
  frame: string;
  grid: string;
  gridOpacity: number;
  /** Every data line's stroke width: QF_CHART_LINE_WIDTH. */
  lineWidth: number;
  palette: readonly string[];
  tooltipBackground: string;
  tooltipBorder: string;
  tooltipText: string;
}

// --------------------------------------------------------------------------- #
// Subscription
// --------------------------------------------------------------------------- #

const ROOT_ATTRIBUTES = [
  'data-theme',
  'data-style-preset',
  'data-density',
  'data-contrast',
] as const;

// `qf:chart-theme-change` announces a stylesheet swap no root attribute records. Bumping
// a generation in the signature makes the snapshot differ, so subscribers re-render;
// this listener registers at import, before any component subscribes.
let eventGeneration = 0;
if (typeof window !== 'undefined') {
  window.addEventListener('qf:chart-theme-change', () => {
    eventGeneration += 1;
  });
}

function signature(): string {
  if (typeof document === 'undefined') return 'server';
  const attributes = ROOT_ATTRIBUTES.map(
    (name) => document.documentElement.getAttribute(name) ?? '',
  ).join('|');
  return `${eventGeneration}|${attributes}|${colorSchemeSignature()}`;
}

function mediaQuery(query: string): MediaQueryList | null {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null;
  return window.matchMedia(query);
}

function subscribe(callback: () => void): () => void {
  if (typeof document === 'undefined') return () => undefined;
  const observer = new MutationObserver(callback);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: [...ROOT_ATTRIBUTES],
  });
  window.addEventListener('qf:chart-theme-change', callback);
  const query = mediaQuery('(prefers-color-scheme: dark)');
  query?.addEventListener?.('change', callback);
  return () => {
    observer.disconnect();
    window.removeEventListener('qf:chart-theme-change', callback);
    query?.removeEventListener?.('change', callback);
  };
}

// Dark is the package default: only an explicit light preference flips the theme,
// which keeps SSR and jsdom (where no query matches) on the dark defaults.
function colorSchemeSignature(): string {
  return mediaQuery('(prefers-color-scheme: light)')?.matches ? 'light' : 'dark';
}

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export function useChartTheme(): QfChartTheme {
  const themeSignature = useSyncExternalStore(subscribe, signature, () => 'server');
  return useMemo(() => resolveTheme(themeSignature), [themeSignature]);
}

// --------------------------------------------------------------------------- #
// Resolution
// --------------------------------------------------------------------------- #

// The signature is a parameter, not just a memo key: React Compiler re-derives memo
// dependencies from what a body reads, and a body that only reads `defaults` would
// keep stale colours across a `data-theme` change.
function resolveTheme(themeSignature: string): QfChartTheme {
  const defaults = themeSignature.endsWith('|light') ? QF_LIGHT_THEME : QF_DARK_THEME;
  const palette = defaults.palette.map((fallback, index) =>
    resolveChartColor(`--qf-chart-${index + 1}`, fallback),
  );
  return {
    axis: resolveChartColor('--qf-chart-axis-label', defaults.axisLabel),
    axisFontSize: 12,
    background: resolveChartColor('--qf-chart-surface', defaults.surface),
    benchmark: resolveChartColor('--qf-chart-benchmark', defaults.benchmark),
    crosshair: resolveChartColor('--qf-chart-crosshair', defaults.crosshair),
    focus: resolveChartColor('--qf-chart-tone-info', defaults.focus),
    fontFamily: resolveChartFont(),
    frame: resolveChartColor('--qf-chart-axis', defaults.axis),
    grid: resolveChartColor('--qf-chart-grid', defaults.grid),
    gridOpacity: defaults.gridOpacity,
    lineWidth: QF_CHART_LINE_WIDTH,
    palette,
    tooltipBackground: resolveChartColor('--qf-chart-tooltip-bg', defaults.tooltipBackground),
    tooltipBorder: resolveChartColor('--qf-chart-tooltip-border', defaults.tooltipBorder),
    tooltipText: resolveChartColor('--qf-chart-tooltip-text', defaults.tooltipText),
  };
}
