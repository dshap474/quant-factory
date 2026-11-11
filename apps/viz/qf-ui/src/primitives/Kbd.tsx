/**
 * Inline keyboard hint: a square hairline keycap in mono 2xs, plus a group wrapper for combos.
 *
 * USAGE:
 *   <Kbd>Esc</Kbd>
 *   <KbdGroup>
 *     <Kbd>⌘</Kbd>
 *     <Kbd>K</Kbd>
 *   </KbdGroup>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentPropsWithRef } from 'react';

import { cn } from '../lib/cn';

import './Kbd.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type KbdProps = ComponentPropsWithRef<'kbd'>;
export type KbdGroupProps = ComponentPropsWithRef<'kbd'>;

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function Kbd({ className, ...props }: KbdProps) {
  return <kbd className={cn('ui-kbd', className)} {...props} />;
}

/** Wraps several `Kbd` keys; nested `<kbd>` is the HTML idiom for key combos. */
export function KbdGroup({ className, ...props }: KbdGroupProps) {
  return <kbd className={cn('ui-kbd-group', className)} {...props} />;
}
