/**
 * Typographic refinement for rendered prose: curly quotes and apostrophes, en dashes in
 * number ranges, true minus signs, ellipses, compounds rejoined after a line-end hyphen,
 * non-breaking spaces that keep a label with its number, and acronyms set as `span.qf-caps`.
 * Code, math and reference chips are left alone.
 *
 * USAGE:
 *   refineProse(article);                    // after sanitizing, before inserting
 *   smartPunctuation('"1990-2020" -0.5...'); // '“1990–2020” −0.5…'
 */

// --------------------------------------------------------------------------- #
// Punctuation
// --------------------------------------------------------------------------- #

/** Text inside these is literal: code, TeX, reference chips and heading decorations. */
const LITERAL =
  'code, pre, kbd, samp, script, style, .qf-math, .katex, .qf-ref, .qf-ref-key, .qf-heading-index, .qf-heading-anchor, .qf-figure-label';
/** Quote context resets at each of these, so a paragraph's first quote always opens. */
const BLOCK = 'p, li, td, th, h1, h2, h3, h4, h5, h6, figcaption, blockquote, dt, dd';
/** Acronyms keep full capitals where the type is already set apart. */
const FULL_CAPS = 'h1, h2, h3, h4, h5, h6, th';

/** Two numbers joined by a hyphen, not inside a word, version or identifier. */
const NUMBER_RANGE = /(?<![\p{L}\d\-_/]|\d\.)(\d[\d,.]*)-(\d[\d,.]*)(?![\d\-\p{L}])/gu;
const NEGATIVE_NUMBER = /(^|[\s([=:,;<>≤≥+×*/])-(?=\.?\d)/g;
const LABEL_NUMBER =
  /\b(Fig\.|Figs\.|Figure|Table|Eq\.|Eqs\.|Equation|Ch\.|Chapter|Section|Insight|p\.|pp\.)\s(?=[\d(])|§\s(?=\d)/g;
const NUMBER_UNIT = /(\d) (bps?|bn|mn|pp|ms)\b/g;
/** A compound split at a line end ("decision- making"); "high- and low-frequency" is kept. */
const WRAPPED_COMPOUND =
  /(?<=\p{L}{2})- (?!(?:and|or|nor|to|through|than|vs|versus|but)\b)(?=\p{Ll}{2})/gu;
/** An em dash closed on one side only ("Resistance— Fixes") was split at a line end. */
const WRAPPED_DASH = /(?<=\p{L})— (?=\p{L})/gu;
const OPENS_AFTER = /^$|[\s([{‘“–—/-]$/u;
const WORD_CHAR = /[\p{L}\p{N}.,!?;:)\]%’”]/u;

/** A four-digit year and a month (2024-01) is a date, not a range. */
function isYearMonth(first: string, second: string): boolean {
  return first.length === 4 && second.length === 2 && Number(second) <= 12;
}

/**
 * Typographer's punctuation for one run of text. `before` is the character that precedes
 * it in the same block, so a quote that closes after inline markup still curls the right way.
 */
export function smartPunctuation(text: string, before = ''): string {
  const replaced = text
    .replace(/\.\.\./g, '…')
    .replace(NUMBER_RANGE, (match, first: string, second: string) =>
      isYearMonth(first, second) ? match : `${first}–${second}`,
    )
    .replace(NEGATIVE_NUMBER, '$1−')
    .replace(LABEL_NUMBER, (match) => `${match.slice(0, -1)} `)
    .replace(NUMBER_UNIT, '$1 $2')
    .replace(WRAPPED_COMPOUND, '-')
    .replace(WRAPPED_DASH, '—');
  let out = '';
  let previous = before;
  for (let index = 0; index < replaced.length; index += 1) {
    const char = replaced.charAt(index);
    let next = char;
    if (char === '"') {
      next = OPENS_AFTER.test(previous) ? '“' : '”';
    } else if (char === "'") {
      const following = replaced.charAt(index + 1);
      // An apostrophe after a word, or eliding digits ('90s); otherwise an opening quote.
      next = WORD_CHAR.test(previous) || /\d/.test(following) ? '’' : '‘';
    }
    out += next;
    previous = next;
  }
  return out;
}

// --------------------------------------------------------------------------- #
// Acronyms
// --------------------------------------------------------------------------- #

/** Three or more capitals (with digits or & inside), optionally pluralized: SVD, S&P, ETFs. */
const ACRONYM = /\b[A-Z][A-Z0-9&]*[A-Z0-9](?=s?\b)/g;
const ROMAN_NUMERAL = /^[IVX]+$/;

function isAcronym(word: string): boolean {
  return word.length >= 3 && /[A-Z].*[A-Z]/.test(word) && !ROMAN_NUMERAL.test(word);
}

/** Split a text node so each acronym sits in its own `span.qf-caps`. */
function wrapAcronyms(node: Text): void {
  const matches = [...node.data.matchAll(ACRONYM)].filter((match) => isAcronym(match[0]));
  if (matches.length === 0) return;
  const doc = node.ownerDocument;
  const parts: Node[] = [];
  let cursor = 0;
  for (const match of matches) {
    const start = match.index ?? 0;
    if (start > cursor) parts.push(doc.createTextNode(node.data.slice(cursor, start)));
    const caps = doc.createElement('span');
    caps.className = 'qf-caps';
    caps.textContent = match[0];
    parts.push(caps);
    cursor = start + match[0].length;
  }
  if (cursor < node.data.length) parts.push(doc.createTextNode(node.data.slice(cursor)));
  node.replaceWith(...parts);
}

// --------------------------------------------------------------------------- #
// Entry point
// --------------------------------------------------------------------------- #

/** Refine every prose text node under `root`; literal text only informs quote direction. */
export function refineProse(root: Node & ParentNode): void {
  const doc = root.ownerDocument ?? (root as Document);
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) texts.push(node as Text);

  let block: Element | null = null;
  let previous = '';
  for (const text of texts) {
    const parent = text.parentElement;
    if (!parent) continue;
    const owner = parent.closest(BLOCK);
    if (owner !== block) {
      block = owner;
      previous = '';
    }
    if (parent.closest(LITERAL)) {
      previous = text.data.slice(-1) || previous;
      continue;
    }
    const refined = smartPunctuation(text.data, previous);
    previous = refined.slice(-1) || previous;
    if (refined !== text.data) text.data = refined;
    if (!parent.closest(FULL_CAPS)) wrapAcronyms(text);
  }
}
