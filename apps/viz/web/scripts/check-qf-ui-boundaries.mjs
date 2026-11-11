/**
 * Enforces qf-ui portability, chart and table module ownership, and public import boundaries.
 *
 * USAGE:
 *   node scripts/check-qf-ui-boundaries.mjs
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { existsSync } from 'node:fs';
import { readdir, readFile } from 'node:fs/promises';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

// --------------------------------------------------------------------------- #
// Paths and rules
// --------------------------------------------------------------------------- #

const APP_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const REPO_ROOT = join(APP_ROOT, '..', '..', '..');
const PACKAGE_ROOT = join(APP_ROOT, '..', 'qf-ui');
const CHARTS_ROOT = join(PACKAGE_ROOT, 'src', 'charts');
const TABLES_ROOT = join(PACKAGE_ROOT, 'src', 'tables');
const ROOT_BARREL = join(PACKAGE_ROOT, 'src', 'index.ts');
const ACTIVE_ROOTS = [
  join(APP_ROOT, 'src'),
  join(APP_ROOT, 'e2e'),
  join(APP_ROOT, 'scripts'),
  join(APP_ROOT, '..', 'extensions'),
];
const SOURCE_EXTENSION = /\.(?:css|js|mjs|ts|tsx)$/;
const ECHARTS_IMPORT = /(?:from\s*|import\s*)['"]echarts(?:\/[^'"]*)?['"]/;
const QF_INTERNAL_IMPORT = /['"]@quant-factory\/qf-ui\/(?:src|dist|internal)(?:\/|['"])/;
// Native table markup is rendered only by the tables module; the root barrel never
// re-exports it, so table symbols have one import location (`/tables*`), like charts.
const NATIVE_TABLE_MARKUP = /<(?:table|thead|tbody|tfoot|tr|th|td|caption)\b/;
const TABLES_REEXPORT = /from\s*['"]\.\/tables(?:\/|['"])/;
const RETIRED_QF_CHARTS_PACKAGE = /@quant-factory\/qf-charts\b/;
const OLD_ARCHITECTURE = /(?:vendor\/qf-charts|src\/lib\/qf-charts|qf-charts\.manifest\.json)/;
const RETIRED_MULTI_SERIES_STACK =
  /(?:DatasetMultiSeriesChart|DatasetLinePlot|DatasetChartLegend|DatasetChartPlotHost|dataset-chart-plot)/;
const RETIRED_LOCAL_TIME_SERIES_PLOT =
  /(?:@\/lib\/components\/charts\/TimeSeriesPlot|from\s*['"]\.\/TimeSeriesPlot['"])/;
const FORBIDDEN_PACKAGE_IMPORT =
  /(?:from\s*|import\s*)['"](?:@\/|apps\/|[^'"]*(?:\/api\/|react-router|@tanstack\/react-query))/;
// Examples are stand-ins for another repository: relative imports may only stay inside
// the example's own directory, so the kit is reached through package exports alone.
const EXAMPLES_ROOT = join(PACKAGE_ROOT, 'examples');
const RELATIVE_IMPORT = /(?:from\s*|import\s*|@import\s*)['"](\.{1,2}\/[^'"]*)['"]/g;
const API_EXPORT =
  /export\s+(?:interface|type|class|function|const)\s+\w*(?:Page|Route|DashboardSection|ApiResponse|QueryKey)\b/;

// --------------------------------------------------------------------------- #
// File walking
// --------------------------------------------------------------------------- #

async function filesUnder(root) {
  if (!existsSync(root)) return []; // apps/viz/extensions is optional
  const entries = await readdir(root, { recursive: true, withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && SOURCE_EXTENSION.test(entry.name))
    .filter((entry) => !entry.parentPath.includes('node_modules'))
    .filter((entry) => !entry.parentPath.includes('_archive'))
    .map((entry) => join(entry.parentPath, entry.name));
}

// --------------------------------------------------------------------------- #
// Checks
// --------------------------------------------------------------------------- #

const failures = [];
const packageFiles = await filesUnder(join(PACKAGE_ROOT, 'src'));
for (const path of packageFiles) {
  const source = await readFile(path, 'utf8');
  const localPath = relative(REPO_ROOT, path);
  if (FORBIDDEN_PACKAGE_IMPORT.test(source))
    failures.push(`${localPath}: forbidden application, API, router, or query import`);
  // Page-shaped names (TerminalPage, PageHeader) are legitimate kit frames, so the
  // application-contract export rule applies to the chart runtime only.
  if (path.startsWith(CHARTS_ROOT) && API_EXPORT.test(source))
    failures.push(`${localPath}: package exports an application/page/API-specific contract`);
  if (!path.startsWith(CHARTS_ROOT) && ECHARTS_IMPORT.test(source))
    failures.push(`${localPath}: ECharts imports belong under qf-ui/src/charts`);
  if (!path.startsWith(`${TABLES_ROOT}/`) && NATIVE_TABLE_MARKUP.test(source))
    failures.push(`${localPath}: native table markup belongs under qf-ui/src/tables`);
  if (path === ROOT_BARREL && TABLES_REEXPORT.test(source))
    failures.push(
      `${localPath}: table modules are exported from @quant-factory/qf-ui/tables, not the root`,
    );
}

for (const path of await filesUnder(EXAMPLES_ROOT)) {
  if (path.includes('/dist/')) continue;
  const source = await readFile(path, 'utf8');
  const localPath = relative(REPO_ROOT, path);
  const exampleRoot = join(EXAMPLES_ROOT, relative(EXAMPLES_ROOT, path).split('/')[0]);
  if (FORBIDDEN_PACKAGE_IMPORT.test(source) || QF_INTERNAL_IMPORT.test(source))
    failures.push(`${localPath}: examples import qf-ui through package exports only`);
  for (const match of source.matchAll(RELATIVE_IMPORT)) {
    const target = join(dirname(path), match[1]);
    if (!target.startsWith(`${exampleRoot}/`))
      failures.push(`${localPath}: relative import ${match[1]} leaves the example`);
  }
}

for (const root of ACTIVE_ROOTS) {
  for (const path of await filesUnder(root)) {
    if (path.endsWith('check-qf-ui-boundaries.mjs')) continue;
    const source = await readFile(path, 'utf8');
    const localPath = relative(REPO_ROOT, path);
    const production = !/(?:\.test\.|\.spec\.|\/e2e\/)/.test(path);
    if (production && ECHARTS_IMPORT.test(source))
      failures.push(`${localPath}: production ECharts import bypasses qf-ui charts`);
    if (QF_INTERNAL_IMPORT.test(source))
      failures.push(`${localPath}: qf-ui internal source import is forbidden`);
    if (RETIRED_QF_CHARTS_PACKAGE.test(source))
      failures.push(`${localPath}: qf-charts merged into @quant-factory/qf-ui/charts`);
    if (OLD_ARCHITECTURE.test(source))
      failures.push(`${localPath}: references removed qf-charts architecture`);
    if (production && RETIRED_MULTI_SERIES_STACK.test(source))
      failures.push(`${localPath}: references the retired app-local multi-series chart stack`);
    if (production && RETIRED_LOCAL_TIME_SERIES_PLOT.test(source))
      failures.push(`${localPath}: imports the retired app-local TimeSeriesPlot adapter`);
  }
}

if (failures.length > 0) {
  console.error(`qf-ui boundary check failed:\n${failures.join('\n')}`);
  process.exitCode = 1;
} else {
  console.log('qf-ui boundary check passed.');
}
