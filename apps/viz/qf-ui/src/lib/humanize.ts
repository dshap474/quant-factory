/**
 * Slug-to-label helper: turns `equities_quality-value` into `Equities quality value`.
 * Opt-in only. No qf-ui component calls it, and it must never be applied to ids, hashes
 * or paths.
 *
 * Rules, in order:
 *   1. "on" + "chain" joined by a hyphen or underscore becomes `onchain`.
 *   2. Underscores become spaces.
 *   3. Hyphens become spaces, except inside an allowlisted compound (`long-flat`, ...).
 *   4. Words are lowercased, except known acronyms (uppercased), version tokens such as
 *      `v012` (kept lowercase) and other tokens with digits (kept as written).
 *   5. The first letter is capitalized (sentence case) unless the first word is a
 *      version or digit token.
 *
 * `familyName` is the title-case sibling for `<sector>_<kebab-name>` family slugs: a known
 * sector before the first `_` becomes the uppercased sector, the rest the name in title
 * case with the same acronyms and small words (`of`, `the`, ...) lowercased mid-name. A
 * slug with no `_` is title-cased with no sector; any other slug (an unknown or trailing
 * sector, as in a legacy `quality-value_equities`) is returned verbatim, so a
 * legacy family never reads as a convention one.
 *
 * USAGE:
 *   import { familyName, humanize } from '@quant-factory/qf-ui';
 *   humanize('macro_yield-curve-long-flat');      // 'Macro yield curve long-flat'
 *   humanize('not_tested');                         // 'Not tested'
 *   familyName('equities_quality-value');    // { sector: 'EQUITIES', name: 'Quality Value' }
 *   familyName('example-trend');                    // { sector: null, name: 'Example Trend' }
 *   familyName('quality-value_equities');  // { sector: null, name: 'quality-value_equities' }
 */

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

const HUMANIZE_COMPOUNDS: readonly (readonly string[])[] = [
  ['out', 'of', 'sample'],
  ['factor', 'neutral'],
  ['long', 'flat'],
  ['long', 'short'],
  ['cross', 'asset'],
  ['walk', 'forward'],
];

const HUMANIZE_ACRONYMS = new Set([
  'btc',
  'eth',
  'usd',
  'usdc',
  'xs',
  'ta',
  'ml',
  'ic',
  'api',
  'mdd',
  'cagr',
  'pit',
  'ttm',
  'etf',
  'lgbm',
  'ai',
  'kg',
  'twap',
  'vwap',
]);

// `\b` treats `_` as a word character, so slug separators bound the pair explicitly.
/** Sectors that may lead a `<sector>_<kebab-name>` family slug. */
const FAMILY_SECTORS = new Set(['crypto', 'equities', 'cross-asset', 'macro', 'onchain']);

const TITLE_SMALL_WORDS = new Set([
  'a',
  'an',
  'and',
  'at',
  'by',
  'for',
  'in',
  'of',
  'on',
  'or',
  'the',
  'to',
  'vs',
]);

const ONCHAIN_PATTERN = /(?<![a-z0-9])on[-_]chain(?![a-z0-9])/gi;
const VERSION_PATTERN = /^v\d+$/i;
const DIGIT_PATTERN = /\d/;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function caseWord(word: string): string {
  const lower = word.toLowerCase();
  if (HUMANIZE_ACRONYMS.has(lower)) return lower.toUpperCase();
  if (VERSION_PATTERN.test(word)) return lower;
  if (DIGIT_PATTERN.test(word)) return word;
  return lower;
}

/** Splits one hyphenated run into words, re-joining allowlisted compounds with `-`. */
function splitHyphens(run: string): string[] {
  const parts = run.split('-').filter((part) => part.length > 0);
  const words: string[] = [];
  let index = 0;
  while (index < parts.length) {
    const compound = HUMANIZE_COMPOUNDS.find((candidate) =>
      candidate.every((piece, offset) => parts[index + offset]?.toLowerCase() === piece),
    );
    const span = compound ? compound.length : 1;
    words.push(
      parts
        .slice(index, index + span)
        .map(caseWord)
        .join('-'),
    );
    index += span;
  }
  return words;
}

// --------------------------------------------------------------------------- #
// Public API
// --------------------------------------------------------------------------- #

export function humanize(slug: string): string {
  const words = slug
    .replace(ONCHAIN_PATTERN, 'onchain')
    .replace(/_/g, ' ')
    .split(/\s+/)
    .filter((run) => run.length > 0)
    .flatMap(splitHyphens);
  const text = words.join(' ');
  const first = words[0] ?? '';
  if (!first || DIGIT_PATTERN.test(first) || HUMANIZE_ACRONYMS.has(first.toLowerCase())) {
    return text;
  }
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}

export interface FamilyName {
  /** Uppercased segment before the first `_`; null when the slug has none. */
  sector: string | null;
  name: string;
}

export function familyName(slug: string): FamilyName {
  const normalized = slug.replace(ONCHAIN_PATTERN, 'onchain');
  const split = normalized.indexOf('_');
  const lead = split > 0 ? normalized.slice(0, split).toLowerCase() : null;
  if (lead !== null && !FAMILY_SECTORS.has(lead)) return { sector: null, name: slug };
  const words = (lead === null ? normalized : normalized.slice(split + 1))
    .split(/[-_\s]+/)
    .filter((word) => word.length > 0)
    .map((word, index) => {
      const lower = word.toLowerCase();
      if (HUMANIZE_ACRONYMS.has(lower)) return lower.toUpperCase();
      if (VERSION_PATTERN.test(word)) return lower;
      if (index > 0 && TITLE_SMALL_WORDS.has(lower)) return lower;
      return `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`;
    });
  return { sector: lead?.toUpperCase() ?? null, name: words.join(' ') };
}
