/**
 * Shared link primitive: in-app routes via `to`, external URLs via `href`.
 *
 * External links open in a new tab with rel="noopener noreferrer" and a trailing ↗
 * marker; downloads stay in the same tab and carry no marker. `to` wins when both
 * are given.
 *
 * USAGE:
 *   <Link to="/agents">Agents</Link>
 *   <Link to={runHref} variant="subtle">{runId}</Link>
 *   <Link to={runHref} variant="control">Back to runs</Link>
 *   <Link to={runHref} variant="control" icon aria-label="Open run">…</Link>
 *   <Link to={runHref} variant="control" size="sm">Back</Link>
 *   <Link href="https://example.com/docs">Reference</Link>
 *   <Link href={fileUrl} download>report.csv</Link>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentPropsWithoutRef, ReactNode } from 'react';
import { cn } from '../lib/cn';
import { useQfRouter } from '../router/RouterAdapter';

import { type ControlSize, controlSizeClasses } from './control-size';

import './Link.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type LinkVariant = 'inline' | 'subtle' | 'control';

export interface LinkProps extends Omit<ComponentPropsWithoutRef<'a'>, 'href'> {
  /** In-app route; rendered through the router. Takes precedence over `href`. */
  to?: string;
  /** External URL or download target; rendered as a plain anchor. */
  href?: string;
  /** inline: accent text; subtle: inherits color, accent on hover; control: button-shaped. */
  variant?: LinkVariant;
  /** Only meaningful with variant="control"; mirrors Button's size step. Default `md`. */
  size?: ControlSize;
  /** Only meaningful with variant="control"; square icon-only control, mirrors Button. */
  icon?: boolean;
  /** Trailing ↗ marker; defaults to true for `href` links that are not downloads. */
  glyph?: boolean;
  /** Router location state; only applied to `to` links. */
  state?: unknown;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Link({
  to,
  href,
  variant = 'inline',
  size,
  icon = false,
  glyph,
  state,
  className,
  download,
  target,
  rel,
  children,
  ...rest
}: LinkProps) {
  const { Link: RouterLink } = useQfRouter();
  const classes = cn(
    'ui-link',
    variant === 'control' ? 'ui-button ui-button-control' : `ui-link-${variant}`,
    variant === 'control' ? controlSizeClasses(size, icon) : undefined,
    className,
  );

  if (to !== undefined) {
    return (
      <RouterLink
        to={to}
        state={state}
        className={classes}
        download={download}
        target={target}
        rel={rel}
        {...rest}
      >
        {children}
      </RouterLink>
    );
  }

  const opensNewTab = download === undefined || download === false;
  const showGlyph = glyph ?? opensNewTab;
  return (
    <a
      href={href}
      className={classes}
      download={download}
      target={target ?? (opensNewTab ? '_blank' : undefined)}
      rel={rel ?? (opensNewTab ? 'noopener noreferrer' : undefined)}
      {...rest}
    >
      {children}
      {showGlyph ? (
        <span aria-hidden="true" className="ui-link-glyph">
          ↗
        </span>
      ) : null}
    </a>
  );
}
