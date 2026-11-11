/**
 * TeX math in markdown: a marked extension that keeps `$…$` and `\\(…\\)` (inline) and
 * `$$…$$` and `\\[…\\]` (display) away from emphasis and escape parsing, and a lazy KaTeX
 * pass that typesets them after the document is sanitized. KaTeX and its stylesheet load only
 * for documents that contain math.
 *
 * Display equations are numbered: a note that numbers its own (`\\tag{8.1}`, or `\\quad (8.1)`
 * copied from its source) keeps those numbers and its "Eq. 8.1" and "(8.1)" mentions link to
 * them; otherwise every display equation is numbered (1), (2), … in order. Equations wider
 * than the column shrink to fit, up to a limit, and scroll past it.
 *
 * USAGE:
 *   const markdown = new Marked(mathExtension);
 *   numberEquations(fragment);
 *   article.replaceChildren(fragment);
 *   const dispose = await typesetMath(article, signal);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { MarkedExtension, TokenizerAndRendererExtension, Tokens } from 'marked';
import { trackScrollEdges } from '@/ui';

// --------------------------------------------------------------------------- #
// Markdown extension
// --------------------------------------------------------------------------- #

interface MathToken extends Tokens.Generic {
  text: string;
  display: boolean;
}

/** Inline `$x$`: no space inside either `$`, and no digit after the closing one ($5 and $10). */
const INLINE_MATH = /^\$(?!\s)((?:\\.|[^\\$\n])+?)(?<!\s)\$(?!\d)/;
const INLINE_DISPLAY_MATH = /^\$\$((?:\\.|[^\\$])+?)\$\$/;
const PAREN_MATH = /^\\\((.+?)\\\)/;
const BRACKET_MATH = /^\\\[([\s\S]+?)\\\]/;
/** `\[…\]` is math only when it reads as TeX; `\[[1](#ref-1)\]` is an escaped citation. */
const TEX_LIKE = /[\\^_={}]/;
/** A `$$` block, never spanning another `$$`; a source's `(1)` after it becomes its tag. */
const BLOCK_MATH =
  /^ {0,3}\$\$((?:\\[\s\S]|[^\\$]|\$(?!\$))+?)\$\$[ \t]*(?:\((\d+(?:\.\d+)*[a-z]?)\))?[ \t]*(?:\n+|$)/;

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** The TeX stays as the element's text, so a document that fails to typeset still reads. */
function renderMath(token: Tokens.Generic): string {
  const { text, display } = token as MathToken;
  const tag = display && token.type === 'blockMath' ? 'div' : 'span';
  return `<${tag} class="qf-math" data-display="${display}">${escapeHtml(text)}</${tag}>`;
}

const blockMath: TokenizerAndRendererExtension = {
  name: 'blockMath',
  level: 'block',
  start: (src) => src.match(/^ {0,3}\$\$/m)?.index,
  tokenizer(src) {
    const match = BLOCK_MATH.exec(src);
    if (!match) return undefined;
    const text = match[2] ? `${match[1].trim()} \\tag{${match[2]}}` : match[1].trim();
    return { type: 'blockMath', raw: match[0], text, display: true };
  },
  renderer: renderMath,
};

