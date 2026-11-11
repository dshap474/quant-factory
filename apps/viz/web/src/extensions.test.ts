/**
 * Known-answer validation tests for the typed extension registry.
 *
 * USAGE: pnpm test -- src/extensions.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { lazy } from 'react';
import { describe, expect, it } from 'vitest';
import { extensions, type VizExtension, validateExtensions } from './extensions';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const component = lazy(async () => ({ default: () => null }));

function extension(overrides: Partial<VizExtension> = {}): VizExtension {
  return {
    id: 'example',
    mount: 'dashboards',
    order: 1,
    routes: [{ path: 'example', component, order: 1 }],
    ...overrides,
  };
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('validateExtensions', () => {
  it('accepts the discovered registry', () => {
    expect(() => validateExtensions(extensions)).not.toThrow();
  });

  it('rejects duplicate IDs and routes', () => {
    expect(() => validateExtensions([extension(), extension()])).toThrow(/Duplicate extension ID/);
    expect(() => validateExtensions([extension(), extension({ id: 'second' })])).toThrow(
      /Duplicate extension route/,
    );
  });

  it('rejects duplicate navigation positions and dead links', () => {
    expect(() =>
      validateExtensions([
        extension({ navigation: [{ label: 'Example', path: '/dashboards/missing', position: 1 }] }),
      ]),
    ).toThrow(/unregistered extension route/);
    expect(() =>
      validateExtensions([
        extension({ navigation: [{ label: 'Example', path: '/dashboards/example', position: 1 }] }),
        extension({
          id: 'second',
          routes: [{ path: 'second', component, order: 2 }],
          navigation: [{ label: 'Second', path: '/dashboards/second', position: 1 }],
        }),
      ]),
    ).toThrow(/Duplicate navigation position/);
  });

  it('rejects public shadows and parameter routes before specific routes', () => {
    expect(() =>
      validateExtensions([
        extension({ mount: 'sandbox', routes: [{ path: 'doc/*', component, order: 1 }] }),
      ]),
    ).toThrow(/shadows public route/);
    expect(() =>
      validateExtensions([
        extension({
          mount: 'strategies',
          routes: [
            { path: ':family', component, order: 1 },
            { path: 'specific', component, order: 2 },
          ],
        }),
      ]),
    ).toThrow(/Parameter route/);
  });

  it('rejects duplicate exclusive extension claims', () => {
    const first = extension({
      defaultDashboard: 'example',
      strategyRedirects: { 'example/v001': '/strategies/example' },
      signalRunPanels: [{ signalType: 'example-signal', component }],
    });
    const second = extension({
      id: 'second',
      routes: [{ path: 'second', component, order: 2 }],
      defaultDashboard: 'second',
      strategyRedirects: { 'example/v001': '/strategies/second' },
      signalRunPanels: [{ signalType: 'example-signal', component }],
    });

    expect(() => validateExtensions([first, second])).toThrow(/default dashboard owner/);
    expect(() =>
      validateExtensions([
        { ...first, defaultDashboard: undefined },
        { ...second, defaultDashboard: undefined },
      ]),
    ).toThrow(/strategy redirect/);
    expect(() =>
      validateExtensions([
        { ...first, defaultDashboard: undefined, strategyRedirects: undefined },
        { ...second, defaultDashboard: undefined, strategyRedirects: undefined },
      ]),
    ).toThrow(/signal run panel/);
  });
});
