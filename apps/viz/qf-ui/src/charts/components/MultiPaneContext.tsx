/**
 * Pane-link contract shared by the multi-pane shell and the plots it hosts.
 *
 * USAGE:
 *   const link = useMultiPaneLink();   // inside a linked pane's plot; null when unlinked
 *   linkedPaneGrid(link);              // ECharts grid insets for that pane
 *   link.requestLeftInset?.(width);    // widest value label the pane needs room for
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { createContext, useContext } from 'react';

import { QF_CHART_INSET, QF_CHART_LABEL_GAP, valueGutterWidth } from '../core/geometry';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type MultiPanePosition = 'only' | 'top' | 'middle' | 'bottom';

export interface MultiPaneGutter {
  left: number;
  right: number;
}

export interface MultiPaneLink {
  position: MultiPanePosition;
  gutter: MultiPaneGutter;
  xDomain: readonly [Date, Date] | null;
  /** True when the stack renders one tooltip for every pane, so the pane hides its own. */
  shellTooltip?: boolean;
  /** Reports the pixel width of the pane's widest value label; the stack keeps the max. */
  requestLeftInset?: (width: number) => void;
}

export interface LinkedPaneGrid {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

/** Left gutter fits five-character value labels; the right one is the card inset. */
export const DEFAULT_PANE_GUTTER: MultiPaneGutter = { left: 64, right: QF_CHART_INSET };
/** Room kept above each plot: the overlaid pane label (24px) plus half a value label, so
 * the top gridline and its label clear the pane title. */
export const PANE_LABEL_INSET = 32;
/** Height of the shared time axis under the bottom pane. */
export const PANE_AXIS_INSET = 26;
/** Room under a pane that does not carry the axis: half a value label plus a little air. */
export const PANE_EDGE_INSET = 12;
/** Gap ECharts keeps between a linked pane's value labels and its plot edge. */
export const PANE_LABEL_MARGIN = QF_CHART_LABEL_GAP;

// --------------------------------------------------------------------------- #
// Context
// --------------------------------------------------------------------------- #

const MultiPaneLinkContext = createContext<MultiPaneLink | null>(null);

export const MultiPaneLinkProvider = MultiPaneLinkContext.Provider;

export function useMultiPaneLink(): MultiPaneLink | null {
  return useContext(MultiPaneLinkContext);
}

// --------------------------------------------------------------------------- #
// Geometry
// --------------------------------------------------------------------------- #

export function panePosition(index: number, count: number): MultiPanePosition {
  if (count <= 1) return 'only';
  if (index <= 0) return 'top';
  if (index >= count - 1) return 'bottom';
  return 'middle';
}

/** Only the bottom pane draws the shared time axis; the others keep its grid lines. */
export function showsSharedAxis(position: MultiPanePosition): boolean {
  return position === 'bottom' || position === 'only';
}

export function linkedPaneGrid(link: MultiPaneLink): LinkedPaneGrid {
  return {
    top: PANE_LABEL_INSET,
    right: link.gutter.right,
    bottom: showsSharedAxis(link.position) ? PANE_AXIS_INSET : PANE_EDGE_INSET,
    left: link.gutter.left,
  };
}

/** Vertical pixels of a linked pane that are chrome, not plot: insets plus its divider. */
export function linkedPaneChrome(position: MultiPanePosition): number {
  const divider = position === 'top' || position === 'middle' ? 1 : 0;
  return (
    PANE_LABEL_INSET + (showsSharedAxis(position) ? PANE_AXIS_INSET : PANE_EDGE_INSET) + divider
  );
}

/**
 * Shared left gutter for a stack whose widest value label measures `labelWidth` pixels.
 * Falls back to the default gutter until a pane has reported a label.
 */
export function leftInsetForLabelWidth(labelWidth: number): number {
  if (!Number.isFinite(labelWidth) || labelWidth <= 0) return DEFAULT_PANE_GUTTER.left;
  return valueGutterWidth(labelWidth);
}

/**
 * Crosshair offset inside the pane stack for a pointer at `pointerX`, or null when the
 * pointer sits in a gutter; every linked pane shares the gutters, so one x fits all.
 */
export function crosshairOffset(
  pointerX: number,
  width: number,
  gutter: MultiPaneGutter,
): number | null {
  const left = gutter.left;
  const right = width - gutter.right;
  if (!Number.isFinite(pointerX) || !Number.isFinite(width) || right <= left) return null;
  return pointerX >= left && pointerX <= right ? pointerX : null;
}

/** Time under a crosshair at `offsetX` in a stack `width` wide that plots `xDomain`. */
export function dateAtOffset(
  offsetX: number,
  width: number,
  gutter: MultiPaneGutter,
  xDomain: readonly [Date, Date],
): Date | null {
  const left = gutter.left;
  const span = width - gutter.right - left;
  if (!Number.isFinite(offsetX) || !(span > 0)) return null;
  const start = xDomain[0].getTime();
  const end = xDomain[1].getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  const fraction = Math.min(1, Math.max(0, (offsetX - left) / span));
  return new Date(start + fraction * (end - start));
}
