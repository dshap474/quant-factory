/**
 * Measure production-route DOM, request, long-task, and hit-area baselines.
 *
 * USAGE:
 *   pnpm run measure:app
 *   VIZ_WEB_URL=http://127.0.0.1:5174 pnpm run measure:app
 */

/* global document, getComputedStyle, window */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { chromium } from '@playwright/test';
import { readExtensionJson } from './read-extension-json.mjs';

// --------------------------------------------------------------------------- #
// Configuration
// --------------------------------------------------------------------------- #

const baseUrl = process.env.VIZ_WEB_URL ?? 'http://127.0.0.1:5174';
const routes = ['/', '/catalog', '/features', '/signals', '/strategies', '/docs'];

for (const policy of await readExtensionJson('measurement-routes.json')) {
  routes.push(...policy);
}
const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];

// --------------------------------------------------------------------------- #
// Measurement
// --------------------------------------------------------------------------- #

async function measureRoute(browser, viewport, route) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const requestStarts = new Map();
  const apiRequests = [];
  const errors = [];

  await page.addInitScript(() => {
    window.__vizLongTasks = [];
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        window.__vizLongTasks.push(Math.round(entry.duration));
      }
    }).observe({ type: 'longtask', buffered: true });
  });
  page.on('request', (request) => requestStarts.set(request, performance.now()));
  page.on('response', (response) => {
    const request = response.request();
    const pathname = new URL(response.url()).pathname;
    if (!pathname.startsWith('/api/') && pathname !== '/health') return;
    apiRequests.push({
      pathname,
      status: response.status(),
      durationMs: Math.round(performance.now() - (requestStarts.get(request) ?? performance.now())),
    });
  });
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));

  const startedAt = performance.now();
  await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded', timeout: 20_000 });
  await page.waitForLoadState('networkidle', { timeout: 12_000 }).catch(() => {});
  await page.waitForTimeout(300);

  const documentMetrics = await page.evaluate(() => {
    const controls = [
      ...document.querySelectorAll('button, input:not([type="hidden"]), select, a[href]'),
    ].filter((element) => {
      const style = getComputedStyle(element);
      const bounds = element.getBoundingClientRect();
      return (
        style.display !== 'none' &&
        style.visibility !== 'hidden' &&
        bounds.width > 1 &&
        bounds.height > 1
      );
    });
    const undersizedControls = controls.filter((element) => {
      const bounds = element.getBoundingClientRect();
      return bounds.width < 40 || bounds.height < 40;
    });
    return {
      domElements: document.querySelectorAll('*').length,
      controls: controls.length,
      undersizedControls: undersizedControls.length,
      tables: [...document.querySelectorAll('table')].map((table) => ({
        rows: table.querySelectorAll('tbody tr').length,
        columns: table.querySelectorAll('thead th').length,
        cells: table.querySelectorAll('td').length,
      })),
      longTasksMs: window.__vizLongTasks ?? [],
    };
  });

  await context.close();
  return {
    viewport: viewport.name,
    route,
    readyMs: Math.round(performance.now() - startedAt),
    apiRequests,
    consoleErrors: errors,
    ...documentMetrics,
  };
}

// --------------------------------------------------------------------------- #
// Entry point
// --------------------------------------------------------------------------- #

const browser = await chromium.launch({ headless: true });
try {
  for (const viewport of viewports) {
    for (const route of routes) {
      console.log(JSON.stringify(await measureRoute(browser, viewport, route)));
    }
  }
} finally {
  await browser.close();
}
