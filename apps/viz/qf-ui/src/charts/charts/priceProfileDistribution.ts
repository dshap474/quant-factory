/** Horizontal distributions sharing the main chart price axis.
 * USAGE: internal PriceProfileChart profileSeries(profile, hidden).
 */
// --------------------------------------------------------------------------- #
// Imports and constants
// --------------------------------------------------------------------------- #
import { QF_CHART_RULE_WIDTH } from '../core/geometry';
import { chartColor, withOpacity } from '../theme/chartColor';
import { resolveCssColor } from '../theme/tokens';
import type { PriceProfileDistribution } from './priceProfileTypes';

/** Filled profile: value-band rows in the profile colour, the rest in the neutral tone. */
const PROFILE_BAND_OPACITY = 0.55;
const PROFILE_NEUTRAL_OPACITY = 0.35;
/** Outlined comparison profile: faint stroke over a near-transparent fill. */
const PROFILE_OUTLINE_OPACITY = 0.58;
const PROFILE_OUTLINE_FILL_OPACITY = 0.05;
// --------------------------------------------------------------------------- #
// Distribution layer
// --------------------------------------------------------------------------- #
interface RenderApi {
  value: (dim: number) => number;
  coord: (point: [number, number]) => [number, number];
}

/** Legend and outline colour of a profile: outlined profiles recede to a faint stroke. */
export function profileLegendColor(profile: PriceProfileDistribution): string {
  return profile.variant === 'outline'
    ? withOpacity(profile.color, PROFILE_OUTLINE_OPACITY)
    : profile.color;
}

export function profileSeries(profile: PriceProfileDistribution, hidden: boolean, overlay = false) {
  const outlined = profile.variant === 'outline';
  const band = profile.band;
  const opacity = (overlay ? 0.4 : 1) * Math.max(0, Math.min(1, profile.opacity ?? 1));
  const fill = resolveCssColor(
    outlined
      ? withOpacity(profile.color, PROFILE_OUTLINE_FILL_OPACITY * opacity)
      : withOpacity(
          band ? chartColor('label') : profile.color,
          (band ? PROFILE_NEUTRAL_OPACITY : PROFILE_BAND_OPACITY) * opacity,
        ),
  );
  const bandFill = outlined
    ? fill
    : resolveCssColor(withOpacity(profile.color, PROFILE_BAND_OPACITY * opacity));
  const outline = outlined
    ? resolveCssColor(withOpacity(profileLegendColor(profile), profile.opacity))
    : null;
  return {
    id: `profile:${profile.key}`,
    name: profile.label,
    type: 'custom',
    z: overlay ? 0 : 2,
    xAxisIndex: 1,
    yAxisIndex: 1,
    silent: true,
    clip: true,
    emphasis: { disabled: true },
    encode: { x: 1, y: 0 },
    data: hidden ? [] : profile.rows.map(([price, mass]) => [price, mass]),
    renderItem: (_params: unknown, api: RenderApi) => {
      const price = api.value(0);
      const mass = api.value(1);
      const top = api.coord([0, price + profile.rowSize / 2]);
      const bottom = api.coord([0, price - profile.rowSize / 2]);
      const start = api.coord([0, price]);
      const end = api.coord([mass, price]);
      const inBand = band != null && price >= band[0] && price <= band[1];
      return {
        type: 'rect',
        shape: {
          x: start[0],
          y: Math.min(top[1], bottom[1]),
          width: Math.max(1, end[0] - start[0]),
          height: Math.max(1, Math.abs(bottom[1] - top[1])),
        },
        style: outline
          ? { fill, stroke: outline, lineWidth: QF_CHART_RULE_WIDTH }
          : { fill: inBand ? bandFill : fill },
      };
    },
  };
}
