/**
 * Shared metric comparison with aligned values and an optional signed difference.
 *
 * USAGE: <MetricComparisonTable columns={columns} rows={rows}
 *   difference={{ current: 'candidate', reference: 'control' }} />
 *   <MetricComparisonTable view="rank" columns={columns} rows={rowsWithRank} />
 *
 * Rank view replaces each value with `rank / N` (1 best) on a relative green-yellow-red
 * tint; a popover gives the compared raw value, direction, count and ties. Rows or cells
 * without a rank stay neutral and show an explained em dash.
 */

// --------------------------------------------------------------------------- #
// Imports and contract
// --------------------------------------------------------------------------- #

import { ScrollArea } from '../../layout/ScrollArea';
import { cn } from '../../lib/cn';
import { rankCellColor } from '../../lib/heat';
import { InfoTip } from '../../overlay/InfoTip';
import { Popover, PopoverContent, PopoverTrigger } from '../../overlay/Popover';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../primitives/Table';
import './MetricComparisonTable.css';

export type MetricFormat = 'number' | 'percent' | 'money' | 'text' | 'days';
export type MetricComparisonView = 'values' | 'rank';
export type MetricRankDirection = 'higher' | 'lower';
/** One cell's standing among `count` compared observations; rank 1 is best. */
export interface MetricRankCell {
  rank: number;
  count: number;
  /** Other observations sharing this exact value. */
  ties: number;
  /** 0 (best) to 1 (worst) at the tie midpoint; null colours the cell neutral. */
  position: number | null;
  /** The raw value the rank compares, which may differ from the Values view. */
  value: number;
}
export interface MetricRowRank {
  direction: MetricRankDirection;
  cells: Readonly<Record<string, MetricRankCell | null | undefined>>;
  /** Explains a column without a rank, e.g. an undefined ratio. */
  missingNote?: string;
}
export interface MetricComparisonColumn {
  id: string;
  label: string;
  detail?: string;
  color?: string;
  description?: string;
}
export interface MetricComparisonRow {
  key: string;
  label: string;
  format: MetricFormat;
  values: Readonly<Record<string, number | string | null | undefined>>;
  higherIsBetter?: boolean;
  /** Adjacent rows with the same group share a category band. */
  group?: string;
  description?: string;
  emphasis?: boolean;
  /** Standing per column, shown only in the rank view. */
  rank?: MetricRowRank;
}
export interface MetricComparisonTableProps {
  columns: readonly MetricComparisonColumn[];
  rows: readonly MetricComparisonRow[];
  difference?: { current: string; reference: string };
  caption?: string;
  className?: string;
  /** 'values' (default) shows recorded values; 'rank' shows each row's `rank`. */
  view?: MetricComparisonView;
  /** Rank view: explanation for rows that carry no rank. */
  unrankedNote?: string;
  /** Rank view: popover label for the compared raw value. */
  rankValueLabel?: string;
}

// --------------------------------------------------------------------------- #
// Formatting
// --------------------------------------------------------------------------- #

