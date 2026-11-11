/**
 * Ensure non-chart route static-import closures cannot pull ECharts into first load.
 *
 * USAGE:
 *   pnpm run build
 *   node scripts/check-route-closures.mjs
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { readExtensionJson } from './read-extension-json.mjs';

// --------------------------------------------------------------------------- #
// Route ownership
// --------------------------------------------------------------------------- #

const NON_CHART_ROUTES = {
  '/': ['src/pages/HomePage.tsx'],
  '/signals': ['src/pages/signals/SignalsLayout.tsx', 'src/pages/SignalsPage.tsx'],
  '/signals/:family': [
    'src/pages/signals/SignalsLayout.tsx',
    'src/pages/signals/SignalFamilyPage.tsx',
  ],
  '/strategies': [
    'src/pages/strategies/StrategiesLayout.tsx',
    'src/pages/strategies/StrategiesPage.tsx',
  ],
  '/docs': ['src/pages/DocsPage.tsx'],
  '/agents/strategy-optimizer/runs/:runId': [
    'src/pages/agents/AgentsLayout.tsx',
    'src/pages/agents/OptimizerRunPage.tsx',
  ],
};
const CHART_CONTROLS = [];

async function loadExtensionPolicies() {
  for (const policy of await readExtensionJson('route-closures.json')) {
    Object.assign(NON_CHART_ROUTES, policy.nonChartRoutes ?? {});
    CHART_CONTROLS.push(...(policy.chartControls ?? []));
  }
}

// --------------------------------------------------------------------------- #
// Graph helpers
// --------------------------------------------------------------------------- #

function sourceKey(manifest, source) {
  if (manifest[source]) return source;
  return Object.keys(manifest).find((key) => manifest[key]?.src === source) ?? null;
}

export function findImportPath(manifest, graph, sources) {
  const queue = [];
  const seen = new Set();
  for (const source of sources) {
    const key = sourceKey(manifest, source);
    if (!key) return { missing: source, path: null };
    const file = manifest[key]?.file;
    if (!file || !graph[file]) return { missing: `${source} build chunk`, path: null };
    queue.push({ file, path: [file] });
  }

  while (queue.length) {
    const current = queue.shift();
    if (!current || seen.has(current.file)) continue;
    seen.add(current.file);
    const entry = graph[current.file];
    if (entry?.containsEcharts) return { missing: null, path: current.path };
    for (const dependency of entry?.imports ?? []) {
      queue.push({ file: dependency, path: [...current.path, dependency] });
    }
  }
  return { missing: null, path: null };
}

export function collectRouteClosureFailures(manifest, graph) {
  const failures = [];
  for (const [route, sources] of Object.entries(NON_CHART_ROUTES)) {
    const result = findImportPath(manifest, graph, sources);
    if (result.missing) {
      failures.push(`${route}: manifest entry is missing for ${result.missing}`);
    } else if (result.path) {
      failures.push(`${route}: reaches ECharts via ${result.path.join(' -> ')}`);
    }
  }

  for (const chartControl of CHART_CONTROLS) {
    const control = findImportPath(manifest, graph, chartControl.sources);
    if (control.missing) {
      failures.push(
        `${chartControl.route}: positive-control entry is missing for ${control.missing}`,
      );
    } else if (!control.path) {
      failures.push(`${chartControl.route}: positive control did not reach the ECharts chunk`);
    }
  }
  return failures;
}

// --------------------------------------------------------------------------- #
// Entry point
// --------------------------------------------------------------------------- #

async function checkRouteClosures() {
  await loadExtensionPolicies();
  const manifestUrl = new URL('../dist/.vite/manifest.json', import.meta.url);
  const graphUrl = new URL('../dist/.vite/route-module-graph.json', import.meta.url);
  const manifest = JSON.parse(await readFile(manifestUrl, 'utf8'));
  const graph = JSON.parse(await readFile(graphUrl, 'utf8'));
  const failures = collectRouteClosureFailures(manifest, graph);
  if (failures.length) {
    console.error(`Route-closure check failed:\n${failures.join('\n')}`);
    process.exitCode = 1;
    return;
  }
  console.log(
    `Route-closure check passed: ${Object.keys(NON_CHART_ROUTES).length} non-chart routes exclude ECharts; ${CHART_CONTROLS.length} chart controls reach it.`,
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await checkRouteClosures();
}
