/**
 * Known-answer tests for release runtime issue classification.
 *
 * USAGE:
 *   pnpm exec playwright test e2e/runtime-issues.spec.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { expect, test } from '@playwright/test';

import { httpResponseIssue, isExpectedApiCancellation } from './support/runtime-issues';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

test('only exempts intentionally cancelled API GET requests', () => {
  expect(
    isExpectedApiCancellation(
      'GET',
      'http://127.0.0.1:4174/api/catalog/query/data',
      'net::ERR_ABORTED',
    ),
  ).toBe(true);
  expect(
    isExpectedApiCancellation('POST', 'http://127.0.0.1:4174/api/query', 'net::ERR_ABORTED'),
  ).toBe(false);
  expect(isExpectedApiCancellation('GET', 'http://127.0.0.1:4174/docs', 'net::ERR_ABORTED')).toBe(
    false,
  );
  expect(
    isExpectedApiCancellation('GET', 'http://127.0.0.1:4174/api/query', 'net::ERR_FAILED'),
  ).toBe(false);
});

test('records HTTP error responses with request details', () => {
  expect(httpResponseIssue('GET', 'http://127.0.0.1:4174/api/catalog', 399)).toBeNull();
  expect(httpResponseIssue('GET', 'http://127.0.0.1:4174/api/catalog', 503)).toEqual({
    kind: 'http',
    message: 'GET http://127.0.0.1:4174/api/catalog (HTTP 503)',
  });
});
