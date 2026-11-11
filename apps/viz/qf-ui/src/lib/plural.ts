/**
 * English count nouns: the singular for exactly one, otherwise the plural
 * (`s` appended unless an irregular plural is given).
 *
 * USAGE:
 *   `${count} ${pluralize(count, 'run')}`                  // 1 run, 3 runs
 *   `${formatCount(n)} ${pluralize(n, 'entry', 'entries')}`
 */

// --------------------------------------------------------------------------- #
// Helper
// --------------------------------------------------------------------------- #

/** `singular` when `count` is 1, else `plural` (default `${singular}s`). */
export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return count === 1 ? singular : plural;
}
