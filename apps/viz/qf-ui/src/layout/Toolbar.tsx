/**
 * Shared dense toolbar surface for related controls.
 *
 * USAGE:
 *   <Toolbar aria-label="Chart controls">…</Toolbar>
 *   <Toolbar band aria-label="Table filters">…</Toolbar>   // edge band of a bounded pane
 *
 * A `band` toolbar spans its pane and insets its controls by `--ui-band-inset` (the
 * surface gutter by default); an edge-to-edge host sets it to the page inset.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { HTMLAttributes } from 'react';

import { Surface } from '../primitives/Surface';

import './Toolbar.css';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export interface ToolbarProps extends HTMLAttributes<HTMLDivElement> {
  /** Render as a full-width band of a bounded pane, inset by `--ui-band-inset`. */
  band?: boolean;
}

export function Toolbar({ band = false, className, children, ...props }: ToolbarProps) {
  return (
    <Surface
      padding={band ? 'none' : 'sm'}
      className={['ui-toolbar', band && 'ui-toolbar-band', className].filter(Boolean).join(' ')}
      {...props}
    >
      {children}
    </Surface>
  );
}
