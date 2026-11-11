/**
 * Tone vocabulary tests: class maps, signTone, statusTone, and the contrast floor of the
 * colour tokens resolved from styles/tokens.css. Contrast is pinned two ways: WCAG 2.x
 * ratios (tones on every core surface and on their own tinted surface, the focus ring,
 * brand-foreground on brand) and APCA-W3 0.0.98G lightness contrast (tones and the text
 * ladder on the core surfaces and on the translucent state fills).
 *
 * Colour resolution is a small CSS subset evaluated in the test: `oklch(L C H)`, `var(--x)`,
 * `color-mix(in oklch, A p%, B)` and `color-mix(in oklab, A p%, B)`. An oklch mix interpolates
 * L, C and hue (shorter arc); an oklab mix interpolates L, a and b linearly, as CSS does, with
 * both operands treated as opaque. Translucent `rgb(r g b / a)` fills are composited in
 * gamma-encoded sRGB over a resolved base, as browsers paint them. Colours convert through
 * oklab to sRGB with out-of-gamut channels clamped, which differs from CSS gamut mapping only
 * negligibly for these in-gamut, low-chroma tokens.
 *
 * Exemptions: `--color-fg-disabled` is exempt from every floor (disabled text is not required
 * to be legible). Tone text on a state fill composited over the overlay surface is a known
 * flag (APCA Lc about 54), so it is not asserted.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/tone.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  STATUS_TONES,
  signTone,
  statusTone,
  TONES,
  type Tone,
  toneSurfaceClass,
  toneTextClass,
} from './tone';

// --------------------------------------------------------------------------- #
// Token parsing and colour resolution
// --------------------------------------------------------------------------- #

interface Oklch {
  l: number;
  c: number;
  h: number;
}

/** Gamma-encoded sRGB channels in 0..1. */
type Rgb = readonly [number, number, number];

const TOKENS_PATH = resolve(dirname(fileURLToPath(import.meta.url)), '../styles/tokens.css');

function parseTokens(css: string): Map<string, string> {
  const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const tokens = new Map<string, string>();
  for (const match of withoutComments.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    const name = match[1];
    const value = match[2];
    if (name && value && !tokens.has(name)) tokens.set(name, value.replace(/\s+/g, ' ').trim());
  }
  return tokens;
}

/** Split `a, b, c` at top-level commas (color-mix operands contain nested parentheses). */
function splitTopLevel(text: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === '(') depth += 1;
    else if (ch === ')') depth -= 1;
    else if (ch === ',' && depth === 0) {
      parts.push(text.slice(start, i).trim());
      start = i + 1;
    }
  }
  parts.push(text.slice(start).trim());
  return parts;
}

function mixHue(a: number, b: number, weightA: number): number {
  let delta = b - a;
  if (delta > 180) delta -= 360;
  if (delta < -180) delta += 360;
  return (a + delta * (1 - weightA) + 360) % 360;
}

function mixOklab(a: Oklch, b: Oklch, weightA: number): Oklch {
  const toLab = ({ l, c, h }: Oklch) => {
    const hue = (h * Math.PI) / 180;
    return [l, c * Math.cos(hue), c * Math.sin(hue)] as const;
  };
  const [la, aa, ba] = toLab(a);
  const [lb, ab, bb] = toLab(b);
  const l = la * weightA + lb * (1 - weightA);
  const labA = aa * weightA + ab * (1 - weightA);
  const labB = ba * weightA + bb * (1 - weightA);
  const h = ((Math.atan2(labB, labA) * 180) / Math.PI + 360) % 360;
  return { l, c: Math.hypot(labA, labB), h };
}

function resolveValue(value: string, tokens: Map<string, string>): string {
  const text = value.trim();
  const variable = text.match(/^var\((--[\w-]+)\)$/);
  if (!variable?.[1]) return text;
  const target = tokens.get(variable[1]);
  if (target === undefined) throw new Error(`unresolved token ${variable[1]}`);
  return resolveValue(target, tokens);
}

