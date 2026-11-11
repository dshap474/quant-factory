/**
 * Application route table (react-router library mode).
 *
 * USAGE:
 *   import { router } from './routes';
 *   <RouterProvider router={router} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { createElement } from 'react';
import {
  createBrowserRouter,
  Navigate,
  type RouteObject,
  redirect,
  useLocation,
  useParams,
} from 'react-router';
import { lazyNamed } from '@/ui';
import { defaultDashboard, extensionRoutes } from './extensions';
import { AppLayout } from './layouts/AppLayout';
import { RouteErrorBoundary } from './layouts/RouteErrorBoundary';
import { DashboardNotFoundPage } from './pages/dashboards/DashboardNotFoundPage';
import { PlaceholderPage } from './pages/PlaceholderPage';

// --------------------------------------------------------------------------- #
// Route bundles
// --------------------------------------------------------------------------- #

const HomePage = lazyNamed(() => import('./pages/HomePage'), 'HomePage');
const CatalogPage = lazyNamed(() => import('./pages/CatalogPage'), 'CatalogPage');
const CatalogDetailPage = lazyNamed(() => import('./pages/CatalogDetailPage'), 'CatalogDetailPage');
const FeaturesPage = lazyNamed(() => import('./pages/FeaturesPage'), 'FeaturesPage');
const MlEnginePage = lazyNamed(() => import('./pages/ml-engine/MlEnginePage'), 'MlEnginePage');
const BacktestEnginePage = lazyNamed(
  () => import('./pages/backtest-engine/BacktestEnginePage'),
  'BacktestEnginePage',
);
const BacktestRunPage = lazyNamed(
  () => import('./pages/backtest-engine/BacktestRunPage'),
  'BacktestRunPage',
);
const BacktestExecutionDayPage = lazyNamed(
  () => import('./pages/backtest-engine/BacktestExecutionDayPage'),
  'BacktestExecutionDayPage',
);
const SignalsPage = lazyNamed(() => import('./pages/SignalsPage'), 'SignalsPage');
const SignalsLayout = lazyNamed(() => import('./pages/signals/SignalsLayout'), 'SignalsLayout');
const SignalFamilyPage = lazyNamed(
  () => import('./pages/signals/SignalFamilyPage'),
  'SignalFamilyPage',
);
const SignalVersionPage = lazyNamed(
  () => import('./pages/signals/SignalVersionPage'),
  'SignalVersionPage',
);
const StrategiesLayout = lazyNamed(
  () => import('./pages/strategies/StrategiesLayout'),
  'StrategiesLayout',
);
const StrategiesPage = lazyNamed(
  () => import('./pages/strategies/StrategiesPage'),
  'StrategiesPage',
);
const BacktestingPage = lazyNamed(
  () => import('./pages/strategies/BacktestingPage'),
  'BacktestingPage',
);
const StrategyTypePage = lazyNamed(
  () => import('./pages/strategies/StrategyTypePage'),
  'StrategyTypePage',
);
const StrategyVersionPage = lazyNamed(
  () => import('./pages/strategies/StrategyVersionPage'),
  'StrategyVersionPage',
);
const ExecutionLayout = lazyNamed(
  () => import('./pages/execution/ExecutionLayout'),
  'ExecutionLayout',
);
const ExecutionIndexPage = lazyNamed(
  () => import('./pages/execution/ExecutionLayout'),
  'ExecutionIndexPage',
);
const ProductionLivePage = lazyNamed(
  () => import('./pages/production/ProductionLivePage'),
  'ProductionLivePage',
);
const OpsLayout = lazyNamed(() => import('./pages/ops/OpsLayout'), 'OpsLayout');
const OpsPage = lazyNamed(() => import('./pages/ops/OpsPage'), 'OpsPage');
const DocsPage = lazyNamed(() => import('./pages/DocsPage'), 'DocsPage');
const AgentsPage = lazyNamed(() => import('./pages/AgentsPage'), 'AgentsPage');
const AgentDetailPage = lazyNamed(
  () => import('./pages/agents/AgentDetailPage'),
  'AgentDetailPage',
);
const OptimizerRunPage = lazyNamed(
  () => import('./pages/agents/OptimizerRunPage'),
  'OptimizerRunPage',
);
const AgentRunPage = lazyNamed(() => import('./pages/agents/RunPage'), 'RunPage');
const AgentsLayout = lazyNamed(() => import('./pages/agents/AgentsLayout'), 'AgentsLayout');
const ResearchPage = lazyNamed(() => import('./pages/research/ResearchPage'), 'ResearchPage');
const ResearchLayout = lazyNamed(() => import('./pages/research/ResearchLayout'), 'ResearchLayout');
const ResearchDocPage = lazyNamed(
  () => import('./pages/research/ResearchDocPage'),
  'ResearchDocPage',
);
const SandboxPage = lazyNamed(() => import('./pages/sandbox/SandboxPage'), 'SandboxPage');
const SandboxLayout = lazyNamed(() => import('./pages/sandbox/SandboxLayout'), 'SandboxLayout');
const CorpusLayout = lazyNamed(() => import('./pages/corpus/CorpusLayout'), 'CorpusLayout');
const CorpusWikiPage = lazyNamed(() => import('./pages/corpus/CorpusWikiPage'), 'CorpusWikiPage');
const CorpusSourcesPage = lazyNamed(
  () => import('./pages/corpus/CorpusSourcesPage'),
  'CorpusSourcesPage',
);
const DashboardsLayout = lazyNamed(
  () => import('./pages/dashboards/DashboardsLayout'),
  'DashboardsLayout',
);

// --------------------------------------------------------------------------- #
// Redirects
// --------------------------------------------------------------------------- #

/** Redirect to `to`, keeping the current query string and hash. */
function RedirectWithSearch({ to }: { to: string }) {
  const { search, hash } = useLocation();
  return <Navigate to={{ pathname: to, search, hash }} replace />;
}

