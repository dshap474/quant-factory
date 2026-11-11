/**
 * Focused known-answer tests for design-system literal enforcement.
 *
 * USAGE:
 *   node --test scripts/check-design-system.test.mjs
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  classTokens,
  collectFileFailures,
  collectLayoutSpacingFailures,
  collectLiteralFailures,
  collectShellFailures,
  collectSpacingFailures,
  isVisualUtility,
  resolveRelativeImport,
  stripComments,
} from './check-design-system.mjs';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('design-system literal rules', () => {
  it('strips comments without stripping quoted content or line positions', () => {
    const source = `// #abc\nconst color = '#def'; /* rgb(0 0 0) */\n`;
    const stripped = stripComments(source);

    assert.equal(stripped.split('\n').length, source.split('\n').length);
    assert.doesNotMatch(stripped, /#abc|rgb\(/);
    assert.match(stripped, /'#def'/);
    assert.deepEqual(
      collectLiteralFailures('pages/Comment.css', '/* #abc; bg-red-500; border-radius: 2px; */'),
      [],
    );
  });

  it('rejects raw colors and named Tailwind palette classes outside exemptions', () => {
    const failures = collectLiteralFailures(
      'pages/Example.tsx',
      `const color = '#abcdef';\nconst className = 'hover:bg-red-500';`,
    );

    assert.equal(failures.length, 2);
    assert.match(failures[0], /Example\.tsx:1: replace raw color/);
    assert.match(failures[1], /Example\.tsx:2: replace named palette class/);
    assert.deepEqual(
      collectLiteralFailures('qf-ui/styles/tokens.css', ':root { --brand: #abcdef; }'),
      [],
    );
    assert.deepEqual(
      collectLiteralFailures('pages/Example.test.ts', `expect(color).toBe('#abcdef');`),
      [],
    );
  });

  it('rejects every raw CSS color function', () => {
    for (const color of [
      'rgb(1 2 3)',
      'rgba(1, 2, 3, 0.5)',
      'hsl(10 20% 30%)',
      'hsla(10, 20%, 30%, 0.5)',
      'hwb(10 20% 30%)',
      'lab(50% 0 0)',
      'lch(50% 0 0)',
      'oklab(50% 0 0)',
      'oklch(50% 0 0)',
      'color(display-p3 1 0 0)',
    ]) {
      assert.equal(
        collectLiteralFailures('pages/Example.css', `.sample { color: ${color}; }`).length,
        1,
      );
    }
  });

  it('rejects presentation named colors without scanning prose or identifiers', () => {
    const failures = collectLiteralFailures(
      'pages/Example.tsx',
      `.sample { color: RED; box-shadow: 0 0 1px rebeccapurple; border: 1px solid blue; }\nconst style = { boxShadow: '0 0 1px teal' };\nconst icon = <path fill="navy" />;`,
    );

    assert.equal(failures.length, 5);
    assert.match(failures[0], /named color "RED"/);
    assert.match(failures[1], /named color "rebeccapurple"/);
    assert.match(failures[2], /named color "blue"/);
    assert.match(failures[3], /named color "teal"/);
    assert.match(failures[4], /named color "navy"/);
    assert.deepEqual(
      collectLiteralFailures('pages/Example.tsx', `<path fill={'red'} stroke={"navy"} />`),
      [
        'pages/Example.tsx:1: replace named color "red" with a semantic token',
        'pages/Example.tsx:1: replace named color "navy" with a semantic token',
      ],
    );
    assert.deepEqual(
      collectLiteralFailures('pages/Example.tsx', '<path fill={`teal`} stroke={"currentColor"} />'),
      ['pages/Example.tsx:1: replace named color "teal" with a semantic token'],
    );
    assert.deepEqual(
      collectLiteralFailures(
        'pages/Example.css',
        '.x { --local-accent: red; color: var(--local-accent); }',
      ),
      ['pages/Example.css:1: replace named color "red" with a semantic token'],
    );
    assert.deepEqual(
      collectLiteralFailures(
        'pages/Example.tsx',
        `const prose = 'red indicates a failed run';\nconst token = '--red-status';\n.sample { color: var(--red-status); background: var(--blue-surface); outline-color: currentColor; }`,
      ),
      [],
    );
  });

  it('allows zero tokens and documented shapes while rejecting cosmetic literals', () => {
    const source = `
