/**
 * Middle truncation for ids, hashes, addresses and mints: keep the head and the
 * tail around one ellipsis. The standard is 8 leading and 6 trailing characters
 * (what `<Identifier truncate="middle">` renders); values no longer than
 * head + tail + 2 stay whole, since cutting them would save almost nothing.
 *
 * USAGE:
 *   truncateMiddle('0x8f3c2a91d04e7b55c1aa');            // '0x8f3c2a…55c1aa'
 *   truncateMiddle(runId, { head: 13, tail: 10 });
 */

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TruncateMiddleOptions {
  /** Leading characters kept. Defaults to 8. */
  head?: number;
  /** Trailing characters kept. Defaults to 6. */
  tail?: number;
}

// --------------------------------------------------------------------------- #
// Truncation
// --------------------------------------------------------------------------- #

export const TRUNCATE_MIDDLE_HEAD = 8;
export const TRUNCATE_MIDDLE_TAIL = 6;

/** Whether `truncateMiddle` would shorten `value` with these lengths. */
export function isMiddleTruncated(value: string, options: TruncateMiddleOptions = {}): boolean {
  const { head = TRUNCATE_MIDDLE_HEAD, tail = TRUNCATE_MIDDLE_TAIL } = options;
  return value.length > head + tail + 2;
}

/** `head…tail` for long values; shorter values come back unchanged. */
export function truncateMiddle(value: string, options: TruncateMiddleOptions = {}): string {
  const { head = TRUNCATE_MIDDLE_HEAD, tail = TRUNCATE_MIDDLE_TAIL } = options;
  if (!isMiddleTruncated(value, options)) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}
