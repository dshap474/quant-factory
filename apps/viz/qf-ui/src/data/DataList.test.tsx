/**
 * Structural tests for DataList: semantic markup, items API, composable parts, tones.
 *
 * USAGE:
 *   pnpm exec vitest run src/data/DataList.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { DataList } from './DataList';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('DataList', () => {
  it('renders items as dl > div > dt + dd pairs, vertical by default', () => {
    const markup = renderToStaticMarkup(
      <DataList
        items={[
          { label: 'Sharpe', value: '1.42' },
          { label: 'Trades', value: '318' },
        ]}
      />,
    );
    expect(markup.startsWith('<dl class="ui-data-list" data-orientation="vertical"')).toBe(true);
    expect(markup.match(/<div class="ui-data-list-item">/g)).toHaveLength(2);
    expect(markup).toContain('<dt class="ui-data-list-label">Sharpe</dt>');
    expect(markup).toContain('<dd class="ui-data-list-value">1.42</dd>');
    expect(markup).not.toContain('data-divided');
  });

  it('marks numeric values, applies tone text, and sets orientation and dividers', () => {
    const markup = renderToStaticMarkup(
      <DataList
        orientation="horizontal"
        divided
        items={[{ label: 'Return', value: '+4.1%', numeric: true, tone: 'success' }]}
      />,
    );
    expect(markup).toContain('data-orientation="horizontal"');
    expect(markup).toContain('data-divided=""');
    expect(markup).toContain('data-numeric=""');
    expect(markup).toContain('text-tone-success');
  });

  it('composes with DataList.Item / Label / Value and merges className', () => {
    const markup = renderToStaticMarkup(
      <DataList className="extra">
        <DataList.Item>
          <DataList.Label>Vol</DataList.Label>
          <DataList.Value numeric tone="critical">
            -2.0%
          </DataList.Value>
        </DataList.Item>
      </DataList>,
    );
    expect(markup).toContain('class="ui-data-list extra"');
    expect(markup).toContain('>Vol</dt>');
    expect(markup).toContain('text-tone-critical');
    expect(markup).toContain('data-numeric=""');
  });

  it('renders items before children', () => {
    const markup = renderToStaticMarkup(
      <DataList items={[{ label: 'A', value: '1' }]}>
        <DataList.Item>
          <DataList.Label>B</DataList.Label>
          <DataList.Value>2</DataList.Value>
        </DataList.Item>
      </DataList>,
    );
    expect(markup.indexOf('>A<')).toBeLessThan(markup.indexOf('>B<'));
  });
});
