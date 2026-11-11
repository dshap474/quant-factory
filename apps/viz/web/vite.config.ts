/**
 * Vite config for the quant-factory React viz SPA.
 *
 * USAGE:
 *   pnpm dev          # /api and /health → VIZ_API_URL
 *   pnpm build        # production static build
 *   pnpm preview      # serve dist
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

// --------------------------------------------------------------------------- #
// Runtime configuration
// --------------------------------------------------------------------------- #

const apiTarget = process.env.VIZ_API_URL ?? 'http://127.0.0.1:8014';

// --------------------------------------------------------------------------- #
// Chunking
// --------------------------------------------------------------------------- #

/** pnpm-safe `node_modules` matcher for an explicit package list. */
function vendorPattern(packages: readonly string[]): RegExp {
  const alternation = packages
    .map((name) => name.replace(/[/\\^$*+?.()|[\]{}]/g, '\\$&'))
    .join('|');
  return new RegExp(`/node_modules/(?:\\.pnpm/[^/]+/node_modules/)?(?:${alternation})/`);
}

const VENDOR_REACT_PATTERN = vendorPattern(['react', 'react-dom', 'scheduler', 'react-router']);
const VENDOR_DATA_PATTERN = vendorPattern([
  'zod',
  '@tanstack/react-query',
  '@tanstack/query-core',
  'openapi-fetch',
]);

// --------------------------------------------------------------------------- #
// Local plugins
// --------------------------------------------------------------------------- #

// The three dominant text faces; the remaining faces load on demand via CSS.
const PRELOADED_FONT_NAMES = [
  'ibm-plex-sans-latin-400-normal',
  'ibm-plex-sans-latin-500-normal',
  'ibm-plex-sans-latin-600-normal',
];

const require = createRequire(import.meta.url);

/**
 * Preload the dominant woff2 faces so cold loads skip the CSS-parse delay. Text is hidden
 * until its face arrives (font-display: block), so dev needs this as much as a build does.
 */
function fontPreloadPlugin(): Plugin {
  let base = '/';
  return {
    name: 'viz:font-preload',
    configResolved(config) {
      base = config.base;
    },
    transformIndexHtml: {
      order: 'post',
      handler(_html, ctx) {
        const hrefs = ctx.bundle
          ? Object.keys(ctx.bundle)
              .filter(
                (fileName) =>
                  fileName.endsWith('.woff2') &&
                  PRELOADED_FONT_NAMES.some((name) => fileName.includes(name)),
              )
              .sort()
              .map((fileName) => `${base}${fileName}`)
          : PRELOADED_FONT_NAMES.map(
              (name) => `/@fs${require.resolve(`@fontsource/ibm-plex-sans/files/${name}.woff2`)}`,
            );
        return hrefs.map((href) => ({
          tag: 'link',
          attrs: { rel: 'preload', href, as: 'font', type: 'font/woff2', crossorigin: true },
          injectTo: 'head' as const,
        }));
      },
    },
  };
}

/**
 * `vite preview` serves everything with sirv's dev-mode `no-cache`; hashed
 * /assets/ files are immutable, so mark them cacheable (sirv keeps response
 * headers that are already set). index.html stays no-cache.
 */
function previewAssetCachePlugin(): Plugin {
  return {
    name: 'viz:preview-asset-cache',
    configurePreviewServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url?.startsWith('/assets/')) {
          res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
        }
        next();
      });
    },
  };
}

/** Emit a source-aware static-import graph for route bundle-closure checks. */
function routeModuleGraphPlugin(): Plugin {
  return {
    name: 'viz:route-module-graph',
    apply: 'build',
    generateBundle(_options, bundle) {
      const graph = Object.fromEntries(
        Object.values(bundle)
          .filter((output) => output.type === 'chunk')
          .map((chunk) => [
            chunk.fileName,
            {
              imports: chunk.imports,
              containsEcharts: Object.keys(chunk.modules).some((id) =>
                /\/node_modules\/(?:\.pnpm\/[^/]+\/node_modules\/)?(?:echarts|zrender)\//.test(id),
              ),
            },
          ]),
      );
      this.emitFile({
        type: 'asset',
        fileName: '.vite/route-module-graph.json',
        source: JSON.stringify(graph, null, 2),
      });
    },
  };
}

// --------------------------------------------------------------------------- #
// Config
// --------------------------------------------------------------------------- #

type ProxyRoute = { target: string; changeOrigin: boolean };

/** Proxy routes Viz extensions declare in `vite.proxy.json` (`{ "<path prefix>": "<target URL>" }`).
 *  They spread ahead of the generic `/api` route, so a more specific prefix wins. */
function extensionProxies(): Record<string, ProxyRoute> {
  const root = fileURLToPath(new URL('../extensions/', import.meta.url));
  const routes: Record<string, ProxyRoute> = {};
  if (!fs.existsSync(root)) return routes;
  for (const name of fs.readdirSync(root).sort()) {
    const file = path.join(root, name, 'vite.proxy.json');
    if (!fs.existsSync(file)) continue;
    const declared = JSON.parse(fs.readFileSync(file, 'utf8')) as Record<string, string>;
    for (const [prefix, target] of Object.entries(declared)) {
      routes[prefix] = { target, changeOrigin: true };
    }
  }
  return routes;
}

export default defineConfig(({ mode }) => ({
  build: {
    manifest: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Rollup hoists shared vendor code into the FIRST matching manual
          // chunk, so these named vendor groups must precede the extension
          // rule — otherwise zod/TanStack Query land in an extension chunk that
          // index.html then modulepreloads. Never add a catch-all vendor group:
          // it would drag ECharts out of its isolated lazy chart chunk.
          if (VENDOR_REACT_PATTERN.test(id)) return 'vendor-react';
          if (VENDOR_DATA_PATTERN.test(id)) return 'vendor-data';
          const match = id.match(/\/extensions\/([^/]+)\/api\.ts$/);
          return match?.[1] ? `extension-api-${match[1]}` : undefined;
        },
      },
    },
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify(mode === 'production' ? 'production' : 'development'),
    'process.env.QF_CHART_DEBUG': JSON.stringify(process.env.QF_CHART_DEBUG ?? '0'),
  },
  plugins: [
    tailwindcss(),
    react({
      babel: {
        plugins: [['babel-plugin-react-compiler', {}]],
      },
    }),
    fontPreloadPlugin(),
    previewAssetCachePlugin(),
    routeModuleGraphPlugin(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    // Extension source lives beside `web`, so resolve its bare imports through
    // this app's declared dependency graph instead of the importer's directory.
    dedupe: [
      '@quant-factory/qf-ui/charts',
      '@quant-factory/qf-ui/tables',
      '@quant-factory/qf-ui/tables/core',
      '@tanstack/react-query',
      'lucide-react',
      'react',
      'react-dom',
      'react-router',
      'zod',
    ],
  },
  server: {
    host: '127.0.0.1',
    allowedHosts: ['quant-factory.localhost'],
    port: 5174,
    strictPort: true,
    // Fonts resolve into the pnpm store at the repo root; allow the workspace, not just this app.
    fs: {
      allow: [fileURLToPath(new URL('../../../', import.meta.url))],
    },
    proxy: {
      ...extensionProxies(),
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      // The OpenAPI `/health` route is served outside the `/api` prefix.
      '/health': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  // E2E uses `vite preview`; mirror dev proxies so a live API is reachable.
  preview: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: {
      ...extensionProxies(),
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/health': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
}));
