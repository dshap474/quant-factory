/**
 * Odometer-style number: every digit is a clipped 0-9 reel that rolls vertically when the
 * value changes. With `flash` the number briefly tints success (rose) or critical (fell)
 * and fades back. Digits are tabular mono at 1ch, so nothing shifts. The rolling glyphs are
 * aria-hidden; screen readers get the full formatted value from a polite live region.
 * Reduced motion swaps instantly and never flashes.
 *
 * USAGE:
 *   <RollingNumber value={price} formatOptions={{ style: 'currency', currency: 'USD' }} />
 *   <RollingNumber value={count} format={(v) => `${v} items`} flash={false} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type ComponentPropsWithRef, useState } from 'react';

import { cn } from '../lib/cn';

import './RollingNumber.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type RollingNumberDirection = 'up' | 'down';

export interface RollingNumberProps extends Omit<ComponentPropsWithRef<'span'>, 'children'> {
  /** Number (or pre-formatted numeric string) to display. */
  value: number | string;
  /** Custom formatter; takes precedence over `formatOptions`. */
  format?: (value: number | string) => string;
  /** `Intl.NumberFormat` options applied to finite numeric values. */
  formatOptions?: Intl.NumberFormatOptions;
  /** Locale for `formatOptions`; defaults to the runtime locale. */
  locale?: string;
  /** Tint the number success/critical for a moment when it rises/falls. */
  flash?: boolean;
}

interface ChangeState {
  value: number | string;
  direction: RollingNumberDirection | null;
  tick: number;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const REEL_DIGITS = Array.from({ length: 10 }, (_, digit) => digit);
const DIGIT = /\d/;

function formatValue(
  value: number | string,
  format: RollingNumberProps['format'],
  formatOptions: Intl.NumberFormatOptions | undefined,
  locale: string | undefined,
): string {
  if (format) return format(value);
  if (formatOptions && typeof value === 'number' && Number.isFinite(value)) {
    return new Intl.NumberFormat(locale, formatOptions).format(value);
  }
  return String(value);
}

function directionOf(
  next: number | string,
  previous: number | string,
): RollingNumberDirection | null {
  const a = Number(next);
  const b = Number(previous);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  if (a > b) return 'up';
  if (a < b) return 'down';
  return null;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function RollingNumber({
  value,
  format,
  formatOptions,
  locale,
  flash = true,
  className,
  ...props
}: RollingNumberProps) {
  const [change, setChange] = useState<ChangeState>({ value, direction: null, tick: 0 });

  // Derive the change from the previous render's value (React's "adjust state on prop change").
  if (!Object.is(change.value, value)) {
    setChange({
      value,
      direction: directionOf(value, change.value),
      tick: change.tick + 1,
    });
  }

  const text = formatValue(value, format, formatOptions, locale);
  const chars = [...text];
  const flashing = flash && change.direction !== null;

  return (
    <span
      className={cn('ui-rolling-number', className)}
      data-direction={change.direction ?? undefined}
      data-flash={flashing ? (change.tick % 2 === 0 ? 'a' : 'b') : undefined}
      {...props}
    >
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {text}
      </span>
      <span className="ui-rolling-number-visual" aria-hidden="true">
        {chars.map((char, index) => {
          // Key from the right so place values keep their reel when the digit count changes.
          const key = chars.length - index;
          if (!DIGIT.test(char)) {
            return (
              <span key={key} className="ui-rolling-number-char">
                {char}
              </span>
            );
          }
          return (
            <span key={key} className="ui-rolling-number-digit" data-rolling-digit={char}>
              <span className="ui-rolling-number-ghost">0</span>
              <span
                className="ui-rolling-number-reel"
                style={{ transform: `translateY(-${char}em)` }}
              >
                {REEL_DIGITS.map((digit) => (
                  <span key={digit} className="ui-rolling-number-cell">
                    {digit}
                  </span>
                ))}
              </span>
            </span>
          );
        })}
      </span>
    </span>
  );
}
