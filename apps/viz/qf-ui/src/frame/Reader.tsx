/**
 * Long-form reading frame. A fixed-measure column holds the title, a lede, labelled metadata
 * and the document in relaxed type. A sticky rail beside it holds the controls (a
 * column-alignment toggle remembered per browser), the title once the header has scrolled
 * away, a numbered table of contents whose active section unfolds its subsections, and a
 * reading-progress bar. Elements inside the document that carry
 * `data-preview` (and optionally `data-preview-title`) show that text in a preview card on
 * hover or focus, so hosts can turn citations into readable references. On narrow panes the
 * rail stacks above the column. A document in a sequence (a book's chapters) takes `pager`:
 * its previous and next links sit in the rail and close the column, and the left and right
 * arrow keys follow them. `ReaderPager` is that closing pair on its own; `ReaderLinkList` is a titled
 * list of links in document type (a work's contents), placed inside a `Prose`, whose `id`
 * the contents can target.
 *
 * USAGE:
 *   <Reader
 *     title="What good means for a signal"
 *     lede="IC is the primary forecast-level metric."
 *     meta={[{ label: 'Topic', value: 'evaluation' }, { label: 'Backlinks', value: 11 }]}
 *     sections={[{ id: 'answer', index: '1', label: 'Answer', children: [{ id: 'ic', label: 'IC' }] }]}
 *     actions={<Link to="/graph" variant="control" size="sm" icon aria-label="Graph">…</Link>}
 *     pager={{ label: 'Chapters', previous: { label: 'Chapter 2', to: '/ch/2' } }}
 *   >
 *     <Prose as="article">…</Prose>
 *     <Prose><ReaderLinkList id="contents" title="Contents" items={[{ label: 'Ch 1', to: '/ch/1' }]} /></Prose>
 *     <ReaderPager previous={{ label: 'Chapter 2', to: '/ch/2' }} next={{ label: 'Chapter 4', to: '/ch/4' }} />
 *   </Reader>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { PreviewCard } from '@base-ui/react/preview-card';
import { AlignCenter, AlignLeft } from 'lucide-react';
import {
  type MouseEvent,
  type ReactNode,
  type RefObject,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';

import { cn } from '../lib/cn';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';
import { isTypingTarget } from '../lib/typing-target';
import { OVERLAY_SIDE_OFFSET } from '../overlay/placement';
import { Button } from '../primitives/Button';
import { Link } from '../primitives/Link';
import { useQfRouter } from '../router/RouterAdapter';

import '../overlay/Overlay.css';
import './Reader.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ReaderSection {
  /** Element id of the section heading inside the document. */
  id: string;
  label: string;
  /** Marker text, e.g. "1"; defaults to the section's position. */
  index?: string;
  /** Subsections, listed under the section while it is being read. */
  children?: readonly ReaderSection[];
}

export interface ReaderMetaItem {
  label: string;
  value: ReactNode;
}

export type ReaderAlignment = 'left' | 'center';

export interface ReaderPagerLink {
  label: string;
  to: string;
}

export interface ReaderLinkListProps {
  /** Section id, so a `ReaderSection` with the same id tracks it. */
  id: string;
  title: string;
  items: readonly ReaderPagerLink[];
  /** Shown instead of the list when there are no items. */
  empty?: ReactNode;
}

export interface ReaderPagerProps {
  previous?: ReaderPagerLink;
  next?: ReaderPagerLink;
  /** Accessible name of the sequence. */
  label?: string;
  className?: string;
}

export interface ReaderProps {
  title?: ReactNode;
  /** One or two sentences under the title. */
  lede?: ReactNode;
  /** Labelled facts under the lede. */
  meta?: readonly ReaderMetaItem[];
  sections?: readonly ReaderSection[];
  /** Controls placed before the alignment toggle. */
  actions?: ReactNode;
  /** Heading and accessible name of the table of contents. */
  label?: string;
  /** Previous and next documents in a sequence: in the rail, after the column, on ← and →. */
  pager?: Omit<ReaderPagerProps, 'className'>;
  className?: string;
  children: ReactNode;
}

// Alignment preference
// --------------------------------------------------------------------------- #

const ALIGNMENT_KEY = 'qf-reader-alignment';
const ALIGNMENT_EVENT = 'qf-reader-alignment-change';

function readAlignment(): ReaderAlignment {
  try {
    return window.localStorage.getItem(ALIGNMENT_KEY) === 'center' ? 'center' : 'left';
  } catch {
    return 'left';
  }
}

function subscribeAlignment(notify: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key === ALIGNMENT_KEY || event.key === null) notify();
  };
  window.addEventListener(ALIGNMENT_EVENT, notify);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener(ALIGNMENT_EVENT, notify);
    window.removeEventListener('storage', onStorage);
  };
}

