/**
 * Route-derived document titles for the viz SPA.
 *
 * USAGE:
 *   usePageTitle();                    // in AppLayout; syncs document.title per route
 *   useDocumentTitle(doc?.title);      // in a page; names the tab once its data loads
 *   pageTitleForPath('/docs');         // 'Docs · quant-factory Viz'
 *   pageTitleForPath('/signals/example-signal'); // 'example-signal · Signals · quant-factory Viz'
 *   pageTitleForPath('/strategies/example/v002');
 *   // 'Example Strategy / v003 · Strategies · quant-factory Viz'
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useEffect, useLayoutEffect } from 'react';
import { useLocation } from 'react-router';
import { familyName } from '@/ui';

// --------------------------------------------------------------------------- #
// Values
// --------------------------------------------------------------------------- #

const BASE_TITLE = 'quant-factory Viz';

const SECTION_TITLES: Readonly<Record<string, string>> = {
  catalog: 'Catalog',
  features: 'Features',
  'backtest-engine': 'Backtest Engine',
  'ml-engine': 'ML Engine',
  signals: 'Signals',
  strategies: 'Strategies',
  execution: 'Execution',
  production: 'Production',
  research: 'Research',
  corpus: 'Corpus',
  sandbox: 'Sandbox',
  agents: 'Agents',
  dashboards: 'Dashboards',
  docs: 'Docs',
};

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function decodeSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

function detailSegment(section: string, rest: readonly string[]): string | undefined {
  if (rest.length === 0) return undefined;
  // /catalog/view is a view mode of the catalog, not a detail page.
  if (section === 'catalog') return undefined;
  // Readers title by the file name; the splat's leading folders are its place in the tree.
  if ((section === 'research' || section === 'sandbox') && rest[0] === 'doc')
    return rest.at(-1)?.replace(/\.md$/i, '');
  if (section === 'corpus') return rest.at(-1)?.replace(/\.md$/i, '');
  // A run page titles by its run id, the last of family/version/preset/run.
  if (section === 'backtest-engine' && rest[0] === 'runs') return rest.at(-1);
  // Strategy families read as their display name, matching the page header.
  if (section === 'strategies')
    return [familyName(rest[0]).name, rest[1]].filter(Boolean).join(' / ');
  return rest[0];
}

// --------------------------------------------------------------------------- #
// Title mapping
// --------------------------------------------------------------------------- #

/** `detail` replaces the route-derived detail (a document's own title for its file name). */
export function pageTitleForPath(pathname: string, detail?: string): string {
  const segments = pathname.split('/').filter(Boolean).map(decodeSegment);
  if (segments.length === 0) return BASE_TITLE;

  const [head, ...rest] = segments;
  const section = SECTION_TITLES[head];
  if (!section) return detail ? `${detail} · ${BASE_TITLE}` : BASE_TITLE;

  detail ??= detailSegment(head, rest);
  return detail ? `${detail} · ${section} · ${BASE_TITLE}` : `${section} · ${BASE_TITLE}`;
}

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

/** A layout effect, so a page's `useDocumentTitle` (a passive effect) always lands after it. */
export function usePageTitle(): void {
  const location = useLocation();
  useLayoutEffect(() => {
    document.title = pageTitleForPath(location.pathname);
  }, [location.pathname]);
}

/** Name the tab after a page's own data (a document title) once it is known. */
export function useDocumentTitle(detail: string | undefined): void {
  const { pathname } = useLocation();
  useEffect(() => {
    if (detail) document.title = pageTitleForPath(pathname, detail);
  }, [pathname, detail]);
}
