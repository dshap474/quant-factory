/**
 * Ops page — the home page (`home` panels: what is running and scheduled now), the Runs page (the
 * package panels, with an All tab and one tab per package), or a page an extension adds.
 *
 * USAGE:
 *   Routed at /ops (home) and /ops/:scope/:view? inside OpsLayout: /ops/runs (every package),
 *   /ops/runs/data (one package), /ops/<page> (an extension page). An old package link
 *   (/ops/data, /ops/data/<view>) redirects to its Runs tab, keeping the query string.
 *   Extensions contribute panels through `opsPanels`: a `page` of its own, a `home` panel, or a
 *   package panel shown on the Runs page (narrowed by `scopes`), stacked by `order`. Panels fill
 *   the content pane and own their scrolling.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Suspense } from 'react';
import { Navigate, useLocation, useParams } from 'react-router';
import { type OpsPanel, opsPanels } from '@/extensions';
import { EmptyState, Inset, LoadingSkeleton, PageHeader, RouteTabs } from '@/ui';
import { OPS_SCOPES, RUNS_PAGE } from './OpsLayout';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function Panels({ panels, scope }: { panels: OpsPanel[]; scope: string }) {
  if (panels.length === 0) {
    return (
      <Inset padding="pane">
        <EmptyState
          title="No ops panels here"
          hint="An extension adds one by declaring opsPanels in its extension.tsx."
        />
      </Inset>
    );
  }
  return panels.map(({ id, component: Panel }) => (
    <Suspense
      key={id}
      fallback={
        <Inset padding="pane">
          <LoadingSkeleton variant="table" count={6} label="Loading panel" />
        </Inset>
      }
    >
      <Panel scope={scope} />
    </Suspense>
  ));
}

// --------------------------------------------------------------------------- #
// Pages
// --------------------------------------------------------------------------- #

/** Package panels with an All tab (scope '') and one tab per package. */
function RunsPage({ scope }: { scope: string }) {
  const known = scope === '' || OPS_SCOPES.some(({ id }) => id === scope);
  const panels = opsPanels().filter(
    (panel) =>
      !panel.page && !panel.home && (!panel.scopes || scope === '' || panel.scopes.includes(scope)),
  );
  const tabs = [
    { label: 'All', to: `/ops/${RUNS_PAGE.id}`, end: true },
    ...OPS_SCOPES.map(({ id, label }) => ({ label, to: `/ops/${RUNS_PAGE.id}/${id}`, end: true })),
  ];
  return (
    <>
      <PageHeader
        title={RUNS_PAGE.label}
        tabs={<RouteTabs label="Runs by package" items={tabs} />}
      />
      {known ? (
        <Panels key={scope} panels={panels} scope={scope} />
      ) : (
        <Inset padding="pane">
          <EmptyState title={`No package "${scope}"`} hint="Pick a package tab." />
        </Inset>
      )}
    </>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function OpsPage() {
  const params = useParams();
  const { search } = useLocation();
  const scope = params.scope;

  if (scope === RUNS_PAGE.id) return <RunsPage scope={params.view ?? ''} />;
  if (OPS_SCOPES.some(({ id }) => id === scope)) {
    return <Navigate to={`/ops/${RUNS_PAGE.id}/${scope}${search}`} replace />;
  }
  const home = scope === undefined;
  const page = opsPanels().find((panel) => panel.page?.id === scope);
  if (!home && !page) {
    return (
      <Inset padding="pane">
        <EmptyState title={`No Ops page "${scope}"`} hint="Pick a page in the navigator." />
      </Inset>
    );
  }
  const panels = page ? [page] : opsPanels().filter((panel) => panel.home);
  return (
    <>
      <PageHeader title={page?.page?.label ?? 'Ops'} />
      <Panels panels={panels} scope={scope ?? ''} />
    </>
  );
}
