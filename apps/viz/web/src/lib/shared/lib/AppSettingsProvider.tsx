/**
 * React provider for app-wide visualization preferences.
 *
 * USAGE:
 *   <AppSettingsProvider><App /></AppSettingsProvider>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type ReactNode, useState } from 'react';
import { applyQfTheme, type QfThemeId } from '@/ui';

import {
  AppSettingsContext,
  persistPreviewPageSize,
  persistSectionNavNarrow,
  persistSidebarCollapsed,
  persistTheme,
  readPreviewPageSize,
  readSectionNavNarrow,
  readSidebarCollapsed,
  readTheme,
} from './app-settings';

// --------------------------------------------------------------------------- #
// Provider
// --------------------------------------------------------------------------- #

export function AppSettingsProvider({ children }: { children: ReactNode }) {
  const [previewPageSize, setPageSize] = useState(readPreviewPageSize);
  const [sidebarCollapsed, setCollapsed] = useState(readSidebarCollapsed);
  const [sectionNavNarrow, setNarrow] = useState(readSectionNavNarrow);
  const [theme, setThemeState] = useState(readTheme);

  function setPreviewPageSize(value: number) {
    if (persistPreviewPageSize(value)) setPageSize(value);
  }

  function setSidebarCollapsed(value: boolean) {
    persistSidebarCollapsed(value);
    setCollapsed(value);
  }

  function setSectionNavNarrow(value: boolean) {
    persistSectionNavNarrow(value);
    setNarrow(value);
  }

  function setTheme(value: QfThemeId) {
    persistTheme(value);
    applyQfTheme(value);
    setThemeState(value);
  }

  return (
    <AppSettingsContext
      value={{
        previewPageSize,
        setPreviewPageSize,
        sidebarCollapsed,
        setSidebarCollapsed,
        sectionNavNarrow,
        setSectionNavNarrow,
        theme,
        setTheme,
      }}
    >
      {children}
    </AppSettingsContext>
  );
}
