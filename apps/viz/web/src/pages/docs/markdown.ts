/**
 * Markdown rendering helpers for the docs page (dompurify sanitization).
 *
 * USAGE:
 *   const fragment = renderMarkdownFragment(docPage);
 *   const research = renderMarkdownFragment(docPage, {
 *     toHref: (path) => `/sandbox/doc/${path}`,
 *     toAssetSrc: (path) => `/api/research/asset/${path}`,
 *   });
 *
 * The `links` option is optional; omitting it keeps the /docs behaviour.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import DOMPurify from 'dompurify';
import { Marked, type TokenizerAndRendererExtension } from 'marked';
import type { DocPage } from '@/lib/api/docs';
import { smartPunctuation } from '@/ui';

import { mathExtension } from './math';

/** Pandoc superscripts in converted documents: footnote marks `^(5)` and symbols `^(®)`. */
const SUPERSCRIPT = /^\^\(([^()\s]{1,12})\)/;

const superscript: TokenizerAndRendererExtension = {
  name: 'superscript',
  level: 'inline',
  start: (src) => {
    const index = src.indexOf('^(');
    return index === -1 ? undefined : index;
  },
  tokenizer(src) {
    const match = SUPERSCRIPT.exec(src);
    return match ? { type: 'superscript', raw: match[0], text: match[1] } : undefined;
  },
  renderer: (token) =>
    `<sup>${token.text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</sup>`,
};

// One parser for every document, with TeX math kept intact for the KaTeX pass.
const markdown = new Marked(mathExtension, { extensions: [superscript] });

// --------------------------------------------------------------------------- #
// Path helpers
// --------------------------------------------------------------------------- #

export function normalizeDocPath(path: string): string | null {
  const parts = path.split('/');
  const normalized: string[] = [];

  for (const rawPart of parts) {
    const part = rawPart.trim();
    if (!part || part === '.') continue;
    if (part === '..') {
      if (normalized.length === 0) return null;
      normalized.pop();
      continue;
    }
    normalized.push(part);
  }

  if (normalized.length === 0) return null;
  return normalized.join('/');
}

/** Resolve a relative reference against the current document's directory. */
export function resolveRelativeDocPath(target: string, currentPath: string): string | null {
  const rawPath = target.split('#', 1)[0];
  if (!rawPath) return null;

  const currentDirParts = currentPath.split('/').slice(0, -1);
  const joined = [currentDirParts.join('/'), rawPath].filter(Boolean).join('/');
  return normalizeDocPath(joined);
}

interface LinkResolution {
  path: string;
  hash: string;
}

export function resolveInternalDocLink(
  targetHref: string,
  currentPath: string,
): LinkResolution | null {
  const [rawPath, rawHash] = targetHref.split('#', 2);
  const hash = rawHash ? rawHash.trim() : '';

  if (!rawPath) return null;

  const candidate = rawPath.endsWith('/') ? `${rawPath}index.md` : rawPath;
  const normalized = resolveRelativeDocPath(candidate, currentPath);
  if (!normalized) return null;

  const last = normalized.split('/').pop() ?? '';
  let finalPath = normalized;
  if (!last.includes('.')) {
    finalPath = `${normalized}.md`;
  }
  if (!finalPath.toLowerCase().endsWith('.md')) {
    return null;
  }

  return { path: finalPath, hash };
}

function toDocHref(path: string): string {
  return `/docs?doc=${encodeURIComponent(path)}`;
}

/** Absolute URL, protocol-relative URL, or `data:` payload — never repointed. */
function isExternalReference(value: string): boolean {
  return /^([a-z][a-z0-9+.-]*:|\/\/)/i.test(value);
}

// --------------------------------------------------------------------------- #
// Link options
// --------------------------------------------------------------------------- #

/**
 * Where resolved relative references point. `toHref` receives a normalized
 * markdown path; `toAssetSrc`, when supplied, receives a normalized asset path
 * (images are left untouched without it, which is the /docs behaviour).
 */