/** Research packages moved to the Sandbox section; /research/<package> keeps working. */
function SandboxPackageRedirect() {
  const { packageId = '' } = useParams();
  return <RedirectWithSearch to={`/sandbox/${packageId}`} />;
}

// --------------------------------------------------------------------------- #
// Error elements
// --------------------------------------------------------------------------- #

/**
 * Give every route its own error element so a thrown render or a stale lazy
 * chunk is caught at the closest route and stays inside the content pane.
 */
function withErrorElement(routes: RouteObject[]): RouteObject[] {
  return routes.map((route) => {
    if (route.index === true) {
      return { ...route, errorElement: <RouteErrorBoundary /> };
    }
    return {
      ...route,
      errorElement: <RouteErrorBoundary />,
      children: route.children ? withErrorElement(route.children) : route.children,
    };
  });
}

// --------------------------------------------------------------------------- #
// Routes
// --------------------------------------------------------------------------- #

export const routes: RouteObject[] = withErrorElement([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'catalog', element: <CatalogPage /> },
      { path: 'catalog/view', element: <CatalogDetailPage /> },
      { path: 'features', element: <FeaturesPage /> },
      { path: 'backtest-engine', element: <BacktestEnginePage /> },
      {
        path: 'backtest-engine/runs/:family/:version/:preset/:runId',
        element: <BacktestRunPage />,
      },
      {
        path: 'backtest-engine/runs/:family/:version/:preset/:runId/execution/:day',
        element: <BacktestExecutionDayPage />,
      },
      { path: 'ml-engine', element: <MlEnginePage /> },
      {
        path: 'signals',
        element: <SignalsLayout />,
        children: [
          { index: true, element: <SignalsPage /> },
          ...extensionRoutes('signals').map((route) => ({
            path: route.path,
            element: createElement(route.component),
          })),
          { path: ':family', element: <SignalFamilyPage /> },
          { path: ':family/:memoryVersion', element: <SignalVersionPage /> },
        ],
      },
      {
        path: 'strategies',
        element: <StrategiesLayout />,
        children: [
          { index: true, element: <StrategiesPage /> },
          { path: 'backtesting', element: <BacktestingPage /> },
          ...extensionRoutes('strategies').map((route) => ({
            path: route.path,
            element: createElement(route.component),
          })),
          { path: ':type', element: <StrategyTypePage /> },
          { path: ':type/:memoryVersion', element: <StrategyVersionPage /> },
        ],
      },
      // Paper Trading became Strategies → Backtesting; old links keep their query.
      { path: 'strategies/paper', element: <RedirectWithSearch to="/strategies/backtesting" /> },
      {
        path: 'execution',
        element: <ExecutionLayout />,
        children: [
          // The navigator, index page and every page come from installed 'execution' extensions.
          { index: true, element: <ExecutionIndexPage /> },
          ...extensionRoutes('execution').map((route) => ({
            path: route.path,
            element: createElement(route.component),
          })),
        ],
      },
      {
        path: 'production',
        children: [
          // Loader redirects resolve before render, so the section never paints empty.
          { index: true, loader: () => redirect('/production/live') },
          { path: 'live', element: <ProductionLivePage /> },
          { path: 'paper', element: <RedirectWithSearch to="/strategies/backtesting" /> },
        ],
      },
      {
        path: 'research',
        element: <ResearchLayout />,
        children: [
          { index: true, element: <ResearchPage /> },
          { path: 'doc/*', element: <ResearchDocPage /> },
          { path: ':packageId', element: <SandboxPackageRedirect /> },
        ],
      },
      {
        path: 'corpus',
        element: <CorpusLayout />,
        children: [
          { index: true, loader: () => redirect('/corpus/wiki') },
          { path: 'wiki/*', element: <CorpusWikiPage /> },
          { path: 'sources/*', element: <CorpusSourcesPage /> },
        ],
      },
      {
        path: 'sandbox',
        element: <SandboxLayout />,
        children: [
          { index: true, element: <SandboxPage /> },
          ...extensionRoutes('sandbox').map((route) => ({
            path: route.path,
            element: createElement(route.component),
          })),
          { path: 'doc/*', element: <ResearchDocPage /> },
        ],
      },
      {
        path: 'ops',
        element: <OpsLayout />,
        children: [
          { index: true, element: <OpsPage /> },
          { path: ':scope/:view?', element: <OpsPage /> },
        ],
      },
      {
        path: 'agents',
        element: <AgentsLayout />,
        children: [
          { index: true, element: <AgentsPage /> },
          { path: 'runs/:runId', element: <AgentRunPage /> },
          { path: ':agentId', element: <AgentDetailPage /> },
          { path: 'strategy-optimizer/runs/:runId', element: <OptimizerRunPage /> },
        ],
      },
      {
        path: 'dashboards',
        element: <DashboardsLayout />,
        children: [
          {
            index: true,
            loader: () => {
              const dashboard = defaultDashboard();
              return dashboard ? redirect(`/dashboards/${dashboard}`) : null;
            },
            element: <DashboardNotFoundPage />,
          },
          ...extensionRoutes('dashboards').map((route) => ({
            path: route.path,
            element: createElement(route.component),
          })),
          { path: ':dashboardId', element: <DashboardNotFoundPage /> },
        ],
      },
      { path: 'docs', element: <DocsPage /> },
      {
        path: '*',
        element: <PlaceholderPage title="Not found" subtitle="No page at this address" />,
      },
    ],
  },
]);

// --------------------------------------------------------------------------- #
// Entry point
// --------------------------------------------------------------------------- #

export const router = createBrowserRouter(routes);
