/**
 * Application-wide TanStack Query provider.
 *
 * USAGE:
 *   <AppQueryProvider>
 *     <RouterProvider router={router} />
 *   </AppQueryProvider>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { QueryClientProvider } from '@tanstack/react-query';
import { type ReactNode, useState } from 'react';

import { createAppQueryClient } from './query-client';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function AppQueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => createAppQueryClient());
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
