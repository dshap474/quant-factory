/**
 * Execution section shell: the navigator and index page an installed extension contributes,
 * beside the routed pages. Core has no Execution content of its own.
 *
 * USAGE:
 *   Declared as the parent route for /execution/*; ExecutionIndexPage is its index route.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { createElement, Suspense } from 'react';
import { sectionContribution } from '@/extensions';
import { EmptyState, Inset, Navigator, SectionLayout } from '@/ui';

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

export function ExecutionLayout() {
  const navigator = sectionContribution('execution')?.navigator;
  return (
    <SectionLayout
      navigator={
        navigator ? (
          <Suspense fallback={<Navigator title="Execution" titleTo="/execution" loading />}>
            {createElement(navigator)}
          </Suspense>
        ) : null
      }
    />
  );
}

// --------------------------------------------------------------------------- #
// Index
// --------------------------------------------------------------------------- #

export function ExecutionIndexPage() {
  const index = sectionContribution('execution')?.index;
  if (index) return createElement(index);
  return (
    <Inset padding="pane">
      <EmptyState
        title="No execution pages installed"
        hint="An extension mounted on 'execution' provides them through its section hook."
      />
    </Inset>
  );
}
