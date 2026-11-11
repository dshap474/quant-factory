import { describe, expect, it } from 'vitest';

import {
  formatPredictionDay,
  formatPredictionRange,
  isStalePrediction,
  predictionAgeDays,
  STALE_AFTER_DAYS,
} from './signal-freshness';

const NOW = new Date('2026-09-01T04:00:00Z');

describe('predictionAgeDays', () => {
  it('counts whole UTC days regardless of the time of day', () => {
    expect(predictionAgeDays('2026-09-01T00:00:00', NOW)).toBe(0);
    expect(predictionAgeDays('2026-08-31T23:59:59', NOW)).toBe(1);
    expect(predictionAgeDays('2026-05-16T00:00:00', NOW)).toBe(108);
  });

  it('reports a bare date the same as a full timestamp', () => {
    expect(predictionAgeDays('2026-08-25', NOW)).toBe(
      predictionAgeDays('2026-08-25T12:00:00', NOW),
    );
  });

  it('is null when there is no parseable date', () => {
    expect(predictionAgeDays(null, NOW)).toBeNull();
    expect(predictionAgeDays(undefined, NOW)).toBeNull();
    expect(predictionAgeDays('', NOW)).toBeNull();
    expect(predictionAgeDays('not-a-date', NOW)).toBeNull();
  });
});

describe('isStalePrediction', () => {
  it('tolerates exactly the threshold and flags one day past it', () => {
    expect(predictionAgeDays('2026-08-25T00:00:00', NOW)).toBe(STALE_AFTER_DAYS);
    expect(isStalePrediction('2026-08-25T00:00:00', NOW)).toBe(false);
    expect(isStalePrediction('2026-08-24T00:00:00', NOW)).toBe(true);
  });

  it('flags a history months behind its inputs', () => {
    expect(isStalePrediction('2026-05-16T00:00:00', NOW)).toBe(true);
  });

  it('treats a missing date as unknown rather than stale', () => {
    expect(isStalePrediction(null, NOW)).toBe(false);
  });

  it('does not flag a forward-looking horizon', () => {
    expect(isStalePrediction('2026-11-30T00:00:00', NOW)).toBe(false);
  });
});

describe('formatting', () => {
  it('renders the calendar day, or a dash when absent', () => {
    expect(formatPredictionDay('2024-06-26T00:00:00')).toBe('2024-06-26');
    expect(formatPredictionDay(null)).toBe('-');
  });

  it('renders a range, collapses a single day, and needs both ends', () => {
    expect(formatPredictionRange('2024-01-02T00:00:00', '2024-06-28T00:00:00')).toBe(
      '2024-01-02 → 2024-06-28',
    );
    expect(formatPredictionRange('2024-06-28', '2024-06-28')).toBe('2024-06-28');
    expect(formatPredictionRange(null, '2024-06-28')).toBeNull();
    expect(formatPredictionRange('2024-06-28', null)).toBeNull();
  });
});
