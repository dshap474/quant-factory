/**
 * Strategies section frame: the page header, led by the Overview / Backtesting route tabs, above a tab's body.
 *
 * USAGE:
 *   <StrategiesFrame right={<Button>Update backtest</Button>}>
 *     <Section>…</Section>
 *   </StrategiesFrame>
 *
 * Every tab renders this frame, so the title, subtitle, tab strip and spacing are the same on each.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { PageHeader, PageShell, RouteTabs } from '@/ui';

// --------------------------------------------------------------------------- #
// Values
// --------------------------------------------------------------------------- #

export const STRATEGIES_TABS = [
  { label: 'Overview', to: '/strategies' },
  { label: 'Backtesting', to: '/strategies/backtesting' },
] as const;

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StrategiesFrame({ right, children }: { right?: ReactNode; children: ReactNode }) {
  return (
    <PageShell>
      <PageHeader
        title="Strategies"
        subtitle="signals → strategies → execution"
        right={right}
        tabs={<RouteTabs label="Strategies views" items={STRATEGIES_TABS} />}
      />
      {children}
    </PageShell>
  );
}
