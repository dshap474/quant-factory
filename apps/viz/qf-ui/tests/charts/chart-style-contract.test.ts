/**
 * Static portability contracts for qf-charts CSS.
 *
 * USAGE:
 *   pnpm test -- tests/charts/chart-style-contract.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function sourceFiles(directory: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) found.push(...sourceFiles(path));
    else if (/\.(css|tsx)$/.test(entry.name)) found.push(path);
  }
  return found.sort();
}

/** Bridge declarations (`--qf-chart-x: var(--color-x, …)`) read host tokens with a fallback. */
function isBridgeDeclaration(line: string): boolean {
  return /^\s*--qf-chart-[a-z0-9-]+:\s*var\(--(?:color|font|radius|shadow|text)-[a-z0-9-]+,/.test(
    line,
  );
}

/** Every custom property the package itself declares, in CSS or in an inline style. */
function packageDeclaredTokens(paths: readonly string[]): Set<string> {
  const declared = new Set<string>();
  for (const path of paths) {
    const text = readFileSync(path, 'utf8');
    for (const match of text.matchAll(/(?:^|[\s{;'"])(--[a-z0-9-]+)\s*'?\s*:/g)) {
      if (match[1]) declared.add(match[1]);
    }
  }
  return declared;
}

/** Every `selector { body }` rule (innermost) in a stylesheet, with its 1-based line. */
function cssRules(text: string): { selector: string; body: string; line: number }[] {
  const rules: { selector: string; body: string; line: number }[] = [];
  for (const match of text.matchAll(/([^{};]+)\{([^{}]*)\}/g)) {
    const line = text.slice(0, match.index ?? 0).split('\n').length;
    rules.push({ selector: (match[1] ?? '').trim(), body: match[2] ?? '', line });
  }
  return rules;
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('chart CSS portability', () => {
  it('owns the plot stack and no-data text in the theme sheet with the portable label token', () => {
    const styles = readFileSync(join(process.cwd(), 'src/charts/theme/qf-charts.css'), 'utf8');
    const noDataRule = styles.match(/\.chart-no-data\s*\{[^}]+\}/s)?.[0] ?? '';

    expect(styles).toContain('.chart-stack {');
    expect(styles).toContain('.chart-stack-main {');
    expect(noDataRule).toContain('color: var(--qf-chart-label);');
    expect(noDataRule).not.toContain('--color-chart-axis-muted');
  });

  it('never consumes a legacy host --chart-* triplet or wraps a bridge in hsl()', () => {
    for (const path of sourceFiles(join(process.cwd(), 'src/charts'))) {
      const styles = readFileSync(path, 'utf8');
      expect(styles, path).not.toContain('var(--chart-');
      expect(styles, path).not.toContain('hsl(var(--qf-chart');
    }
  });

  it('leaves no legacy --chart-* triplet declared in the host tokens (D-5.1)', () => {
    const tokensCss = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');
    expect(tokensCss).not.toMatch(/^\s*--chart-[a-z0-9-]+:/m);
  });

  it('never reads a host variable without a fallback outside the theme bridges', () => {
    const paths = sourceFiles(join(process.cwd(), 'src/charts'));
    const declared = packageDeclaredTokens(paths);
    const offenders: string[] = [];
    for (const path of paths) {
      const lines = readFileSync(path, 'utf8').split('\n');
      lines.forEach((line, index) => {
        if (isBridgeDeclaration(line)) return;
        for (const match of line.matchAll(/var\((--[a-z0-9-]+)\s*([,)])/g)) {
          const name = match[1] ?? '';
          const hasFallback = match[2] === ',';
          if (hasFallback) continue;
          if (name.startsWith('--qf-chart-')) continue;
          if (declared.has(name)) continue;
          offenders.push(`${path}:${index + 1}: ${line.trim()}`);
        }
      });
    }
    expect(offenders).toEqual([]);
  });

  it('bridges the host tokens chart chrome depends on', () => {
    const styles = readFileSync(join(process.cwd(), 'src/charts/theme/qf-charts.css'), 'utf8');
    for (const bridge of [
      '--qf-chart-series-primary: var(--color-chart-1,',
      '--qf-chart-font-data: var(--font-mono,',
      '--qf-chart-font-sans: var(--font-sans,',
      '--qf-chart-focus-ring: var(--color-focus-ring,',
      '--qf-chart-radius-badge: var(--radius-badge,',
      '--qf-chart-radius-control: var(--radius-control,',
      '--qf-chart-text-caption: var(--text-caption,',
      '--qf-chart-radius-swatch: calc(var(--radius-badge,',
    ]) {
      expect(styles).toContain(bridge);
    }
  });

  it('draws tooltip series swatches as 10px rounded squares, not circles', () => {
    const styles = readFileSync(join(process.cwd(), 'src/charts/theme/qf-charts.css'), 'utf8');
    const swatch = styles.match(/\.tooltip-swatch \{([^}]*)\}/)?.[1] ?? '';
    expect(swatch).toContain('width: var(--qf-chart-tooltip-swatch-size);');
    expect(swatch).toContain('border-radius: var(--qf-chart-radius-swatch);');
    expect(styles).toContain('--qf-chart-tooltip-swatch-size: 10px;');
  });

  it('declares no retired chart-local tokens and reads no retired host tokens (D-5.2)', () => {
    const retired =
      /--qf-chart-(?:border-tint|focus|chrome-surface|radius-xs|control-radius|text-(?:sm|xs|2xs)|row-height)\b(?!-)/;
    const retiredHost =
      /var\(--(?:control-radius|panel-radius|font-data|radius-(?:xs|sm|md|lg|xl))[,)]/;
    const offenders: string[] = [];
    for (const path of sourceFiles(join(process.cwd(), 'src/charts'))) {
      readFileSync(path, 'utf8')
        .split('\n')
        .forEach((line, index) => {
          if (retired.test(line) || retiredHost.test(line)) offenders.push(`${path}:${index + 1}`);
        });
    }
    expect(offenders).toEqual([]);
  });

  it('styles chart keys and notes with package tokens only', () => {
    for (const file of [
      'src/charts/components/ChartKey.css',
      'src/charts/components/ChartNote.css',
    ]) {
      const styles = readFileSync(join(process.cwd(), file), 'utf8');
      expect(styles).toContain('var(--qf-chart-label)');
      expect(styles).not.toContain('--color-text-muted');
      expect(styles).not.toContain('--color-muted-foreground');
    }
  });

  it('keeps the tooltip frosted glass, on the overlay shadow, and chart-contained', () => {
    const styles = readFileSync(join(process.cwd(), 'src/charts/theme/qf-charts.css'), 'utf8');
    const tooltipSurface =
      styles.match(/\.qf-echarts-tooltip-host,\s*\.tooltip\s*\{[^}]+\}/s)?.[0] ?? '';

    expect(tooltipSurface).toContain('max-width: calc(100% - 24px);');
    expect(styles).toContain('background-color: var(--qf-chart-tooltip-glass);');
    expect(tooltipSurface).toContain('backdrop-filter: blur(16px) saturate(140%);');
    expect(tooltipSurface).toContain('box-shadow: var(--qf-chart-popover-shadow);');
  });

  it('keeps only ordinary solid legend markers', () => {
    const styles = readFileSync(join(process.cwd(), 'src/charts/theme/qf-charts.css'), 'utf8');

    expect(styles).toContain('.chart-legend-marker.solid');
    expect(styles).not.toContain('.chart-legend-marker.dashed');
    expect(styles).not.toContain('.chart-legend-marker.dotted');
  });
});

describe('chart style bans (D-5.4)', () => {
  const root = join(process.cwd(), 'src/charts');
  const paths = sourceFiles(root);
  const cssPaths = paths.filter((path) => path.endsWith('.css'));

  function offenders(check: (path: string, text: string) => string[]): string[] {
    return paths.flatMap((path) => check(path, readFileSync(path, 'utf8')));
  }

  it('never animates hover, press or pressed-state rules and never scales on press', () => {
    const found: string[] = [];
    for (const path of cssPaths) {
      for (const rule of cssRules(readFileSync(path, 'utf8'))) {
        const stateful = /:hover|:active|\[aria-pressed/.test(rule.selector);
        if (stateful && /(?:^|[\s;])transition(?:-[a-z]+)?\s*:/.test(rule.body)) {
          found.push(`${path}:${rule.line} transition`);
        }
        if (/:active/.test(rule.selector) && /transform\s*:\s*scale\(/.test(rule.body)) {
          found.push(`${path}:${rule.line} scale`);
        }
      }
    }
    expect(found).toEqual([]);
  });

  it('keeps smooth series interpolation inside interpolation.ts', () => {
    expect(
      offenders((path, text) =>
        /smooth:\s*true/.test(text) && !path.endsWith('interpolation.ts') ? [path] : [],
      ),
    ).toEqual([]);
    const tsFiles = (dir: string): string[] =>
      readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
        const path = join(dir, entry.name);
        if (entry.isDirectory()) return tsFiles(path);
        return /\.tsx?$/.test(entry.name) && !entry.name.endsWith('interpolation.ts') ? [path] : [];
      });
    expect(
      tsFiles(root).filter((path) => /smooth:\s*true/.test(readFileSync(path, 'utf8'))),
    ).toEqual([]);
  });

  it('sets no chart text in the data face outside id contexts and none in uppercase', () => {
    // Allow-by-class list of id contexts: <code> elements that show ids and hashes.
    const idContext = /(?:^|[\s>])code$/;
    const found: string[] = [];
    for (const path of cssPaths) {
      const text = readFileSync(path, 'utf8');
      for (const rule of cssRules(text)) {
        if (!/font-family:\s*var\(--qf-chart-font-data\)/.test(rule.body)) continue;
        const items = rule.selector.split(',').map((item) => item.trim());
        if (!items.every((item) => idContext.test(item))) found.push(`${path}:${rule.line}`);
      }
      if (/text-transform:\s*uppercase/.test(text)) found.push(`${path} uppercase`);
    }
    expect(found).toEqual([]);
  });

  it('stacks with named --qf-chart-z-* tokens, except the fatal error overlay', () => {
    const found: string[] = [];
    for (const path of cssPaths) {
      for (const rule of cssRules(readFileSync(path, 'utf8'))) {
        if (rule.selector === '.qf-chart-error') continue;
        if (/z-index\s*:\s*-?\d/.test(rule.body)) found.push(`${path}:${rule.line}`);
      }
    }
    expect(found).toEqual([]);
  });

  it('draws no px border radius outside the Histogram and Heatmap marks', () => {
    expect(
      offenders((path, text) =>
        /(?:border-radius|borderRadius)\s*:\s*['"]?[^;'"\n]*\d+px/.test(text) &&
        !/(?:Histogram|Heatmap)\.tsx$/.test(path)
          ? [path]
          : [],
      ),
    ).toEqual([]);
  });
});
