/**
 * Shared semantic table primitives for application data.
 *
 * USAGE:
 *   <Table>
 *     <TableHeader>
 *       <TableRow><TableHead>Name</TableHead><TableHead numeric>Close</TableHead></TableRow>
 *     </TableHeader>
 *     <TableBody>
 *       <TableRow aria-selected><TableCell>BTC</TableCell><TableCell numeric>0.12</TableCell></TableRow>
 *       <TableRow><TableCell wrap>{longNote}</TableCell></TableRow>
 *       <TableRow><TableCell detail="example">Strategy optimizer</TableCell></TableRow>
 *     </TableBody>
 *   </Table>
 *
 *   <TableRow><TableCell><TableRowLink to={href}>{name}</TableRowLink></TableCell>…</TableRow>
 *
 *   <Table density="dense">…</Table>
 *   <TableHeader sticky>…</TableHeader>   // pinned head inside a bounded ScrollArea
 *
 * `numeric` right-aligns a column; numeric cells also take tabular figures through
 * `data-numeric`. Cells are one line, capped at 24rem with an ellipsis; `wrap` opts a prose
 * cell into wrapping. `detail` puts a muted secondary value on the same line after the
 * primary content (ellipsized, with the full string as its title), so a name-plus-detail
 * cell keeps the one-line row. Controls inside a cell drop one size step (28, or 24 dense)
 * so they sit inside the row. Rows with `aria-selected` take the selected surface. `density="dense"`
 * Every body shares subtle alternating rows and the same hover/selection colors. Table
 * containers use the shared surface radius. Indexed bodies use `data-indexed-rows` with per-row `data-zebra`
 * markers to keep parity stable through virtualization; group captions use `data-table-group`.
 * `TableRowLink` makes the whole row its click target while staying a real link (new-tab
 * clicks, keyboard focus); other controls in that row stay clickable above it.
 * `density="dense"` sets the compact reference-table scale: smaller type and 28px rows. `heat` tints a cell
 * on the shared heat scale (`divergingCellColor`): `<TableCell numeric heat={{ value, maxAbs }}>`.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentPropsWithRef, ReactNode } from 'react';

import { trackScrollEdges } from '../../layout/ScrollArea';
import { cn } from '../../lib/cn';
import { type CellHeat, divergingCellColor } from '../../lib/heat';
import { Link, type LinkProps } from '../../primitives/Link';

import '../../primitives/Surface.css';
import './Table.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type TableDensity = 'default' | 'dense';

export interface TableProps extends ComponentPropsWithRef<'table'> {
  /** `dense`: compact reference-table scale (smaller type, tighter rows). */
  density?: TableDensity;
}

export interface TableHeadProps extends ComponentPropsWithRef<'th'> {
  /** Right-align the column (numbers, prices, counts). */
  numeric?: boolean;
}

export interface TableHeaderProps extends ComponentPropsWithRef<'thead'> {
  /** Pin the header row while the host ScrollArea scrolls; cells take the card background. */
  sticky?: boolean;
}

export interface TableCellProps extends ComponentPropsWithRef<'td'> {
  /** Right-align and set in tabular figures. */
  numeric?: boolean;
  /** Prose cell: wrap instead of the one-line ellipsis. Never forwarded to the DOM. */
  wrap?: boolean;
  /**
   * Secondary value on the same line after the children, muted and ellipsized. A string
   * detail is also its own title, so truncated text stays reachable on hover.
   */
  detail?: ReactNode;
  /** Tint the cell on the shared heat scale; a missing value leaves it untinted. */
  heat?: CellHeat;
  /** Full-width nested content. Mark its parent row `data-table-group` to exclude striping. */
  fullBleed?: boolean;
}

export type TableRowLinkProps = Omit<LinkProps, 'variant' | 'size' | 'icon' | 'href'> & {
  /** In-app route the row opens. */
  to: string;
};

export type TableMarkupCleanup = () => void;

// --------------------------------------------------------------------------- #
// Sanitized markup adapter
// --------------------------------------------------------------------------- #

/** A cell that reads as one quantity: 1,250 · −0.42 · 12.5% · $3.2bn · 1.8x · (0.3) · 5–10. */
const NUMERIC_CELL =
  /^[(+\-−±~≈<>≤≥]?\s?[$€£]?\d[\d,.]*(?:\s?[–-]\s?\d[\d,.]*)?\s?(?:%|bps?|pp|x|×|[kKMB]|bn|mn)?\)?\*?$/;