export interface MarkdownLinkOptions {
  toHref(path: string): string;
  /** Override local file/folder links without markdown suffix completion. */
  resolveHref?(href: string, currentPath: string): string | null;
  toAssetSrc?(path: string): string;
  /** Rewritten hrefs that are citations; set to mark citations as <cite>. */
  isCitation?(href: string): boolean;
}

export const DOCS_LINKS: MarkdownLinkOptions = { toHref: toDocHref };

export function rewriteDocLinks(
  html: string,
  currentPath: string,
  links: MarkdownLinkOptions = DOCS_LINKS,
): string {
  if (typeof window === 'undefined') return html;

  const parsed = new DOMParser().parseFromString(html, 'text/html');

  for (const anchor of parsed.querySelectorAll('a[href]')) {
    const href = anchor.getAttribute('href')?.trim();
    if (!href) continue;

    if (href.startsWith('#')) continue;

    if (isExternalReference(href)) {
      anchor.setAttribute('target', '_blank');
      anchor.setAttribute('rel', 'noopener noreferrer');
      continue;
    }

    if (links.resolveHref) {
      const target = links.resolveHref(href, currentPath);
      if (target) anchor.setAttribute('href', target);
      else anchor.removeAttribute('href');
      continue;
    }

    if (href.startsWith('/')) continue;

    const resolved = resolveInternalDocLink(href, currentPath);
    if (!resolved) continue;

    const target = `${links.toHref(resolved.path)}${resolved.hash ? `#${resolved.hash}` : ''}`;
    anchor.setAttribute('href', target);
  }

  const toAssetSrc = links.toAssetSrc;
  if (toAssetSrc) {
    for (const image of parsed.querySelectorAll('img[src]')) {
      const src = image.getAttribute('src')?.trim();
      if (!src) continue;
      if (src.startsWith('#') || src.startsWith('/')) continue;
      if (isExternalReference(src)) continue;

      // Assets keep their own suffix — no `.md` completion here.
      const resolved = resolveRelativeDocPath(src, currentPath);
      if (!resolved) continue;

      image.setAttribute('src', toAssetSrc(resolved));
    }
  }

  return parsed.body.innerHTML;
}

// --------------------------------------------------------------------------- #
// Render
// --------------------------------------------------------------------------- #

const FRONTMATTER = /^---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/;

/** YAML frontmatter is metadata for tools, not part of the document. */
export function stripFrontmatter(markdown: string): string {
  return markdown.replace(FRONTMATTER, '');
}

export function renderMarkdown(page: DocPage, links: MarkdownLinkOptions = DOCS_LINKS): string {
  const parsed = markdown.parse(stripFrontmatter(page.markdown), {
    gfm: true,
    breaks: false,
  }) as string;
  const rewritten = rewriteDocLinks(parsed, page.path, links);
  return DOMPurify.sanitize(rewritten, { USE_PROFILES: { html: true }, ADD_ATTR: ['target'] });
}

// --------------------------------------------------------------------------- #
// Reader markup: outline, references, figures
// --------------------------------------------------------------------------- #

export interface DocumentSection {
  id: string;
  label: string;
  index?: string;
  children?: DocumentSection[];
}

/** GitHub-style heading slug, so `[x](#results-by-decade-19902020)` anchors resolve. */
export function headingSlug(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s_-]/gu, '')
    .replace(/\s/g, '-');
}

/** "1. Answer" or "2.3 Detail": the section number and the heading text after it. */
const NUMBERED_HEADING = /^(\d+(?:\.\d+)+|\d+[.)])\s+(.*)$/s;

/** Give every heading a slug id (unique within the document). */
function assignHeadingIds(root: ParentNode): void {
  const seen = new Map<string, number>();
  for (const heading of root.querySelectorAll<HTMLElement>('h1, h2, h3, h4')) {
    if (heading.id) continue;
    const base = headingSlug(heading.textContent ?? '') || 'section';
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    heading.id = count === 0 ? base : `${base}-${count}`;
  }
}

