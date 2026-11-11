/**
 * Categorical chart key: one swatch, name, and optional detail per category.
 *
 * Regime shading, classification bands, and other segment palettes describe categories,
 * not toggleable series, so the key is static and package-styled.
 *
 * USAGE:
 *   <MultiPaneTimeSeriesChart legend={<ChartKey ariaLabel="State key" items={STATES} />} … />
 *   <ChartKey items={items} emphasized={active} onEmphasizeChange={setActive} />
 *   <ChartKey items={chartKeyItems(chart.series)} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { chartPaletteColor } from '../theme/chartColor';

import './ChartKey.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartKeyItem {
  id: string;
  label: string;
  detail?: string;
  /** Any CSS color, typically a host chart token such as the host's `--color-chart-6`. */
  color: string;
  /** Native tooltip; defaults to label. */
  title?: string;
}

/** A plotted series as the key reads it: `key` is the item id, an absent colour takes the
    series' palette slot by position. */
export interface ChartKeySeries {
  key: string;
  label: string;
  color?: string | undefined;
}

/** Key items for plotted series, in order; uncoloured series take palette slots by index. */
export function chartKeyItems(series: readonly ChartKeySeries[]): ChartKeyItem[] {
  return series.map((item, index) => ({
    id: item.key,
    label: item.label,
    color: item.color ?? chartPaletteColor(index),
  }));
}

export interface ChartKeyProps {
  items: readonly ChartKeyItem[];
  /** Accessible name of the list. */
  ariaLabel?: string;
  /** Emphasized item id; the others dim. Only meaningful with onEmphasizeChange. */
  emphasized?: string | null;
  /**
   * Hover/focus emphasis. When given, each row renders as a button and the list clears
   * emphasis on pointer leave and on focus leaving the list.
   */
  onEmphasizeChange?: (id: string | null) => void;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ChartKey({
  items,
  ariaLabel = 'Chart key',
  emphasized,
  onEmphasizeChange,
  className,
}: ChartKeyProps) {
  const interactive = Boolean(onEmphasizeChange);
  const classes = ['qf-chart-key', interactive ? 'is-interactive' : '', className ?? '']
    .filter(Boolean)
    .join(' ');

  return (
    <ul
      className={classes}
      aria-label={ariaLabel}
      onPointerLeave={interactive ? () => onEmphasizeChange?.(null) : undefined}
      onBlur={
        interactive
          ? (event) => {
              if (!event.currentTarget.contains(event.relatedTarget)) onEmphasizeChange?.(null);
            }
          : undefined
      }
    >
      {items.map((item) => {
        const body = (
          <>
            <span className="qf-chart-key-swatch" aria-hidden="true" />
            <span className="qf-chart-key-text">
              <span className="qf-chart-key-name">{item.label}</span>
              {item.detail ? <span className="qf-chart-key-detail">{item.detail}</span> : null}
            </span>
          </>
        );
        const itemClasses = [
          'qf-chart-key-item',
          emphasized === item.id ? 'is-emphasized' : '',
          emphasized != null && emphasized !== item.id ? 'is-dimmed' : '',
        ]
          .filter(Boolean)
          .join(' ');
        return (
          <li
            className={itemClasses}
            key={item.id}
            style={{ ['--qf-chart-key-color' as string]: item.color }}
          >
            {interactive ? (
              <button
                type="button"
                className="qf-chart-key-button"
                title={item.title ?? item.label}
                onPointerEnter={() => onEmphasizeChange?.(item.id)}
                onFocus={() => onEmphasizeChange?.(item.id)}
              >
                {body}
              </button>
            ) : (
              body
            )}
          </li>
        );
      })}
    </ul>
  );
}
