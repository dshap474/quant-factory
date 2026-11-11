/**
 * Master-controls band above a workspace, ruled off by one bottom hairline: a label title with a muted
 * note on the left, right-aligned actions (transform toolbars, selects) on the right.
 *
 * USAGE:
 *   <WorkspaceToolbar
 *     title="Chart controls"
 *     note="Applies to every chart"
 *     aria-label="Chart transforms"
 *   >
 *     <ChartTransformToolbar … />
 *   </WorkspaceToolbar>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

import { Text } from '../primitives/Text';
import './WorkspaceToolbar.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface WorkspaceToolbarProps {
  /** Label title on the left (sentence case, medium weight, primary text). */
  title?: ReactNode;
  /** Muted note under the title. */
  note?: ReactNode;
  'aria-label'?: string;
  className?: string;
  /** Right-aligned actions (transform toolbars, selects). */
  children?: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function WorkspaceToolbar({
  title,
  note,
  'aria-label': ariaLabel,
  className,
  children,
}: WorkspaceToolbarProps) {
  return (
    <div className={cn('ui-workspace-toolbar', className)} role="toolbar" aria-label={ariaLabel}>
      {title || note ? (
        <div className="ui-workspace-toolbar-copy">
          {title ? (
            <Text as="span" size="sm" weight="medium">
              {title}
            </Text>
          ) : null}
          {note ? <Text variant="caption">{note}</Text> : null}
        </div>
      ) : null}
      <div className="ui-workspace-toolbar-actions">{children}</div>
    </div>
  );
}