/**
 * The document's sections: its h2s with their h3s as children, or its h3s when it has no h2.
 * Every heading gets a slug id; with `decorate`, a leading section number moves into a muted
 * `.qf-heading-index` span and each section heading gains a `#` anchor link.
 */
export function outlineDocument(root: ParentNode, decorate = false): DocumentSection[] {
  assignHeadingIds(root);
  const top = root.querySelector('h2') ? 'H2' : 'H3';
  const sections: DocumentSection[] = [];
  let parent: DocumentSection | undefined;
  for (const heading of root.querySelectorAll<HTMLElement>('h2, h3')) {
    const text = (heading.textContent ?? '').trim();
    const numbered = NUMBERED_HEADING.exec(text);
    const index = numbered?.[1].replace(/[.)]$/, '');
    const section: DocumentSection = index
      ? { id: heading.id, index, label: numbered?.[2] ?? text }
      : { id: heading.id, label: text };
    if (decorate) decorateHeading(heading, index);
    if (heading.tagName === top) {
      sections.push(section);
      parent = section;
    } else if (parent) {
      parent.children = [...(parent.children ?? []), section];
    }
  }
  return sections;
}

function decorateHeading(heading: HTMLElement, index: string | undefined): void {
  const doc = heading.ownerDocument;
  const first = heading.firstChild;
  if (index && first?.nodeType === Node.TEXT_NODE) {
    const text = first as Text;
    text.data = text.data.replace(/^\s*\S+\s+/, '');
    const marker = doc.createElement('span');
    marker.className = 'qf-heading-index';
    marker.textContent = index.padStart(2, '0');
    heading.prepend(marker);
  }
  const anchor = doc.createElement('a');
  anchor.className = 'qf-heading-anchor';
  anchor.href = `#${heading.id}`;
  anchor.setAttribute('aria-label', 'Link to this section');
  anchor.textContent = '#';
  heading.append(anchor);
}

const CLAIM_CITATION = /\[([a-z0-9][a-z0-9-]*):([A-Za-z0-9-]+)\]/g;
const LEDGER_ENTRY = /^\s*\[([a-z0-9][a-z0-9-]*):([A-Za-z0-9-]+)\]\s*/;
const PREVIEW_CHARS = 420;

function referenceId(key: string, claim: string): string {
  return `ref-${key}-${claim}`;
}

function clip(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim();
  const clipped = flat.length > PREVIEW_CHARS ? `${flat.slice(0, PREVIEW_CHARS).trimEnd()}…` : flat;
  return smartPunctuation(clipped);
}

/**
 * Turn corpus citations into references. Claim keys such as `[example-source:C01]`
 * become numbered `a.qf-ref` chips (numbered by first use) that link to their evidence-ledger
 * entry and preview its text; a ledger entry is a list item that opens with the key, and gets
 * `li.qf-ref-entry` with the number. Links whose rewritten href `isCitation` accepts become
 * `a.qf-ref-source` pills.
 */