function resolveColor(value: string, tokens: Map<string, string>): Oklch {
  const text = resolveValue(value, tokens);
  const oklch = text.match(/^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)$/);
  if (oklch) return { l: Number(oklch[1]), c: Number(oklch[2]), h: Number(oklch[3]) };
  const mix = text.match(/^color-mix\((.*)\)$/);
  if (mix?.[1]) {
    const [space, first, second] = splitTopLevel(mix[1]);
    if ((space !== 'in oklch' && space !== 'in oklab') || !first || !second) {
      throw new Error(`unsupported mix: ${text}`);
    }
    const share = first.match(/^(.*)\s+([\d.]+)%$/);
    if (!share?.[1] || !share[2]) throw new Error(`mix needs an explicit percentage: ${text}`);
    const weightA = Number(share[2]) / 100;
    const a = resolveColor(share[1], tokens);
    const b = resolveColor(second, tokens);
    if (space === 'in oklab') return mixOklab(a, b, weightA);
    return {
      l: a.l * weightA + b.l * (1 - weightA),
      c: a.c * weightA + b.c * (1 - weightA),
      h: mixHue(a.h, b.h, weightA),
    };
  }
  throw new Error(`unsupported colour: ${text}`);
}

function toLinear(channel: number): number {
  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
}

function toGamma(channel: number): number {
  return channel <= 0.0031308 ? channel * 12.92 : 1.055 * channel ** (1 / 2.4) - 0.055;
}

function toRgb({ l, c, h }: Oklch): Rgb {
  const hue = (h * Math.PI) / 180;
  const a = c * Math.cos(hue);
  const b = c * Math.sin(hue);
  const l3 = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m3 = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s3 = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const clamp = (x: number) => Math.min(1, Math.max(0, x));
  return [
    toGamma(clamp(4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3)),
    toGamma(clamp(-1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3)),
    toGamma(clamp(-0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3)),
  ];
}

/** Composite a translucent `rgb(r g b / a)` fill over an opaque base in gamma-encoded sRGB. */
function composite(fill: string, base: Rgb, tokens: Map<string, string>): Rgb {
  const text = resolveValue(fill, tokens);
  const rgb = text.match(/^rgb\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\/\s*([\d.]+)\s*\)$/);
  if (!rgb) throw new Error(`unsupported fill: ${text}`);
  const alpha = Number(rgb[4]);
  const channel = (index: number) => Number(rgb[index + 1]) / 255;
  return [0, 1, 2].map(
    (index) => channel(index) * alpha + (base[index] ?? 0) * (1 - alpha),
  ) as unknown as Rgb;
}

