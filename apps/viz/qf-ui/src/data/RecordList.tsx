/**
 * Renders a plain JSON record (for example a parsed TOML file) as a divided key/value
 * list. Nested tables flatten into dotted keys, labels are humanized (the raw key stays
 * on hover), and values print as recorded: numbers unrounded, booleans as yes/no,
 * primitive arrays comma-joined.
 *
 * USAGE:
 *   <RecordList record={{ status: 'supported', control_parity: true }} />
 *   <RecordList record={record} omit={['version', 'phase']} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentPropsWithRef } from 'react';

import { cn } from '../lib/cn';
import { humanize } from '../lib/humanize';
import { DataList } from './DataList';

import './RecordList.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface RecordListProps extends Omit<ComponentPropsWithRef<'dl'>, 'children'> {
  record: Readonly<Record<string, unknown>>;
  /** Top-level keys to leave out (shown elsewhere on the page). */
  omit?: readonly string[];
}

interface RecordRow {
  key: string;
  value: unknown;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function isTable(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function flatten(record: Readonly<Record<string, unknown>>, prefix = ''): RecordRow[] {
  return Object.entries(record).flatMap(([key, value]) =>
    isTable(value) ? flatten(value, `${prefix}${key}.`) : [{ key: `${prefix}${key}`, value }],
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (Array.isArray(value)) {
    return value.every((item) => item === null || typeof item !== 'object')
      ? value.map(formatValue).join(', ')
      : JSON.stringify(value);
  }
  return String(value);
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function RecordList({ record, omit = [], className, ...props }: RecordListProps) {
  const rows = flatten(record).filter((row) => !omit.includes(row.key));
  return (
    <DataList
      orientation="horizontal"
      divided
      className={cn('ui-record-list', className)}
      {...props}
    >
      {rows.map((row) => (
        <DataList.Item key={row.key}>
          <DataList.Label title={row.key}>
            {row.key.split('.').map(humanize).join(' · ')}
          </DataList.Label>
          <DataList.Value numeric={typeof row.value === 'number'}>
            {formatValue(row.value)}
          </DataList.Value>
        </DataList.Item>
      ))}
    </DataList>
  );
}