export function markReferences(
  root: Node & ParentNode,
  isCitation: (href: string) => boolean,
): void {
  const doc = root.ownerDocument ?? document;
  for (const anchor of root.querySelectorAll<HTMLAnchorElement>('a[href]')) {
    if (isCitation(anchor.getAttribute('href') ?? '')) anchor.classList.add('qf-ref-source');
  }

  const ledger = new Map<string, { entry: HTMLLIElement; preview: string }>();
  for (const entry of root.querySelectorAll<HTMLLIElement>('li')) {
    const first = entry.firstChild;
    if (first?.nodeType !== Node.TEXT_NODE) continue;
    const text = first as Text;
    const match = LEDGER_ENTRY.exec(text.data);
    if (!match) continue;
    text.data = text.data.slice(match[0].length);
    entry.id = referenceId(match[1], match[2]);
    entry.classList.add('qf-ref-entry');
    ledger.set(`${match[1]}:${match[2]}`, { entry, preview: clip(entry.textContent ?? '') });
  }

  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.parentElement?.closest('code, pre, a, .qf-math')) texts.push(node as Text);
  }
  const numbers = new Map<string, number>();
  for (const text of texts) {
    const value = text.data;
    const matches = [...value.matchAll(CLAIM_CITATION)];
    if (matches.length === 0) continue;
    const fragment = doc.createDocumentFragment();
    let last = 0;
    for (const match of matches) {
      const token = `${match[1]}:${match[2]}`;
      const number = numbers.get(token) ?? numbers.size + 1;
      numbers.set(token, number);
      fragment.append(value.slice(last, match.index).replace(/\s+$/, ''));
      const chip = doc.createElement('a');
      chip.className = 'qf-ref';
      chip.textContent = String(number);
      chip.dataset.previewTitle = `${match[1]} · ${match[2]}`;
      const target = ledger.get(token);
      chip.dataset.preview = target?.preview ?? 'Not in this note’s evidence ledger.';
      if (target) chip.href = `#${target.entry.id}`;
      chip.setAttribute('aria-label', `Reference ${number}: ${token}`);
      fragment.append(chip);
      last = match.index + match[0].length;
    }
    fragment.append(value.slice(last));
    text.replaceWith(fragment);
  }

  for (const [token, { entry }] of ledger) {
    const key = doc.createElement('span');
    key.className = 'qf-ref-key';
    const number = numbers.get(token);
    key.textContent = number ? `${number} · ${token}` : token;
    entry.prepend(key, ' ');
  }
}

/** Superscript digits as written in a note mark (`³`), for the preview title. */
const SUPERSCRIPT_DIGITS = '⁰¹²³⁴⁵⁶⁷⁸⁹';

/**
 * Link a converted document's notes. Some converters mark a note `[³](#note-3)` and set
 * the note as a list item opening `[3](#R_note-3)`, but neither id survives
 * conversion. The note takes the id its marks point to and the ledger style; each mark gets
 * the note as a hover preview, and the first mark the id the note links back to.
 */
export function linkNotes(root: ParentNode): void {
  const notes = new Map<string, { note: HTMLElement; preview: string }>();
  for (const back of root.querySelectorAll<HTMLAnchorElement>('a[href^="#R_"]')) {
    const id = (back.getAttribute('href') ?? '').slice(3);
    const note = back.closest<HTMLElement>('li, p');
    if (!id || !note || notes.has(id)) continue;
    note.id = id;
    note.classList.add('qf-ref-entry');
    // The note's own number leads it; the list's numbering restarts at 1 under each block.
    if (note.parentElement?.tagName === 'OL') note.parentElement.classList.add('qf-notes');
    const preview = clip((note.textContent ?? '').replace(back.textContent ?? '', ''));
    notes.set(id, { note, preview });
  }
  const linked = new Set<string>();
  for (const mark of root.querySelectorAll<HTMLAnchorElement>('a[href^="#"]')) {
    const id = (mark.getAttribute('href') ?? '').slice(1);
    const target = notes.get(id);
    if (!target || target.note.contains(mark)) continue;
    const number = [...(mark.textContent ?? '')]
      .map((char) => (SUPERSCRIPT_DIGITS.includes(char) ? SUPERSCRIPT_DIGITS.indexOf(char) : char))
      .join('');
    mark.classList.add('qf-note-ref');
    mark.dataset.previewTitle = `Note ${number}`;
    mark.dataset.preview = target.preview;
    if (!linked.has(id)) mark.id = `R_${id}`;
    linked.add(id);
  }
}

/** A book's own caption label: "Figure 3.1:", "Figs. 2.9", "Exhibit 4.2 —". */
const FIGURE_LABEL =
  /^\s*(fig(?:ure)?s?\.?|exhibit|chart)\s+(\d+(?:[.\-–]\d+)*[a-z]?)\s*[:.—–-]?\s*/i;
const MAX_CAPTION_CHARS = 600;
/** Alt text that says nothing ("img", "image", a file name). */
const EMPTY_ALT =
  /^(?:img|images?|figure|picture|photo|graphic|untitled|[\w-]+\.(?:jpe?g|png|gif|svg|webp))?$/i;

