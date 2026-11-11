/**
 * Minimal class-name combiner used by qf-ui components.
 *
 * USAGE:
 *   cn('base', active && 'active');
 */

// --------------------------------------------------------------------------- #
// Utility
// --------------------------------------------------------------------------- #

export function cn(...values: Array<false | null | string | undefined>): string {
  return values.filter(Boolean).join(' ');
}
