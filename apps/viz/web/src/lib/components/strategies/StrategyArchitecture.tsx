/**
 * Strategy family architecture: the family's `docs/ARCHITECTURE.md` (its current baseline's
 * diagrams as Mermaid code), drawn by the shared `ArchitectureDiagrams`. The file is bundled
 * from the repository, so editing it updates the page (hot reload in dev, next build otherwise).
 *
 * USAGE:
 *   <StrategyArchitecture strategyType="example" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { ArchitectureDiagrams } from '@/lib/components/ArchitectureDiagrams';
import { familyDocPath, hasFamilyDoc, useFamilyDoc } from '@/lib/strategy-docs';
import { LoadingSkeleton, Text } from '@/ui';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StrategyArchitecture({ strategyType }: { strategyType: string }) {
  const markdown = useFamilyDoc(strategyType, 'docs/ARCHITECTURE.md');
  if (!hasFamilyDoc(strategyType, 'docs/ARCHITECTURE.md'))
    return (
      <Text tone="muted">{`No docs/ARCHITECTURE.md for ${strategyType}; add one to show its architecture.`}</Text>
    );
  if (markdown === null) return <LoadingSkeleton variant="line" count={4} />;
  return (
    <ArchitectureDiagrams
      markdown={markdown}
      path={familyDocPath(strategyType, 'docs/ARCHITECTURE.md')}
    />
  );
}