.square { border-radius: 0; }
.semantic { border-radius: var(--radius-control); }
.card { border-radius: 2px; }
`;
    const failures = collectLiteralFailures('pages/Example.css', source);

    assert.equal(failures.length, 1);
    assert.match(failures[0], /Example\.css:4: replace nonzero border radius "2px"/);
    assert.match(
      collectLiteralFailures(
        'pages/Unreadable.css',
        '.label { color: var(--color-chart-axis-muted); }',
      )[0],
      /use --color-chart-axis-label for readable chart text/,
    );
    assert.deepEqual(
      collectLiteralFailures(
        'pages/Marker.css',
        '.marker { --marker-color: var(--color-chart-axis-muted); border-color: var(--marker-color); }',
      ),
      [],
    );
  });
});

describe('page-level rules', () => {
  it('rejects visual utilities in page code while allowing layout and text alignment', () => {
    const failures = collectFileFailures(
      'pages/Example.tsx',
      '<div className="flex gap-2 bg-card rounded-lg text-left">x</div>',
    );
    assert.equal(failures.length, 2);
    assert.ok(failures.some((failure) => failure.includes('"bg-card"')));
    assert.ok(failures.some((failure) => failure.includes('"rounded-lg"')));
  });

  it('rejects extended native tags', () => {
    const failures = collectFileFailures('pages/Example.tsx', '<a href="/x">x</a>');
    assert.equal(failures.length, 1);
    assert.match(failures[0], /native <a>/);
  });

  it('rejects loading text', () => {
    const failures = collectFileFailures('pages/Example.tsx', '<p>Loading strategy catalog…</p>');
    assert.equal(failures.length, 1);
    assert.match(failures[0], /LoadingSkeleton/);
  });

  it('rejects page-level CSS', () => {
    const failures = collectFileFailures('pages/Example.css', '.x { display: flex; }');
    assert.equal(failures.length, 1);
    assert.match(failures[0], /page-level CSS/);
  });

  it('gates extension files like page files', () => {
    const failures = collectFileFailures(
      'extensions/foo/Page.tsx',
      '<button style={{ color: "#fff" }}>x</button>',
    );
    assert.equal(failures.length, 2);
    assert.match(failures[1], /native <button>/);
    const chartFailures = collectFileFailures(
      'extensions/foo/Page.tsx',
      "import * as echarts from 'echarts';",
    );
    assert.equal(chartFailures.length, 1);
    assert.match(chartFailures[0], /ECharts/);
  });

  it('exempts shared UI from presentation and page-level rules', () => {
    assert.deepEqual(
      collectFileFailures(
        'ui/primitives/Button.tsx',
        '<button className="bg-surface-raised rounded-control">x</button>',
      ),
      [],
    );
  });

  it('tokenizes className expressions and classifies utilities', () => {
    assert.deepEqual(
      classTokens(['flex hover:bg-card $', '{active ? "text-right" : "underline"}'].join('')),
      ['flex', 'bg-card', 'active', 'text-right', 'underline'],
    );
    assert.equal(isVisualUtility('h-screen'), true);
    assert.equal(isVisualUtility('gap-2'), false);
    assert.equal(isVisualUtility('overflow-auto'), true);
    assert.equal(isVisualUtility('fill'), false);
    assert.equal(isVisualUtility('fill-current'), true);
    assert.equal(isVisualUtility('border'), true);
    assert.equal(isVisualUtility('to'), false);
  });
});

describe('shared-UI import rules', () => {
  it('accepts the @/ui barrel and rejects subpath imports from pages', () => {
    assert.deepEqual(
      collectFileFailures('pages/HomePage.tsx', "import { Button } from '@/ui';\n"),
      [],
    );
    const failures = collectFileFailures(
      'pages/HomePage.tsx',
      "import { Button } from '@/ui/primitives/Button';\n",
    );
    assert.equal(failures.length, 1);
    assert.match(failures[0], /through the @\/ui barrel/);
  });

  it('routes the qf-ui root through the @/ui barrel but allows chart subpaths', () => {
    const failures = collectFileFailures(
      'pages/HomePage.tsx',
      "import { Button } from '@quant-factory/qf-ui';\n",
    );
    assert.equal(failures.length, 1);
    assert.match(failures[0], /through the @\/ui barrel/);
    assert.deepEqual(
      collectFileFailures(
        'pages/HomePage.tsx',
        "import { LineChart } from '@quant-factory/qf-ui/charts/renderers';\n",
      ),
      [],
    );
    assert.deepEqual(
      collectFileFailures(
        'ui/shell/AppShell.tsx',
        "import { Button } from '@quant-factory/qf-ui';\n",
      ),
      [],
    );
  });

  it('treats qf-ui source as shared UI', () => {
    assert.deepEqual(
      collectFileFailures(
        'qf-ui/primitives/Button.tsx',
        '<button className="bg-surface-raised rounded-control">x</button>',
      ),
      [],
    );
    const failures = collectFileFailures(
      'extensions/foo/FooPage.tsx',
      "import { Button } from '../../qf-ui/src/primitives/Button';\n",
    );
    assert.equal(failures.length, 1);
    assert.match(failures[0], /through the @\/ui barrel/);
  });

  it('rejects relative and dynamic imports into shared UI', () => {
    assert.equal(resolveRelativeImport('pages/agents/AgentDetailPage.tsx', '../../ui/x'), 'ui/x');
    for (const [path, source] of [
      ['pages/HomePage.tsx', "import { Button } from '../ui/primitives/Button';\n"],
      [
        'pages/agents/AgentDetailPage.tsx',
        "import { Surface } from '../../ui/primitives/Surface';\n",
      ],
      ['pages/HomePage.tsx', "const load = () => import('@/ui/frame/PageShell');\n"],
      [
        'extensions/foo/FooPage.tsx',
        "import { Button } from '../../web/src/ui/primitives/Button';\n",
      ],
    ]) {
      const failures = collectFileFailures(path, source);
      assert.equal(failures.length, 1, `${path}: ${failures.join(' | ')}`);
      assert.match(failures[0], /through the @\/ui barrel/);
    }
    assert.deepEqual(
      collectFileFailures('extensions/foo/FooPage.tsx', "import { Button } from '@/ui';\n"),
      [],
    );
  });

  it('keeps shared UI modules off the barrel and exempts tests', () => {
    assert.deepEqual(
      collectFileFailures(
        'ui/layout/Toolbar.tsx',
        "import { Surface } from '../primitives/Surface';\n",
      ),
      [],
    );
    const failures = collectFileFailures(
      'ui/layout/Toolbar.tsx',
      "import { Surface } from '@/ui';\n",
    );
    assert.equal(failures.length, 1);
    assert.match(failures[0], /siblings relatively/);
    assert.deepEqual(
      collectFileFailures(
        'pages/agents/AgentsLiveDashboard.test.tsx',
        "import { PipelineArchitectureMap } from '@/ui/frame/PipelineArchitectureMap';\nvi.mock('@/ui/frame/PipelineArchitectureMap', () => ({}));\n",
      ),
      [],
    );
  });
});

describe('retired tokens and utilities', () => {
  it('rejects retired utilities in shared TSX and allows the roles', () => {
    const failures = collectFileFailures(
      'qf-ui/primitives/X.tsx',
      '<p className="text-xs hover:rounded font-bold">x</p>',
    );
    assert.equal(failures.length, 3);
    assert.ok(
      failures.some((failure) => failure.includes('"text-xs" is not a design-system utility')),
    );
    assert.ok(
      failures.some((failure) => failure.includes('"rounded" is not a design-system utility')),
    );
    assert.ok(failures.some((failure) => failure.includes('"font-bold"')));
    assert.deepEqual(
      collectFileFailures(
        'qf-ui/primitives/X.tsx',
        `const SIZES = { sm: 'text-caption', md: 'text-body' };\n<p className="rounded-surface text-muted-foreground font-medium">x</p>`,
      ),
      [],
    );
    assert.equal(
      collectFileFailures('qf-ui/primitives/X.tsx', "const SIZES = { sm: 'text-sm leading-5' };")
        .length,
      2,
    );
  });

  it('rejects a reference to a retired token in any scanned file', () => {
    const failures = collectFileFailures('lib/X.ts', "const font = 'var(--font-data)';");
    assert.deepEqual(failures, [
      'lib/X.ts:1: "--font-data" was retired; use --font-sans (or --font-mono for identifiers)',
    ]);
    assert.match(
      collectFileFailures(
        'ui/shell/X.css',
        '@layer qf-components { .x { padding: var(--space-md); } }',
      )[0],
      /"--space-md" was retired; use --space-5/,
    );
    assert.match(
      collectFileFailures('extensions/foo/x.ts', "const c = 'var(--chart-1)';")[0],
      /"--chart-1" was retired/,
    );
    assert.deepEqual(
      collectFileFailures('lib/X.ts', "const c = 'var(--color-muted-foreground)';"),
      [],
    );
  });

  it('names the Surface component for a hand-built card in page code', () => {
    const failures = collectFileFailures(
      'pages/X.tsx',
      'const card = "bg-surface-raised border rounded-surface";',
    );
    assert.deepEqual(failures, ['pages/X.tsx: use the shared Surface component (rounded-surface)']);
  });
});

describe('Style rules', () => {
  const css = (body) => collectLiteralFailures('qf-ui/primitives/X.css', body);

  it('accepts only radius roles', () => {
    assert.deepEqual(
      css('.a { border-radius: var(--radius-surface) var(--radius-surface) 0 0; }'),
      [],
    );
    assert.match(css('.a { border-radius: var(--radius-xs); }')[0], /radius role token/);
    assert.match(
      collectLiteralFailures('qf-ui/state/Status.css', '.ui-status-dot { border-radius: 50%; }')[0],
      /replace nonzero border radius "50%"/,
    );
  });

  it('keeps elevation on the shadow tokens', () => {
    assert.deepEqual(css('.a { box-shadow: var(--shadow-overlay); }'), []);
    assert.deepEqual(css('.a { box-shadow: inset 0 -2px 0 var(--color-brand); }'), []);
    assert.match(css('.a { box-shadow: inset 0 0 4px var(--color-border); }')[0], /elevation uses/);
    assert.ok(
      css('.a { box-shadow: 0 2px 6px rgb(0 0 0 / .3); }').some((f) =>
        f.includes('elevation uses'),
      ),
    );
  });

  it('closes the type voice', () => {
    assert.deepEqual(css('.a { font-size: var(--text-caption); }'), []);
    for (const body of [
      '.a { font-size: 13px; }',
      '.a { font-size: var(--text-xs); }',
      '.a { line-height: 1.4; }',
      '.a { letter-spacing: 0.08em; }',
      '.a { font-weight: 700; }',
    ]) {
      assert.equal(css(body).length, 1, body);
    }
    assert.match(css('.ui-label { font-family: var(--font-mono); }')[0], /mono is for ids/);
    assert.deepEqual(css('.ui-run-hash, code { font-family: var(--font-mono); }'), []);
    assert.match(css('.x code, .y { font-family: var(--font-mono); }')[0], /mono is for ids/);
    assert.deepEqual(
      css(
        '.overline { font-size: var(--text-overline); letter-spacing: var(--text-overline--letter-spacing); text-transform: uppercase; }',
      ),
      [],
    );
    assert.match(css('.head { text-transform: uppercase; }')[0], /sentence case only/);
    assert.match(
      collectFileFailures('qf-ui/primitives/X.tsx', 'const label = "uppercase text-caption";')[0],
      /sentence case only/,
    );
    assert.deepEqual(
      collectFileFailures('qf-ui/primitives/X.tsx', 'const label = "uppercase text-overline";'),
      [],
    );
  });

  it('puts shared spacing on the 4px scale', () => {
    const spacing = (body) => collectSpacingFailures('qf-ui/primitives/X.css', body);
    assert.match(spacing('.a { padding: 0.4rem 0; }')[0], /off the 4px spacing scale/);
    assert.deepEqual(spacing('.a { padding: var(--space-2) 0; }'), []);
    assert.deepEqual(spacing('.a { margin: 1px 0; }'), []);
    assert.equal(spacing('.a { gap: 0.3em; }').length, 1);
    assert.equal(spacing('.a { top: calc(50% - 6px); }').length, 1);
    assert.deepEqual(spacing('.a { top: calc(50% - 8px); }'), []);
    assert.match(
      collectFileFailures('ui/X.tsx', '<div className="flex gap-5" />')[0],
      /"gap-5" is off the 4px spacing scale/,
    );
    assert.match(
      collectFileFailures('pages/X.tsx', '<div className="flex gap-5" />')[0],
      /"gap-5" is layout spacing/,
    );
    assert.deepEqual(collectFileFailures('pages/X.tsx', '<div className="flex gap-2" />'), []);
  });

  it('guards the shell against its retired recipes', () => {
    assert.match(
      collectShellFailures('ui/shell/X.css', '.a { z-index: 30; }')[0],
      /shell z-index must use the --z-\* scale/,
    );
    assert.deepEqual(
      collectShellFailures('ui/frame/X.css', '.a { z-index: var(--z-sticky); }'),
      [],
    );
    assert.match(
      collectShellFailures('ui/X.tsx', 'const c = "bg-sidebar-accent";')[0],
      /not sidebar aliases/,
    );
    assert.match(
      collectShellFailures('qf-ui/X.css', '.a { color: var(--color-sidebar-foreground); }')[0],
      /not sidebar aliases/,
    );
    assert.deepEqual(collectShellFailures('ui/X.tsx', 'const c = "bg-surface-sunken";'), []);
    assert.match(
      collectShellFailures('ui/shell/X.css', '.a { color: var(--color-primary); }')[0],
      /--color-brand only for the active mark/,
    );
    assert.match(
      collectShellFailures('ui/frame/X.css', '.a { color: var(--color-champion); }')[0],
      /--color-brand only for the active mark/,
    );
    assert.deepEqual(
      collectShellFailures('ui/shell/X.css', '.a { color: var(--color-brand); }'),
      [],
    );
    assert.match(
      collectShellFailures('ui/shell/X.css', '.a { font-family: var(--font-data); }')[0],
      /the shell navigator is sans/,
    );
    assert.deepEqual(
      collectShellFailures('ui/shell/X.css', '.a { font-family: var(--font-sans); }'),
      [],
    );
    assert.match(
      collectShellFailures('qf-ui/shell/X.css', '.a { z-index: 30; }')[0],
      /shell z-index must use the --z-\* scale/,
    );
    assert.match(
      collectShellFailures('qf-ui/shell/X.css', '.a { font-family: var(--font-data); }')[0],
      /the shell navigator is sans/,
    );
    assert.match(
      collectShellFailures('qf-ui/frame/X.css', '.a { z-index: 30; }')[0],
      /shell z-index must use the --z-\* scale/,
    );
    assert.match(
      collectShellFailures('qf-ui/frame/X.css', '.a { color: var(--color-primary); }')[0],
      /--color-brand only for the active mark/,
    );
  });
});

describe('layout spacing belongs to the primitives (spacing SPEC §4)', () => {
  const layout = (source, path = 'pages/X.tsx') => collectLayoutSpacingFailures(path, source);

  it('rejects 12px and up of padding, margin, gap and space on every axis and side', () => {
    for (const token of [
      'p-3',
      'px-3',
      'pb-12',
      'mt-4',
      'mb-3',
      'my-4',
      '-mx-6',
      'gap-4',
      'gap-x-3',
      'gap-y-8',
      'space-y-3',
      'space-x-4',
      'md:pt-6',
      '!mb-3',
      'p-3.5',
    ]) {
      const failures = layout(`<div className="flex ${token}" />`);
      assert.equal(failures.length, 1, token);
      assert.match(failures[0], /is layout spacing \(12px or more\)/, token);
    }
  });

  it('keeps 0 to 8px and positioning offsets legal for component internals', () => {
    assert.deepEqual(
      layout(
        '<div className="p-2 px-1 py-1.5 gap-1 gap-x-2 mt-2.5 m-px mx-auto gap-0 space-y-2 top-4 inset-x-6 -mt-2" />',
      ),
      [],
    );
  });

  it('rejects arbitrary inset and gap token spacing and arbitrary lengths of 12px and up', () => {
    for (const token of [
      'p-[var(--inset-page)]',
      'gap-[var(--gap-block)]',
      'gap-x-[var(--gap-block)]',
      'px-[calc(var(--inset-page)-var(--space-3))]',
      'p-(--gap-stack)',
      'mt-[20px]',
      'gap-[1rem]',
      'pb-[var(--space-4)]',
    ]) {
      assert.equal(layout(`<div className="${token}" />`).length, 1, token);
    }
    assert.deepEqual(layout('<div className="p-[var(--space-2)] mt-[4px]" />'), []);
  });

  it('names the primitive prop to use instead', () => {
    assert.match(layout('<div className="gap-4" />')[0], /use Stack, Cluster or Grid gap="block"/);
    assert.match(layout('<div className="gap-3" />')[0], /gap="heading"/);
    assert.match(
      layout('<div className="mt-8" />')[0],
      /let the parent primitive own the gap \(Stack gap="section", PageShell rhythm\)/,
    );
    assert.match(layout('<div className="p-4" />')[0], /PageShell, Surface padding/);
  });

  it('rejects any spacing utility on a layout primitive className', () => {
    const failures = layout(
      `<Stack gap="block" className={cn('min-w-0', open && 'mt-2')}>x</Stack>`,
    );
    assert.deepEqual(failures, [
      'pages/X.tsx:1: <Stack> owns its spacing; remove "mt-2" from its className and use its props',
    ]);
    for (const tag of ['PageShell', 'Section', 'Cluster', 'Grid', 'ChartGrid']) {
      const tagFailures = layout(`<${tag}\n  title="T"\n  className="pb-1">x</${tag}>`);
      assert.equal(tagFailures.length, 1, tag);
      assert.match(tagFailures[0], new RegExp(`<${tag}> owns its spacing; remove "pb-1"`));
    }
    assert.equal(layout('<PageShell maxWidth="full" className="pb-12">x</PageShell>').length, 2);
    assert.deepEqual(
      layout('<Cluster justify="between" className="min-w-0 flex-1 lg:flex-row">x</Cluster>'),
      [],
    );
    assert.deepEqual(layout('<StatGrid className="mt-2">x</StatGrid>'), []);
  });

  it('applies to page, lib, layout and extension code but not to shared UI or tests', () => {
    const source = '<div className="p-4 gap-[var(--gap-block)]" />';
    for (const path of ['pages/X.tsx', 'lib/X.tsx', 'layouts/X.tsx', 'extensions/foo/X.tsx']) {
      assert.equal(collectFileFailures(path, source).length, 2, path);
    }
    assert.equal(collectFileFailures('lib/classes.ts', "const cls = 'mb-4';").length, 1);
    for (const path of ['ui/frame/X.tsx', 'qf-ui/layout/X.tsx', 'pages/X.test.tsx']) {
      assert.deepEqual(collectFileFailures(path, source), [], path);
    }
  });
});