const inlineMath: TokenizerAndRendererExtension = {
  name: 'inlineMath',
  level: 'inline',
  start: (src) => {
    const index = src.search(/\$|\\[([]/);
    return index === -1 ? undefined : index;
  },
  tokenizer(src) {
    const bracket = BRACKET_MATH.exec(src);
    if (bracket && TEX_LIKE.test(bracket[1]) && !bracket[1].includes('](')) {
      return { type: 'inlineMath', raw: bracket[0], text: bracket[1].trim(), display: true };
    }
    const paren = PAREN_MATH.exec(src);
    if (paren) {
      return { type: 'inlineMath', raw: paren[0], text: paren[1], display: false };
    }
    const display = INLINE_DISPLAY_MATH.exec(src);
    if (display) {
      return { type: 'inlineMath', raw: display[0], text: display[1].trim(), display: true };
    }
    const inline = INLINE_MATH.exec(src);
    if (!inline) return undefined;
    return { type: 'inlineMath', raw: inline[0], text: inline[1], display: false };
  },
  renderer: renderMath,
};

export const mathExtension: MarkedExtension = { extensions: [blockMath, inlineMath] };

// --------------------------------------------------------------------------- #
// TeX repair
// --------------------------------------------------------------------------- #

/** `l_\max` is fine in MathJax but a KaTeX error: brace operator names used as a sub/superscript. */
const BARE_OPERATOR_SCRIPT = /([_^])(\\(?:max|min|sup|inf|lim|arg|det|log|exp))(?![A-Za-z])/g;
/** `\tag{19.b.6)`: a source closed its tag with a parenthesis. */
const UNCLOSED_TAG = /\\tag\{([^{}()]*)\)/g;

function repairTex(tex: string): string {
  return tex.replace(BARE_OPERATOR_SCRIPT, '$1{$2}').replace(UNCLOSED_TAG, '\\tag{$1}');
}

// --------------------------------------------------------------------------- #
// Equation numbers
// --------------------------------------------------------------------------- #

const TAG = /\\tag\*?\{([^}]+)\}/;
/** A source's own number written into the TeX after a space: `\quad (6.2)`. */
const WRITTEN_NUMBER = /(?:\\q?quad|\\[ ;,]|~)\s*\((\d+(?:\.\d+)+[a-z]?)\)/g;
/** The same number closing the equation, with any sentence punctuation after it. */
const TRAILING_NUMBER = /(?:\s|\\q?quad|\\[ ;,]|~)*\((\d+(?:\.\d+)+[a-z]?)\)\s*([.,;]?)\s*$/;
/** "Eq. 8.1", "Equation (8.1)" or a bare "(8.1)" in the text. */
const EQUATION_MENTION =
  /\b(?:Eqs?\.|[Ee]quations?)\s\(?(\d+(?:\.\d+)*[a-z]?)\)?|\((\d+(?:\.\d+)+[a-z]?)\)/g;

function equationId(number: string): string {
  return `eq-${number}`;
}

/** The numbers an equation carries: its `\tag`, or numbers its source wrote into the TeX. */
function equationNumbers(node: HTMLElement): string[] {
  const tex = repairTex(node.textContent ?? '');
  node.textContent = tex;
  const tag = TAG.exec(tex)?.[1]?.trim();
  if (tag) return [tag];
  const written = [...tex.matchAll(WRITTEN_NUMBER)].map((match) => match[1]);
  // A lone closing number becomes a tag, so KaTeX sets it in the margin.
  if (written.length === 1 && TRAILING_NUMBER.test(tex)) {
    node.textContent = tex.replace(TRAILING_NUMBER, '$2\\tag{$1}');
  }
  return written;
}

/** Link mentions of a numbered equation ("Eq. 12.8", "(6.3)") to it. */
function linkEquationMentions(root: ParentNode, targets: Map<string, string>): void {
  const doc = (root as Node).ownerDocument ?? (root as Document);
  const walker = doc.createTreeWalker(root as Node, NodeFilter.SHOW_TEXT);
  const texts: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.parentElement?.closest('code, pre, a, .qf-math')) texts.push(node as Text);
  }
  for (const text of texts) {
    const mentions = [...text.data.matchAll(EQUATION_MENTION)].filter((match) =>
      targets.has(match[1] ?? match[2]),
    );
    if (mentions.length === 0) continue;
    const parts: Node[] = [];
    let cursor = 0;
    for (const mention of mentions) {
      const start = mention.index ?? 0;
      parts.push(doc.createTextNode(text.data.slice(cursor, start)));
      const link = doc.createElement('a');
      link.href = `#${targets.get(mention[1] ?? mention[2])}`;
      link.textContent = mention[0];
      parts.push(link);
      cursor = start + mention[0].length;
    }
    parts.push(doc.createTextNode(text.data.slice(cursor)));
    text.replaceWith(...parts);
  }
}

/**
 * Give display equations ids and numbers before the document is inserted, so a deep link
 * to `#eq-3` resolves on first render. A note that numbers its own equations (a `\tag`, or a
 * source number written after the TeX) keeps those numbers and links its mentions of them;
 * any other note gets `data-eq` numbers (1), (2), … that the reader sets in the margin.
 */
export function numberEquations(root: ParentNode): void {
  const equations = [...root.querySelectorAll<HTMLElement>('.qf-math[data-display="true"]')];
  const numbers = equations.map(equationNumbers);
  if (numbers.some((list) => list.length > 0)) {
    const targets = new Map<string, string>();
    equations.forEach((node, index) => {
      const own = numbers[index].filter((number) => !targets.has(number));
      if (own.length === 0) return;
      node.id = equationId(own[0]);
      for (const number of own) targets.set(number, node.id);
    });
    linkEquationMentions(root, targets);
    return;
  }
  equations.forEach((node, index) => {
    node.id = equationId(String(index + 1));
    node.dataset.eq = String(index + 1);
  });
}

// --------------------------------------------------------------------------- #
// Typesetting
// --------------------------------------------------------------------------- #

/** Below this scale a wide equation stops shrinking and scrolls instead. */
const MIN_FIT_SCALE = 0.8;

/** Shrink an equation that overflows its column a little; scroll one that overflows a lot. */
function fitDisplay(display: HTMLElement): () => void {
  const ratio = display.clientWidth / display.scrollWidth;
  if (ratio >= 1) return () => {};
  if (ratio >= MIN_FIT_SCALE) {
    display.style.fontSize = `${Math.floor(ratio * 100) / 100}em`;
    return () => {};
  }
  display.classList.add('ui-scroll-area', 'is-x');
  return trackScrollEdges(display as HTMLDivElement);
}

/**
 * Typeset every `.qf-math` element under `root`, loading KaTeX only when there is one, then
 * fit wide display equations once the math fonts have loaded. Resolves to a cleanup.
 */
export async function typesetMath(root: ParentNode, signal?: AbortSignal): Promise<() => void> {
  const nodes = root.querySelectorAll<HTMLElement>('.qf-math:not([data-typeset])');
  if (nodes.length === 0) return () => {};
  const [{ default: katex }] = await Promise.all([
    import('katex'),
    import('katex/dist/katex.min.css'),
  ]);
  if (signal?.aborted) return () => {};
  for (const node of nodes) {
    katex.render(repairTex(node.textContent ?? ''), node, {
      displayMode: node.dataset.display === 'true',
      throwOnError: false,
      strict: 'ignore',
      output: 'htmlAndMathml',
    });
    node.dataset.typeset = '';
  }
  await document.fonts.ready;
  if (signal?.aborted) return () => {};
  const cleanups = [...root.querySelectorAll<HTMLElement>('.qf-math .katex-display')].map(
    fitDisplay,
  );
  return () => {
    for (const cleanup of cleanups) cleanup();
  };
}
