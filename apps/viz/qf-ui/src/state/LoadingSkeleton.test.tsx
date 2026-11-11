/**
 * Structural tests for shared loading skeletons.
 *
 * USAGE:
 *   pnpm test -- src/state/LoadingSkeleton.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { LoadingSkeleton } from './LoadingSkeleton';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('LoadingSkeleton', () => {
  it('renders chart loading as the shared pulse at chart geometry', () => {
    const markup = renderToStaticMarkup(<LoadingSkeleton variant="chart" />);

    expect(markup).toContain('role="status"');
    expect(markup).toContain('aria-label="Loading content"');
    expect(markup).toContain('animate-pulse');
    expect(markup).not.toContain('animate-spin');
  });

  it('keeps repeated decorative skeletons out of the accessibility tree', () => {
    const markup = renderToStaticMarkup(
      <div>
        <LoadingSkeleton label="Loading catalog" count={3} />
        <LoadingSkeleton variant="table" count={4} announce={false} />
      </div>,
    );

    expect(markup.match(/role="status"/g)).toHaveLength(1);
    expect(markup).toContain('aria-label="Loading catalog"');
    expect(markup).toContain('aria-hidden="true"');
  });

  it('gives independent loading regions distinct useful labels', () => {
    const markup = renderToStaticMarkup(
      <div>
        <LoadingSkeleton label="Loading regime statistics" />
        <LoadingSkeleton label="Loading transition matrix" />
      </div>,
    );

    expect(markup.match(/role="status"/g)).toHaveLength(2);
    expect(markup).toContain('aria-label="Loading regime statistics"');
    expect(markup).toContain('aria-label="Loading transition matrix"');
  });
});
