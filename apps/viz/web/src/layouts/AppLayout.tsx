/**
 * Root route element: the shared AppShell around the route outlet, plus the
 * per-route document title and the dev-only ?profile=1 commit recorder
 * (lazy, dev builds only).
 *
 * USAGE:
 *   Declared as the parent route element in routes.tsx; child routes render
 *   into <Outlet />.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Outlet, useLocation } from 'react-router';
import { usePageTitle } from '@/lib/shared/lib/page-title';
import { AppShell, lazyNamed } from '@/ui';

// --------------------------------------------------------------------------- #
// Dev-only profiler
// --------------------------------------------------------------------------- #

const RouteProfiler = import.meta.env.DEV
  ? lazyNamed(() => import('@/lib/shared/lib/RouteProfiler'), 'RouteProfiler')
  : null;

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function AppLayout() {
  const location = useLocation();
  const profileEnabled =
    import.meta.env.DEV && new URLSearchParams(location.search).get('profile') === '1';

  usePageTitle();

  return (
    <AppShell>
      {profileEnabled && RouteProfiler ? (
        <RouteProfiler id={`route:${location.pathname}`}>
          <Outlet />
        </RouteProfiler>
      ) : (
        <Outlet />
      )}
    </AppShell>
  );
}
