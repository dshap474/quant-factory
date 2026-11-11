/**
 * Lazy-loaded body of the sidebar settings popover.
 *
 * USAGE:
 *   const SettingsPanel = lazyNamed(() => import('./SettingsPanel'), 'SettingsPanel');
 *   <SettingsPanel />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { isQfThemeId, QF_THEMES, SelectControl } from '@quant-factory/qf-ui';
import { PREVIEW_PAGE_SIZE_OPTIONS, useAppSettings } from '@/lib/shared/lib/app-settings';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SettingsPanel() {
  const { previewPageSize, setPreviewPageSize, theme, setTheme } = useAppSettings();

  return (
    <>
      <div className="settings-section">
        <div>
          <strong>Theme</strong>
          <span>Interface colours</span>
        </div>
        <label htmlFor="settings-theme">
          <span className="sr-only">Theme</span>
          <SelectControl
            id="settings-theme"
            className="settings-select"
            ariaLabel="Theme"
            value={theme}
            onValueChange={(value) => {
              if (isQfThemeId(value)) setTheme(value);
            }}
            options={QF_THEMES.map(({ id, label }) => ({ value: id, label }))}
          />
        </label>
      </div>
      <div className="settings-section">
        <div>
          <strong>Rows</strong>
          <span>Preview pagination</span>
        </div>
        <label htmlFor="settings-preview-rows">
          <span className="sr-only">Preview rows</span>
          <SelectControl
            id="settings-preview-rows"
            className="settings-select"
            ariaLabel="Preview rows"
            value={String(previewPageSize)}
            onValueChange={(value) => setPreviewPageSize(Number(value))}
            options={PREVIEW_PAGE_SIZE_OPTIONS.map((size) => ({
              value: String(size),
              label: size,
            }))}
          />
        </label>
      </div>
    </>
  );
}
