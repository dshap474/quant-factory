/**
 * Faceted table filter: a dashed control button that opens a checklist of values with counts,
 * showing the active selection on the button itself. Selecting nothing means "no filter".
 *
 * USAGE:
 *   <FacetedFilter
 *     title="Status"
 *     options={[{ value: 'active', label: 'Active', count: 12 }]}
 *     selected={statuses}
 *     onSelectedChange={setStatuses}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { CirclePlus } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '../lib/cn';
import { ICON_SIZE_SM, ICON_STROKE } from '../lib/icon';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../overlay/DropdownMenu';
import { Badge } from '../primitives/Badge';
import { Button } from '../primitives/Button';
import type { ControlSize } from '../primitives/control-size';

import './FacetedFilter.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface FacetedFilterOption<T extends string> {
  value: T;
  label: ReactNode;
  /** Rows carrying this value; shown right-aligned in the list. */
  count?: number;
}

export interface FacetedFilterProps<T extends string> {
  /** Facet name on the button and the list heading. */
  title: string;
  options: ReadonlyArray<FacetedFilterOption<T>>;
  selected: readonly T[];
  onSelectedChange: (selected: T[]) => void;
  /** Up to this many selected labels show on the button; more collapse to "n selected". Default 2. */
  maxLabels?: number;
  size?: ControlSize;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function FacetedFilter<T extends string>({
  title,
  options,
  selected,
  onSelectedChange,
  maxLabels = 2,
  size = 'sm',
  className,
}: FacetedFilterProps<T>) {
  const chosen = new Set(selected);
  const active = options.filter((option) => chosen.has(option.value));
  const toggle = (value: T, on: boolean) =>
    onSelectedChange(
      options
        .map((option) => option.value)
        .filter((item) => (item === value ? on : chosen.has(item))),
    );
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="control"
            size={size}
            className={cn('ui-faceted-trigger', className)}
            aria-label={`${title} filter${active.length ? `, ${active.length} selected` : ''}`}
          />
        }
      >
        <CirclePlus aria-hidden="true" size={ICON_SIZE_SM} strokeWidth={ICON_STROKE} />
        {title}
        {active.length ? (
          <span className="ui-faceted-selection">
            {active.length > maxLabels ? (
              <Badge size="sm" variant="ghost">{`${active.length} selected`}</Badge>
            ) : (
              active.map((option) => (
                <Badge key={option.value} size="sm" variant="ghost">
                  {option.label}
                </Badge>
              ))
            )}
          </span>
        ) : null}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuLabel>{title}</DropdownMenuLabel>
        {options.map((option) => (
          <DropdownMenuCheckboxItem
            key={option.value}
            checked={chosen.has(option.value)}
            onCheckedChange={(on) => toggle(option.value, on)}
          >
            <span className="ui-faceted-label">{option.label}</span>
            {option.count === undefined ? null : (
              <span className="ui-faceted-count">{option.count.toLocaleString()}</span>
            )}
          </DropdownMenuCheckboxItem>
        ))}
        {active.length ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => onSelectedChange([])}>Clear filter</DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
