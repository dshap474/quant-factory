/**
 * Pins every humanize rule and the four reference examples.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/humanize.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import { humanize } from './humanize';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('humanize', () => {
  it('renders the reference examples', () => {
    expect(humanize('equities_quality-value')).toBe('Equities quality value');
    expect(humanize('macro_yield-curve-long-flat')).toBe('Macro yield curve long-flat');
    expect(humanize('not_tested')).toBe('Not tested');
    expect(humanize('v012')).toBe('v012');
  });

  it('normalizes on-chain and on_chain to onchain', () => {
    expect(humanize('on-chain_flows')).toBe('Onchain flows');
    expect(humanize('btc_on_chain')).toBe('BTC onchain');
    expect(humanize('ON-CHAIN')).toBe('Onchain');
  });

  it('turns underscores and stray hyphens into spaces', () => {
    expect(humanize('relative_strength-ta')).toBe('Relative strength TA');
    expect(humanize('signal--strength')).toBe('Signal strength');
  });

  it('keeps allowlisted compounds hyphenated', () => {
    expect(humanize('walk-forward_out-of-sample')).toBe('Walk-forward out-of-sample');
    expect(humanize('long-short_book')).toBe('Long-short book');
  });

  it('uppercases acronyms and keeps versions lowercase and digit tokens as written', () => {
    expect(humanize('ML_engine')).toBe('ML engine');
    expect(humanize('lgbm_ic_v012')).toBe('LGBM IC v012');
    expect(humanize('btc_etf_ml')).toBe('BTC ETF ML');
    expect(humanize('ema5_3_1x')).toBe('ema5 3 1x');
    expect(humanize('BASELINE')).toBe('Baseline');
  });

  it('sentence-cases the first word only', () => {
    expect(humanize('NOT_TESTED')).toBe('Not tested');
    expect(humanize('')).toBe('');
  });
});
