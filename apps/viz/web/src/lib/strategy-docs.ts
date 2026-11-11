/**
 * Strategy and signal family documents bundled from the repository: each strategy family's
 * baseline diagrams (`docs/ARCHITECTURE.md`) and every family's design space
 * (`optimization/DESIGN-SPACE.md`).
 * Files load on demand; editing one reloads it (hot reload in
 * dev, next build otherwise). With no extensions present the set is simply empty.
 *
 * USAGE:
 *   hasFamilyDoc('example', 'optimization/DESIGN-SPACE.md')   // boolean
 *   const markdown = useFamilyDoc(family, 'docs/ARCHITECTURE.md');                // string | null
 *   useFamilyDoc(signalFamily, 'optimization/DESIGN-SPACE.md', 'signals')
 *   familyDocPath(family, 'docs/ARCHITECTURE.md')   // repo-relative path, for doc links
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useEffect, useState } from 'react';

// --------------------------------------------------------------------------- #
// Files
// --------------------------------------------------------------------------- #

interface FamilyDocNames {
  architecture: 'docs/ARCHITECTURE.md';
  designSpace: 'optimization/DESIGN-SPACE.md';
}
export type FamilyDoc = FamilyDocNames[keyof FamilyDocNames];
/** The package whose `extensions/lib/` holds the family. */
export type FamilyPackage = 'strategies' | 'signals' | 'features';

const ROOT = '../../../../../';

const FILES = import.meta.glob<string>(
  [
    '../../../../../packages/strategies/extensions/lib/*/docs/ARCHITECTURE.md',
    '../../../../../packages/strategies/extensions/lib/*/optimization/DESIGN-SPACE.md',
    '../../../../../packages/signals/extensions/lib/*/optimization/DESIGN-SPACE.md',
  ],
  { query: '?raw', import: 'default' },
);

export function familyDocPath(
  family: string,
  doc: FamilyDoc,
  pkg: FamilyPackage = 'strategies',
): string {
  return `packages/${pkg}/extensions/lib/${family}/${doc}`;
}

export function hasFamilyDoc(
  family: string,
  doc: FamilyDoc,
  pkg: FamilyPackage = 'strategies',
): boolean {
  return `${ROOT}${familyDocPath(family, doc, pkg)}` in FILES;
}

/** The document's Markdown, or null while loading or when the family has none. */
export function useFamilyDoc(
  family: string,
  doc: FamilyDoc,
  pkg: FamilyPackage = 'strategies',
): string | null {
  return useBundledText(FILES[`${ROOT}${familyDocPath(family, doc, pkg)}`]);
}

/** A bundled file's text from its lazy loader, or null while loading or when there is none. */
export function useBundledText(load: (() => Promise<string>) | undefined): string | null {
  const [loaded, setLoaded] = useState<{ load: typeof load; text: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    void load?.().then((text) => {
      if (!cancelled) setLoaded({ load, text });
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  return loaded && loaded.load === load ? loaded.text : null;
}
