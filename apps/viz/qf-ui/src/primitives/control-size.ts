/**
 * Shared control-size scale for Button, Link, Input, Select, and SegmentedControl.
 *
 * `size` maps to one step of `--control-height-{xs..xl}` (see styles/tokens.css) through a
 * `.ui-size-*` class that sets `--ui-control-h` and `--ui-icon-size`; `icon` squares the
 * control at that height. An unset size is `md`: no class is emitted and every recipe falls
 * back to `--control-height` (= md).
 *
 * USAGE:
 *   import { controlSizeClasses, type ControlSize } from './control-size';
 *   const classes = cn('ui-button', controlSizeClasses(size, icon), className);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import './control-size.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type ControlSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

export const CONTROL_SIZES: readonly ControlSize[] = ['xs', 'sm', 'md', 'lg', 'xl'];

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Class for one size step; undefined (the md default) emits nothing. */
export function controlSizeClass(size: ControlSize | undefined): string | undefined {
  return size === undefined ? undefined : `ui-size-${size}`;
}

/** Size class plus the square icon-only modifier. */
export function controlSizeClasses(size: ControlSize | undefined, icon = false): string {
  return [controlSizeClass(size), icon ? 'ui-icon-only' : undefined].filter(Boolean).join(' ');
}
