/**
 * Semantic CSS-token resolution for qf-charts.
 *
 * Token values are full colours (`oklch(...)`, `color-mix(...)`, `rgb(...)`); a bare HSL
 * triplet from a legacy host still resolves through `hsl()`. In a browser every resolved
 * colour is normalized to `rgba()` through a 1x1 canvas readback, because zrender's colour
 * math (emphasis lift, alpha modification) parses only hex, rgb and hsl.
 *
 * USAGE:
 *   const color = resolveChartColor('--qf-chart-axis', 'rgb(255 255 255 / 0.12)');
 *   const fill = resolveChartColor('--qf-chart-1', QF_DARK_THEME.palette[0], 0.2);
 */

// --------------------------------------------------------------------------- #
// Theme signature and cache invalidation
// --------------------------------------------------------------------------- #

// Option builds read tokens dozens of times per chart; getComputedStyle forces a
// style recalc per call, so resolved values are cached under a signature of every
// theming input (color scheme plus the root element's theme-bearing class and data
// attributes). A signature change keys fresh entries, and `qf:chart-theme-change`
// (the package's escape hatch for out-of-band stylesheet swaps, also observed by
// useChartTheme) clears both caches outright.
let lightSchemeQuery: MediaQueryList | null = null;
const resolvedColors = new Map<string, string>();
const resolvedTokens = new Map<string, string>();

function themeSignature(): string {
  const root = document.documentElement;
  lightSchemeQuery ??= window.matchMedia('(prefers-color-scheme: light)');
  const scheme = lightSchemeQuery.matches ? 'light' : 'dark';
  const data = root.dataset;
  return `${scheme}:${root.className}:${data.theme ?? ''}:${data.stylePreset ?? ''}:${data.density ?? ''}:${data.contrast ?? ''}`;
}

if (typeof window !== 'undefined') {
  window.addEventListener('qf:chart-theme-change', () => {
    resolvedColors.clear();
    resolvedTokens.clear();
  });
}

// --------------------------------------------------------------------------- #
// Token resolution
// --------------------------------------------------------------------------- #

let colorProbe: HTMLSpanElement | null = null;

function probeForColor(): HTMLSpanElement {
  if (colorProbe?.isConnected) return colorProbe;
  colorProbe = document.createElement('span');
  colorProbe.style.display = 'none';
  colorProbe.setAttribute('aria-hidden', 'true');
  document.body.appendChild(colorProbe);
  return colorProbe;
}

export function readChartToken(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  const cacheKey = `${themeSignature()}:${name}`;
  const cached = resolvedTokens.get(cacheKey);
  // The raw (possibly empty) value is cached and the fallback applied per call, so
  // callers passing different fallbacks for the same unset token stay independent.
  if (cached != null) return cached || fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  resolvedTokens.set(cacheKey, value);
  return value || fallback;
}

// Any hex or functional colour (`oklch(`, `color-mix(`, `var(`, `rgb(`, ...) is a full colour.
const FULL_COLOR = /^(#|[a-z-]+\()/i;

export function resolveChartColor(name: string, fallback: string, alpha?: number): string {
  const value = readChartToken(name, fallback);
  if (FULL_COLOR.test(value)) {
    const percent = alpha == null ? null : Math.round(alpha * 1000) / 10;
    const composed =
      percent == null ? value : `color-mix(in oklch, ${value} ${percent}%, transparent)`;
    return canvasSafeColor(composed);
  }
  return canvasSafeColor(alpha == null ? `hsl(${value})` : `hsl(${value} / ${alpha})`);
}

// ECharts draws text to canvas, where a CSS custom property is not resolvable: the
// font family handed to it must already be a concrete family list. Chart text is the
// token sans; the mono data face is kept for callers that render identifiers.
export const QF_CHART_FONT_SANS_FALLBACK =
  '"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif';
export const QF_CHART_FONT_DATA_FALLBACK = 'ui-monospace, "SFMono-Regular", Consolas, monospace';

export function resolveChartFont(): string {
  return readChartToken('--qf-chart-font-sans', QF_CHART_FONT_SANS_FALLBACK);
}

export function resolveChartDataFont(): string {
  return readChartToken('--qf-chart-font-data', QF_CHART_FONT_DATA_FALLBACK);
}

export function resolveCssColor(value: string): string {
  if (typeof document === 'undefined') return value;
  const cacheKey = `${themeSignature()}:${value}`;
  const cached = resolvedColors.get(cacheKey);
  if (cached) return cached;
  const probe = probeForColor();
  probe.style.color = value;
  const resolved = getComputedStyle(probe).color || value;
  const result = readBackColor(resolved) ?? resolved;
  resolvedColors.set(cacheKey, result);
  return result;
}

// --------------------------------------------------------------------------- #
// Canvas-safe normalization
// --------------------------------------------------------------------------- #

let paintContext: CanvasRenderingContext2D | null | undefined;

function paintCanvas(): CanvasRenderingContext2D | null {
  if (paintContext !== undefined) return paintContext;
  paintContext = null;
  if (typeof document === 'undefined') return null;
  try {
    const canvas = document.createElement('canvas');
    canvas.width = 1;
    canvas.height = 1;
    paintContext = canvas.getContext('2d', { willReadFrequently: true });
  } catch {
    paintContext = null;
  }
  return paintContext;
}

// Paint the colour into a 1x1 canvas and read the pixel back. A colour the canvas rejects
// leaves the sentinel fill style in place, so the caller keeps its own value.
const SENTINEL_FILL = '#010203';

function readBackColor(color: string): string | null {
  const context = paintCanvas();
  if (!context) return null;
  try {
    context.fillStyle = SENTINEL_FILL;
    context.fillStyle = color;
    if (context.fillStyle === SENTINEL_FILL) return null;
    context.clearRect(0, 0, 1, 1);
    context.fillRect(0, 0, 1, 1);
    const [r = 0, g = 0, b = 0, a = 0] = context.getImageData(0, 0, 1, 1).data;
    return `rgba(${r}, ${g}, ${b}, ${Math.round((a / 255) * 1000) / 1000})`;
  } catch {
    return null;
  }
}

/** A colour ECharts can do math on: `rgba()` in a browser, the value itself without a canvas. */
function canvasSafeColor(value: string): string {
  if (!paintCanvas()) return value;
  return resolveCssColor(value);
}
