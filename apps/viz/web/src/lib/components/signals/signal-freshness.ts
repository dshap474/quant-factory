/**
 * Prediction-clock model for the signals pages.
 *
 * A signal is stale when its newest *prediction* is old, not when its newest *run* is old:
 * a runner that fired last night over three-month-old inputs looks healthy by run time and
 * is useless by prediction time. Everything here reads the prediction clock.
 *
 * All comparisons are UTC calendar days, so a run and a reader in different timezones agree.
 *
 * USAGE:
 *   isStalePrediction(signal.latest_prediction);            // true when older than 7 days
 *   formatPredictionDay(signal.latest_prediction);          // "2024-06-26" | "-"
 *   formatPredictionRange(run.first_prediction, run.latest_prediction);  // "2024-01-02 → 2024-06-28"
 */

// --------------------------------------------------------------------------- #
// Contract
// --------------------------------------------------------------------------- #

/** Days a prediction history may trail today before the UI calls it stale. */
export const STALE_AFTER_DAYS = 7;

const MS_PER_DAY = 86_400_000;

// --------------------------------------------------------------------------- #
// Model
// --------------------------------------------------------------------------- #

/** Midnight-UTC epoch ms for the calendar day of an ISO timestamp, or null when unparseable. */
function utcDay(value: string | null | undefined): number | null {
  const day = value?.split('T')[0];
  if (!day) return null;
  const parts = day.split('-');
  if (parts.length !== 3) return null;
  const [year, month, date] = parts.map(Number);
  if (year === undefined || month === undefined || date === undefined) return null;
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(date)) return null;
  return Date.UTC(year, month - 1, date);
}

/**
 * Whole UTC days between a prediction date and `now`, or null when there is no date.
 *
 * Negative when the history runs ahead of today, which a forward-looking horizon can do.
 */
export function predictionAgeDays(
  latestPrediction: string | null | undefined,
  now: Date = new Date(),
): number | null {
  const day = utcDay(latestPrediction);
  if (day === null) return null;
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.round((today - day) / MS_PER_DAY);
}

/**
 * True when the newest prediction is more than `STALE_AFTER_DAYS` old.
 *
 * A missing date is unknown, not stale: signals with no date column are not accused.
 */
export function isStalePrediction(
  latestPrediction: string | null | undefined,
  now: Date = new Date(),
): boolean {
  const age = predictionAgeDays(latestPrediction, now);
  return age !== null && age > STALE_AFTER_DAYS;
}

// --------------------------------------------------------------------------- #
// Formatting
// --------------------------------------------------------------------------- #

/** The calendar day of an ISO timestamp, or `-` when absent. */
export function formatPredictionDay(value: string | null | undefined): string {
  return value?.split('T')[0] ?? '-';
}

/** `first → last` when both ends exist, a single day when they match, else null. */
export function formatPredictionRange(
  first: string | null | undefined,
  last: string | null | undefined,
): string | null {
  const start = first?.split('T')[0];
  const end = last?.split('T')[0];
  if (!start || !end) return null;
  return start === end ? start : `${start} → ${end}`;
}
