/**
 * List-detail split: a fixed-width list pane beside the detail of its selection, each pane
 * scrolling on its own and divided by a hairline (Mail, Linear's inbox). It fills a bounded
 * flex-column host (a `contentMode="fill"` workspace) and stacks the panes when its own
 * width is under 40rem.
 *
 * USAGE:
 *   <ListDetail label="Runs" list={<SelectList label="Runs">…</SelectList>} detail={<RunDetail id={id} />} />
 *   <ListDetail label="Timers" listWidth="18rem" list={list} detail={detail} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { CSSProperties, ReactNode } from 'react';

import { cn } from '../lib/cn';
import { Inset } from './Inset';
import { ScrollArea } from './ScrollArea';

import './ListDetail.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ListDetailProps {
  /** Accessible name of the list pane; the detail pane is named `${label} detail`. */
  label: string;
  list: ReactNode;
  detail: ReactNode;
  /** Width of the list pane once split. Default 20rem. */
  listWidth?: string;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ListDetail({
  label,
  list,
  detail,
  listWidth = '20rem',
  className,
}: ListDetailProps) {
  const style = { '--ui-list-detail-width': listWidth } as CSSProperties;
  return (
    <div className={cn('ui-list-detail', className)} style={style}>
      <div className="ui-list-detail-grid">
        <div className="ui-list-detail-list">
          <ScrollArea fill label={label}>
            <Inset padding="sm">{list}</Inset>
          </ScrollArea>
        </div>
        <div className="ui-list-detail-detail">
          <ScrollArea fill label={`${label} detail`}>
            <Inset padding="pane">{detail}</Inset>
          </ScrollArea>
        </div>
      </div>
    </div>
  );
}
