/**
 * Research version ordering shared by the Signals and Strategies navigators:
 * newest memory version first. Tag tones come straight from qf-ui `statusTone`.
 *
 * USAGE:
 *   versions.sort(compareVersionsDesc)
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { compareNatural } from '@/ui';

// --------------------------------------------------------------------------- #
// Ordering
// --------------------------------------------------------------------------- #

/** Newest memory version first (`v010` before `v009`). */
export function compareVersionsDesc(
  left: { memory_version: string },
  right: { memory_version: string },
): number {
  return compareNatural(right.memory_version, left.memory_version);
}
