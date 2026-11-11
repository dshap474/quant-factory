/**
 * Browser entry for the quant-factory React viz SPA.
 *
 * USAGE:
 *   Loaded by index.html via <script type="module" src="/src/main.tsx">.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router';

import '@quant-factory/qf-ui/charts/styles.css';
import './app.css';

import { AppQueryProvider } from './lib/api/query-provider';
import { reloadForStaleChunk } from './lib/chunk-reload';
import { AppSettingsProvider } from './lib/shared/lib/AppSettingsProvider';
import { router } from './routes';

// --------------------------------------------------------------------------- #
// Stale-chunk recovery
// --------------------------------------------------------------------------- #

// A deploy replaces the hashed chunks this tab preloads; Vite reports the
// failure here before any route renders, and one reload picks up the new build.
window.addEventListener('vite:preloadError', (event) => {
  if (reloadForStaleChunk()) {
    event.preventDefault();
  }
});

// --------------------------------------------------------------------------- #
// Bootstrap
// --------------------------------------------------------------------------- #

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('Root element #root not found');
}

createRoot(rootEl).render(
  <StrictMode>
    <AppQueryProvider>
      <AppSettingsProvider>
        <RouterProvider router={router} />
      </AppSettingsProvider>
    </AppQueryProvider>
  </StrictMode>,
);