/** Columns whose every non-empty body cell is numeric, so the column aligns right. */
function numericColumns(table: HTMLTableElement): Set<number> {
  const counts = new Map<number, { numeric: number; total: number }>();
  for (const body of table.tBodies) {
    for (const row of body.rows) {
      for (const cell of row.cells) {
        const text = (cell.textContent ?? '').trim();
        if (!text || text === '—' || text === '-') continue;
        const count = counts.get(cell.cellIndex) ?? { numeric: 0, total: 0 };
        count.total += 1;
        if (NUMERIC_CELL.test(text) && !cell.querySelector('.qf-math')) count.numeric += 1;
        counts.set(cell.cellIndex, count);
      }
    }
  }
  const columns = new Set<number>();
  for (const [index, count] of counts) {
    if (count.total > 0 && count.numeric === count.total) columns.add(index);
  }
  return columns;
}

/** Apply the same recipes to already-sanitized HTML (for example, Markdown tables).
 * Call after inserting the markup into the document; dispose when replacing it.
 * USAGE: const dispose = enhanceTableMarkup(article); return dispose;
 * This styles existing DOM only; the host must sanitize untrusted content first. */
export function enhanceTableMarkup(root: ParentNode): TableMarkupCleanup {
  const cleanups: TableMarkupCleanup[] = [];
  for (const table of root.querySelectorAll<HTMLTableElement>('table:not(.ui-table)')) {
    table.classList.add('ui-table', 'caption-bottom', 'text-body');
    table.tHead?.classList.add('ui-table-header');
    for (const body of table.tBodies) body.classList.add('ui-table-body');
    const numeric = numericColumns(table);
    for (const row of table.rows) {
      row.classList.add('ui-table-row');
      for (const cell of row.cells) {
        const head = cell.tagName === 'TH';
        cell.classList.add(head ? 'ui-table-head' : 'ui-table-cell', 'is-wrap');
        const alignment = cell.getAttribute('align');
        if (alignment === 'left' || alignment === 'center' || alignment === 'right') {
          cell.style.textAlign = alignment;
        } else if (numeric.has(cell.cellIndex)) {
          cell.classList.add('text-right');
          if (head) cell.classList.add('is-numeric');
          else cell.dataset.numeric = '';
        }
      }
    }
    const frame = table.ownerDocument.createElement('div');
    frame.className = 'ui-surface ui-surface-clip ui-table-markup-frame';
    const scroll = table.ownerDocument.createElement('div');
    scroll.className = 'ui-scroll-area is-x';
    scroll.tabIndex = 0;
    scroll.setAttribute('role', 'region');
    scroll.setAttribute('aria-label', table.caption?.textContent?.trim() || 'Scrollable table');
    table.before(frame);
    frame.append(scroll);
    scroll.append(table);
    cleanups.push(trackScrollEdges(scroll));
  }
  return () => {
    for (const cleanup of cleanups) cleanup();
  };
}

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function Table({ density = 'default', className, ...props }: TableProps) {
  const dense = density === 'dense';
  return (
    <table
      className={cn(
        'ui-table caption-bottom',
        dense ? 'text-caption' : 'text-body',
        dense && 'is-dense',
        className,
      )}
      {...props}
    />
  );
}

export function TableHeader({ sticky = false, className, ...props }: TableHeaderProps) {
  return (
    <thead
      className={cn('ui-table-header', sticky && 'ui-table-sticky-head', className)}
      {...props}
    />
  );
}

export function TableBody({ className, ...props }: ComponentPropsWithRef<'tbody'>) {
  return <tbody className={cn('ui-table-body', className)} {...props} />;
}

export function TableRow({ className, ...props }: ComponentPropsWithRef<'tr'>) {
  return <tr className={cn('ui-table-row', className)} {...props} />;
}

/** The row's primary link, stretched over the whole row. One per row. */
export function TableRowLink({ className, ...props }: TableRowLinkProps) {
  return <Link variant="subtle" className={cn('ui-table-row-link', className)} {...props} />;
}

export function TableHead({ numeric = false, className, ...props }: TableHeadProps) {
  return (
    <th
      className={cn('ui-table-head', numeric ? 'is-numeric text-right' : 'text-left', className)}
      {...props}
    />
  );
}

export function TableCell({
  numeric = false,
  wrap = false,
  detail,
  heat,
  fullBleed = false,
  className,
  style,
  children,
  ...props
}: TableCellProps) {
  const hasDetail = detail !== undefined && detail !== null && detail !== false && detail !== '';
  const heatStyle = heat ? { ...style, background: divergingCellColor(heat.value, heat) } : style;
  return (
    <td
      className={cn(
        'ui-table-cell',
        numeric && 'text-right',
        wrap && 'is-wrap',
        fullBleed && 'is-full-bleed',
        className,
      )}
      data-numeric={numeric ? '' : undefined}
      style={heatStyle}
      {...props}
    >
      {hasDetail ? (
        <span className="ui-table-cell-line">
          <span className="ui-table-cell-primary">{children}</span>
          <span
            className="ui-table-cell-detail"
            title={typeof detail === 'string' ? detail : undefined}
          >
            {detail}
          </span>
        </span>
      ) : (
        children
      )}
    </td>
  );
}
