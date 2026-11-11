/**
 * Value-to-text rendering for the public `QfSeries.valueFormat` contract.
 *
 * USAGE:
 *   formatQfValue(0.0123, 'percent'); // "1.2300%"
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { QfValueFormat } from '../types/contracts';
import { formatTooltipValue } from './multiSeriesModel';

// --------------------------------------------------------------------------- #
// Formatting
// --------------------------------------------------------------------------- #

/** Renders a series value with its declared format; unset formats fall back to `number`. */
export function formatQfValue(value: number, format: QfValueFormat = 'number'): string {
  if (typeof format === 'function') return format(value);
  if (format === 'integer') return Math.round(value).toLocaleString();
  if (format === 'percent') return formatTooltipValue(value, 'percent');
  if (format === 'currency') return formatTooltipValue(value, 'money');
  return formatTooltipValue(value, 'number');
}
