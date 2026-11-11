/**
 * Selectable list: rows of rich content where one is the current selection, for a list beside the
 * detail of what is selected (runs, jobs, alerts). Rows are inset pills on the shared selection
 * recipe: hover --color-state-hover, press --color-state-pressed, the selected row --color-state-selected.
 * A row reads leading slot, one-line title and unwrapped meta, then a one-line description and any
 * children (e.g. a third line or a ProgressBar); the title and description truncate rather than wrap.
 * Lines under the title start under it, so they align flush when there is no leading slot.
 *
 * USAGE:
 *   <SelectList label="Runs">
 *     <SelectList.Group title="Running">
 *       <SelectList.Item
 *         selected={id === current}
 *         onSelect={() => setCurrent(id)}
 *         leading={<StatusDot tone="info" />}
 *         title="daily bars backfill"
 *         meta="40%"
 *         description="example-source · 2024-01:2024-12"
 *       >
 *         <ProgressBar value={4} max={10} label="assets" />
 *       </SelectList.Item>
 *     </SelectList.Group>
 *   </SelectList>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

import './SelectList.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SelectListProps {
  /** Accessible name of the list. */
  label: string;
  className?: string;
  children: ReactNode;
}

export interface SelectListGroupProps {
  /** Overline above the group's rows; the group renders nothing when it has no rows. */
  title: ReactNode;
  /** Shown after the title, e.g. a count. */
  meta?: ReactNode;
  children: ReactNode;
}

export interface SelectListItemProps {
  selected?: boolean;
  onSelect: () => void;
  /** Before the title, e.g. a StatusDot. */
  leading?: ReactNode;
  title: ReactNode;
  /** Right of the title in tabular figures, e.g. a percent or a relative time. */
  meta?: ReactNode;
  /** One muted line under the title. */
  description?: ReactNode;
  /** Under the description, e.g. a ProgressBar. */
  children?: ReactNode;
}

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

function SelectListRoot({ label, className, children }: SelectListProps) {
  return (
    <nav aria-label={label} className={cn('ui-select-list', className)}>
      {children}
    </nav>
  );
}

function SelectListGroup({ title, meta, children }: SelectListGroupProps) {
  const rows = Array.isArray(children) ? children.filter(Boolean) : children ? [children] : [];
  if (rows.length === 0) return null;
  return (
    <section className="ui-select-list-group">
      <header className="ui-select-list-title">
        <span>{title}</span>
        {meta == null ? null : <span className="ui-select-list-meta">{meta}</span>}
      </header>
      <ul className="ui-select-list-rows">{rows}</ul>
    </section>
  );
}

function SelectListItem({
  selected = false,
  onSelect,
  leading,
  title,
  meta,
  description,
  children,
}: SelectListItemProps) {
  return (
    <li>
      <button
        type="button"
        aria-current={selected ? 'true' : undefined}
        className={cn(
          'ui-select-list-row',
          selected && 'is-selected',
          leading != null && 'has-leading',
        )}
        onClick={onSelect}
      >
        <span className="ui-select-list-head">
          {leading == null ? null : <span className="ui-select-list-leading">{leading}</span>}
          <span className="ui-select-list-name">{title}</span>
          {meta == null ? null : <span className="ui-select-list-figure">{meta}</span>}
        </span>
        {description == null ? null : (
          <span className="ui-select-list-description">{description}</span>
        )}
        {children == null ? null : <span className="ui-select-list-extra">{children}</span>}
      </button>
    </li>
  );
}

export const SelectList = Object.assign(SelectListRoot, {
  Group: SelectListGroup,
  Item: SelectListItem,
});
