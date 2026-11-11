/**
 * Compact vertical index list with optional navigable rows.
 *
 * USAGE:
 *   <IndexList>
 *     <IndexBar href="/signals/x" title="Signal X" description="Latest signal summary" />
 *   </IndexList>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { cn } from '../lib/cn';
import { useQfRouter } from '../router/RouterAdapter';

import './IndexBar.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface IndexListProps {
  className?: string;
  children: ReactNode;
}

export interface IndexBarProps {
  href?: string;
  title: ReactNode;
  description?: ReactNode;
  status?: ReactNode;
  metrics?: ReactNode;
  tags?: ReactNode;
  monoTitle?: boolean;
  /** Leading marker for step/lane rows (e.g. '01', 'ML'). Renders a square hairline chip. */
  index?: ReactNode;
  /** Let the description wrap instead of ellipsing on one line. */
  wrap?: boolean;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function IndexList({ className, children }: IndexListProps) {
  return <div className={cn('index-list', className)}>{children}</div>;
}

export function IndexBar({
  href,
  title,
  description,
  status,
  metrics,
  tags,
  monoTitle = false,
  index,
  wrap = false,
  className,
}: IndexBarProps) {
  const { Link } = useQfRouter();
  const content = (
    <>
      {index !== undefined ? (
        <span className="index-bar-index" aria-hidden="true">
          {index}
        </span>
      ) : null}

      <div className="index-bar-main">
        <div className="index-bar-title-line">
          <h2 className={monoTitle ? 'index-bar-title font-mono' : 'index-bar-title'}>{title}</h2>
          {status}
        </div>
        {description ? <div className="index-bar-description">{description}</div> : null}
      </div>

      {metrics || tags ? (
        <div className="index-bar-side">
          {metrics ? <div className="index-bar-metrics">{metrics}</div> : null}
          {tags ? <div className="index-bar-tags">{tags}</div> : null}
        </div>
      ) : null}

      {href ? (
        <svg
          className="index-bar-arrow"
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="m9 18 6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : null}
    </>
  );

  const rootClass = cn(
    'index-bar',
    href && 'index-bar-link',
    index !== undefined && 'is-indexed',
    wrap && 'is-wrap',
    className,
  );

  if (href) {
    return (
      <Link className={rootClass} to={href}>
        {content}
      </Link>
    );
  }
  return <div className={rootClass}>{content}</div>;
}
