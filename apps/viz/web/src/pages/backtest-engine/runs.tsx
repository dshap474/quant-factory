/**
 * Shared Backtest Engine run presentation: the run and update-job state badge, and price
 * label precision.
 *
 * USAGE:
 *   <RunStateBadge state={run.state} />
 *   formatLocalePrice(price, priceDigits(price))
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { humanize, liveStatusTone, StatusBadge } from '@/ui';

// --------------------------------------------------------------------------- #
// Run presentation
// --------------------------------------------------------------------------- #

export function RunStateBadge({ state }: { state: string }) {
  return (
    <StatusBadge status={state} tone={liveStatusTone(state)}>
      {humanize(state)}
    </StatusBadge>
  );
}

/** Decimals that keep about five significant digits of a price. */
export function priceDigits(price: number | null | undefined): number {
  if (!price || price <= 0) return 2;
  return Math.max(0, Math.min(8, 4 - Math.floor(Math.log10(price))));
}