function writeAlignment(next: ReaderAlignment) {
  try {
    window.localStorage.setItem(ALIGNMENT_KEY, next);
  } catch {
    // Storage may be unavailable; the event still updates this tab.
  }
  window.dispatchEvent(new Event(ALIGNMENT_EVENT));
}

/** The reading column's placement, shared by every reader in this browser. */
export function useReaderAlignment(): ReaderAlignment {
  return useSyncExternalStore(subscribeAlignment, readAlignment, () => 'left');
}

// --------------------------------------------------------------------------- #
// Reading position
// --------------------------------------------------------------------------- #

/** Distance below the pane's top edge at which a heading counts as reached. */
const READING_LINE = 48;
const PROGRESS_SEGMENTS = 24;

function scrollParent(element: HTMLElement): HTMLElement | null {
  for (let node = element.parentElement; node; node = node.parentElement) {
    const { overflowY } = window.getComputedStyle(node);
    if (overflowY === 'auto' || overflowY === 'scroll') return node;
  }
  return null;
}

function flatten(sections: readonly ReaderSection[]): ReaderSection[] {
  return sections.flatMap((section) => [section, ...flatten(section.children ?? [])]);
}

interface ReadingPosition {
  activeId: string | undefined;
  /** 0..1 through the document. */
  progress: number;
  /** The header has scrolled out of view. */
  pastHeader: boolean;
}

/** Where the reader is: the section last crossed, how far through, and whether the title is gone. */
function useReadingPosition(
  frameRef: RefObject<HTMLElement | null>,
  headerRef: RefObject<HTMLElement | null>,
  sections: readonly ReaderSection[],
): [ReadingPosition, (id: string) => void] {
  const [position, setPosition] = useState<ReadingPosition>({
    activeId: sections[0]?.id,
    progress: 0,
    pastHeader: false,
  });

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const container = scrollParent(frame);
    const target: HTMLElement | Window = container ?? window;
    const flat = flatten(sections);
    const update = () => {
      const top = container?.getBoundingClientRect().top ?? 0;
      const viewport = container?.clientHeight ?? window.innerHeight;
      let activeId = flat[0]?.id;
      for (const section of flat) {
        const element = document.getElementById(section.id);
        if (!element || element.getBoundingClientRect().top > top + READING_LINE) break;
        activeId = section.id;
      }
      const box = frame.getBoundingClientRect();
      const travel = box.height - viewport;
      const progress = travel > 0 ? Math.min(1, Math.max(0, (top - box.top) / travel)) : 1;
      if (progress >= 1) activeId = flat.at(-1)?.id ?? activeId;
      const header = headerRef.current;
      const pastHeader = header ? header.getBoundingClientRect().bottom < top : false;
      setPosition((previous) =>
        previous.activeId === activeId &&
        previous.progress === progress &&
        previous.pastHeader === pastHeader
          ? previous
          : { activeId, progress, pastHeader },
      );
    };
    update();
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(update) : undefined;
    observer?.observe(frame);
    target.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      observer?.disconnect();
      target.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, [frameRef, headerRef, sections]);

  const setActiveId = (id: string) => setPosition((previous) => ({ ...previous, activeId: id }));
  return [position, setActiveId];
}

// --------------------------------------------------------------------------- #
// Reference previews
// --------------------------------------------------------------------------- #

interface PreviewTarget {
  anchor: HTMLElement;
  title: string | undefined;
  text: string;
}

/** The `[data-preview]` element under the pointer or focus inside the document. */
function usePreviewTarget(bodyRef: RefObject<HTMLElement | null>): PreviewTarget | null {
  const [target, setTarget] = useState<PreviewTarget | null>(null);
  useEffect(() => {
    const body = bodyRef.current;
    if (!body) return;
    const show = (event: Event) => {
      const anchor =
        event.target instanceof Element
          ? event.target.closest<HTMLElement>('[data-preview]')
          : null;
      if (!anchor || !body.contains(anchor)) return;
      setTarget((previous) =>
        previous?.anchor === anchor
          ? previous
          : {
              anchor,
              title: anchor.dataset.previewTitle,
              text: anchor.dataset.preview ?? '',
            },
      );
    };
    const hide = (event: Event) => {
      const next = (event as FocusEvent | PointerEvent).relatedTarget;
      const leaving =
        event.target instanceof Element ? event.target.closest('[data-preview]') : null;
      if (leaving && !(next instanceof Node && leaving.contains(next))) setTarget(null);
    };
    body.addEventListener('pointerover', show);
    body.addEventListener('focusin', show);
    body.addEventListener('pointerout', hide);
    body.addEventListener('focusout', hide);
    return () => {
      body.removeEventListener('pointerover', show);
      body.removeEventListener('focusin', show);
      body.removeEventListener('pointerout', hide);
      body.removeEventListener('focusout', hide);
    };
  }, [bodyRef]);
  return target;
}

