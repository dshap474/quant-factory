/**
 * Generic accessible chart tooltip chrome.
 *
 * USAGE:
 *   <ChartTooltip date={date} items={[{ label: 'IC', value: '0.12' }]} />
 *   <ChartTooltipItems items={items} detail="net of fees" />   // rows without the date header
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { formatTooltipDate } from '../charts/timeAxisFormat';
import { escapeHtml } from '../utils/escapeHtml';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartTooltipItem {
  label?: string;
  value: string;
  swatch?: string;
  positive?: boolean;
  negative?: boolean;
}

export interface ChartTooltipItemsProps {
  items: readonly ChartTooltipItem[];
  detail?: string;
}

export interface ChartTooltipProps extends ChartTooltipItemsProps {
  date: Date;
}

export interface ChartTooltipHtmlOptions {
  date: string;
  items: readonly ChartTooltipItem[];
  detail?: string;
}

// --------------------------------------------------------------------------- #
// HTML formatter
// --------------------------------------------------------------------------- #

export function chartTooltipHtml({ date, items, detail }: ChartTooltipHtmlOptions): string {
  const rows = items
    .map((item) => {
      const swatch = item.swatch
        ? `<span class="tooltip-swatch" style="--tooltip-swatch:${escapeHtml(item.swatch)}"></span>`
        : '';
      const label = item.label
        ? `<span class="tooltip-label">${escapeHtml(item.label)}</span>`
        : '';
      return `<div class="tooltip-row"><div class="tooltip-label-group">${swatch}${label}</div><div class="tooltip-value">${escapeHtml(item.value)}</div></div>`;
    })
    .join('');
  const detailHtml = detail ? `<div class="tooltip-detail">${escapeHtml(detail)}</div>` : '';
  return `<div class="qf-echarts-tooltip"><div class="tooltip-date">${escapeHtml(date)}</div><div class="tooltip-items">${rows}</div>${detailHtml}</div>`;
}

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

/** The value rows and optional detail line; hosts add their own date header around it. */
export function ChartTooltipItems({ items, detail }: ChartTooltipItemsProps) {
  return (
    <>
      <div className="tooltip-items">
        {items.map((item) => (
          <div className="tooltip-row" key={`${item.label ?? 'item'}-${item.value}`}>
            <div className="tooltip-label-group">
              {item.swatch ? (
                <span
                  className="tooltip-swatch"
                  style={{ ['--tooltip-swatch' as string]: item.swatch }}
                />
              ) : null}
              {item.label ? <span className="tooltip-label">{item.label}</span> : null}
            </div>
            <div
              className={[
                'tooltip-value',
                item.positive ? 'positive' : '',
                item.negative ? 'negative' : '',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              {item.value}
            </div>
          </div>
        ))}
      </div>
      {detail ? <div className="tooltip-detail">{detail}</div> : null}
    </>
  );
}

export function ChartTooltip({ date, items, detail }: ChartTooltipProps) {
  return (
    <div className="tooltip" role="status">
      <div className="tooltip-date">{formatTooltipDate(date)}</div>
      <ChartTooltipItems items={items} {...(detail === undefined ? {} : { detail })} />
    </div>
  );
}
