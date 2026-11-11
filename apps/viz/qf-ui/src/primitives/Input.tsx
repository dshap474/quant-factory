/**
 * Shared text-input primitive for consistent focus, sizing, and disabled states.
 *
 * USAGE:
 *   <Input type="search" value={query} onChange={handleChange} />
 *   <Input size="sm" placeholder="filter" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentPropsWithRef } from 'react';

import { cn } from '../lib/cn';
import { type ControlSize, controlSizeClass } from './control-size';

import './Input.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface InputProps extends Omit<ComponentPropsWithRef<'input'>, 'size'> {
  /** Height step from the control-size scale (replaces the numeric HTML `size`). Default `md`. */
  size?: ControlSize;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Input({ size, className, ...props }: InputProps) {
  return <input className={cn('ui-input', controlSizeClass(size), className)} {...props} />;
}