/**
 * The book's caption beside a figure: the next paragraph or minor heading, else the one
 * before, opening with a label.
 */
/** A node's first child that shows something; a converted document's link anchor
 * (`<a id="F3-1"></a>`) is empty and is skipped. */
function leadingNode(node: Element): ChildNode | null {
  let child = node.firstChild;
  while (child instanceof Element && !child.textContent && !child.querySelector('img')) {
    child = child.nextSibling;
  }
  return child;
}

/** Whether a link points into the image's paragraph or a neighbour of it (its own caption). */
function linksToFigure(link: Element, paragraph: Element): boolean {
  const id = /^#(.+)/.exec(link.getAttribute('href') ?? '')?.[1];
  if (!id) return false;
  const selector = `[id="${CSS.escape(id)}"]`;
  return [paragraph, paragraph.previousElementSibling, paragraph.nextElementSibling].some(
    (node) => node?.matches(selector) || node?.querySelector(selector),
  );
}

function figureCaption(paragraph: Element): { caption: Element; number: string } | null {
  for (const sibling of [paragraph.nextElementSibling, paragraph.previousElementSibling]) {
    if (!sibling || !/^(?:P|H4|H5|H6)$/.test(sibling.tagName) || sibling.querySelector('img'))
      continue;
    const text = (sibling.textContent ?? '').trim();
    const label = FIGURE_LABEL.exec(text);
    // A caption's label is set apart (a heading, bold, a link or punctuated);
    // "Figure 3.1 shows…" is prose, also when its label links to this figure.
    const lead = leadingNode(sibling);
    const setApart =
      sibling.tagName !== 'P' ||
      /[:.—–-]\s*$/.test(label?.[0] ?? '') ||
      (lead instanceof Element &&
        /^(?:STRONG|B|A)$/.test(lead.tagName) &&
        !linksToFigure(lead, paragraph) &&
        FIGURE_LABEL.test(lead.textContent ?? ''));
    if (label && setApart && text.length <= MAX_CAPTION_CHARS)
      return { caption: sibling, number: label[2] };
  }
  return null;
}

/** Drop the caption's leading label (bold, linked or plain), keeping the rest of its markup. */
function stripFigureLabel(caption: Element): void {
  const first = leadingNode(caption);
  if (first instanceof Element && FIGURE_LABEL.test(first.textContent ?? '')) {
    const rest = (first.textContent ?? '').replace(FIGURE_LABEL, '');
    if (rest) first.textContent = rest;
    else first.remove();
  } else if (first?.nodeType === Node.TEXT_NODE) {
    first.textContent = (first.textContent ?? '').replace(FIGURE_LABEL, '');
  }
  const lead = leadingNode(caption);
  if (lead?.nodeType === Node.TEXT_NODE) lead.textContent = (lead.textContent ?? '').trimStart();
}

export function figureId(number: string): string {
  return `figure-${number.toLowerCase().replace(/[^\da-z]+/g, '-')}`;
}

/**
 * A paragraph holding only an image becomes a figure. A book's caption beside it
 * ("**Figure 3.1:** At the beginning…") moves under the image, and the figure takes its
 * number and an id (`figure-3-1`) that references link to. Otherwise its alt text, when that
 * says anything, captions it, numbered in order only on a page where the book numbers none,
 * so a stray image never takes a number between the book's own.
 */