function relativeLuminance(rgb: Rgb): number {
  const [r, g, b] = rgb.map(toLinear) as unknown as Rgb;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: Oklch | Rgb, b: Oklch | Rgb): number {
  const la = relativeLuminance(Array.isArray(a) ? (a as Rgb) : toRgb(a as Oklch));
  const lb = relativeLuminance(Array.isArray(b) ? (b as Rgb) : toRgb(b as Oklch));
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** APCA-W3 0.0.98G lightness contrast, returned as |Lc| (0..~108). */
function apca(text: Oklch | Rgb, background: Oklch | Rgb): number {
  const luminance = (color: Oklch | Rgb) => {
    const [r, g, b] = Array.isArray(color) ? (color as Rgb) : toRgb(color as Oklch);
    const y = 0.2126729 * r ** 2.4 + 0.7151522 * g ** 2.4 + 0.072175 * b ** 2.4;
    // biome-ignore lint/suspicious/noApproximativeNumericConstant: APCA's blkClmp is 1.414, not the square root of two.
    return y < 0.022 ? y + (0.022 - y) ** 1.414 : y;
  };
  const yText = luminance(text);
  const yBackground = luminance(background);
  if (Math.abs(yBackground - yText) < 0.0005) return 0;
  if (yBackground > yText) {
    const sapc = (yBackground ** 0.56 - yText ** 0.57) * 1.14;
    return sapc < 0.1 ? 0 : (sapc - 0.027) * 100;
  }
  const sapc = (yBackground ** 0.65 - yText ** 0.62) * 1.14;
  return sapc > -0.1 ? 0 : Math.abs(sapc + 0.027) * 100;
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('tone contrast (styles/tokens.css)', () => {
  const tokens = parseTokens(readFileSync(TOKENS_PATH, 'utf8'));
  const color = (name: string) => resolveColor(`var(--color-${name})`, tokens);
  const background = color('background');
  const SURFACES = ['sunken', 'canvas', 'raised', 'overlay'] as const;
  const STATE_FILLS = ['hover', 'pressed', 'selected', 'selected-hover'] as const;
  const surfaceCases = SURFACES.map((surface) => [surface, color(`surface-${surface}`)] as const);
  // The four state fills composited over sunken and over raised (overlay is a known flag).
  const stateCases = (['sunken', 'raised'] as const).flatMap((base) =>
    STATE_FILLS.map(
      (fill) =>
        [
          `${fill} over ${base}`,
          composite(`var(--color-state-${fill})`, toRgb(color(`surface-${base}`)), tokens),
        ] as const,
    ),
  );

  it('resolves colours the way CSS defines them', () => {
    // color-mix at 0% keeps B, at 100% keeps A.
    expect(
      resolveColor('color-mix(in oklch, oklch(0.8 0.1 40) 100%, oklch(0.2 0 0))', tokens).l,
    ).toBeCloseTo(0.8);
    expect(
      resolveColor('color-mix(in oklch, oklch(0.8 0.1 40) 0%, oklch(0.2 0 0))', tokens).l,
    ).toBeCloseTo(0.2);
    // An oklab mix interpolates a and b, not hue: blue over warm sand stays blue.
    const mixed = resolveColor(
      'color-mix(in oklab, oklch(0.78 0.12 250) 12%, oklch(0.205 0.004 90))',
      tokens,
    );
    expect(mixed.l).toBeCloseTo(0.274, 3);
    expect(mixed.c).toBeCloseTo(0.0112, 3);
    expect(mixed.h).toBeCloseTo(244, 0);
    // Black on white is the WCAG maximum, 21:1; APCA reads about Lc 106 / 108.
    expect(contrast({ l: 0, c: 0, h: 0 }, { l: 1, c: 0, h: 0 })).toBeCloseTo(21, 0);
    expect(apca({ l: 0, c: 0, h: 0 }, { l: 1, c: 0, h: 0 })).toBeCloseTo(106.04, 1);
    expect(apca({ l: 1, c: 0, h: 0 }, { l: 0, c: 0, h: 0 })).toBeCloseTo(107.88, 1);
    // A translucent white fill composites in gamma space: 50% over black is mid grey.
    expect(composite('rgb(255 255 255 / 0.5)', [0, 0, 0], tokens)[0]).toBeCloseTo(0.5);
  });

  it.each(TONES)('%s text meets 4.5:1 on the canvas', (tone) => {
    expect(contrast(color(`tone-${tone}`), background)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(TONES)('%s text meets 4.5:1 on its own surface', (tone) => {
    expect(contrast(color(`tone-${tone}`), color(`tone-${tone}-surface`))).toBeGreaterThanOrEqual(
      4.5,
    );
  });

  it.each(
    TONES.flatMap((tone) => surfaceCases.map(([name, bg]) => [tone, name, bg] as const)),
  )('%s text meets 4.5:1 on the %s surface', (tone, _name, bg) => {
    expect(contrast(color(`tone-${tone}`), bg)).toBeGreaterThanOrEqual(4.5);
  });

  const apcaTexts = [...TONES.map((tone) => `tone-${tone}`), 'fg-tertiary'];
  it.each(
    apcaTexts.flatMap((text) =>
      [...surfaceCases, ...stateCases].map(([name, bg]) => [text, name, bg] as const),
    ),
  )('%s reaches APCA Lc 55 on %s', (text, _name, bg) => {
    expect(apca(color(text), bg)).toBeGreaterThanOrEqual(55);
  });

  it.each(surfaceCases)('fg-primary reaches Lc 75 and fg-secondary Lc 60 on %s', (_name, bg) => {
    expect(apca(color('fg-primary'), bg)).toBeGreaterThanOrEqual(75);
    expect(apca(color('fg-secondary'), bg)).toBeGreaterThanOrEqual(60);
  });

  it.each([
    ...surfaceCases,
    ['control', color('surface-control')] as const,
  ])('the focus ring meets 3:1 on %s', (_name, bg) => {
    expect(contrast(color('focus-ring'), bg)).toBeGreaterThanOrEqual(3);
  });

  it('brand-foreground meets 4.5:1 on brand', () => {
    expect(contrast(color('brand-foreground'), color('brand'))).toBeGreaterThanOrEqual(4.5);
  });
});

describe('tone class maps', () => {
  it.each(TONES)('maps %s onto the tone utilities', (tone: Tone) => {
    expect(toneTextClass(tone)).toBe(`text-tone-${tone}`);
    expect(toneSurfaceClass(tone)).toContain(`bg-tone-${tone}-surface`);
    expect(toneSurfaceClass(tone)).toContain(`border-tone-${tone}-border`);
  });

  it('defaults to neutral', () => {
    expect(toneTextClass()).toBe('text-tone-neutral');
    expect(toneSurfaceClass()).toContain('bg-tone-neutral-surface');
  });
});

describe('signTone', () => {
  it.each([
    [1, 'success'],
    [0.0001, 'success'],
    [-1, 'critical'],
    [-0.0001, 'critical'],
    [0, 'neutral'],
    [-0, 'neutral'],
    [Number.NaN, 'neutral'],
    [null, 'neutral'],
    [undefined, 'neutral'],
  ] as const)('maps %s to %s', (value, expected) => {
    expect(signTone(value)).toBe(expected);
  });

  it('maps infinities by sign', () => {
    expect(signTone(Number.POSITIVE_INFINITY)).toBe('success');
    expect(signTone(Number.NEGATIVE_INFINITY)).toBe('critical');
  });
});

describe('statusTone', () => {
  const TABLE: Record<Tone, readonly string[]> = {
    success: [
      'supported',
      'succeeded',
      'completed',
      'complete',
      'success',
      'baseline',
      'promoted',
      'healthy',
      'live',
      'ok',
      'updated',
      'passing',
      'enabled',
    ],
    info: ['descriptive', 'running', 'starting', 'checking', 'delayed', 'recovering'],
    neutral: [
      'not_tested',
      'candidate',
      'queued',
      'pending',
      'registered',
      'published',
      'unchanged',
      'unknown',
      'offline',
      'paused',
      'stopped',
      'skipped',
      'cancelled',
      'never',
      'monitored',
      'not_monitored',
      'unregistered',
      'disabled',
      'idle',
    ],
    warning: [
      'inconclusive',
      'warning',
      'stale',
      'partial',
      'unavailable',
      'degraded',
      'missing',
      'attention',
      'incomplete',
    ],
    critical: [
      'falsified',
      'failed',
      'failure',
      'error',
      'rejected',
      'invalidated',
      'interrupted',
      'unresponsive',
      'failing',
      'breach',
      'expired',
      'wrong_schema',
    ],
  };
  const rows = TONES.flatMap((tone) => TABLE[tone].map((status) => [status, tone] as const));

  it.each(rows)('maps %s to %s', (status, tone) => {
    expect(statusTone(status)).toBe(tone);
  });

  it('holds exactly the table', () => {
    expect(Object.keys(STATUS_TONES)).toHaveLength(rows.length);
  });

  it('normalizes case, spaces and hyphens', () => {
    expect(statusTone('NOT TESTED')).toBe('neutral');
    expect(statusTone('not-tested')).toBe('neutral');
    expect(statusTone('Falsified')).toBe('critical');
  });

  it('falls back to neutral', () => {
    expect(statusTone(undefined)).toBe('neutral');
    expect(statusTone(null)).toBe('neutral');
    expect(statusTone('')).toBe('neutral');
    expect(statusTone('mystery')).toBe('neutral');
  });
});
