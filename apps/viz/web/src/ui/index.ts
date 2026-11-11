/**
 * Public surface of the Viz design system: every UI element the app renders is
 * exported from here and imported as `@/ui`.
 *
 * The portable kit lives in `@quant-factory/qf-ui` (including the shell's
 * SidebarShell, Navigator and SectionWorkspace); this barrel re-exports it and adds
 * the Viz-bound shell and section frames that depend on React Router, TanStack
 * Query, app settings, or registered extensions.
 *
 * USAGE:
 *   import { Button, PageHeader, Surface } from '@/ui';
 *
 * Inside `src/ui/` import siblings by relative path, never through this barrel.
 */

// --------------------------------------------------------------------------- #
// Portable kit
// --------------------------------------------------------------------------- #

export * from '@quant-factory/qf-ui';

// --------------------------------------------------------------------------- #
// Router binding
// --------------------------------------------------------------------------- #

export * from './router/ViewerRouterProvider';

// --------------------------------------------------------------------------- #
// Frame
// --------------------------------------------------------------------------- #

export * from './frame/PipelineArchitectureMap';
export * from './frame/SectionLayout';

// --------------------------------------------------------------------------- #
// Shell
// --------------------------------------------------------------------------- #

export * from './shell/AppShell';
export * from './shell/CommandMenu';
export * from './shell/CommandMenuShortcut';
export * from './shell/SettingsButton';
export * from './shell/SettingsPanel';
export * from './shell/Sidebar';
export * from './shell/useNavigatorModel';
