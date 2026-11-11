/**
 * Key/value description list on semantic `dl` / `dt` / `dd` markup. Labels are muted mono;
 * values are foreground and, when numeric, right-aligned tabular mono. A value can carry a
 * `Tone` for gain/loss colouring.
 *
 * USAGE:
 *   <DataList orientation="horizontal" divided items={[
 *     { label: 'Sharpe', value: '1.42', numeric: true },
 *     { label: 'Return', value: '+4.1%', numeric: true, tone: 'success' },
 *   ]} />
 *
 *   <DataList orientation="vertical">
 *     <DataList.Item>
 *       <DataList.Label>Volatility</DataList.Label>
 *       <DataList.Value numeric>42.1%</DataList.Value>
 *     </DataList.Item>
 *   </DataList>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentPropsWithRef, ReactNode } from 'react';

import { cn } from '../lib/cn';
import { type Tone, toneTextClass } from '../lib/tone';

import './DataList.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type DataListOrientation = 'horizontal' | 'vertical';

export interface DataListEntry {
  label: ReactNode;
  value: ReactNode;
  /** Right-align the value in tabular mono. */
  numeric?: boolean;
  /** Colour the value with a tone text token. */
  tone?: Tone;
  /** Stable key; defaults to the label when it is a string, else the index. */
  id?: string;
}

export interface DataListProps extends ComponentPropsWithRef<'dl'> {
  /** Data-driven entries, rendered before any children. */
  items?: readonly DataListEntry[];
  /** `vertical` stacks label over value; `horizontal` puts them side by side. */
  orientation?: DataListOrientation;
  /** Draw a hairline between entries. */
  divided?: boolean;
}

export type DataListItemProps = ComponentPropsWithRef<'div'>;

export type DataListLabelProps = ComponentPropsWithRef<'dt'>;

export interface DataListValueProps extends ComponentPropsWithRef<'dd'> {
  /** Right-align the value in tabular mono. */
  numeric?: boolean;
  /** Colour the value with a tone text token. */
  tone?: Tone;
}

// --------------------------------------------------------------------------- #
// Parts
// --------------------------------------------------------------------------- #

/** Groups one `dt` / `dd` pair; a `div` wrapper is valid inside `dl`. */
export function DataListItem({ className, ...props }: DataListItemProps) {
  return <div className={cn('ui-data-list-item', className)} {...props} />;
}

export function DataListLabel({ className, ...props }: DataListLabelProps) {
  return <dt className={cn('ui-data-list-label', className)} {...props} />;
}

export function DataListValue({ numeric = false, tone, className, ...props }: DataListValueProps) {
  return (
    <dd
      className={cn('ui-data-list-value', tone && toneTextClass(tone), className)}
      data-numeric={numeric ? '' : undefined}
      {...props}
    />
  );
}

// --------------------------------------------------------------------------- #
// Root
// --------------------------------------------------------------------------- #

function DataListRoot({
  items,
  orientation = 'vertical',
  divided = false,
  className,
  children,
  ...props
}: DataListProps) {
  return (
    <dl
      className={cn('ui-data-list', className)}
      data-orientation={orientation}
      data-divided={divided ? '' : undefined}
      {...props}
    >
      {items?.map((entry, index) => (
        <DataListItem key={entry.id ?? (typeof entry.label === 'string' ? entry.label : index)}>
          <DataListLabel>{entry.label}</DataListLabel>
          <DataListValue
            numeric={entry.numeric ?? false}
            {...(entry.tone ? { tone: entry.tone } : {})}
          >
            {entry.value}
          </DataListValue>
        </DataListItem>
      ))}
      {children}
    </dl>
  );
}

export const DataList = Object.assign(DataListRoot, {
  Item: DataListItem,
  Label: DataListLabel,
  Value: DataListValue,
});
