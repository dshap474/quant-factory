/**
 * Inner sidebar chrome: brand, body, footer, collapse control.
 *
 * With `collapsePlacement="bar"` (section navigators) a 56px header band shows the
 * title only, and a 49px bottom bar holds every control: in DOM and visual order the
 * collapse button at the docked edge, then the header actions and the trailing actions
 * at the far edge. Collapsed, the bottom bar holds only the expand tile.
 *
 * `rail` marks the host's primary icon rail: its padding centers every 32px slot in
 * the rail and its brand row is a full-width flex row. Fill the rail with
 * `RailNavList` / `RailNavLink` (+ `RailNavDivider`): each link keeps its icon in a
 * permanent 32px slot, shows its label only while expanded, and a hover label while
 * collapsed; the current link takes the neutral selected fill and never a gold bar.
 *
 * USAGE:
 *   <SidebarShell title="quant-factory" rail collapsed={collapsed} ...>
 *     <RailNavList aria-label="Main navigation">
 *       <RailNavLink to="/data" label="Data" icon={<Database />} current collapsed={collapsed} />
 *       <RailNavDivider />
 *     </RailNavList>
 *   </SidebarShell>
 *   <SidebarShell title="Strategies" collapsePlacement="bar" collapseButtonVariant="icon" ...>
 *     <nav>...</nav>
 *   </SidebarShell>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentPropsWithoutRef, MouseEventHandler, ReactNode } from 'react';

import { cn } from '../lib/cn';
import { useQfRouter } from '../router/RouterAdapter';
import { SidebarCollapseButton } from './SidebarCollapseButton';
import './SidebarShell.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SidebarShellProps {
  title: string;
  /** With the 'bar' placement, the title links here (the section's home). */
  titleTo?: string | undefined;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  collapseButtonVariant?: 'bar' | 'tile' | 'icon';
  /** Edge the sidebar docks to; the collapse chevron points toward it. Default 'left'. */
  collapseSide?: 'left' | 'right';
  href?: string;
  onBrandClick?: () => void;
  brandShort?: string;
  headerActions?: ReactNode;
  controls?: ReactNode;
  footerControls?: ReactNode;
  /** Trailing controls on the collapse-button row (the bottom bar when placement is 'bar'). */
  footerActions?: ReactNode;
  /**
   * Where the collapse control lives. 'footer' (default) keeps it after the body;
   * 'bar' renders a title-only header band and a bottom bar holding the collapse
   * button first, then the header and trailing actions. Only applies without `href`.
   */
  collapsePlacement?: 'footer' | 'bar';
  /** The host's primary icon rail (rail padding and a full-width brand row). */
  rail?: boolean;
  children: ReactNode;
}

export interface RailNavListProps extends ComponentPropsWithoutRef<'nav'> {
  children: ReactNode;
}

export interface RailNavLinkProps {
  to: string;
  label: string;
  /** The route icon; it renders inside the permanent 32px slot. */
  icon: ReactNode;
  /** The current section: `aria-current="page"` and the neutral selected fill. */
  current?: boolean;
  /** Collapsed rail: icon only, with a hover/focus label beside the rail. */
  collapsed?: boolean;
  onClick?: MouseEventHandler<HTMLAnchorElement>;
}

// --------------------------------------------------------------------------- #
// Rail navigation
// --------------------------------------------------------------------------- #

/** The rail's route list. */
export function RailNavList({ className, children, ...rest }: RailNavListProps) {
  return (
    <nav className={cn('primary-nav-list', className)} {...rest}>
      {children}
    </nav>
  );
}

/** One rail route through the host router adapter. */
export function RailNavLink({
  to,
  label,
  icon,
  current = false,
  collapsed = false,
  onClick,
}: RailNavLinkProps) {
  const { Link } = useQfRouter();
  return (
    <Link
      to={to}
      aria-current={current ? 'page' : undefined}
      aria-label={label}
      onClick={onClick}
      className="nav-link flex items-center"
    >
      <span className="nav-icon-slot" aria-hidden="true">
        {icon}
      </span>
      {collapsed ? null : <span className="nav-label">{label}</span>}
      {collapsed ? (
        <span className="nav-hover-label" role="tooltip">
          {label}
        </span>
      ) : null}
    </Link>
  );
}

/** Hairline between rail route groups. */
export function RailNavDivider() {
  return <hr className="nav-section-divider" />;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SidebarShell({
  title,
  titleTo,
  collapsed = false,
  onToggleCollapse,
  collapseButtonVariant = 'bar',
  collapseSide = 'left',
  href,
  onBrandClick,
  brandShort,
  headerActions,
  controls,
  footerControls,
  footerActions,
  collapsePlacement = 'footer',
  rail = false,
  children,
}: SidebarShellProps) {
  const { Link } = useQfRouter();
  const shellClass = cn('shell', rail && 'shell-rail', collapsed && 'collapsed');
  const collapsedLabel = brandShort ?? title.slice(0, 2);
  const toggleLabel = `${collapsed ? 'Expand' : 'Collapse'} ${title} navigation`;
  const collapseButton = onToggleCollapse ? (
    <SidebarCollapseButton
      variant={collapseButtonVariant}
      side={collapseSide}
      collapsed={collapsed}
      label={toggleLabel}
      onClick={onToggleCollapse}
    />
  ) : null;

  if (!href && collapsePlacement === 'bar') {
    return (
      <div className={shellClass}>
        {collapsed ? null : (
          <div className="shell-header shell-topbar">
            {titleTo ? (
              <Link to={titleTo} className="shell-topbar-title is-link">
                {title}
              </Link>
            ) : (
              <div className="shell-topbar-title">{title}</div>
            )}
          </div>
        )}

        {controls && !collapsed ? <div className="controls">{controls}</div> : null}

        <div className="body">{children}</div>

        {footerControls ? <div className="footer">{footerControls}</div> : null}

        <div className="shell-bottombar">
          {collapseButton}
          {!collapsed && (headerActions || footerActions) ? (
            <div className="shell-bottombar-actions">
              {headerActions}
              {footerActions}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className={shellClass}>
      {href ? (
        <Link to={href} className="brand" onClick={onBrandClick} aria-label={`Go to ${title}`}>
          <span className="brand-short">
            <span className="brand-leading">
              {collapsedLabel}
              {collapsed ? null : (
                <span className="brand-suffix">
                  {title.startsWith(collapsedLabel) ? title.slice(collapsedLabel.length) : title}
                </span>
              )}
            </span>
          </span>
        </Link>
      ) : collapsed ? null : headerActions ? (
        <div className="shell-header">
          <div className="brand brand-static">
            <span>{title}</span>
          </div>
          <div className="shell-header-actions">{headerActions}</div>
        </div>
      ) : (
        <div className="brand brand-static">
          <span>{title}</span>
        </div>
      )}

      {controls && !collapsed ? <div className="controls">{controls}</div> : null}

      <div className="body">{children}</div>

      <div className="footer">
        {footerControls}
        {collapseButton && footerActions ? (
          <div className="footer-bar">
            {collapseButton}
            <div className="footer-bar-actions">{footerActions}</div>
          </div>
        ) : (
          collapseButton
        )}
      </div>
    </div>
  );
}
