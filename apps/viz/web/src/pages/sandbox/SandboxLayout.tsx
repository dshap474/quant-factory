/**
 * Sandbox workspace layout: the sandbox projects and research source tools beside the
 * routed sandbox pages.
 *
 * USAGE:
 *   Declared as the parent route for /sandbox/*.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useResearchPackages } from '@/lib/api/research';
import { SectionLayout } from '@/ui';
import { ResearchTreeNavigator } from '../research/ResearchTreeNavigator';

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

function SandboxNavigator() {
  const packages = useResearchPackages();
  return (
    <ResearchTreeNavigator
      title="Sandbox"
      home="/sandbox"
      nav={packages.data?.nav ?? []}
      loading={packages.isLoading}
      error={packages.error?.message ?? null}
      open={['sandbox']}
      noun="sandbox projects"
    />
  );
}

export function SandboxLayout() {
  return <SectionLayout navigator={<SandboxNavigator />} />;
}
