/**
 * Unit tests for the route path -> document title mapping.
 *
 * USAGE:
 *   pnpm test -- src/lib/shared/lib/page-title.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import { pageTitleForPath } from './page-title';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('pageTitleForPath', () => {
  it('keeps the bare base title on the root route', () => {
    expect(pageTitleForPath('/')).toBe('quant-factory Viz');
  });

  it('maps every primary section index route', () => {
    expect(pageTitleForPath('/catalog')).toBe('Catalog · quant-factory Viz');
    expect(pageTitleForPath('/features')).toBe('Features · quant-factory Viz');
    expect(pageTitleForPath('/ml-engine')).toBe('ML Engine · quant-factory Viz');
    expect(pageTitleForPath('/signals')).toBe('Signals · quant-factory Viz');
    expect(pageTitleForPath('/strategies')).toBe('Strategies · quant-factory Viz');
    expect(pageTitleForPath('/production/live')).toBe('live · Production · quant-factory Viz');
    expect(pageTitleForPath('/research')).toBe('Research · quant-factory Viz');
    expect(pageTitleForPath('/agents')).toBe('Agents · quant-factory Viz');
    expect(pageTitleForPath('/dashboards')).toBe('Dashboards · quant-factory Viz');
    expect(pageTitleForPath('/docs')).toBe('Docs · quant-factory Viz');
  });

  it('treats the catalog view mode as the catalog section', () => {
    expect(pageTitleForPath('/catalog/view')).toBe('Catalog · quant-factory Viz');
  });

  it('uses the detail segment on parameterized routes', () => {
    expect(pageTitleForPath('/signals/example-signal')).toBe(
      'example-signal · Signals · quant-factory Viz',
    );
    expect(pageTitleForPath('/signals/example-signal/20260830T000000Z')).toBe(
      'example-signal · Signals · quant-factory Viz',
    );
    expect(pageTitleForPath('/strategies/example-alpha')).toBe(
      'Example Alpha · Strategies · quant-factory Viz',
    );
    expect(pageTitleForPath('/strategies/example-alpha/v002')).toBe(
      'Example Alpha / v002 · Strategies · quant-factory Viz',
    );
    expect(pageTitleForPath('/agents/optimizer')).toBe('optimizer · Agents · quant-factory Viz');
    expect(pageTitleForPath('/dashboards/my-dashboard')).toBe(
      'my-dashboard · Dashboards · quant-factory Viz',
    );
  });

  it('titles signal families and versions under the flat signals section', () => {
    expect(pageTitleForPath('/signals/example-signal')).toBe(
      'example-signal · Signals · quant-factory Viz',
    );
    expect(pageTitleForPath('/signals/example-signal/v000')).toBe(
      'example-signal · Signals · quant-factory Viz',
    );
  });

  it('uses the file name for research, sandbox and corpus docs', () => {
    expect(pageTitleForPath('/research/doc/docs/example-brief.md')).toBe(
      'example-brief · Research · quant-factory Viz',
    );
    expect(pageTitleForPath('/sandbox/example-package')).toBe(
      'example-package · Sandbox · quant-factory Viz',
    );
    expect(pageTitleForPath('/corpus/wiki/factors/momentum.md')).toBe(
      'momentum · Corpus · quant-factory Viz',
    );
  });

  it('decodes URL-encoded detail segments and survives malformed encodings', () => {
    expect(pageTitleForPath('/signals/a%20b')).toBe('a b · Signals · quant-factory Viz');
    expect(pageTitleForPath('/signals/a%ZZb')).toBe('a%ZZb · Signals · quant-factory Viz');
  });

  it('falls back to the base title on unknown sections', () => {
    expect(pageTitleForPath('/nope')).toBe('quant-factory Viz');
    expect(pageTitleForPath('/nope/deeper')).toBe('quant-factory Viz');
  });
});
