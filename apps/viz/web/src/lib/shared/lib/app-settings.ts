/**
 * Shared state contract and persistence helpers for visualization preferences.
 *
 * USAGE:
 *   const { previewPageSize, setPreviewPageSize } = useAppSettings();
 *   const { sidebarCollapsed, setSidebarCollapsed } = useAppSettings();
 *   const { sectionNavNarrow, setSectionNavNarrow } = useAppSettings();
 *   const { theme, setTheme } = useAppSettings();
 *   persistPreviewPageSize(100);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { createContext, useContext } from 'react';
import { isQfThemeId, QF_DEFAULT_THEME, type QfThemeId } from '@/ui';

// --------------------------------------------------------------------------- #
// Settings contract
// --------------------------------------------------------------------------- #

const PAGE_SIZE_KEY = 'qf-viz-preview-page-size';
const DEFAULT_PREVIEW_PAGE_SIZE = 50;
const SIDEBAR_COLLAPSED_KEY = 'qf-viz-sidebar-collapsed';
const DEFAULT_SIDEBAR_COLLAPSED = true;
const SECTION_NAV_NARROW_KEY = 'qf-viz-section-nav-narrow';
// index.html reads this key before first paint; keep the two in step.
const THEME_KEY = 'qf-viz-theme';

export const PREVIEW_PAGE_SIZE_OPTIONS = [25, 50, 100, 250] as const;

export interface AppSettingsValue {
  previewPageSize: number;
  setPreviewPageSize: (value: number) => void;
  /** Primary sidebar collapsed to its icon rail (desktop); persisted across reloads. */
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (value: boolean) => void;
  /** Secondary section navigators use the narrow width; persisted across reloads. */
  sectionNavNarrow: boolean;
  setSectionNavNarrow: (value: boolean) => void;
  /** Colour palette applied as `data-theme` on <html>; persisted across reloads. */
  theme: QfThemeId;
  setTheme: (value: QfThemeId) => void;
}

export const AppSettingsContext = createContext<AppSettingsValue | null>(null);

// --------------------------------------------------------------------------- #
// Persistence
// --------------------------------------------------------------------------- #

function isPreviewPageSize(value: number): boolean {
  return PREVIEW_PAGE_SIZE_OPTIONS.includes(value as (typeof PREVIEW_PAGE_SIZE_OPTIONS)[number]);
}

export function readPreviewPageSize(): number {
  const stored = Number(localStorage.getItem(PAGE_SIZE_KEY));
  return isPreviewPageSize(stored) ? stored : DEFAULT_PREVIEW_PAGE_SIZE;
}

export function persistPreviewPageSize(value: number): boolean {
  if (!isPreviewPageSize(value)) return false;
  localStorage.setItem(PAGE_SIZE_KEY, String(value));
  return true;
}

export function readSidebarCollapsed(): boolean {
  const stored = localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
  if (stored === '1') return true;
  if (stored === '0') return false;
  return DEFAULT_SIDEBAR_COLLAPSED;
}

export function persistSidebarCollapsed(value: boolean): void {
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, value ? '1' : '0');
}

export function readSectionNavNarrow(): boolean {
  return localStorage.getItem(SECTION_NAV_NARROW_KEY) === '1';
}

export function persistSectionNavNarrow(value: boolean): void {
  localStorage.setItem(SECTION_NAV_NARROW_KEY, value ? '1' : '0');
}

export function readTheme(): QfThemeId {
  const stored = localStorage.getItem(THEME_KEY);
  return isQfThemeId(stored) ? stored : QF_DEFAULT_THEME;
}

export function persistTheme(value: QfThemeId): void {
  localStorage.setItem(THEME_KEY, value);
}

// --------------------------------------------------------------------------- #
// Consumer hook
// --------------------------------------------------------------------------- #

export function useAppSettings(): AppSettingsValue {
  const settings = useContext(AppSettingsContext);
  if (!settings) throw new Error('useAppSettings must be used within AppSettingsProvider');
  return settings;
}
