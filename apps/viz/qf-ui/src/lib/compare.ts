/**
 * Natural ordering for display strings: digit runs compare as numbers, so `v10`
 * follows `v9` and `file2` precedes `file10`; case and accents are ignored.
 *
 * USAGE:
 *   versions.sort(compareNatural);                     // v001, v002, v010
 *   versions.sort((a, b) => compareNatural(b, a));     // newest first
 */

// --------------------------------------------------------------------------- #
// Comparator
// --------------------------------------------------------------------------- #

const NATURAL = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

/** Ascending natural comparison of two strings. */
export function compareNatural(left: string, right: string): number {
  return NATURAL.compare(left, right);
}
