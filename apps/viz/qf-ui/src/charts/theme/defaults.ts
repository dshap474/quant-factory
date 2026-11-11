/**
 * Dark and light semantic defaults matching the Viz chart palette.
 *
 * USAGE:
 *   import { QF_DARK_THEME } from '@quant-factory/qf-ui/charts/theme';
 */

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface QfThemeDefaults {
  /** Card surface: header, plot canvas and legend share it. */
  surface: string;
  grid: string;
  gridOpacity: number;
  axis: string;
  /** Hover crosshair rule. */
  crosshair: string;
  /** Tick-label colour, one step under `label` so the axes recede behind the data. */
  axisLabel: string;
  label: string;
  tooltipBackground: string;
  tooltipBorder: string;
  tooltipText: string;
  benchmark: string;
  focus: string;
  palette: readonly string[];
}

// --------------------------------------------------------------------------- #
// Defaults
// --------------------------------------------------------------------------- #

export const QF_DARK_THEME: QfThemeDefaults = {
  surface: 'oklch(0.19 0.006 60)',
  // A host token is an exact colour, so no opacity is layered on the grid.
  grid: 'rgb(255 255 255 / 0.07)',
  gridOpacity: 1,
  axis: 'rgb(255 255 255 / 0.12)',
  crosshair: 'rgb(255 255 255 / 0.32)',
  axisLabel: 'oklch(0.71 0.004 90)',
  label: 'oklch(0.78 0.004 90)',
  tooltipBackground: 'oklch(0.245 0.006 60)',
  tooltipBorder: 'rgb(255 255 255 / 0.08)',
  tooltipText: 'oklch(0.93 0.003 90)',
  benchmark: 'oklch(0.72 0.005 90)',
  focus: 'oklch(0.78 0.12 250)',
  // Series 1 is the brand gold (--color-primary); the rotation mirrors tokens.css.
  palette: [
    'oklch(0.895 0.092 77)',
    'oklch(0.76 0.12 250)',
    'oklch(0.8 0.11 180)',
    'oklch(0.75 0.13 300)',
    'oklch(0.76 0.14 25)',
    'oklch(0.8 0.13 145)',
    'oklch(0.76 0.13 350)',
    'oklch(0.8 0.1 220)',
    'oklch(0.72 0.15 50)',
    'oklch(0.63 0.13 265)',
    'oklch(0.65 0.1 195)',
    'oklch(0.62 0.13 315)',
    'oklch(0.62 0.15 15)',
    'oklch(0.65 0.13 155)',
    'oklch(0.62 0.14 335)',
    'oklch(0.64 0.11 235)',
    'oklch(0.86 0.07 235)',
    'oklch(0.88 0.08 165)',
    'oklch(0.86 0.07 290)',
    'oklch(0.87 0.08 40)',
  ],
};

export const QF_LIGHT_THEME: QfThemeDefaults = {
  surface: 'hsl(0 0% 100%)',
  grid: 'hsl(214 14% 93%)',
  gridOpacity: 1,
  axis: 'hsl(214 12% 64%)',
  crosshair: 'hsl(214 12% 64%)',
  axisLabel: 'hsl(214 12% 38%)',
  label: 'hsl(214 12% 38%)',
  tooltipBackground: 'hsl(0 0% 100%)',
  tooltipBorder: 'hsl(214 14% 72%)',
  tooltipText: 'hsl(214 18% 16%)',
  benchmark: 'hsl(214 8% 42%)',
  focus: 'hsl(214 72% 42%)',
  palette: QF_DARK_THEME.palette,
};
