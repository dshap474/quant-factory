/**
 * Ops workspace layout: a navigator with the Runs page (queued run jobs, one tab per package),
 * then any pages extensions add, beside the routed page. The content pane
 * fills the workspace so a page can split into panes that scroll on their own.
 *
 * USAGE:
 *   Declared as the parent route for /ops/*; the navigator title opens the home page (/ops).
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useLocation } from 'react-router';
import { opsPanels } from '@/extensions';
import { Navigator, SectionLayout } from '@/ui';

// --------------------------------------------------------------------------- #
// Values
// --------------------------------------------------------------------------- #

/** The repository's packages, in pipeline order: the Runs page's tabs after All. */
export const OPS_SCOPES = [
  { id: 'data', label: 'Data' },
  { id: 'features', label: 'Features' },
  { id: 'signals', label: 'Signals' },
  { id: 'strategies', label: 'Strategies' },
  { id: 'execution', label: 'Execution' },
  { id: 'production', label: 'Production' },
  { id: 'research', label: 'Research' },
  { id: 'platform', label: 'Platform' },
] as const;

/** The page listing every package's runs; `/ops/runs/<package>` is one package's tab. */
export const RUNS_PAGE = { id: 'runs', label: 'Runs' } as const;

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

function OpsNavigator() {
  const current = useLocation().pathname.split('/')[2];
  const row = ({ id, label }: { id: string; label: string }) => ({
    id,
    label,
    to: `/ops/${id}`,
    current: id === current,
  });
  const pages = opsPanels().flatMap((panel) => (panel.page ? [panel.page] : []));
  return (
    <Navigator
      title="Ops"
      titleTo="/ops"
      listLabel="Ops pages"
      groups={[{ id: 'pages', items: [RUNS_PAGE, ...pages].map(row) }]}
    />
  );
}

export function OpsLayout() {
  return <SectionLayout navigator={<OpsNavigator />} contentMode="fill" />;
}
