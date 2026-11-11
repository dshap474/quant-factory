/**
 * Loading frame for the composition view: the toolbar's controls, disabled at their
 * loaded widths, over the chart skeleton, so nothing moves when the run arrives. Kept
 * out of the lazy composition chunk so the page can show it before that chunk loads.
 *
 * USAGE:
 *   if (loading) return <CompositionPending />;
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { LoadingSkeleton, Section, SelectControl, Toolbar } from '@/ui';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function CompositionPending() {
  return (
    <>
      <Section>
        <Toolbar aria-label="Composition controls">
          <SelectControl
            disabled
            ariaLabel="Rank assets by"
            placeholder="Rank"
            className="w-full sm:w-52"
            options={[]}
          />
          <SelectControl
            disabled
            ariaLabel="Assets"
            placeholder="assets"
            className="w-full sm:w-72"
            options={[]}
          />
          <SelectControl
            disabled
            ariaLabel="Configuration"
            placeholder="Configuration"
            className="w-full sm:w-72"
            options={[]}
          />
        </Toolbar>
      </Section>
      <Section>
        <LoadingSkeleton variant="chart" label="Loading composition" />
      </Section>
    </>
  );
}
