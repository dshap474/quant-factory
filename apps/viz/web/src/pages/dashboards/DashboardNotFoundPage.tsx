/**
 * Terminal page for a `/dashboards/:dashboardId` id that no extension claims.
 *
 * USAGE:
 *   { path: ':dashboardId', element: <DashboardNotFoundPage /> }
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { EmptyState, PageHeader, PageShell } from '@/ui';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DashboardNotFoundPage() {
  return (
    <PageShell maxWidth="full">
      <PageHeader
        title="Dashboard not found"
        subtitle="This dashboard is not available in the local Viz workspace."
      />
      <EmptyState
        title="Dashboard not found"
        hint="This dashboard is not available in the local Viz workspace."
      />
    </PageShell>
  );
}