function ReferencePreview({ target }: { target: PreviewTarget | null }) {
  return (
    <PreviewCard.Root open={target !== null}>
      <PreviewCard.Portal>
        <PreviewCard.Positioner
          className="ui-overlay-positioner"
          anchor={target?.anchor ?? null}
          side="top"
          align="center"
          sideOffset={OVERLAY_SIDE_OFFSET}
        >
          <PreviewCard.Popup className="ui-overlay-surface qf-reader-preview qf-motion-pop">
            {target?.title ? <p className="qf-reader-preview-title">{target.title}</p> : null}
            <p className="qf-reader-preview-text">{target?.text}</p>
          </PreviewCard.Popup>
        </PreviewCard.Positioner>
      </PreviewCard.Portal>
    </PreviewCard.Root>
  );
}

// --------------------------------------------------------------------------- #
// Rail
// --------------------------------------------------------------------------- #

function ProgressBar({ progress }: { progress: number }) {
  const filled = Math.round(progress * PROGRESS_SEGMENTS);
  const percent = Math.round(progress * 100);
  return (
    <div
      className="qf-reader-progress-bar"
      role="progressbar"
      aria-label="Reading progress"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      {Array.from({ length: PROGRESS_SEGMENTS }, (_, index) => (
        <span key={index} data-filled={index < filled ? '' : undefined} />
      ))}
      <span className="qf-reader-progress-value">{percent}%</span>
    </div>
  );
}

function TocList({
  sections,
  activeId,
  activePath,
  onJump,
  nested = false,
}: {
  sections: readonly ReaderSection[];
  activeId: string | undefined;
  activePath: ReadonlySet<string>;
  onJump: (event: MouseEvent<HTMLAnchorElement>, id: string) => void;
  nested?: boolean;
}) {
  return (
    <ol className={nested ? 'qf-reader-toc-sublist' : 'qf-reader-toc-list'}>
      {sections.map((section, position) => (
        <li key={section.id}>
          <a
            href={`#${section.id}`}
            className={nested ? 'qf-reader-toc-subitem' : 'qf-reader-toc-item'}
            aria-current={section.id === activeId ? 'location' : undefined}
            data-on-path={activePath.has(section.id) ? '' : undefined}
            onClick={(event) => onJump(event, section.id)}
          >
            {nested ? null : (
              <span className="qf-reader-toc-marker" aria-hidden="true">
                {/* A chapter's "2.1" is "1" here: the round marker holds one number. */}
                {section.index?.split('.').at(-1) ?? position + 1}
              </span>
            )}
            <span className="qf-reader-toc-text">{section.label}</span>
          </a>
          {section.children?.length && activePath.has(section.id) ? (
            <TocList
              sections={section.children}
              activeId={activeId}
              activePath={activePath}
              onJump={onJump}
              nested
            />
          ) : null}
        </li>
      ))}
    </ol>
  );
}

