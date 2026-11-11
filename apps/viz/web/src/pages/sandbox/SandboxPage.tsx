/**
 * Sandbox index — ad-hoc wired research surfaces under Sandbox / Source.
 *
 * USAGE:
 *   Routed at /sandbox
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { researchPackageDetail } from '@/extensions';
import type { ResearchPackage } from '@/lib/api/research';
import { useResearchPackages } from '@/lib/api/research';
import type { PipelineRow } from '@/ui';
import { PageHeader, PipelineArchitectureMap } from '@/ui';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function packageRow(pkg: ResearchPackage): PipelineRow {
  return { key: pkg.id, detail: researchPackageDetail(pkg), href: pkg.route };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SandboxPage() {
  const query = useResearchPackages();
  const rows = (query.data?.packages ?? []).map(packageRow);

  return (
    <>
      <PageHeader title="Sandbox" subtitle="sandbox → promotion" />
      <PipelineArchitectureMap
        scope="research"
        hideHeader
        laneRows={{
          '01': {
            rows,
            loading: query.isLoading,
            empty: query.error ? 'sandbox index unavailable' : 'no sandbox packages wired',
          },
        }}
      />
    </>
  );
}
