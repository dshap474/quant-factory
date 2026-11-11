/**
 * Dashboards workspace: the "My dashboards" navigator plus routed content.
 *
 * USAGE:
 *   Declared as the parent route for /dashboards/*.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useLocation } from 'react-router';

import { dashboardDestinations } from '@/extensions';
import { Navigator, SectionLayout } from '@/ui';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const DASHBOARDS = dashboardDestinations();

// --------------------------------------------------------------------------- #
// Navigator
// --------------------------------------------------------------------------- #

function DashboardsNavigator() {
  const { pathname } = useLocation();
  return (
    <Navigator
      title="Dashboards"
      titleTo="/dashboards"
      listLabel="My dashboards"
      groups={[
        {
          id: 'mine',
          label: 'My dashboards',
          items: DASHBOARDS.map((dashboard) => ({
            id: dashboard.path,
            label: dashboard.label,
            to: dashboard.path,
            current: pathname === dashboard.path,
            glyph: String(dashboard.position).padStart(2, '0'),
          })),
        },
      ]}
    />
  );
}

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

export function DashboardsLayout() {
  return <SectionLayout navigator={<DashboardsNavigator />} className="dashboards-workspace" />;
}
