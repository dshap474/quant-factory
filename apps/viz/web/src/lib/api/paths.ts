/**
 * Path encoding helpers for multi-segment lake-relative paths.
 *
 * USAGE:
 *   encodePath('a/b/c.parquet') // 'a/b/c.parquet' with each segment URI-encoded
 */

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Encode each path segment so spaces / special chars are safe; preserve `/` separators. */
export function encodePath(path: string): string {
  return path
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}