export function markFigures(root: ParentNode): void {
  const figures = [...root.querySelectorAll('p')]
    .filter((paragraph) => {
      const images = paragraph.querySelectorAll('img');
      return images.length === 1 && (paragraph.textContent ?? '').trim() === '';
    })
    .map((paragraph) => ({ paragraph, own: figureCaption(paragraph) }));
  const numberInOrder = figures.every((figure) => !figure.own);
  let count = 0;
  for (const { paragraph, own } of figures) {
    const images = paragraph.querySelectorAll('img');
    count += 1;
    const doc = paragraph.ownerDocument;
    const figure = doc.createElement('figure');
    const caption = doc.createElement('figcaption');
    const label = doc.createElement('span');
    label.className = 'qf-figure-label';
    if (own) {
      label.textContent = `Fig ${own.number}`;
      figure.id = figureId(own.number);
      stripFigureLabel(own.caption);
      caption.append(label, ...own.caption.childNodes);
      own.caption.remove();
    } else {
      label.textContent = `Fig ${count}`;
      const alt = (images[0].getAttribute('alt') ?? '').trim();
      if (numberInOrder) caption.append(label);
      if (!EMPTY_ALT.test(alt)) caption.append(alt);
    }
    figure.append(...paragraph.childNodes);
    if (caption.hasChildNodes()) figure.append(caption);
    paragraph.replaceWith(figure);
  }
}

/** Captions, labels, index entries and sentences stay bold paragraphs. */
const NOT_A_HEADING =
  /^(?:fig(?:ure)?s?\.?|table|exhibit|chart|panel|source|note)s?\b|[.:;,]$|\d[\d,–-]*$/i;
const MAX_HEADING_CHARS = 90;

/**
 * A paragraph that is only bold text, as converted documents set their headings, becomes a
 * heading. In a document with no headings of its own it is an `h3`, listed in the contents;
 * otherwise, and when it is set in capitals ("THE WAY OUT"), an `h4` that stays out of them.
 */
export function promoteBoldHeadings(root: ParentNode): void {
  const doc = (root as Node).ownerDocument ?? document;
  const level = root.querySelector('h2, h3') ? 'h4' : 'h3';
  const candidates = new Map<Element, HTMLElement>();
  for (const paragraph of root.querySelectorAll('p')) {
    if (paragraph.parentNode !== root) continue;
    const [strong, ...rest] = [...paragraph.childNodes].filter(
      (node) => node.nodeType !== Node.TEXT_NODE || (node.textContent ?? '').trim() !== '',
    );
    if (rest.length > 0 || !(strong instanceof HTMLElement) || strong.tagName !== 'STRONG')
      continue;
    candidates.set(paragraph, strong);
  }
  for (const [paragraph, strong] of candidates) {
    // A run of bold lines is a list (contents, an index), and a heading leads something.
    const next = paragraph.nextElementSibling;
    if (!next || candidates.has(next)) continue;
    const previous = paragraph.previousElementSibling;
    if (previous && candidates.has(previous)) continue;
    const text = (strong.textContent ?? '').replace(/\s+/g, ' ').trim();
    if (text.length < 3 || text.length > MAX_HEADING_CHARS || !/\p{L}/u.test(text)) continue;
    // Headings open with a capital; a lowercase bold line is an index entry or a term.
    if (NOT_A_HEADING.test(text) || /^\p{Ll}/u.test(text)) continue;
    const heading = doc.createElement(text === text.toUpperCase() ? 'h4' : level);
    heading.append(...strong.childNodes);
    paragraph.replaceWith(heading);
  }
}

/** An index's letter headings, at whatever level the conversion set them. */
const INDEX_LETTER = /^(?:[A-Z]|[A-Z]–[A-Z]|Symbols|Numbers|Numerics?)$/i;

/**
 * A back-of-book index's entries are text, not sections: only its letter headings stay.
 * Converted indexes also leave unmatched `**` on entries, which are never literal there.
 */
export function flattenIndexEntries(root: ParentNode): void {
  const doc = (root as Node).ownerDocument ?? document;
  const walker = doc.createTreeWalker(root as Node, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (node.textContent?.includes('**')) node.textContent = node.textContent.replace(/\*\*/g, '');
  }
  for (const heading of root.querySelectorAll('h3, h4, h5, h6')) {
    if (INDEX_LETTER.test((heading.textContent ?? '').trim())) {
      const letter = doc.createElement('h2');
      letter.append(...heading.childNodes);
      heading.replaceWith(letter);
      continue;
    }
    // `### **actions 2, 14**` and `### actions 2, 14` both become a bold entry.
    const entry = doc.createElement('strong');
    entry.append(...(heading.querySelector(':scope > strong:only-child') ?? heading).childNodes);
    const paragraph = doc.createElement('p');
    paragraph.append(entry);
    heading.replaceWith(paragraph);
  }
}

