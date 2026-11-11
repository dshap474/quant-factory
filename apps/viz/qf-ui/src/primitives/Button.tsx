/**
 * Shared button primitive for every application action.
 *
 * USAGE:
 *   <Button variant="control" onClick={refresh}>Refresh</Button>
 *   <Button variant="control" icon aria-label="Previous">…</Button>
 *   <Button variant="control" size="sm">Compact</Button>
 *   <Button variant="control" size="lg" icon aria-label="Open">…</Button>
 *   <Button variant="nav" className="is-selected">…</Button>
 *   <Button variant="link" onClick={goUp}>datasets</Button>
 *   <Button variant="primary" onClick={save}>Save</Button>
 *   <Button variant="destructive" onClick={remove}>Delete</Button>
 *   <Button className="sidebar-collapse-button" aria-label="Collapse">…</Button>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentPropsWithRef } from 'react';

import { cn } from '../lib/cn';
import { type ControlSize, controlSizeClasses } from './control-size';

import './Button.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type { ControlSize };

export interface ButtonProps extends ComponentPropsWithRef<'button'> {
  variant?: 'plain' | 'control' | 'nav' | 'link' | 'primary' | 'destructive';
  /** Height step from the control-size scale. Default `md`. */
  size?: ControlSize;
  /** Square, icon-only control at the `size` height (16px glyph at md, scaled per step). */
  icon?: boolean;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Button({
  variant = 'plain',
  size,
  icon = false,
  className,
  type = 'button',
  ...props
}: ButtonProps) {
  const variantClass =
    variant === 'control'
      ? 'ui-button-control'
      : variant === 'nav'
        ? 'ui-button-nav'
        : variant === 'link'
          ? 'ui-button-link'
          : variant === 'primary'
            ? 'ui-button-primary'
            : variant === 'destructive'
              ? 'ui-button-destructive'
              : '';
  const classes = cn('ui-button', variantClass, controlSizeClasses(size, icon), className);

  return <button type={type} className={classes} {...props} />;
}
