/**
 * Known-answer graph tests for the non-chart route closure guard.
 *
 * USAGE:
 *   node --test scripts/check-route-closures.test.mjs
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { collectRouteClosureFailures, findImportPath } from './check-route-closures.mjs';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('route closure graph', () => {
  it('returns the transitive import path to ECharts', () => {
    const manifest = {
      'src/pages/HomePage.tsx': { file: 'assets/HomePage.js' },
    };
    const graph = {
      'assets/HomePage.js': { imports: ['assets/shared.js'], containsEcharts: false },
      'assets/shared.js': { imports: ['assets/charts.js'], containsEcharts: false },
      'assets/charts.js': { imports: [], containsEcharts: true },
    };

    assert.deepEqual(findImportPath(manifest, graph, ['src/pages/HomePage.tsx']).path, [
      'assets/HomePage.js',
      'assets/shared.js',
      'assets/charts.js',
    ]);
  });

  it('reports missing route entries', () => {
    const failures = collectRouteClosureFailures({}, {});

    assert.ok(failures.some((failure) => failure.includes('/docs: manifest entry is missing')));
  });
});
