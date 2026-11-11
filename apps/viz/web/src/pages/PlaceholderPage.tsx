/**
 * Generic informational page used for the not-found route and unported sections.
 *
 * USAGE:
 *   <PlaceholderPage title="Not found" subtitle="No page at this address" />
 *   <PlaceholderPage title="Signals" message="This section isn't available yet." />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { CommandMenuShortcut, Link, PageHeader, Stack, Surface, Text } from '@/ui';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface PlaceholderPageProps {
  title: string;
  subtitle?: string;
  message?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function PlaceholderPage({ title, subtitle, message }: PlaceholderPageProps) {
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title={title} subtitle={subtitle} />
      <Surface padding="lg">
        <Stack gap="block">
          <Text as="p" size="sm" tone="muted">
            {message ?? "There's no page at this address."}
          </Text>
          <Text as="p" size="sm" tone="muted">
            <Link to="/" variant="inline">
              Back to overview
            </Link>{' '}
            or press <CommandMenuShortcut /> to jump to any page.
          </Text>
        </Stack>
      </Surface>
    </div>
  );
}
