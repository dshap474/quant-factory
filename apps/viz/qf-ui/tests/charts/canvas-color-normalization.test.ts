/**
 * Canvas-safe colour normalization: with a 2D context available, resolved chart colours are
 * painted into a 1x1 canvas and read back as `rgba()`, so zrender's colour math can parse
 * them. jsdom has no canvas, so the context is stubbed here.
 *
 * USAGE:
 *   pnpm exec vitest run tests/charts/canvas-color-normalization.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { resolveChartColor, resolveCssColor } from '../../src/charts/theme/tokens';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

// A stub 2D context: it accepts every fill style unless `rejectAll` is set, and always reads
// back one half-transparent pixel.
const stubContext = {
  fill: '#000000',
  rejectAll: false,
  get fillStyle(): string {
    return this.fill;
  },
  set fillStyle(value: string) {
    if (!this.rejectAll || value === '#010203') this.fill = value;
  },
  clearRect: () => undefined,
  fillRect: () => undefined,
  getImageData: () => ({ data: new Uint8ClampedArray([10, 20, 30, 128]) }),
};

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('canvas colour normalization', () => {
  beforeAll(() => {
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
      configurable: true,
      value: () => stubContext,
    });
  });

  afterAll(() => {
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
      configurable: true,
      value: () => null,
    });
  });

  it('reads a resolved colour back as rgba()', () => {
    expect(resolveCssColor('oklch(0.77 0.125 245)')).toBe('rgba(10, 20, 30, 0.502)');
  });

  it('sends a composed alpha colour from resolveChartColor through the same readback', () => {
    expect(resolveChartColor('--qf-chart-unset-for-test', 'oklch(0.7 0.14 290)', 0.5)).toBe(
      'rgba(10, 20, 30, 0.502)',
    );
  });

  it('keeps the probe result when the canvas rejects the colour', () => {
    const value = 'oklch(0.64 0.12 45)';
    const probe = document.createElement('span');
    document.body.appendChild(probe);
    probe.style.color = value;
    const expected = getComputedStyle(probe).color || value;
    probe.remove();

    stubContext.rejectAll = true;
    try {
      expect(resolveCssColor(value)).toBe(expected);
    } finally {
      stubContext.rejectAll = false;
    }
  });
});