/** Letter links across the top of an index: one hop to any letter, in place of contents. */
export function indexLetterBar(root: ParentNode): HTMLElement | null {
  const letters = [...root.querySelectorAll<HTMLElement>('h2[id]')];
  if (letters.length === 0) return null;
  const doc = (root as Node).ownerDocument ?? document;
  const bar = doc.createElement('nav');
  bar.className = 'prose-index-letters';
  bar.setAttribute('aria-label', 'Index letters');
  for (const letter of letters) {
    const link = doc.createElement('a');
    link.href = `#${letter.id}`;
    link.textContent = (letter.textContent ?? '').replace(/#$/, '').trim();
    bar.append(link);
  }
  return bar;
}

// --------------------------------------------------------------------------- #
// Search highlights
// --------------------------------------------------------------------------- #

/** Endings the server's stemmer folds away, so "trading" here also lights "trade". */
const SEARCH_SUFFIX = /(?:ations?|ings?|ies|ied|ed|es|ly|s|e|y)$/;
const SEARCH_SKIP = '.katex, code, pre, script, style, mark';

/** One pattern lighting every word of a search, each matched from its stem on. */
function searchPattern(query: string): RegExp | null {
  // Letters and digits only, so the stems need no escaping.
  const words = query.toLocaleLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [];
  const stems = [...new Set(words)].map((word) => {
    const stem = word.replace(SEARCH_SUFFIX, '');
    return stem.length >= 3 ? stem : word;
  });
  if (stems.length === 0) return null;
  return new RegExp(`(?<![\\p{L}\\p{N}])(?:${stems.join('|')})[\\p{L}\\p{N}]*`, 'giu');
}

/**
 * Wrap each word of `query` in `root`'s text in `<mark class="qf-search-hit">`, outside math
 * and code, and return the first mark so the reader can bring it into view.
 */
export function highlightMatches(root: HTMLElement, query: string): HTMLElement | null {
  const pattern = searchPattern(query);
  if (!pattern) return null;
  const doc = root.ownerDocument;
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) =>
      node.parentElement?.closest(SEARCH_SKIP)
        ? NodeFilter.FILTER_REJECT
        : NodeFilter.FILTER_ACCEPT,
  });
  const texts: Text[] = [];
  while (walker.nextNode()) texts.push(walker.currentNode as Text);
  let first: HTMLElement | null = null;
  for (const text of texts) {
    const value = text.data;
    const matches = [...value.matchAll(pattern)];
    if (matches.length === 0) continue;
    const pieces = doc.createDocumentFragment();
    let at = 0;
    for (const match of matches) {
      const start = match.index ?? 0;
      pieces.append(value.slice(at, start));
      const mark = doc.createElement('mark');
      mark.className = 'qf-search-hit';
      mark.textContent = match[0];
      pieces.append(mark);
      first ??= mark;
      at = start + match[0].length;
    }
    pieces.append(value.slice(at));
    text.replaceWith(pieces);
  }
  return first;
}

export function renderMarkdownFragment(
  page: DocPage,
  links: MarkdownLinkOptions = DOCS_LINKS,
): DocumentFragment {
  const sanitized = renderMarkdown(page, links);
  const fragment = DOMPurify.sanitize(sanitized, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ['target'],
    RETURN_DOM_FRAGMENT: true,
  });
  // Converted documents leave hard breaks as a lone `\` paragraph or a heading's last character.
  for (const paragraph of fragment.querySelectorAll('p')) {
    if ((paragraph.textContent ?? '').trim() === '\\') paragraph.remove();
  }
  for (const heading of fragment.querySelectorAll('h1, h2, h3, h4, h5, h6')) {
    const last = heading.lastChild;
    if (last?.nodeType === Node.TEXT_NODE)
      last.textContent = (last.textContent ?? '').replace(/\\\s*$/, '');
  }
  return fragment;
}
