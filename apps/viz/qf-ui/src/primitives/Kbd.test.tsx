/**
 * Structural tests for the Kbd keycap primitives.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/Kbd.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Kbd, KbdGroup } from './Kbd';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Kbd', () => {
  it('renders a kbd element carrying the recipe class', () => {
    expect(renderToStaticMarkup(<Kbd>Esc</Kbd>)).toBe('<kbd class="ui-kbd">Esc</kbd>');
  });

  it('merges a caller className and forwards props', () => {
    const html = renderToStaticMarkup(
      <Kbd className="ml-1" aria-label="Escape">
        Esc
      </Kbd>,
    );
    expect(html).toContain('class="ui-kbd ml-1"');
    expect(html).toContain('aria-label="Escape"');
  });

  it('nests keys inside a group', () => {
    const html = renderToStaticMarkup(
      <KbdGroup>
        <Kbd>⌘</Kbd>
        <Kbd>K</Kbd>
      </KbdGroup>,
    );
    expect(html).toBe(
      '<kbd class="ui-kbd-group"><kbd class="ui-kbd">⌘</kbd><kbd class="ui-kbd">K</kbd></kbd>',
    );
  });
});
