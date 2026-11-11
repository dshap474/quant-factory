/**
 * Design token readers for JS consumers of CSS @theme variables.
 *
 * USAGE:
 *   import { CHART_PALETTE_VARS } from '@quant-factory/qf-ui';
 *   const color = `var(${CHART_PALETTE_VARS[0]})`;
 *   applyQfTheme('slate');
 */

// --------------------------------------------------------------------------- #
// Chart palette
// --------------------------------------------------------------------------- #

export const CHART_PALETTE_VARS = [
  '--color-chart-1',
  '--color-chart-2',
  '--color-chart-3',
  '--color-chart-4',
  '--color-chart-5',
  '--color-chart-6',
  '--color-chart-7',
  '--color-chart-8',
  '--color-chart-9',
  '--color-chart-10',
  '--color-chart-11',
  '--color-chart-12',
  '--color-chart-13',
  '--color-chart-14',
  '--color-chart-15',
  '--color-chart-16',
  '--color-chart-17',
  '--color-chart-18',
  '--color-chart-19',
  '--color-chart-20',
] as const;

// --------------------------------------------------------------------------- #
// Theme palettes
// --------------------------------------------------------------------------- #

/** Palettes selectable through `data-theme` on <html>; `sand` is the default (no attribute). */
export const QF_THEMES = [
  { id: 'sand', label: 'Sand' },
  { id: 'slate', label: 'Slate' },
  { id: 'graphite', label: 'Graphite' },
  { id: 'amethyst', label: 'Amethyst' },
] as const;

export type QfThemeId = (typeof QF_THEMES)[number]['id'];

export const QF_DEFAULT_THEME: QfThemeId = 'sand';

export function isQfThemeId(value: unknown): value is QfThemeId {
  return QF_THEMES.some((theme) => theme.id === value);
}

/** Set the palette on <html>; the default removes the attribute. */
export function applyQfTheme(theme: QfThemeId): void {
  const root = document.documentElement;
  if (theme === QF_DEFAULT_THEME) root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', theme);
}
