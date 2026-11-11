/**
 * Shared cursor-following tooltip behavior for qf-charts renderers.
 *
 * USAGE:
 *   tooltip: { ...qfEChartsTooltip(theme), trigger: 'axis' }
 *   tooltip: { ...qfEChartsTooltipChrome(theme), ...hostTooltip }   // box only
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { resolveChartFont } from '../theme/tokens';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

interface TooltipTheme {
  axisFontSize: number;
  tooltipBackground: string;
  tooltipBorder: string;
  tooltipText: string;
}

interface TooltipSize {
  contentSize: readonly number[];
  viewSize: readonly number[];
}

// --------------------------------------------------------------------------- #
// Positioning
// --------------------------------------------------------------------------- #

const TOOLTIP_GAP = 14;
/** Seconds the ECharts tooltip glides to each new spot; 0 under reduced motion. */
const TOOLTIP_GLIDE_SECONDS = 0.18;

function tooltipGlideSeconds(): number {
  const reduced =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
  return reduced ? 0 : TOOLTIP_GLIDE_SECONDS;
}
const TOOLTIP_INSET = 12;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

export function containTooltipAtCursor(
  point: readonly [number, number],
  contentSize: readonly [number, number],
  viewSize: readonly [number, number],
): [number, number] {
  const [cursorX, cursorY] = point;
  const [contentWidth, contentHeight] = contentSize;
  const [viewWidth, viewHeight] = viewSize;
  const maxX = Math.max(TOOLTIP_INSET, viewWidth - contentWidth - TOOLTIP_INSET);
  const maxY = Math.max(TOOLTIP_INSET, viewHeight - contentHeight - TOOLTIP_INSET);
  const right = cursorX + TOOLTIP_GAP;
  const below = cursorY + TOOLTIP_GAP;
  const preferredX =
    right + contentWidth <= viewWidth - TOOLTIP_INSET
      ? right
      : cursorX - contentWidth - TOOLTIP_GAP;
  const preferredY =
    below + contentHeight <= viewHeight - TOOLTIP_INSET
      ? below
      : cursorY - contentHeight - TOOLTIP_GAP;

  return [clamp(preferredX, TOOLTIP_INSET, maxX), clamp(preferredY, TOOLTIP_INSET, maxY)];
}

export function positionEChartsTooltip(
  point: readonly number[],
  _params: unknown,
  _element: unknown,
  _rect: unknown,
  size: TooltipSize,
): [number, number] {
  return containTooltipAtCursor(
    [point[0] ?? 0, point[1] ?? 0],
    [size.contentSize[0] ?? 0, size.contentSize[1] ?? 0],
    [size.viewSize[0] ?? 0, size.viewSize[1] ?? 0],
  );
}

// --------------------------------------------------------------------------- #
// ECharts defaults
// --------------------------------------------------------------------------- #

/** The tooltip box alone: surface, radius, padding and text, with no behaviour. */
export function qfEChartsTooltipChrome(theme: TooltipTheme, fontSize = theme.axisFontSize) {
  return {
    // Frosted glass from qf-charts.css; the theme colour is the fallback without the sheet.
    backgroundColor: `var(--qf-chart-tooltip-glass, ${theme.tooltipBackground})`,
    borderColor: theme.tooltipBorder,
    borderRadius: 8,
    borderWidth: 1,
    className: 'qf-echarts-tooltip-host',
    padding: [8, 12],
    // The HTML tooltip otherwise writes an inline box-shadow over the CSS overlay shadow.
    shadowBlur: 0,
    shadowColor: 'transparent',
    textStyle: {
      color: theme.tooltipText,
      fontFamily: resolveChartFont(),
      fontSize,
    },
  } as const;
}

export function qfEChartsTooltip(theme: TooltipTheme, fontSize = theme.axisFontSize) {
  return {
    ...qfEChartsTooltipChrome(theme, fontSize),
    appendToBody: false,
    confine: true,
    position: positionEChartsTooltip,
    renderMode: 'html',
    // ECharts eases the box's transform, so it glides with the cursor and across it on a flip.
    transitionDuration: tooltipGlideSeconds(),
  } as const;
}

/**
 * The value read-out an axis pointer pins to its axis (the price at the crosshair): the
 * tooltip's surface and text on a compact radius, formatted like the axis labels.
 */
export function qfAxisPointerLabel(theme: TooltipTheme, formatter: (value: number) => string) {
  return {
    show: true,
    backgroundColor: theme.tooltipBackground,
    borderColor: theme.tooltipBorder,
    borderWidth: 1,
    borderRadius: 4,
    padding: [2, 6],
    color: theme.tooltipText,
    fontFamily: resolveChartFont(),
    fontSize: theme.axisFontSize,
    shadowBlur: 0,
    formatter: (params: { value?: unknown }) => formatter(Number(params.value)),
  } as const;
}
