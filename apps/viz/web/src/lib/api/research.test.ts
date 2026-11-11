/**
 * General research API schema tests.
 *
 * USAGE: pnpm test -- src/lib/api/research.test.ts
 */

import { describe, expect, it } from 'vitest';
import { researchPackagesResponseSchema } from './research';

describe('research package schema', () => {
  it('parses generic manifest-backed packages and nested navigation', () => {
    const parsed = researchPackagesResponseSchema.parse({
      disclaimer: 'Research only.',
      packages: [
        {
          id: 'example-lab',
          title: 'Example Lab',
          subtitle: 'Example research.',
          route: '/sandbox/example-lab',
          nav_path: ['Sandbox', 'example-lab'],
          surface: 'document',
        },
      ],
      nav: [
        {
          id: 'corpus',
          title: 'Corpus',
          kind: 'folder',
          children: [
            {
              id: 'doc:sandbox/topic.md',
              title: 'topic',
              kind: 'doc',
              route: '/sandbox/doc/sandbox/topic.md',
              doc_path: 'sandbox/topic.md',
            },
          ],
        },
      ],
    });

    expect(parsed.packages[0]?.id).toBe('example-lab');
    expect(parsed.nav[0]?.children?.[0]?.doc_path).toBe('sandbox/topic.md');
  });
});
