/**
 * Structural tests for the shared Table primitives' numeric and selected affordances.
 *
 * USAGE:
 *   pnpm exec vitest run src/tables/primitives/Table.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './Table';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Table primitives', () => {
  it('right-aligns numeric headers without switching them to the data font', () => {
    const markup = renderToStaticMarkup(
      <table>
        <thead>
          <tr>
            <TableHead numeric>close</TableHead>
            <TableHead>asset</TableHead>
          </tr>
        </thead>
      </table>,
    );
    expect(markup).toContain('text-right');
    expect(markup).toContain('text-left');
    expect(markup).not.toContain('data-numeric');
  });

  it('marks numeric cells for tabular data styling', () => {
    const markup = renderToStaticMarkup(
      <table>
        <tbody>
          <tr>
            <TableCell numeric>0.12</TableCell>
            <TableCell>BTC</TableCell>
          </tr>
        </tbody>
      </table>,
    );
    expect(markup).toContain('<td class="ui-table-cell text-right" data-numeric="">0.12</td>');
    expect(markup).toContain('<td class="ui-table-cell">BTC</td>');
  });

  it('scales down type and cell rows at dense density', () => {
    const markup = renderToStaticMarkup(
      <Table density="dense">
        <TableBody>
          <TableRow>
            <TableCell>BTC</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    expect(markup).toContain('is-dense');
    expect(markup).toContain('text-caption');
    expect(markup).not.toContain('py-2.5');
    expect(markup).not.toContain('text-body');
  });

  it('leaves selected-row surfaces to the shared row-state recipe', () => {
    const markup = renderToStaticMarkup(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>asset</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow aria-selected>
            <TableCell>BTC</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    expect(markup).not.toContain('aria-selected:bg-secondary');
    expect(markup).toContain('aria-selected="true"');
  });

  it('wraps a prose cell only when asked, without forwarding the prop', () => {
    const markup = renderToStaticMarkup(
      <table>
        <tbody>
          <tr>
            <TableCell wrap>long note</TableCell>
          </tr>
        </tbody>
      </table>,
    );
    expect(markup).toContain('<td class="ui-table-cell is-wrap">long note</td>');
    expect(markup).not.toContain('wrap=');
  });

  it('puts a detail on the same line with its full text as the title', () => {
    const markup = renderToStaticMarkup(
      <table>
        <tbody>
          <tr>
            <TableCell detail="example">Strategy optimizer</TableCell>
            <TableCell detail={null}>plain</TableCell>
          </tr>
        </tbody>
      </table>,
    );
    expect(markup).toContain(
      '<td class="ui-table-cell"><span class="ui-table-cell-line"><span class="ui-table-cell-primary">Strategy optimizer</span><span class="ui-table-cell-detail" title="example">example</span></span></td>',
    );
    expect(markup).toContain('<td class="ui-table-cell">plain</td>');
    expect(markup).not.toContain('detail=');
  });

  it('marks the body for the shared row selection bar', () => {
    const markup = renderToStaticMarkup(
      <table>
        <TableBody>
          <TableRow>
            <TableCell>BTC</TableCell>
          </TableRow>
        </TableBody>
      </table>,
    );
    expect(markup).toContain('ui-table-body');
  });

  it('pins the header row when sticky', () => {
    const markup = renderToStaticMarkup(
      <table>
        <TableHeader sticky>
          <TableRow>
            <TableHead>asset</TableHead>
          </TableRow>
        </TableHeader>
      </table>,
    );
    expect(markup).toContain('ui-table-sticky-head');
  });
});
