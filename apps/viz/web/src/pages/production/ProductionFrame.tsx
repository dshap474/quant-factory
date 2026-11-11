/**
 * Production section frame: the page header, led by the route tabs, above a tab's body.
 *
 * USAGE:
 *   <ProductionFrame badges={<StatusBadge status="complete">complete</StatusBadge>}>
 *     <Section>…</Section>
 *   </ProductionFrame>
 *
 * Production is a full-width section, so it carries route tabs rather
 * than a secondary navigator; each tab renders this frame so its header facts stay its own.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { PageHeader, PageShell, RouteTabs } from '@/ui';

// --------------------------------------------------------------------------- #
// Values
// --------------------------------------------------------------------------- #

export const PRODUCTION_TABS = [{ label: 'Live', to: '/production/live' }] as const;

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ProductionFrame({ badges, children }: { badges?: ReactNode; children: ReactNode }) {
  return (
    <PageShell>
      <PageHeader
        title="Production"
        badges={badges}
        tabs={<RouteTabs label="Production views" items={PRODUCTION_TABS} />}
      />
      {children}
    </PageShell>
  );
}
