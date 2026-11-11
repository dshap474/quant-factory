/**
 * Primary app navigation with product, operations, and footer sections.
 * A clicked item is marked current immediately; the router commits the new
 * location only once the next route has loaded, so the rail tracks the click.
 *
 * USAGE:
 *   <Sidebar
 *     collapsed={collapsed}
 *     onCloseSidebar={close}
 *     onToggleCollapse={toggle}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  Button,
  ICON_SIZE,
  ICON_STROKE,
  isRouteActive,
  RailNavDivider,
  RailNavLink,
  RailNavList,
  SidebarShell,
} from '@quant-factory/qf-ui';
import {
  Activity,
  ArrowLeftRight,
  BookOpen,
  BookText,
  Bot,
  ChartLine,
  Cpu,
  Database,
  FlaskConical,
  Layers,
  LayoutGrid,
  Library,
  type LucideIcon,
  Radio,
  Search,
  Timer,
  Waypoints,
} from 'lucide-react';
import { Fragment, useState } from 'react';
import { useLocation } from 'react-router';
import { mountInstalled, opsPanels } from '@/extensions';
import { COMMAND_MENU_SHORTCUT_LABEL, CommandMenuShortcut } from './CommandMenuShortcut';
import { SettingsButton } from './SettingsButton';
import './Sidebar.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SidebarProps {
  collapsed?: boolean;
  onCloseSidebar?: () => void;
  onOpenCommandMenu?: () => void;
  onToggleCollapse?: () => void;
}

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  dividerBefore?: boolean;
}

// --------------------------------------------------------------------------- #
// Data
// --------------------------------------------------------------------------- #

/** Primary rail items. Built on call, not at module load, so this module can be imported
    while `@/extensions` is still initialising (extensions import the `@/ui` barrel). */
export function primaryNavItems(): readonly NavItem[] {
  return [
    { label: 'Data', href: '/catalog', icon: Database },
    { label: 'Features', href: '/features', icon: Layers },
    { label: 'Signals', href: '/signals', icon: Radio },
    { label: 'Strategies', href: '/strategies', icon: ChartLine },
    // Execution pages are extension-built, so its tab exists only when an extension mounts it.
    ...(mountInstalled('execution')
      ? [{ label: 'Execution', href: '/execution', icon: ArrowLeftRight }]
      : []),
    { label: 'Production', href: '/production', icon: Activity },
    { label: 'Agents', href: '/agents', icon: Bot, dividerBefore: true },
    // Ops lists extension panels only, so its tab exists only when an extension installs one.
    ...(opsPanels().length > 0 ? [{ label: 'Ops', href: '/ops', icon: Timer }] : []),
    { label: 'Backtest Engine', href: '/backtest-engine', icon: Waypoints },
    { label: 'ML Engine', href: '/ml-engine', icon: Cpu },
    // Research knowledge: written docs, the book corpus and its wiki, then the lab.
    { label: 'Research', href: '/research', icon: BookText, dividerBefore: true },
    { label: 'Corpus', href: '/corpus', icon: Library },
    { label: 'Sandbox', href: '/sandbox', icon: FlaskConical },
    // Dashboards are extension-built surfaces, so they sit apart from the package's own.
    { label: 'Dashboards', href: '/dashboards', icon: LayoutGrid, dividerBefore: true },
  ];
}

export const DOCS_NAV_ITEM: NavItem = { label: 'Docs', href: '/docs', icon: BookOpen };

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function SidebarNavLink({
  item,
  pathname,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  return (
    <RailNavLink
      to={item.href}
      label={item.label}
      current={isRouteActive(pathname, item.href, item.href === '/')}
      collapsed={collapsed}
      {...(onNavigate ? { onClick: onNavigate } : {})}
      icon={<Icon className="h-4 w-4 flex-shrink-0" size={ICON_SIZE} strokeWidth={ICON_STROKE} />}
    />
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Sidebar({
  collapsed = false,
  onCloseSidebar,
  onOpenCommandMenu,
  onToggleCollapse,
}: SidebarProps) {
  const location = useLocation();
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const [committedPath, setCommittedPath] = useState(location.pathname);
  if (committedPath !== location.pathname) {
    setCommittedPath(location.pathname);
    setPendingHref(null);
  }
  const pathname = pendingHref ?? location.pathname;
  const navigate = (href: string) => () => {
    setPendingHref(href);
    onCloseSidebar?.();
  };

  return (
    <SidebarShell
      title="quant-factory"
      brandShort="q"
      href="/"
      rail
      collapsed={collapsed}
      onToggleCollapse={onToggleCollapse}
      onBrandClick={onCloseSidebar}
      footerControls={
        <div className={collapsed ? 'footer-actions collapsed' : 'footer-actions'}>
          <Button
            type="button"
            className={collapsed ? 'settings-button collapsed' : 'settings-button'}
            aria-label="Search pages"
            title={`Search pages (${COMMAND_MENU_SHORTCUT_LABEL})`}
            onClick={() => {
              onCloseSidebar?.();
              onOpenCommandMenu?.();
            }}
          >
            <span className="sidebar-control-icon-slot" aria-hidden="true">
              <Search size={ICON_SIZE} strokeWidth={ICON_STROKE} />
            </span>
            {collapsed ? null : (
              <>
                <span>Search</span>
                <CommandMenuShortcut className="sidebar-search-shortcut" />
              </>
            )}
          </Button>
          <nav aria-label="Footer navigation">
            <SidebarNavLink
              item={DOCS_NAV_ITEM}
              pathname={pathname}
              collapsed={collapsed}
              onNavigate={navigate(DOCS_NAV_ITEM.href)}
            />
          </nav>
          <SettingsButton collapsed={collapsed} />
        </div>
      }
    >
      <RailNavList aria-label="Main navigation">
        {primaryNavItems().map((item) => (
          <Fragment key={item.href}>
            {item.dividerBefore ? <RailNavDivider /> : null}
            <SidebarNavLink
              item={item}
              pathname={pathname}
              collapsed={collapsed}
              onNavigate={navigate(item.href)}
            />
          </Fragment>
        ))}
      </RailNavList>
    </SidebarShell>
  );
}
