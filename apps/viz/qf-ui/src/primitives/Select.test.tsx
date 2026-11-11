/**
 * Structural tests for the shared shadcn/Radix select primitive.
 *
 * USAGE:
 *   pnpm test -- src/primitives/Select.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { SelectControl } from './Select';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('SelectControl', () => {
  it('renders the shared shadcn combobox trigger with the selected value', () => {
    const markup = renderToStaticMarkup(
      <SelectControl
        ariaLabel="Data source"
        value="vendor-b"
        onValueChange={() => undefined}
        options={[
          { value: '', label: 'All' },
          { value: 'vendor-b', label: 'Vendor B' },
        ]}
      />,
    );

    expect(markup).toContain('role="combobox"');
    expect(markup).toContain('aria-label="Data source"');
    expect(markup).toContain('data-slot="select-trigger"');
    expect(markup).toContain('Vendor B');
  });

  it('tightens the trigger with size="sm"', () => {
    const markup = renderToStaticMarkup(
      <SelectControl
        ariaLabel="Data source"
        size="sm"
        value="vendor-b"
        onValueChange={() => undefined}
        options={[{ value: 'vendor-b', label: 'Vendor B' }]}
      />,
    );

    expect(markup).toContain('ui-select-trigger ui-size-sm is-sm');
  });

  it('maps size to the scale class and leaves the md default unclassed', () => {
    const render = (size?: 'lg') =>
      renderToStaticMarkup(
        <SelectControl
          ariaLabel="Data source"
          {...(size === undefined ? {} : { size })}
          value="vendor-b"
          onValueChange={() => undefined}
          options={[{ value: 'vendor-b', label: 'Vendor B' }]}
        />,
      );

    expect(render('lg')).toContain('ui-select-trigger ui-size-lg"');
    expect(render()).not.toContain('ui-size-');
  });
});
