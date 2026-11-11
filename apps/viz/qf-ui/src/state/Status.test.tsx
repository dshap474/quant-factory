/**
 * Structural tests for StatusDot and StatusBadge.
 *
 * USAGE:
 *   pnpm test -- src/state/Status.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { StatusBadge, StatusDot } from './Status';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('StatusDot', () => {
  it('is decorative without a label', () => {
    const markup = renderToStaticMarkup(<StatusDot />);

    expect(markup).toContain('class="ui-status-dot is-neutral"');
    expect(markup).toContain('aria-hidden="true"');
    expect(markup).not.toContain('role=');
  });

  it('exposes a label as an image', () => {
    const markup = renderToStaticMarkup(<StatusDot tone="running" label="Running" />);

    expect(markup).toContain('is-running');
    expect(markup).toContain('role="img"');
    expect(markup).toContain('aria-label="Running"');
    expect(markup).not.toContain('aria-hidden');
  });
});

describe('StatusBadge', () => {
  it.each([
    { tone: 'success' as const, text: 'text-tone-success' },
    { tone: 'warning' as const, text: 'text-tone-warning' },
    { tone: 'critical' as const, text: 'text-tone-critical' },
    { tone: 'info' as const, text: 'text-tone-info' },
    { tone: 'running' as const, text: 'text-tone-info' },
    { tone: 'neutral' as const, text: 'text-tone-neutral' },
  ])('colours the $tone badge and its dot', ({ tone, text }) => {
    const markup = renderToStaticMarkup(<StatusBadge tone={tone}>state</StatusBadge>);

    expect(markup).toContain(text);
    expect(markup).toContain(`ui-status-dot is-${tone}`);
    expect(markup).toContain('>state<');
  });

  it('omits the dot on request and appends className', () => {
    const markup = renderToStaticMarkup(
      <StatusBadge dot={false} className="ml-2">
        x
      </StatusBadge>,
    );

    expect(markup).not.toContain('ui-status-dot');
    expect(markup).toContain('ml-2');
  });

  it('outlines a bordered badge without a dot', () => {
    const markup = renderToStaticMarkup(
      <StatusBadge tone="success" bordered dot={false}>
        completed
      </StatusBadge>,
    );

    expect(markup).toContain('ui-status-badge is-success is-bordered');
    expect(markup).not.toContain('ui-status-dot');
  });

  it('derives tone and data-status from a raw status string', () => {
    const falsified = renderToStaticMarkup(<StatusBadge status="falsified">falsified</StatusBadge>);
    expect(falsified).toContain('text-tone-critical');
    expect(falsified).toContain('data-status="falsified"');
    expect(falsified).toContain('>falsified<');

    const invalidated = renderToStaticMarkup(
      <StatusBadge status="invalidated">invalidated</StatusBadge>,
    );
    expect(invalidated).toContain('data-status="invalidated"');

    const plain = renderToStaticMarkup(<StatusBadge>x</StatusBadge>);
    expect(plain).not.toContain('data-status');
    expect(plain).toContain('text-tone-neutral');
  });
});