/** Ids of the active section and every section that contains it. */
function pathTo(sections: readonly ReaderSection[], id: string | undefined): Set<string> {
  const path = new Set<string>();
  const walk = (items: readonly ReaderSection[]): boolean => {
    for (const item of items) {
      if (item.id === id || walk(item.children ?? [])) {
        path.add(item.id);
        return true;
      }
    }
    return false;
  };
  walk(sections);
  return path;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Reader({
  title,
  lede,
  meta = [],
  sections = [],
  actions,
  label = 'On this page',
  pager,
  className,
  children,
}: ReaderProps) {
  const frameRef = useRef<HTMLDivElement | null>(null);
  const headerRef = useRef<HTMLElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const alignment = useReaderAlignment();
  const [position, setActiveId] = useReadingPosition(frameRef, headerRef, sections);
  const preview = usePreviewTarget(bodyRef);
  const activePath = useMemo(
    () => pathTo(sections, position.activeId),
    [sections, position.activeId],
  );
  useArrowKeyPaging(pager);
  const toggleLabel = alignment === 'center' ? 'Move reading column left' : 'Center reading column';
  const ToggleIcon = alignment === 'center' ? AlignLeft : AlignCenter;

  const jump = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    const element = document.getElementById(id);
    if (!element) return;
    event.preventDefault();
    setActiveId(id);
    if (window.location.hash !== `#${id}`) window.history.pushState(null, '', `#${id}`);
    element.scrollIntoView({ block: 'start' });
  };

  return (
    <div ref={frameRef} className={cn('qf-reader', className)} data-align={alignment}>
      <div className="qf-reader-layout">
        <aside className="qf-reader-rail">
          <div className="qf-reader-actions">
            {actions}
            <Button
              variant="control"
              size="sm"
              icon
              aria-label={toggleLabel}
              title={toggleLabel}
              onClick={() => writeAlignment(alignment === 'center' ? 'left' : 'center')}
            >
              <ToggleIcon aria-hidden="true" size={ICON_SIZE} strokeWidth={ICON_STROKE} />
            </Button>
          </div>
          {title ? (
            <p className="qf-reader-rail-title" data-shown={position.pastHeader ? '' : undefined}>
              {title}
            </p>
          ) : null}
          {sections.length > 0 ? (
            <nav aria-label={label} className="qf-reader-toc">
              <p className="qf-reader-toc-label">{label}</p>
              <TocList
                sections={sections}
                activeId={position.activeId}
                activePath={activePath}
                onJump={jump}
              />
            </nav>
          ) : null}
          <ProgressBar progress={position.progress} />
          {pager ? <RailPager {...pager} /> : null}
        </aside>
        <div className="qf-reader-column">
          {title || lede || meta.length > 0 ? (
            <header ref={headerRef} className="qf-reader-header">
              {title ? <h1 className="qf-reader-title">{title}</h1> : null}
              {lede ? <p className="qf-reader-lede">{lede}</p> : null}
              {meta.length > 0 ? (
                <dl className="qf-reader-meta">
                  {meta.map((item) => (
                    <div key={item.label} className="qf-reader-meta-item">
                      <dt>{item.label}</dt>
                      <dd>{item.value}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
            </header>
          ) : null}
          <div ref={bodyRef} className="qf-reader-body">
            {children}
          </div>
          {pager ? <ReaderPager {...pager} /> : null}
        </div>
      </div>
      <ReferencePreview target={preview} />
    </div>
  );
}

// --------------------------------------------------------------------------- #
// Link list and pager
// --------------------------------------------------------------------------- #

/** A titled list of links in document type; place one or more inside a `Prose`. */
export function ReaderLinkList({ id, title, items, empty }: ReaderLinkListProps) {
  return (
    <>
      <h2 id={id}>{title}</h2>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item.to}>
              <Link to={item.to}>{item.label}</Link>
            </li>
          ))}
        </ul>
      ) : (
        <p>{empty}</p>
      )}
    </>
  );
}

/** ← and → open the previous and next documents, unless a field or a modifier has the key. */
function useArrowKeyPaging(pager: ReaderProps['pager']) {
  const navigate = useQfRouter().useNavigate();
  const previous = pager?.previous?.to;
  const next = pager?.next?.to;
  useEffect(() => {
    if (!previous && !next) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.shiftKey || isTypingTarget(event.target)) return;
      const to = event.key === 'ArrowLeft' ? previous : event.key === 'ArrowRight' ? next : null;
      if (!to) return;
      event.preventDefault();
      navigate(to);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [previous, next, navigate]);
}

/** The sequence's previous and next titles in the rail, always in reach while reading. */
function RailPager({ previous, next, label = 'Sequence' }: Omit<ReaderPagerProps, 'className'>) {
  if (!previous && !next) return null;
  return (
    <nav className="qf-reader-rail-pager" aria-label={`${label} (rail)`}>
      {previous ? (
        <Link to={previous.to} variant="subtle" className="qf-reader-rail-pager-link" rel="prev">
          <span className="qf-reader-pager-label">← Previous</span>
          <span className="qf-reader-rail-pager-title">{previous.label}</span>
        </Link>
      ) : null}
      {next ? (
        <Link to={next.to} variant="subtle" className="qf-reader-rail-pager-link" rel="next">
          <span className="qf-reader-pager-label">Next →</span>
          <span className="qf-reader-rail-pager-title">{next.label}</span>
        </Link>
      ) : null}
    </nav>
  );
}

/** Previous and next documents in a sequence, as two cards at the end of the column. */
export function ReaderPager({ previous, next, label = 'Sequence', className }: ReaderPagerProps) {
  if (!previous && !next) return null;
  return (
    <nav className={cn('qf-reader-pager', className)} aria-label={label}>
      {previous ? (
        <Link to={previous.to} variant="subtle" className="qf-reader-pager-link" rel="prev">
          <span className="qf-reader-pager-label">← Previous</span>
          <span className="qf-reader-pager-title">{previous.label}</span>
        </Link>
      ) : null}
      {next ? (
        <Link
          to={next.to}
          variant="subtle"
          className="qf-reader-pager-link"
          data-direction="next"
          rel="next"
        >
          <span className="qf-reader-pager-label">Next →</span>
          <span className="qf-reader-pager-title">{next.label}</span>
        </Link>
      ) : null}
    </nav>
  );
}
