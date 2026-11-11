/**
 * Signals research overview — map registered families and optimization versions.
 *
 * USAGE:
 *   Routed at /signals.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type SignalResearchFamily, useSignalResearchFamilies } from '@/lib/api/signals';
import {
  formatIsoDay,
  PageHeader,
  PipelineArchitectureMap,
  type PipelineRow,
  pluralize,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function familyRow(family: SignalResearchFamily): PipelineRow {
  return {
    key: family.signal_family,
    detail: [
      `${family.version_count} ${pluralize(family.version_count, 'version')}`,
      `${family.total_runs} ${pluralize(family.total_runs, 'run')}`,
      `latest ${formatIsoDay(family.latest_run)}`,
    ].join(' · '),
    href: `/signals/${family.signal_family}`,
  };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SignalsPage() {
  const query = useSignalResearchFamilies();
  const rows = (query.data ?? []).map(familyRow);

  return (
    <>
      <PageHeader title="Signals" subtitle="features → signals → strategies" />
      <PipelineArchitectureMap
        scope="signals"
        hideHeader
        laneRows={{
          '01': {
            rows,
            loading: query.isLoading,
            empty: query.error ? 'signal research index unavailable' : 'no research versions yet',
          },
        }}
      />
    </>
  );
}
