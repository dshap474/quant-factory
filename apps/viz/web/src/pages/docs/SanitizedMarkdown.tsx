/**
 * Explicit DOMPurify trust boundary for backend-provided documentation markdown.
 *
 * USAGE:
 *   <SanitizedMarkdown page={docPage} />
 *   <SanitizedMarkdown page={researchDoc} links={researchLinks} className="docs-prose" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { enhanceTableMarkup } from '@quant-factory/qf-ui/tables';
import { useEffect, useRef } from 'react';
import type { DocPage } from '@/lib/api/docs';
import { Prose, type ProseLayout, refineProse, smartPunctuation } from '@/ui';

import {
  type DocumentSection,
  flattenIndexEntries,
  highlightMatches,
  indexLetterBar,
  linkNotes,
  type MarkdownLinkOptions,
  markFigures,
  markReferences,
  outlineDocument,
  promoteBoldHeadings,
  renderMarkdownFragment,
} from './markdown';
import { numberEquations, typesetMath } from './math';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

function sameText(a: string, b: string): boolean {
  const normalize = (text: string) => text.replace(/\s+/g, ' ').trim().toLocaleLowerCase();
  return normalize(a) === normalize(b);
}

/** Bring the location's `#id` target into view, if the document has it; else the first search
 * match. */
function scrollToTarget(article: HTMLElement): void {
  const hash = window.location.hash.slice(1);
  if (!hash) {
    article.querySelector('mark.qf-search-hit')?.scrollIntoView({ block: 'center' });
    return;
  }
  let id = hash;
  try {
    id = decodeURIComponent(hash);
  } catch {
    // A malformed escape is matched as written.
  }
  // A book's figure anchor sits in its caption, under the image.
  const target = article.querySelector(`#${CSS.escape(id)}`);
  (target?.closest('figure') ?? target)?.scrollIntoView({ block: 'start' });
}

/** Contents labels get the same punctuation as the headings they name. */
function refineSection(section: DocumentSection): DocumentSection {
  return {
    ...section,
    label: smartPunctuation(section.label),
    children: section.children?.map(refineSection),
  };
}

export function SanitizedMarkdown({
  page,
  links,
  className,
  hideLeadingTitle = false,
  readerMarkup = false,
  layout = 'flow',
  highlight,
  onSections,
}: {
  page: DocPage;
  links?: MarkdownLinkOptions;
  /** Host hook classes only; the prose recipe and reading column come from <Prose>. */
  className?: string;
  hideLeadingTitle?: boolean;
  /** Number section headings, add heading anchors, references and figures (Reader frame). */
  readerMarkup?: boolean;
  /** `index`: a back-of-book index, whose entries are flattened and set in columns. */
  layout?: ProseLayout;
  /** A search whose words are marked in the text, the first brought into view. */
  highlight?: string;
  /** Receives the document's sections (with heading ids set) after each render. */
  onSections?: (sections: DocumentSection[]) => void;
}) {
  const articleRef = useRef<HTMLElement | null>(null);
  const onSectionsRef = useRef(onSections);
  useEffect(() => {
    onSectionsRef.current = onSections;
  }, [onSections]);

  useEffect(() => {
    const article = articleRef.current;
    if (!article) return;
    const fragment = renderMarkdownFragment(page, links);
    // The title often opens the file at any level (split chapters open with "## Chapter 3: …").
    const firstHeading = fragment.querySelector('h1, h2, h3');
    if (hideLeadingTitle && firstHeading && sameText(firstHeading.textContent ?? '', page.title)) {
      firstHeading.remove();
    }
    if (readerMarkup) {
      if (links?.isCitation) markReferences(fragment, links.isCitation);
      // Figures first: a caption's back-link (#R_fig-1) is not a note.
      markFigures(fragment);
      linkNotes(fragment);
      if (layout === 'index') flattenIndexEntries(fragment);
      else promoteBoldHeadings(fragment);
    }
    const sections = outlineDocument(fragment, readerMarkup);
    if (readerMarkup) {
      refineProse(fragment);
      numberEquations(fragment);
    }
    // An index's letters go in a bar above its entries, not in the contents.
    const letterBar = layout === 'index' ? indexLetterBar(fragment) : null;
    if (letterBar) fragment.prepend(letterBar);
    article.replaceChildren(fragment);
    const typesetting = new AbortController();
    let disposeMath = () => {};
    void typesetMath(article, typesetting.signal).then((dispose) => {
      disposeMath = dispose;
      // After typesetting, so marks never split the TeX source KaTeX reads.
      if (highlight && !typesetting.signal.aborted) highlightMatches(article, highlight);
      // Typeset math changes the height of everything above the target.
      if (!typesetting.signal.aborted) scrollToTarget(article);
    });
    onSectionsRef.current?.(
      layout === 'index' ? [] : readerMarkup ? sections.map(refineSection) : sections,
    );
    // The document renders after navigation, so a deep link's target exists only now.
    if (!highlight) scrollToTarget(article);
    // Images above the target load later and push it down.
    if (window.location.hash) {
      const images = [...article.querySelectorAll('img')].map((image) =>
        image.decode().catch(() => {}),
      );
      void Promise.all(images).then(() => {
        if (!typesetting.signal.aborted) scrollToTarget(article);
      });
    }
    const disposeTables = enhanceTableMarkup(article);
    return () => {
      typesetting.abort();
      disposeMath();
      disposeTables();
      article.replaceChildren();
    };
  }, [page, links, hideLeadingTitle, readerMarkup, layout, highlight]);

  return <Prose as="article" measure layout={layout} ref={articleRef} className={className} />;
}
