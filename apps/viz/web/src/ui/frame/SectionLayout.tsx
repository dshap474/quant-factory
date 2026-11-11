/**
 * Routed section layout: a SectionWorkspace that renders the matched child
 * route and can hide its navigator on full-bleed child routes. The content pane
 * owns its own Suspense boundary, so a lazy child page shows a skeleton in the
 * pane while the navigator stays on screen.
 *
 * USAGE:
 *   <SectionLayout
 *     navigator={<AgentsNavigator />}
 *     navigatorHiddenOn="/agents/strategy-optimizer/runs/:runId"
 *     hiddenClassName="optimizer-run-shell"
 *   />
 *   <SectionLayout navigator={<DocsNavigator />} className="docs-workspace">
 *     <DocsReader />
 *   </SectionLayout>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { SectionWorkspace, WorkspaceFallback } from '@quant-factory/qf-ui';
import { type ReactNode, Suspense } from 'react';
import { matchPath, Outlet, useLocation } from 'react-router';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SectionLayoutProps {
  navigator: ReactNode;
  className?: string;
  /** Route pattern (react-router syntax) on which the navigator is hidden. */
  navigatorHiddenOn?: string;
  /** Workspace className while the navigator is hidden. */
  hiddenClassName?: string;
  /** Forwarded to SectionWorkspace: 'scroll' (default) or 'fill'. */
  contentMode?: 'scroll' | 'fill';
  /** Defaults to the matched child route (`<Outlet />`). */
  children?: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SectionLayout({
  navigator,
  className,
  navigatorHiddenOn,
  hiddenClassName,
  contentMode,
  children,
}: SectionLayoutProps) {
  const { pathname } = useLocation();
  const hidden = navigatorHiddenOn !== undefined && matchPath(navigatorHiddenOn, pathname) !== null;

  return (
    <SectionWorkspace
      navigator={hidden ? null : navigator}
      className={hidden ? hiddenClassName : className}
      contentMode={contentMode}
      contentKey={pathname}
    >
      <Suspense fallback={<WorkspaceFallback />}>{children ?? <Outlet />}</Suspense>
    </SectionWorkspace>
  );
}
