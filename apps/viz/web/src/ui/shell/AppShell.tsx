/**
 * App shell: the theme root, the primary sidebar dock (a fixed drawer below
 * 768px), and the main column with the workspace header rail and the scrolling
 * route content. Binds qf-ui to the host (router adapter, shared section-navigator
 * width from app settings). Owns the drawer state, the persisted sidebar collapse (app
 * settings), Escape-to-close, and the route content pane. The pane's Suspense
 * boundary stays mounted across navigations, so router transitions keep the
 * current page on screen until the next route's code has loaded (no blank
 * fallback, no fade); the pane scrolls back to the top on every pathname change.
 *
 * USAGE:
 *   <AppShell>
 *     <Outlet />
 *   </AppShell>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  Button,
  ICON_SIZE,
  ICON_STROKE,
  LazyToaster,
  SectionNavigatorWidthProvider,
  WorkspaceFallback,
  WorkspaceHeaderTargetProvider,
} from '@quant-factory/qf-ui';
import { Menu, X } from 'lucide-react';
import { type ReactNode, Suspense, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { useAppSettings } from '@/lib/shared/lib/app-settings';
import { ViewerRouterProvider } from '../router/ViewerRouterProvider';
import { CommandMenu } from './CommandMenu';
import { Sidebar } from './Sidebar';

import '../frame/CatalogWorkbench.css';
import './AppShell.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface AppShellProps {
  /** Route content; scrolled back to the top whenever the pathname changes. */
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function AppShell({ children }: AppShellProps) {
  const location = useLocation();
  const { sidebarCollapsed, setSidebarCollapsed, sectionNavNarrow, setSectionNavNarrow } =
    useAppSettings();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [commandMenuOpen, setCommandMenuOpen] = useState(false);
  const [headerTarget, setHeaderTarget] = useState<HTMLDivElement | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const routeContentRef = useRef<HTMLDivElement | null>(null);
  const collapsed = sidebarCollapsed && !drawerOpen;

  const closeDrawer = () => {
    setDrawerOpen(false);
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: route content scrolls back to the top whenever the pathname changes.
  useLayoutEffect(() => {
    const routeContent = routeContentRef.current;
    if (!routeContent) return;
    routeContent.scrollTop = 0;
    routeContent.scrollLeft = 0;
  }, [location.pathname]);

  useEffect(() => {
    if (!drawerOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      setDrawerOpen(false);
      menuButtonRef.current?.focus();
    };
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [drawerOpen]);

  return (
    <ViewerRouterProvider>
      <SectionNavigatorWidthProvider narrow={sectionNavNarrow} onNarrowChange={setSectionNavNarrow}>
        <a href="#main-content" className="app-skip-link">
          Skip to content
        </a>
        <CommandMenu open={commandMenuOpen} onOpenChange={setCommandMenuOpen} />
        <LazyToaster />

        <div className="app-theme app-shell">
          <Button
            ref={menuButtonRef}
            variant="control"
            className={drawerOpen ? 'app-shell-menu-button is-open' : 'app-shell-menu-button'}
            aria-label="Toggle sidebar"
            aria-expanded={drawerOpen}
            onClick={() => {
              setDrawerOpen((open) => !open);
            }}
          >
            <span className="app-shell-menu-icon" aria-hidden="true">
              {drawerOpen ? (
                <X size={ICON_SIZE} strokeWidth={ICON_STROKE} />
              ) : (
                <Menu size={ICON_SIZE} strokeWidth={ICON_STROKE} />
              )}
            </span>
          </Button>

          {drawerOpen ? (
            <div className="app-shell-overlay" onClick={closeDrawer} role="presentation" />
          ) : null}

          <aside
            className={['app-sidebar', drawerOpen ? 'is-open' : '', collapsed ? 'collapsed' : '']
              .filter(Boolean)
              .join(' ')}
          >
            <Sidebar
              collapsed={collapsed}
              onCloseSidebar={closeDrawer}
              onOpenCommandMenu={() => {
                setCommandMenuOpen(true);
              }}
              onToggleCollapse={() => {
                setSidebarCollapsed(!sidebarCollapsed);
              }}
            />
          </aside>

          <main id="main-content" className="app-main">
            <WorkspaceHeaderTargetProvider target={headerTarget}>
              <div ref={setHeaderTarget} className="app-workspace-header" />
              <div ref={routeContentRef} className="route-content">
                <Suspense fallback={<WorkspaceFallback />}>{children}</Suspense>
              </div>
            </WorkspaceHeaderTargetProvider>
          </main>
        </div>
      </SectionNavigatorWidthProvider>
    </ViewerRouterProvider>
  );
}
