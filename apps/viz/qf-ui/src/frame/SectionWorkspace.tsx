/**
 * Shared section workspace with a persistent navigator and routed content surface.
 *
 * The navigator always docks beside the content and toggles between a wide and a
 * narrow width. The width comes from the `narrow` / `onNarrowChange` props, else
 * from the nearest `SectionNavigatorWidthProvider` (a host mounts one to share and
 * persist the preference across every section navigator), else local state.
 *
 * USAGE:
 *   <SectionNavigatorWidthProvider narrow={narrow} onNarrowChange={setNarrow}>
 *     <SectionWorkspace navigator={<SectionNavigator … />}>…</SectionWorkspace>
 *   </SectionNavigatorWidthProvider>
 *   <SectionNavigator title="Docs" narrow={narrow} onNarrowChange={setNarrow} … />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { FoldHorizontal, UnfoldHorizontal } from 'lucide-react';
import { createContext, type ReactNode, useContext, useState } from 'react';

import { cn } from '../lib/cn';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';
import { Button } from '../primitives/Button';
import { SidebarCollapseButton } from '../shell/SidebarCollapseButton';
import { SidebarShell } from '../shell/SidebarShell';
import {
  WorkspaceHeaderTargetProvider,
  WorkspaceToolbarTargetProvider,
} from './WorkspaceHeaderPortal';

import './SectionWorkspace.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SectionWorkspaceProps {
  navigator: ReactNode;
  children: ReactNode;
  className?: string;
  /** 'scroll' (default): the content pane scrolls and carries the page inset.
   *  'fill': the pane is a bounded flex column with no padding; the child owns its overflow. */
  contentMode?: 'scroll' | 'fill';
  /** Remounts only the content pane when it changes (e.g. the pathname), so the
   *  navigator keeps its scroll and expansion state across in-section navigation. */
  contentKey?: string;
}

export interface SectionNavigatorProps {
  title: string;
  /** The section's home route; the header title links there. */
  titleTo?: string | undefined;
  collapsed: boolean;
  onToggleCollapse: () => void;
  headerActions?: ReactNode;
  controls?: ReactNode;
  /** Footer slot rendered after the rows. */
  footerControls?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Which workspace edge the navigator docks to. Default 'start'. */
  side?: 'start' | 'end';
  /**
   * Collapsed presentation: 'tile' (default) floats the 32px expand tile at the
   * bottom of the column, where the collapse button sat; 'strip' keeps a narrow column
   * with a vertical title and the expand button at its foot.
   */
  collapsedVariant?: 'tile' | 'strip';
  /** Controlled narrow width; defaults to the nearest width provider, else local state. */
  narrow?: boolean | undefined;
  onNarrowChange?: ((narrow: boolean) => void) | undefined;
}

export interface SectionNavigatorWidth {
  narrow: boolean;
  onNarrowChange: (narrow: boolean) => void;
}

