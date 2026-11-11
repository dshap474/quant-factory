/**
 * Public qf-charts theme exports.
 *
 * USAGE:
 *   import { chartColor, useChartTheme } from '@quant-factory/qf-ui/charts/theme';
 */

// --------------------------------------------------------------------------- #
// Exports
// --------------------------------------------------------------------------- #

export { type QfChartTheme, useChartTheme } from '../hooks/useChartTheme';
export {
  CHART_PALETTE_SIZE,
  chartColor,
  chartPaletteColor,
  chartStatusColor,
  type QfChartColorName,
  type QfChartPaletteSlot,
  type QfChartTone,
  withOpacity,
} from './chartColor';
export { QF_DARK_THEME, QF_LIGHT_THEME, type QfThemeDefaults } from './defaults';
export { readChartToken, resolveChartColor, resolveCssColor } from './tokens';
