/**
 * Structural tests for the shared Input primitive.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/Input.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Input } from './Input';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Input', () => {
  it('renders a bare input carrying the recipe class', () => {
    expect(renderToStaticMarkup(<Input />)).toBe('<input class="ui-input"/>');
  });

  it('merges a caller className', () => {
    expect(renderToStaticMarkup(<Input className="w-64" />)).toContain('class="ui-input w-64"');
  });

  it('maps size to the control-size scale class and never forwards it as an attribute', () => {
    const html = renderToStaticMarkup(<Input size="xl" />);

    expect(html).toBe('<input class="ui-input ui-size-xl"/>');
  });

  it('forwards arbitrary input props', () => {
    const html = renderToStaticMarkup(
      <Input type="search" placeholder="Filter runs" disabled aria-label="Run filter" />,
    );

    expect(html).toContain('type="search"');
    expect(html).toContain('placeholder="Filter runs"');
    expect(html).toContain('disabled=""');
    expect(html).toContain('aria-label="Run filter"');
  });
});
