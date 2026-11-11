/**
 * Shared placement vocabulary for anchored overlays (tooltip, popover, menu).
 *
 * USAGE:
 *   import { OVERLAY_SIDE_OFFSET, type OverlayPlacementProps } from './placement';
 *   <BasePopover.Positioner sideOffset={sideOffset ?? OVERLAY_SIDE_OFFSET} />
 */

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type OverlaySide = 'top' | 'bottom' | 'left' | 'right' | 'inline-start' | 'inline-end';

export type OverlayAlign = 'start' | 'center' | 'end';

export interface OverlayPlacementProps {
  /** Preferred side of the anchor; flips on collision. */
  side?: OverlaySide | undefined;
  /** Alignment along the chosen side. */
  align?: OverlayAlign | undefined;
  /** Gap between anchor and popup in px (default 6). */
  sideOffset?: number | undefined;
  /** Shift along the alignment axis in px. */
  alignOffset?: number | undefined;
}

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

export const OVERLAY_SIDE_OFFSET = 6;
