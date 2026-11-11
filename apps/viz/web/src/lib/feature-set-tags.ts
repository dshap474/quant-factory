/**
 * Primary tags for feature sets: the market sector they cover and their panel shape.
 * Sectors come from the catalog domain (for example crypto, equities, cross-asset); the shape is
 * XS (one row per asset and date, ranked across assets) or TS (one time series).
 * USAGE: featureSetSector(item.domain); featureSetShape(item.asset_column).label
 */

// --------------------------------------------------------------------------- #
// Tags
// --------------------------------------------------------------------------- #

const SECTORS: Record<string, string> = {
  btc: 'Crypto',
  crypto: 'Crypto',
  equities: 'Equities',
  etf: 'Equities',
  cross_asset: 'Cross-asset',
  macro: 'Macro',
};

export function featureSetSector(domain: string | null | undefined): string | null {
  return domain ? (SECTORS[domain.toLowerCase()] ?? null) : null;
}

export interface FeatureSetShape {
  label: 'XS' | 'TS';
  title: string;
}

export function featureSetShape(assetPanel: boolean): FeatureSetShape {
  return assetPanel
    ? { label: 'XS', title: 'Cross-sectional: one row per asset and date' }
    : { label: 'TS', title: 'Time series: one row per date' };
}

/** Drop a leading "Cross Sectional" from a label once the XS tag says it. */
export function featureSetLabel(label: string, assetPanel: boolean): string {
  return assetPanel ? label.replace(/^cross[\s_-]?sectional\s+/i, '') : label;
}