function displayValue(
  value: number | string | null | undefined,
  format: MetricFormat,
  delta = false,
): string {
  if (value == null || (typeof value === 'number' && !Number.isFinite(value))) return '—';
  if (typeof value === 'string' || format === 'text') return String(value);
  const sign = value < 0 ? '−' : delta && value > 0 ? '+' : '';
  const magnitude = Math.abs(value);
  if (format === 'percent') return `${sign}${(magnitude * 100).toFixed(2)}${delta ? ' pp' : '%'}`;
  if (format === 'days')
    return `${sign}${magnitude.toLocaleString(undefined, { maximumFractionDigits: 0 })} d`;
  if (format === 'money')
    return `${sign}$${magnitude.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return `${sign}${magnitude.toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 })}`;
}

// --------------------------------------------------------------------------- #
// Rank cells
// --------------------------------------------------------------------------- #

const DEFAULT_UNRANKED_NOTE = 'Not ranked: no comparable better or worse direction.';
const DEFAULT_MISSING_NOTE = 'Not ranked: undefined for this column.';

function NeutralRankCell({ note }: { note: string }) {
  return (
    <TableCell numeric className="metric-comparison-rank-missing" title={note}>
      <span aria-hidden="true">—</span>
      <span className="sr-only">{note}</span>
    </TableCell>
  );
}

function RankCell({
  row,
  column,
  cell,
  valueLabel,
}: {
  row: MetricComparisonRow;
  column: MetricComparisonColumn;
  cell: MetricRankCell;
  valueLabel: string;
}) {
  const standing = `${cell.rank} / ${cell.count}`;
  const tie =
    cell.ties > 0 ? `Tied with ${cell.ties} other${cell.ties === 1 ? '' : 's'}` : 'No ties';
  return (
    <TableCell
      numeric
      className="metric-comparison-rank"
      style={{ background: rankCellColor(cell.position) }}
    >
      <Popover>
        <PopoverTrigger
          type="button"
          className="metric-comparison-rank-trigger"
          aria-label={`${row.label}, ${column.label}: rank ${standing}`}
          openOnHover
          delay={200}
          closeDelay={100}
        >
          {standing}
        </PopoverTrigger>
        <PopoverContent className="ui-info-tip metric-comparison-rank-detail" side="top">
          <strong>
            Rank {standing} · {row.label}
          </strong>
          <span>
            {valueLabel}: {displayValue(cell.value, row.format)}
          </span>
          <span>
            {row.rank?.direction === 'lower' ? 'Lower is better' : 'Higher is better'} ·{' '}
            {cell.count} compared · {tie}
          </span>
        </PopoverContent>
      </Popover>
    </TableCell>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function MetricComparisonTable({
  columns,
  rows,
  difference,
  caption = 'Performance comparison',
  className,
  view = 'values',
  unrankedNote = DEFAULT_UNRANKED_NOTE,
  rankValueLabel = 'Compared value',
}: MetricComparisonTableProps) {
  const current = columns.find((column) => column.id === difference?.current);
  const reference = columns.find((column) => column.id === difference?.reference);
  const ranked = view === 'rank';
  const showDifference = !ranked && current !== undefined && reference !== undefined;
  const groups: { label: string | undefined; rows: MetricComparisonRow[] }[] = [];
  for (const row of rows) {
    const previous = groups.at(-1);
    if (previous && previous.label === row.group) previous.rows.push(row);
    else groups.push({ label: row.group, rows: [row] });
  }
  return (
    <section className={cn('metric-comparison', className)} aria-label={caption}>
      {/* The frame keeps its border; the region inside scrolls (focusable for keyboard
          users) and fades its clipped edge. */}
      <ScrollArea axis="x" tabIndex={0}>
        <Table>
          <caption className="sr-only">{caption}</caption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Metric</TableHead>
              {columns.map((column) => (
                <TableHead key={column.id} scope="col">
                  <span
                    className="metric-comparison-column"
                    title={column.description ?? column.label}
                  >
                    {column.color ? (
                      <span
                        className="metric-comparison-swatch"
                        style={{ background: column.color }}
                      />
                    ) : null}
                    <span>{column.label}</span>
                  </span>
                  {column.detail ? (
                    <span className="metric-comparison-detail">{column.detail}</span>
                  ) : null}
                </TableHead>
              ))}
              {showDifference ? (
                <TableHead scope="col" title={`${current.label} minus ${reference.label}`}>
                  Difference<span className="metric-comparison-detail">Current − comparison</span>
                </TableHead>
              ) : null}
            </TableRow>
          </TableHeader>
          {groups.map((group) => (
            <TableBody key={group.rows[0]?.key}>
              {group.label ? (
                <TableRow className="metric-comparison-group" data-table-group="">
                  <TableHead scope="rowgroup" colSpan={columns.length + 1 + Number(showDifference)}>
                    <span className="metric-comparison-group-label">{group.label}</span>
                  </TableHead>
                </TableRow>
              ) : null}
              {group.rows.map((row) => {
                const a = current ? row.values[current.id] : null;
                const b = reference ? row.values[reference.id] : null;
                const delta =
                  typeof a === 'number' && typeof b === 'number' && row.format !== 'text'
                    ? a - b
                    : null;
                const favorable =
                  delta == null || delta === 0 || row.higherIsBetter === undefined
                    ? null
                    : row.higherIsBetter
                      ? delta > 0
                      : delta < 0;
                return (
                  <TableRow
                    key={row.key}
                    className={row.emphasis ? 'metric-comparison-emphasis' : undefined}
                  >
                    <TableHead scope="row">
                      <span className="metric-comparison-label">
                        {row.label}
                        {row.description ? (
                          <InfoTip label={`About ${row.label}`} content={row.description} />
                        ) : null}
                      </span>
                    </TableHead>
                    {columns.map((column) => {
                      if (!ranked)
                        return (
                          <TableCell
                            key={column.id}
                            numeric={row.format !== 'text'}
                            wrap={row.format === 'text'}
                          >
                            {displayValue(row.values[column.id], row.format)}
                          </TableCell>
                        );
                      const cell = row.rank?.cells[column.id];
                      return cell ? (
                        <RankCell
                          key={column.id}
                          row={row}
                          column={column}
                          cell={cell}
                          valueLabel={rankValueLabel}
                        />
                      ) : (
                        <NeutralRankCell
                          key={column.id}
                          note={
                            row.rank ? (row.rank.missingNote ?? DEFAULT_MISSING_NOTE) : unrankedNote
                          }
                        />
                      );
                    })}
                    {showDifference ? (
                      <TableCell
                        className={
                          favorable == null ? '' : favorable ? 'text-positive' : 'text-negative'
                        }
                      >
                        {displayValue(delta, row.format, true)}
                      </TableCell>
                    ) : null}
                  </TableRow>
                );
              })}
            </TableBody>
          ))}
        </Table>
      </ScrollArea>
    </section>
  );
}
