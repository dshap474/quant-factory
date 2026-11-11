/**
 * `React.lazy` for modules that export a named component instead of a default.
 *
 * USAGE:
 *   const HomePage = lazyNamed(() => import('./pages/HomePage'), 'HomePage');
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type ComponentType, type LazyExoticComponent, lazy } from 'react';

// --------------------------------------------------------------------------- #
// Helper
// --------------------------------------------------------------------------- #

/**
 * Wrap a dynamic `import()` whose module exports `name`, returning the same
 * lazy component `React.lazy` would produce for a default export. The props
 * type is inferred from the named export, so call sites need no casts.
 */
export function lazyNamed<Name extends string, Props>(
  load: () => Promise<Record<Name, ComponentType<Props>>>,
  name: Name,
): LazyExoticComponent<ComponentType<Props>> {
  return lazy(async () => ({ default: (await load())[name] }));
}
