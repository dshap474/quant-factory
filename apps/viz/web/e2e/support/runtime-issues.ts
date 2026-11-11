/**
 * Runtime issue collector for representative Playwright release checks.
 *
 * USAGE:
 *   const issues = collectRuntimeIssues(page);
 *   await expectNoRuntimeIssues('/catalog', issues);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { expect, type Page } from '@playwright/test';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface RuntimeIssue {
  kind: 'console.error' | 'http' | 'pageerror' | 'requestfailed';
  message: string;
}

// --------------------------------------------------------------------------- #
// Classification
// --------------------------------------------------------------------------- #

/** Only cancellable API reads may end in Chromium's intentional ERR_ABORTED. */
export function isExpectedApiCancellation(method: string, url: string, failure: string): boolean {
  return (
    method === 'GET' && failure === 'net::ERR_ABORTED' && new URL(url).pathname.startsWith('/api/')
  );
}

/** Convert an HTTP error response into the collector's actionable issue shape. */
export function httpResponseIssue(
  method: string,
  url: string,
  status: number,
): RuntimeIssue | null {
  if (status < 400) return null;
  return { kind: 'http', message: `${method} ${url} (HTTP ${status})` };
}

// --------------------------------------------------------------------------- #
// Collector
// --------------------------------------------------------------------------- #

/** Collect browser errors without changing the route's request behavior. */
export function collectRuntimeIssues(page: Page): RuntimeIssue[] {
  const issues: RuntimeIssue[] = [];

  page.on('console', (message) => {
    if (message.type() === 'error') {
      issues.push({ kind: 'console.error', message: message.text() });
    }
  });
  page.on('pageerror', (error) => {
    issues.push({ kind: 'pageerror', message: error.message });
  });
  page.on('response', (response) => {
    const issue = httpResponseIssue(response.request().method(), response.url(), response.status());
    if (issue) issues.push(issue);
  });
  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText ?? 'unknown failure';
    // React Query cancels obsolete API reads during route/filter changes.
    if (isExpectedApiCancellation(request.method(), request.url(), failure)) return;
    issues.push({
      kind: 'requestfailed',
      message: `${request.method()} ${request.url()} (${failure})`,
    });
  });

  return issues;
}

/** Fail with route-labelled details so a runtime regression is actionable. */
export async function expectNoRuntimeIssues(route: string, issues: RuntimeIssue[]): Promise<void> {
  await expect(issues, `Unexpected runtime issues on ${route}`).toEqual([]);
}
