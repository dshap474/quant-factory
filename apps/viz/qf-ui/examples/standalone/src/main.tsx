/**
 * Browser entry for the qf-ui standalone example.
 *
 * USAGE: loaded by index.html.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { QfRouterProvider } from '@quant-factory/qf-ui';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import '@quant-factory/qf-ui/charts/styles.css';
import './app.css';

import { App } from './App';
import { historyAdapter } from './router';

// --------------------------------------------------------------------------- #
// Bootstrap
// --------------------------------------------------------------------------- #

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root not found');

createRoot(rootEl).render(
  <StrictMode>
    <QfRouterProvider adapter={historyAdapter}>
      <App />
    </QfRouterProvider>
  </StrictMode>,
);
