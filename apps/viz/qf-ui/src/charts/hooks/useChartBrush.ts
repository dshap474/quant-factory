/**
 * Controlled date-domain brush state that preserves the full source domain.
 *
 * USAGE:
 *   const brush = useChartBrush(points);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useEffect, useRef, useState } from 'react';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function filterWithPadding<T extends { date: Date }>(
  data: readonly T[],
  domain: readonly [Date, Date],
): T[] {
  const [low, high] = domain;
  let start = 0;
  let end = data.length - 1;
  for (let index = 0; index < data.length; index += 1) {
    const point = data[index];
    if (point && point.date >= low) {
      start = Math.max(0, index - 1);
      break;
    }
  }
  for (let index = data.length - 1; index >= 0; index -= 1) {
    const point = data[index];
    if (point && point.date <= high) {
      end = Math.min(data.length - 1, index + 1);
      break;
    }
  }
  return data.slice(start, end + 1);
}

function extentKey(data: readonly { date: Date }[]): string {
  if (data.length === 0) return '';
  return `${data.length}:${data[0]?.date.getTime() ?? 0}:${data.at(-1)?.date.getTime() ?? 0}`;
}

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export function useChartBrush<T extends { date: Date }>(data: readonly T[]) {
  const [xDomain, setXDomain] = useState<[Date, Date] | undefined>();
  const key = extentKey(data);
  const previousKey = useRef(key);
  useEffect(() => {
    if (previousKey.current === key) return;
    previousKey.current = key;
    setXDomain(undefined);
  }, [key]);
  return {
    fullDomain: data.length > 0 ? ([data[0]?.date, data.at(-1)?.date] as const) : undefined,
    xDomain,
    visibleData: xDomain ? filterWithPadding(data, xDomain) : [...data],
    filterToRange: <U extends { date: Date }>(values: readonly U[]) =>
      xDomain ? filterWithPadding(values, xDomain) : [...values],
    setDomain: setXDomain,
  };
}
