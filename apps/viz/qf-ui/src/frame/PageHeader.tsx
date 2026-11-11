/**
 * Page title rail (fixed 56px): the title (with optional badges) on top and an optional
 * one-line subtitle underneath; actions sit right. There is no eyebrow or breadcrumb row:
 * every page header reads title, then subtitle.
 *
 * A page with views passes its tab strip as `tabs`: the tabs lead the rail from the left
 * and the title block shows in full at the right edge. Once the tabs reach it, the title
 * truncates down to its minimum width; when even that does not fit, the title leaves the
 * rail and only then do tabs fold into More. `right` drops to a toolbar row under the rail.
 *
 * USAGE:
 *   <PageHeader title="Signals" subtitle="…" right={<…>} />
 *   <PageHeader title="Round 12" badges={<StatusBadge status="sealed" />} />
 *   <PageHeader kicker="CRYPTO" title="Example Strategy / v003" />
 *   <PageHeader title="Strategies" tabs={<RouteTabs label="Strategies views" items={tabs} />} />
 *   <PageHeader title="v002 / book" back={<Link to="/backtest-engine" …>…</Link>} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode, RefObject } from 'react';
import { useLayoutEffect, useRef, useState } from 'react';
import { cn } from '../lib/cn';

import { TabOverflowProvider } from '../primitives/tab-overflow';
import { WorkspaceHeaderPortal, WorkspaceToolbarPortal } from './WorkspaceHeaderPortal';
import './PageHeader.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface PageHeaderProps {
  title: string;
  /** Short overline label set inline before the title (a family's sector). */
  kicker?: string;
  /** One line under the title; ellipsizes past the rail width, or past the title's width beside tabs. */
  subtitle?: ReactNode;
  /** Status badges rendered right after the title. */
  badges?: ReactNode;
  right?: ReactNode;
  /** The page's view tabs (RouteTabs or a tabs SegmentedControl); see the header note. */
  tabs?: ReactNode;
  /** A back control (usually an icon link to the parent list) set before the title. */
  back?: ReactNode;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Title fit
// --------------------------------------------------------------------------- #

/**
 * Whether the title block fits beside the tabs at its minimum width. The tabs' full width
 * is read while the title shows (tabs never fold then), so the same number decides when
 * the title leaves and when it returns.
 */
function useTitleFits(
  header: HTMLElement | null,
  tabsRef: RefObject<HTMLElement | null>,
  copyRef: RefObject<HTMLElement | null>,
): boolean {
  const [fits, setFits] = useState(true);
  const tabsWidth = useRef(0);
  const copyMin = useRef(0);

  useLayoutEffect(() => {
    const tabs = tabsRef.current;
    if (!header || !tabs) return;
    const measure = () => {
      const copy = copyRef.current;
      if (fits && copy) {
        tabsWidth.current = tabs.offsetWidth;
        copyMin.current = Number.parseFloat(getComputedStyle(copy).minWidth) || 0;
      }
      const style = getComputedStyle(header);
      const room =
        header.clientWidth -
        Number.parseFloat(style.paddingLeft) -
        Number.parseFloat(style.paddingRight);
      const needed =
        tabsWidth.current + (Number.parseFloat(style.columnGap) || 0) + copyMin.current;
      setFits(room >= needed);
    };
    measure();
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : undefined;
    observer?.observe(header);
    observer?.observe(tabs);
    return () => observer?.disconnect();
  }, [header, tabsRef, copyRef, fits]);

  return fits;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function PageHeader({
  kicker,
  title,
  subtitle,
  badges,
  right,
  tabs,
  back,
  className,
}: PageHeaderProps) {
  // State, not a ref: the header mounts through a portal after this component does.
  const [header, setHeader] = useState<HTMLElement | null>(null);
  const tabsRef = useRef<HTMLDivElement | null>(null);
  const copyRef = useRef<HTMLDivElement | null>(null);
  const titleFits = useTitleFits(header, tabsRef, copyRef);
  if (tabs) {
    return (
      <>
        <WorkspaceHeaderPortal>
          <header
            ref={setHeader}
            className={cn('page-header has-tabs', !titleFits && 'is-title-hidden', className)}
          >
            <div ref={tabsRef} className="page-header-tabs">
              <TabOverflowProvider enabled={!titleFits}>{tabs}</TabOverflowProvider>
            </div>
            {titleFits ? (
              <div ref={copyRef} className="page-header-copy">
                <div className="page-header-title-line">
                  {badges ? <span className="page-header-badges">{badges}</span> : null}
                  {kicker ? <span className="page-header-kicker">{kicker}</span> : null}
                  <h1 title={title}>{title}</h1>
                </div>
                {subtitle ? (
                  <div
                    className="page-header-subtitle"
                    title={typeof subtitle === 'string' ? subtitle : undefined}
                  >
                    {subtitle}
                  </div>
                ) : null}
              </div>
            ) : null}
          </header>
        </WorkspaceHeaderPortal>
        {right ? (
          <WorkspaceToolbarPortal>
            <div className="page-header-toolbar">{right}</div>
          </WorkspaceToolbarPortal>
        ) : null}
      </>
    );
  }
  const copy = (
    <div className="page-header-copy">
      <div className="page-header-title-line">
        {kicker ? <span className="page-header-kicker">{kicker}</span> : null}
        <h1>{title}</h1>
        {badges ? <span className="page-header-badges">{badges}</span> : null}
      </div>
      {subtitle ? <div className="page-header-subtitle">{subtitle}</div> : null}
    </div>
  );
  return (
    <WorkspaceHeaderPortal>
      <header className={cn('page-header', className)}>
        {back ? (
          <div className="page-header-lead">
            <span className="page-header-back">{back}</span>
            {copy}
          </div>
        ) : (
          copy
        )}
        {right ? <div className="page-header-actions">{right}</div> : null}
      </header>
    </WorkspaceHeaderPortal>
  );
}
