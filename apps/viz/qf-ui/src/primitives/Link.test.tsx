/**
 * Structural tests for the shared Link primitive.
 *
 * USAGE:
 *   pnpm test -- src/primitives/Link.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MemoryRouter } from '../../tests/memory-router';

import { Link } from './Link';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Link', () => {
  it('renders in-app routes through the router without external attributes', () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <Link to="/agents">Agents</Link>
      </MemoryRouter>,
    );

    expect(markup).toContain('href="/agents"');
    expect(markup).toContain('class="ui-link ui-link-inline"');
    expect(markup).not.toContain('target=');
    expect(markup).not.toContain('rel=');
    expect(markup).not.toContain('↗');
  });

  it('opens external links in a new tab with rel and a glyph', () => {
    const markup = renderToStaticMarkup(<Link href="https://example.test/docs">Docs</Link>);

    expect(markup).toContain('href="https://example.test/docs"');
    expect(markup).toContain('target="_blank"');
    expect(markup).toContain('rel="noopener noreferrer"');
    expect(markup).toContain('<span aria-hidden="true" class="ui-link-glyph">↗</span>');
  });

  it('keeps downloads in the same tab without a glyph', () => {
    const markup = renderToStaticMarkup(
      <Link href="/files/report.csv" download>
        report.csv
      </Link>,
    );

    expect(markup).toContain('download=""');
    expect(markup).not.toContain('target=');
    expect(markup).not.toContain('rel=');
    expect(markup).not.toContain('↗');
  });

  it('honours an explicit glyph={false}', () => {
    const markup = renderToStaticMarkup(
      <Link href="https://example.test" glyph={false}>
        Site
      </Link>,
    );

    expect(markup).not.toContain('↗');
  });

  it.each([
    { variant: 'subtle' as const, expected: 'class="ui-link ui-link-subtle"' },
    { variant: 'control' as const, expected: 'class="ui-link ui-button ui-button-control"' },
  ])('applies the $variant recipe', ({ variant, expected }) => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <Link to="/x" variant={variant}>
          x
        </Link>
      </MemoryRouter>,
    );

    expect(markup).toContain(expected);
  });

  it('applies size and icon classes only to control links', () => {
    const control = renderToStaticMarkup(
      <MemoryRouter>
        <Link to="/x" variant="control" size="lg" icon aria-label="Open">
          …
        </Link>
      </MemoryRouter>,
    );
    const inline = renderToStaticMarkup(
      <MemoryRouter>
        <Link to="/x" size="lg" icon>
          x
        </Link>
      </MemoryRouter>,
    );
    const unsized = renderToStaticMarkup(
      <MemoryRouter>
        <Link to="/x" variant="control">
          x
        </Link>
      </MemoryRouter>,
    );

    expect(control).toContain('ui-size-lg ui-icon-only');
    expect(control).not.toContain('style=');
    expect(inline).not.toContain('ui-size-lg');
    expect(inline).not.toContain('ui-icon-only');
    expect(unsized).not.toContain('ui-size-');
  });

  it('passes router state without emitting a DOM attribute', () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <Link to="/x" state={{ from: '/y' }}>
          x
        </Link>
      </MemoryRouter>,
    );

    expect(markup).toContain('href="/x"');
    expect(markup).not.toContain('state=');
  });

  it('appends className', () => {
    const markup = renderToStaticMarkup(
      <Link href="https://example.test" className="mt-2">
        x
      </Link>,
    );

    expect(markup).toContain('class="ui-link ui-link-inline mt-2"');
  });
});
