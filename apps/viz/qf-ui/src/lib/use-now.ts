/**
 * A clock for live relative times: re-renders every `intervalMs` while `live`,
 * pauses while the tab is hidden, and returns the current epoch milliseconds.
 *
 * USAGE:
 *   const now = useNow({ live: run.status === 'running' });
 *   <RelativeTime value={run.started_at} now={now} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useEffect, useState } from 'react';

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export interface UseNowOptions {
  /** Tick while true; when false the last value holds. Defaults to true. */
  live?: boolean;
  /** Tick interval in ms. Defaults to 1000. */
  intervalMs?: number;
}

export function useNow({ live = true, intervalMs = 1_000 }: UseNowOptions = {}): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!live) return;
    setNow(Date.now());
    const timer = window.setInterval(() => {
      if (!document.hidden) setNow(Date.now());
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [live, intervalMs]);
  return now;
}