export interface SectionNavigatorWidthProviderProps extends SectionNavigatorWidth {
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Width preference
// --------------------------------------------------------------------------- #

const SectionNavigatorWidthContext = createContext<SectionNavigatorWidth | null>(null);

/** Shares one narrow-width preference with every section navigator below it. */
export function SectionNavigatorWidthProvider({
  narrow,
  onNarrowChange,
  children,
}: SectionNavigatorWidthProviderProps) {
  return (
    <SectionNavigatorWidthContext.Provider value={{ narrow, onNarrowChange }}>
      {children}
    </SectionNavigatorWidthContext.Provider>
  );
}

/**
 * Props first, then the nearest provider, then local state. The provider is the page's
 * primary (start-side) navigator preference; an end-side rail is a separate pane, so its
 * width toggle never moves the primary navigator and it keeps its own state.
 */
function useSectionNavNarrow(
  narrowProp: boolean | undefined,
  onNarrowChange: ((narrow: boolean) => void) | undefined,
  side: 'start' | 'end',
): [boolean, (value: boolean) => void] {
  const provided = useContext(SectionNavigatorWidthContext);
  const shared = side === 'start' ? provided : null;
  const [localNarrow, setLocalNarrow] = useState(false);
  const narrow = narrowProp ?? shared?.narrow ?? localNarrow;
  const setNarrow = (value: boolean) => {
    if (narrowProp === undefined) {
      if (shared) shared.onNarrowChange(value);
      else setLocalNarrow(value);
    }
    onNarrowChange?.(value);
  };
  return [narrow, setNarrow];
}

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function SectionWorkspace({
  navigator,
  children,
  className,
  contentMode = 'scroll',
  contentKey,
}: SectionWorkspaceProps) {
  const [headerTarget, setHeaderTarget] = useState<HTMLDivElement | null>(null);
  const [toolbarTarget, setToolbarTarget] = useState<HTMLDivElement | null>(null);

  return (
    <WorkspaceHeaderTargetProvider target={headerTarget}>
      <WorkspaceToolbarTargetProvider target={toolbarTarget}>
        <div
          className={cn(
            'section-workspace',
            contentMode === 'fill' && 'is-fill-content',
            className,
          )}
        >
          {navigator}
          <div className="section-workspace-main">
            <div ref={setHeaderTarget} className="section-workspace-header" />
            <div ref={setToolbarTarget} className="section-workspace-toolbar" />
            <div
              key={contentKey}
              className={cn('section-workspace-content', contentMode === 'fill' && 'is-fill')}
            >
              {children}
            </div>
          </div>
        </div>
      </WorkspaceToolbarTargetProvider>
    </WorkspaceHeaderTargetProvider>
  );
}

export function SectionNavigator({
  title,
  titleTo,
  collapsed,
  onToggleCollapse,
  headerActions,
  controls,
  footerControls,
  children,
  className,
  side = 'start',
  collapsedVariant = 'tile',
  narrow: narrowProp,
  onNarrowChange,
}: SectionNavigatorProps) {
  const [narrow, setNarrow] = useSectionNavNarrow(narrowProp, onNarrowChange, side);
  const widthLabel = `${narrow ? 'Widen' : 'Narrow'} ${title} navigation`;

  return (
    <aside
      className={cn(
        'section-navigator',
        collapsed && 'collapsed',
        narrow && 'is-narrow',
        side === 'end' && 'is-end',
        collapsedVariant === 'strip' && 'is-strip',
        className,
      )}
      aria-label={`${title} navigation`}
    >
      {collapsed && collapsedVariant === 'strip' ? (
        <div className="section-navigator-strip">
          <span className="section-navigator-strip-label" aria-hidden="true">
            {title}
          </span>
          <SidebarCollapseButton
            variant="icon"
            side={side === 'end' ? 'right' : 'left'}
            collapsed
            label={`Expand ${title} navigation`}
            onClick={onToggleCollapse}
          />
        </div>
      ) : (
        <SidebarShell
          title={title}
          titleTo={titleTo}
          collapsed={collapsed}
          collapsePlacement="bar"
          collapseButtonVariant={collapsed ? 'tile' : 'icon'}
          collapseSide={side === 'end' ? 'right' : 'left'}
          headerActions={headerActions}
          controls={controls}
          footerControls={footerControls}
          footerActions={
            collapsed ? undefined : (
              <Button
                type="button"
                className="sidebar-collapse-button section-navigator-width-toggle"
                aria-label={widthLabel}
                title={widthLabel}
                aria-pressed={narrow}
                onClick={() => setNarrow(!narrow)}
              >
                <span className="sidebar-collapse-icon-slot" aria-hidden="true">
                  {narrow ? (
                    <UnfoldHorizontal size={ICON_SIZE} strokeWidth={ICON_STROKE} />
                  ) : (
                    <FoldHorizontal size={ICON_SIZE} strokeWidth={ICON_STROKE} />
                  )}
                </span>
              </Button>
            )
          }
          onToggleCollapse={onToggleCollapse}
        >
          {!collapsed ? children : null}
        </SidebarShell>
      )}
    </aside>
  );
}
