/**
 * Reject visual recipes and literals that bypass the shared UI token system.
 *
 * USAGE:
 *   pnpm run check:ui
 *   node --test scripts/check-design-system.test.mjs
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { existsSync } from 'node:fs';
import { readdir, readFile } from 'node:fs/promises';
import { join, posix, relative } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// --------------------------------------------------------------------------- #
// Rules
// --------------------------------------------------------------------------- #

const WEB_SOURCE_ROOT = new URL('../src/', import.meta.url);
const EXTENSIONS_ROOT = new URL('../../extensions/', import.meta.url);
// qf-ui/examples/ is deliberately not scanned: it plays a foreign host repository whose
// app frame is written with Tailwind utilities, and check-qf-ui-boundaries.mjs holds it
// to the package exports instead.
const QF_UI_SOURCE_ROOT = new URL('../../qf-ui/src/', import.meta.url);
const EXTENSIONS_PREFIX = 'extensions/';
const QF_UI_PREFIX = 'qf-ui/';
// qf-ui's chart runtime is governed by its own rules and tests (ECharts, canvas, theme
// literals); the design-system recipe rules apply to the rest of the kit.
const QF_UI_CHARTS_PREFIX = 'qf-ui/charts/';
const SCAN_ROOTS = [
  { root: WEB_SOURCE_ROOT, prefix: '' },
  { root: EXTENSIONS_ROOT, prefix: EXTENSIONS_PREFIX },
  { root: QF_UI_SOURCE_ROOT, prefix: QF_UI_PREFIX },
];
const SHARED_UI_PATHS = ['ui/', QF_UI_PREFIX];
const CHART_COMPONENT_PATH = 'lib/components/charts/';
const FULL_CHART_COMPONENT_PATTERN =
  /<(?:EquityCurve|MultiPaneTimeSeriesChart|MultiSeriesTimeChart|QfChart|Heatmap|OptimizerGrid|SignalChart|TimeSeriesChart|TransitionMatrix)\b/;
const FIXED_CHART_HEIGHT_CLASS_PATTERN = /\bh-\[[^\]]+\]/;
const CHART_FRAME_OVERRIDE_PATTERN =
  /<(?:MultiPaneTimeSeriesChart|TimeSeriesChart)\b[^>]*(?:aspectRatio|height)=/s;
const FIXED_RENDERER_HEIGHT_PATTERN = /<(?:QfChart|Heatmap)\b[^>]*height=\{?\d/s;
const RAW_COLOR_PATTERN =
  /#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{4}|[0-9a-f]{3})\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\s*\(/gi;
const COLOR_DECLARATION_PATTERN =
  /(?:^|[;{])\s*(?:color|background(?:-color)?|border(?:-(?:top|right|bottom|left))?(?:-color)?|outline(?:-color)?|text-decoration(?:-color)?|caret-color|accent-color|column-rule(?:-color)?|fill|stroke|box-shadow|text-shadow)\s*:\s*([^;}]+)/gim;
const CUSTOM_PROPERTY_DECLARATION_PATTERN = /(?:^|[;{])\s*--[a-z0-9_-]+\s*:\s*([^;}]+)/gim;
const COLOR_PROPERTY_LITERAL_PATTERN =
  /\b(?:color|background|backgroundColor|border|borderColor|borderTop|borderRight|borderBottom|borderLeft|outline|outlineColor|textDecoration|textDecorationColor|caretColor|accentColor|fill|stroke|boxShadow|textShadow)\s*:\s*(["'])([^"']+)\1/gi;
const COLOR_ATTRIBUTE_PATTERN = /\b(?:color|fill|stroke)\s*=\s*(["'])([a-z]+)\1/gi;
const COLOR_ATTRIBUTE_EXPRESSION_LITERAL_PATTERN =
  /\b(?:color|fill|stroke)\s*=\s*\{\s*(["'`])([a-z]+)\1\s*\}/gi;
const NAMED_COLOR_TOKEN_PATTERN = /(?<![-\w])[a-z]+(?![-\w])/gi;
const CSS_NAMED_COLORS = new Set(
  `aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen`.split(
    ' ',
  ),
);
const NAMED_PALETTE_CLASS_PATTERN =
  /(?:^|[^a-z0-9_-])((?:accent|bg|border|caret|decoration|divide|fill|from|outline|ring|shadow|stroke|text|to|via)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|[1-9]00|950)(?:\/\d{1,3})?\b)/gi;
const RADIUS_DECLARATION_PATTERN =
  /\bborder(?:-(?:top|right|bottom|left))?(?:-(?:left|right))?-radius\s*:\s*([^;}]+)/gi;
const ZERO_RADIUS_PATTERN =
  /^(?:0(?:\.0+)?(?:ch|cm|em|ex|in|mm|pc|pt|px|rem|vh|vmax|vmin|vw|%)?)(?:\s+0(?:\.0+)?(?:ch|cm|em|ex|in|mm|pc|pt|px|rem|vh|vmax|vmin|vw|%)?){0,3}$/i;
const RADIUS_ROLE = String.raw`(?:0|var\(--radius-(?:badge|control|surface|dialog|pill)\))`;
const SEMANTIC_RADIUS_PATTERN = new RegExp(`^${RADIUS_ROLE}(?:\\s+${RADIUS_ROLE}){0,3}$`, 'i');
const AXIS_MUTED_TEXT_PATTERN = /(?<![-\w])color\s*:\s*var\(--color-chart-axis-muted\)/gi;
const TEST_EXPECTATION_PATH_PATTERN = /\.(?:test|spec)\.[cm]?[jt]sx?$/;
const TOKEN_SOURCE_PATH = 'qf-ui/styles/tokens.css';
// Import-only stylesheet entry; the only CSS allowed outside shared UI.
const STYLE_ENTRY_PATH = 'app.css';
const SHARED_UI_BARREL = '@/ui';
const QF_UI_PACKAGE = '@quant-factory/qf-ui';
// `from 'x'`, `import 'x'`, and `import('x')`; vi.mock('x') is deliberately not matched.
const IMPORT_SPECIFIER_PATTERN = /(?:\bfrom\s*|\bimport\s*\(?\s*)(["'])([^"'\n]+)\1/g;
const NATIVE_UI_TAGS = [
  'button',
  'input',
  'select',
  'textarea',
  'table',
  'thead',
  'tbody',
  'tfoot',
  'tr',
  'th',
  'td',
  'caption',
];
const EXTENDED_NATIVE_UI_TAGS = [
  'a',
  'details',
  'summary',
  'dl',
  'dt',
  'dd',
  'label',
  'form',
  'nav',
  'dialog',
  'progress',
  'hr',
  'h1',
  'h2',
];
const VISUAL_UTILITY_PREFIXES = [
  'bg',
  'text',
  'border',
  'rounded',
  'shadow',
  'font',
  'tracking',
  'leading',
  'ring',
  'outline',
  'divide',
  'decoration',
  'opacity',
  'from',
  'via',
  'to',
  'fill',
  'stroke',
  'backdrop',
  'blur',
  'drop-shadow',
  'animate',
  'transition',
  'duration',
  'ease',
  'cursor',
  'select',
  'placeholder',
  'accent',
  'caret',
  'prose',
];
const VISUAL_UTILITY_WORDS = new Set([
  'underline',
  'no-underline',
  'italic',
  'not-italic',
  'uppercase',
  'lowercase',
  'capitalize',
  'normal-case',
  'line-through',
  'antialiased',
  'subpixel-antialiased',
]);
/** Prefixes that are also complete utilities on their own (`border`, `rounded`); every other bare prefix (`fill`, `text`, `to`) can only be an identifier inside a className expression. */
const BARE_VISUAL_UTILITIES = new Set([
  'border',
  'rounded',
  'shadow',
  'ring',
  'outline',
  'transition',
  'blur',
  'drop-shadow',
  'prose',
]);
const ALLOWED_TEXT_UTILITIES = new Set([
  'text-left',
  'text-right',
  'text-center',
  'text-justify',
  'text-start',
  'text-end',
  'text-nowrap',
  'text-wrap',
  'text-balance',
  'text-pretty',
  'text-ellipsis',
  'text-clip',
]);
const VIEWPORT_SIZE_UTILITY_PATTERN = /^(?:min-|max-)?[hw]-(?:screen|dvh|svh|lvh|dvw|svw|lvw)$/;
const LOADING_TEXT_PATTERN =
  /\b(?:Loading|Building|Fetching|Preparing|Computing)\b[^"'`<{}\n]{0,80}?(?:…|\.\.\.)/;
const INLINE_OVERFLOW_PATTERN = /\boverflow(?:X|Y)?\s*:/;
const RULES = [
  {
    pattern:
      /rounded-(?:surface|dialog)[^"\n]*border[^"\n]*bg-(?:card|surface-raised)|bg-(?:card|surface-raised)[^"\n]*border[^"\n]*rounded-(?:surface|dialog)/,
    message: 'use the shared Surface component (rounded-surface)',
  },
  {
    pattern:
      /(?:chart-control(?!-marker)|className=["'][^"']*(?:empty-state|inline-state|state-message))/,
    message: 'use shared Button or StateMessage presentation',
  },
];

/* Utilities the namespace resets removed: after the reset they compile to
   nothing, so shared TSX naming one would render unstyled without this ban. */
const RETIRED_UTILITY_PATTERN = new RegExp(
  [
    String.raw`^text-(?:2xs|xs|sm|base|lg|xl|[2-9]xl)$`,
    String.raw`^text-\[(?:length:|[\d.]|calc\()`,
    String.raw`^leading-`,
    String.raw`^tracking-`,
    String.raw`^font-(?:data|body|title|serif|bold|extrabold|black|light|extralight|thin)$`,
    String.raw`^rounded$`,
    String.raw`^rounded-(?:(?:t|r|b|l|s|e|x|y|tl|tr|br|bl|ss|se|es|ee)-)?(?:none|xs|sm|md|lg|xl|2xl|3xl|4xl|full)$`,
    String.raw`^shadow-(?:2xs|xs|sm|md|lg|xl|2xl|inner)$`,
    String.raw`^shadow-\[`,
    String.raw`^(?:bg|text|border|ring|outline|divide|decoration|fill|stroke|from|via|to|accent|caret|shadow)-(?:champion|muted-foreground-subtle|muted|sidebar-ring|tree-depth(?:-\d+)?)(?:\/\d+)?$`,
  ].join('|'),
);

/* Retired tokens and where each consumer goes instead. */
const RETIRED_TOKENS = new Map([
  ['--background', '--color-surface-canvas'],
  ['--foreground', '--color-fg-primary'],
  ['--border', '--color-border'],
  ['--positive', '--color-tone-success'],
  ['--negative', '--color-tone-critical'],
  ['--control-radius', '--radius-control'],
  ['--panel-radius', '--radius-surface or --radius-dialog'],
  ['--duration-fast', '--duration-control'],
  ['--ease-out-quart', '--ease-enter'],
  ['--color-bg', '--color-surface-canvas'],
  ['--color-bg-secondary', '--color-surface-raised'],
  ['--color-bg-hover', '--color-state-hover'],
  ['--color-text-muted', '--color-fg-tertiary'],
  ['--color-text-inverse', '--color-brand-foreground'],
  ['--color-success', '--color-tone-success'],
  ['--color-danger', '--color-tone-critical'],
  ['--color-warning', '--color-tone-warning'],
  ['--sidebar-width-collapsed', '--sidebar-width'],
  ['--page-gutter', '--inset-page (the pane already carries it)'],
  ['--radius-xs', '--radius-badge'],
  ['--radius-sm', '--radius-control or --radius-surface'],
  ['--radius-md', '--radius-surface'],
  ['--radius-lg', '--radius-surface'],
  ['--radius-xl', '--radius-surface'],
  ['--font-body', '--font-sans'],
  ['--font-title', '--font-sans'],
  ['--font-data', '--font-sans (or --font-mono for identifiers)'],
  ['--tracking-label', 'the type-role letter-spacing companion'],
  ['--tracking-mono', 'the type-role letter-spacing companion'],
  ['--text-2xs', '--text-caption'],
  ['--text-xs', '--text-caption'],
  ['--text-sm', '--text-body, --text-label or --text-ui-sm'],
  ['--text-base', '--text-section or --text-body'],
  ['--text-lg', '--text-section or --text-title'],
  ['--text-xl', '--text-section or --text-title'],
  ['--text-2xl', '--text-metric'],
  ['--text-3xl', '--text-metric'],
  ['--leading-tight', 'the type-role line-height companion'],
  ['--leading-normal', 'the type-role line-height companion'],
  ['--leading-relaxed', 'the type-role line-height companion'],
  ['--shadow-selection-soft', '--color-state-hover'],
  ['--color-champion', '--color-tone-neutral or --color-chart-primary'],
  ['--color-chart-bar-champion', '--color-chart-primary'],
  ['--color-muted-foreground-subtle', '--color-fg-tertiary'],
  ['--color-muted', '--color-surface-raised'],
  ['--color-destructive', '--color-tone-critical'],
  ['--color-destructive-foreground', '--color-surface-canvas'],
  ['--color-chart-line', '--color-chart-1'],
  ['--color-chart-area', '--color-chart-1'],
  ['--color-chart-bar', '--color-tone-neutral'],
  ['--color-chart-toolbar', '--color-surface-raised'],
  ['--color-chart-toolbar-border', '--color-border'],
  ['--color-chart-axis-label', '--color-fg-tertiary'],
  ['--color-chart-frame', '--color-border'],
  ['--color-chart-brush-track', '--color-state-hover'],
  ['--color-chart-brush-selection', '--color-state-selected'],
  ['--color-chart-brush-handle', '--color-fg-secondary'],
  ['--space-3xs', '--space-1'],
  ['--space-2xs', '--space-2'],
  ['--space-xs', '--space-3'],
  ['--space-sm', '--space-4'],
  ['--space-md', '--space-5'],
  ['--space-lg', '--space-6'],
  ['--space-xl', '--space-7'],
  ['--space-2xl', '--space-8'],
]);
const RETIRED_TOKEN_FAMILY_PATTERNS = [
  [/^--chart-[a-z0-9-]+$/, '--color-chart-* (or a --qf-chart-* bridge inside charts)'],
  [/^--color-sidebar-[a-z-]+$/, 'surface, fg, border or state tokens'],
  [/^--color-tree-depth-\d+$/, '--color-chart-1..20'],
];
const VAR_REFERENCE_PATTERN = /var\(\s*(--[a-z0-9_-]+)\s*[,)]/gi;
const STRING_LITERAL_PATTERN = /(["'`])((?:\\.|(?!\1)[^\\\n])*)\1/g;

/* At-rules that are not style rules: they carry no selector whose cascade a layer
   could order, so they are allowed at the top level of a shared-UI stylesheet. */
const NON_STYLE_AT_RULES = new Set([
  'charset',
  'custom-variant',
  'font-face',
  'import',
  'keyframes',
  'property',
  'source',
  'theme',
  'utility',
]);

// --------------------------------------------------------------------------- #
// Literal helpers
// --------------------------------------------------------------------------- #

export function stripComments(source) {
  let result = '';
  let quote = null;

  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    const nextCharacter = source[index + 1];

    if (quote) {
      result += character;
      if (character === '\\') {
        result += nextCharacter ?? '';
        index += 1;
      } else if (character === quote) {
        quote = null;
      }
      continue;
    }

    if (character === '"' || character === "'" || character === '`') {
      quote = character;
      result += character;
      continue;
    }

    if (character === '/' && nextCharacter === '/') {
      result += '  ';
      index += 2;
      while (index < source.length && source[index] !== '\n') {
        result += ' ';
        index += 1;
      }
      if (index < source.length) result += '\n';
      continue;
    }

    if (character === '/' && nextCharacter === '*') {
      result += '  ';
      index += 2;
      while (index < source.length && !(source[index] === '*' && source[index + 1] === '/')) {
        result += source[index] === '\n' ? '\n' : ' ';
        index += 1;
      }
      if (index < source.length) {
        result += '  ';
        index += 1;
      }
      continue;
    }

    result += character;
  }

  return result;
}

function lineNumber(source, index) {
  return source.slice(0, index).split('\n').length;
}

/** Resolve a relative import against the importer's local path (posix, no extension). */
export function resolveRelativeImport(localPath, specifier) {
  return posix.normalize(posix.join(posix.dirname(localPath), specifier));
}

function targetsSharedUi(resolvedPath) {
  return (
    resolvedPath === 'ui' ||
    resolvedPath.startsWith('ui/') ||
    /(?:^|\/)src\/ui(?:\/|$)/.test(resolvedPath) ||
    /(?:^|\/)qf-ui\/src(?:\/|$)/.test(resolvedPath)
  );
}

/**
 * Every style rule in a shared-UI stylesheet must sit inside a declared `@layer`, so the
 * cascade is ordered by the layer statement in app.css rather than by module import order.
 * Walks top-level statements only; anything nested is already inside whatever wraps it.
 */
export function collectUnlayeredCssFailures(localPath, source) {
  const failures = [];

  const endOfStatement = (start) => {
    let depth = 0;
    for (let i = start; i < source.length; i += 1) {
      const character = source[i];
      if (character === '{') depth += 1;
      else if (character === '}') {
        depth -= 1;
        if (depth === 0) return i + 1;
      } else if (character === ';' && depth === 0) return i + 1;
    }
    return source.length;
  };

  /* `qf-motion` is the one layer that outranks Tailwind utilities, so it is fenced to the
     reduced-motion policy it exists for. Anything else there is an escape hatch. */
  const checkMotionLayer = (body, offset) => {
    let index = 0;
    while (index < body.length) {
      if (/\s/.test(body[index])) {
        index += 1;
        continue;
      }
      const start = index;
      const brace = body.indexOf('{', start);
      const prelude = (brace < 0 ? body.slice(start) : body.slice(start, brace)).trim();
      let depth = 0;
      let end = body.length;
      for (let i = start; i < body.length; i += 1) {
        if (body[i] === '{') depth += 1;
        else if (body[i] === '}') {
          depth -= 1;
          if (depth === 0) {
            end = i + 1;
            break;
          }
        } else if (body[i] === ';' && depth === 0) {
          end = i + 1;
          break;
        }
      }
      index = end;
      if (
        /^@media\b/i.test(prelude) &&
        /\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)/i.test(prelude)
      ) {
        continue;
      }
      failures.push(
        `${localPath}:${lineNumber(source, offset + start)}: @layer qf-motion holds only @media (prefers-reduced-motion: reduce) blocks; "${prelude.replace(/\s+/g, ' ')}" belongs in @layer qf-components or @layer qf-variants`,
      );
    }
  };

  let index = 0;
  while (index < source.length) {
    if (/\s/.test(source[index])) {
      index += 1;
      continue;
    }
    const start = index;
    const end = endOfStatement(index);

    if (source[index] === '@') {
      const keyword = /^@([a-z-]+)/i.exec(source.slice(index))?.[1]?.toLowerCase() ?? '';
      const brace = source.indexOf('{', start);
      if (keyword === 'layer') {
        const isBlock = brace >= 0 && brace < end;
        const prelude = isBlock ? source.slice(start + '@layer'.length, brace).trim() : '';
        if (isBlock && prelude === 'qf-motion') {
          checkMotionLayer(source.slice(brace + 1, end - 1), brace + 1);
        }
        index = end;
        continue;
      }
      index = end;
      if (NON_STYLE_AT_RULES.has(keyword)) continue;
      failures.push(
        `${localPath}:${lineNumber(source, start)}: @${keyword} holds style rules outside a declared @layer; wrap it in @layer qf-components or @layer qf-variants`,
      );
      continue;
    }

    const brace = source.indexOf('{', start);
    const selector = (brace < 0 ? source.slice(start, end) : source.slice(start, brace))
      .trim()
      .replace(/\s+/g, ' ');
    index = end;
    failures.push(
      `${localPath}:${lineNumber(source, start)}: style rule "${selector}" sits outside a declared @layer; wrap it in @layer qf-components or @layer qf-variants`,
    );
  }

  return failures;
}

export function collectLiteralFailures(localPath, source) {
  const executableSource = stripComments(source);
  const failures = [];

  if (localPath !== TOKEN_SOURCE_PATH && !TEST_EXPECTATION_PATH_PATTERN.test(localPath)) {
    for (const match of executableSource.matchAll(RAW_COLOR_PATTERN)) {
      failures.push(
        `${localPath}:${lineNumber(executableSource, match.index)}: replace raw color "${match[0]}" with a semantic token`,
      );
    }
    const seenNamedColors = new Set();
    for (const pattern of [COLOR_DECLARATION_PATTERN, CUSTOM_PROPERTY_DECLARATION_PATTERN]) {
      for (const declaration of executableSource.matchAll(pattern)) {
        const value = declaration[1] ?? '';
        const valueOffset = (declaration.index ?? 0) + declaration[0].lastIndexOf(value);
        for (const token of value.matchAll(NAMED_COLOR_TOKEN_PATTERN)) {
          const color = token[0].toLowerCase();
          if (!CSS_NAMED_COLORS.has(color)) continue;
          const index = valueOffset + (token.index ?? 0);
          seenNamedColors.add(index);
          failures.push(
            `${localPath}:${lineNumber(executableSource, index)}: replace named color "${token[0]}" with a semantic token`,
          );
        }
      }
    }
    for (const pattern of [
      COLOR_PROPERTY_LITERAL_PATTERN,
      COLOR_ATTRIBUTE_PATTERN,
      COLOR_ATTRIBUTE_EXPRESSION_LITERAL_PATTERN,
    ]) {
      for (const match of executableSource.matchAll(pattern)) {
        const value = match[2] ?? '';
        const valueOffset = (match.index ?? 0) + match[0].lastIndexOf(value);
        for (const token of value.matchAll(NAMED_COLOR_TOKEN_PATTERN)) {
          const color = token[0].toLowerCase();
          const index = valueOffset + (token.index ?? 0);
          if (!CSS_NAMED_COLORS.has(color) || seenNamedColors.has(index)) continue;
          seenNamedColors.add(index);
          failures.push(
            `${localPath}:${lineNumber(executableSource, index)}: replace named color "${token[0]}" with a semantic token`,
          );
        }
      }
    }
  }

  for (const match of executableSource.matchAll(AXIS_MUTED_TEXT_PATTERN)) {
    failures.push(
      `${localPath}:${lineNumber(executableSource, match.index)}: use --color-chart-axis-label for readable chart text`,
    );
  }

  for (const match of executableSource.matchAll(NAMED_PALETTE_CLASS_PATTERN)) {
    failures.push(
      `${localPath}:${lineNumber(executableSource, match.index)}: replace named palette class "${match[1]}" with a semantic color class`,
    );
  }

  if (localPath.endsWith('.css')) {
    for (const match of executableSource.matchAll(RADIUS_DECLARATION_PATTERN)) {
      const value = match[1].trim();
      if (ZERO_RADIUS_PATTERN.test(value) || SEMANTIC_RADIUS_PATTERN.test(value)) continue;
      failures.push(
        `${localPath}:${lineNumber(executableSource, match.index)}: replace nonzero border radius "${value}" with a radius role token (--radius-badge, --radius-control, --radius-surface, --radius-dialog or --radius-pill)`,
      );
    }
    if (localPath !== TOKEN_SOURCE_PATH) {
      failures.push(...collectShadowFailures(localPath, executableSource));
      failures.push(...collectTypeFailures(localPath, executableSource));
    }
  }

  return failures;
}

/** The `{…}` block that holds `index`, its selector prelude and its body (nesting-aware). */
function enclosingRule(source, index) {
  let depth = 0;
  let open = -1;
  for (let i = index - 1; i >= 0; i -= 1) {
    if (source[i] === '}') depth += 1;
    else if (source[i] === '{') {
      if (depth === 0) {
        open = i;
        break;
      }
      depth -= 1;
    }
  }
  if (open < 0) return { selector: '', body: '' };
  depth = 0;
  let close = source.length;
  for (let i = open + 1; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    else if (source[i] === '}') {
      if (depth === 0) {
        close = i;
        break;
      }
      depth -= 1;
    }
  }
  const preludeStart =
    Math.max(
      source.lastIndexOf('{', open - 1),
      source.lastIndexOf('}', open - 1),
      source.lastIndexOf(';', open - 1),
    ) + 1;
  return {
    selector: source.slice(preludeStart, open).trim().replace(/\s+/g, ' '),
    body: source.slice(open + 1, close),
  };
}

/** Declarations of `property` (exact name, never a custom property suffix) with their offsets. */
function declarationsOf(source, propertyPattern) {
  const pattern = new RegExp(`(?<![-\\w])(${propertyPattern})\\s*:\\s*([^;}]+)`, 'gi');
  return [...source.matchAll(pattern)].map((match) => ({
    property: match[1].toLowerCase(),
    value: match[2].trim(),
    index: match.index,
  }));
}

/** Split a CSS value on commas that sit outside parentheses. */
function splitTopLevel(value) {
  const items = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < value.length; i += 1) {
    if (value[i] === '(') depth += 1;
    else if (value[i] === ')') depth -= 1;
    else if (value[i] === ',' && depth === 0) {
      items.push(value.slice(start, i).trim());
      start = i + 1;
    }
  }
  items.push(value.slice(start).trim());
  return items;
}

function lengthInPx(number, unit) {
  return unit === 'rem' ? number * 16 : number;
}

/** Elevation only through the shadow tokens; an inset rule may be at most 3px with no blur. */
export function collectShadowFailures(localPath, source) {
  const failures = [];
  for (const { value, index } of declarationsOf(source, 'box-shadow')) {
    const ok = splitTopLevel(value).every((item) => {
      if (/^(?:none|inherit|initial|unset)$/i.test(item)) return true;
      if (/^var\(--shadow-(?:raised|overlay|dialog|selection)\)$/i.test(item)) return true;
      if (!/^inset\b/i.test(item)) return false;
      const lengths = [];
      const geometry = item.replace(/[a-z-]+\((?:[^()]|\([^()]*\))*\)/gi, ' ');
      for (const token of geometry
        .replace(/^inset\b/i, '')
        .trim()
        .split(/\s+/)) {
        const length = /^(-?\d*\.?\d+)(px|rem)?$/i.exec(token);
        if (!length) continue;
        lengths.push(lengthInPx(Number(length[1]), length[2]?.toLowerCase()));
      }
      if (lengths.length > 2 && lengths[2] !== 0) return false;
      return lengths.every((px) => Math.abs(px) <= 3);
    });
    if (ok) continue;
    failures.push(
      `${localPath}:${lineNumber(source, index)}: elevation uses var(--shadow-raised|overlay|dialog); inset rules may be at most 3px with no blur`,
    );
  }
  return failures;
}

const TYPE_ROLE =
  '(?:caption|ui-sm|body|label|section|title|metric|overline|prose|reading|display|caps)';
const TYPE_VALUE_RULES = [
  {
    property: 'font-size',
    allowed: new RegExp(`^(?:var\\(--text-${TYPE_ROLE}\\)|inherit)$`, 'i'),
    hint: 'var(--text-<role>) or inherit',
  },
  {
    property: 'line-height',
    allowed: new RegExp(`^(?:var\\(--text-${TYPE_ROLE}--line-height\\)|1|normal|inherit)$`, 'i'),
    hint: 'var(--text-<role>--line-height), 1, normal or inherit',
  },
  {
    property: 'letter-spacing',
    allowed: new RegExp(`^(?:0|normal|inherit|var\\(--text-${TYPE_ROLE}--letter-spacing\\))$`, 'i'),
    hint: '0, normal, inherit or var(--text-<role>--letter-spacing)',
  },
  {
    property: 'font-weight',
    allowed: new RegExp(`^(?:400|500|600|inherit|var\\(--text-${TYPE_ROLE}--font-weight\\))$`, 'i'),
    hint: '400, 500, 600, inherit or var(--text-<role>--font-weight)',
  },
  {
    property: 'font-family',
    allowed: /^(?:var\(--font-sans\)|var\(--font-mono\)|inherit)$/i,
    hint: 'var(--font-sans), var(--font-mono) or inherit',
  },
  { property: 'font', allowed: /^inherit$/i, hint: 'inherit' },
];
const MONO_SELECTOR_MARKER =
  /(?:^|[\s>+~(])(?:code|pre|kbd|samp)\b|\.is-mono\b|\[data-mono\]|\[data-identifier\]|\.[\w-]+-(?:code|kbd|path|hash|id|identifier)\b/;
const OVERLINE_SIZE_PATTERN = /(?<![-\w])font-size\s*:\s*var\(--text-overline\)/i;

/** Type roles, the two families, mono only on identifier selectors, uppercase only as overline. */
export function collectTypeFailures(localPath, source) {
  const failures = [];
  for (const rule of TYPE_VALUE_RULES) {
    for (const { value, index } of declarationsOf(source, rule.property)) {
      if (!rule.allowed.test(value)) {
        failures.push(
          `${localPath}:${lineNumber(source, index)}: ${rule.property} "${value}" must be ${rule.hint}`,
        );
        continue;
      }
      if (rule.property === 'font-family' && /--font-mono/i.test(value)) {
        const { selector } = enclosingRule(source, index);
        const items = selector.split(',').map((item) => item.trim());
        if (!items.length || !items.every((item) => MONO_SELECTOR_MARKER.test(item))) {
          failures.push(
            `${localPath}:${lineNumber(source, index)}: mono is for ids, hashes, paths and code; mark the selector or use var(--font-sans)`,
          );
        }
      }
    }
  }
  for (const { value, index } of declarationsOf(source, 'text-transform')) {
    if (!/^(?:uppercase|capitalize)$/i.test(value)) continue;
    if (OVERLINE_SIZE_PATTERN.test(enclosingRule(source, index).body)) continue;
    failures.push(
      `${localPath}:${lineNumber(source, index)}: sentence case only; uppercase is reserved for the overline role`,
    );
  }
  return failures;
}

const SPACING_PROPERTIES =
  'padding(?:-[a-z-]+)?|margin(?:-[a-z-]+)?|gap|row-gap|column-gap|inset(?:-[a-z-]+)?|top|right|bottom|left';
const SPACING_ALLOWED_MULTIPLIERS = new Set([
  '0',
  '1',
  '2',
  '3',
  '4',
  '6',
  '8',
  '10',
  '12',
  '16',
  'px',
]);
const SPACING_UTILITY_PATTERN =
  /^-?(?:p|px|py|pt|pr|pb|pl|ps|pe|m|mx|my|mt|mr|mb|ml|ms|me|gap|gap-x|gap-y|space-x|space-y|inset|inset-x|inset-y|top|right|bottom|left|start|end)-(.+)$/;

/** Shared spacing sits on the 4px scale: 0, exactly 1px, or a multiple of 4px. */
export function collectSpacingFailures(localPath, source) {
  const executableSource = stripComments(source);
  const failures = [];
  if (localPath.endsWith('.css')) {
    for (const { property, value, index } of declarationsOf(executableSource, SPACING_PROPERTIES)) {
      const relative = /^(?:padding|margin|gap|row-gap|column-gap)/.test(property)
        ? /(-?\d*\.?\d+)(em|ch|vw|vh|vmin|vmax)\b/i.exec(value)
        : null;
      const offScale = [...value.matchAll(/(-?\d*\.?\d+)(px|rem)\b/gi)].find((match) => {
        const px = Math.abs(lengthInPx(Number(match[1]), match[2].toLowerCase()));
        return !(px === 0 || px === 1 || Number.isInteger(px / 4));
      });
      if (!relative && !offScale) continue;
      failures.push(
        `${localPath}:${lineNumber(executableSource, index)}: ${property} "${value}" is off the 4px spacing scale; use 0, 1px, a multiple of 4px or a --space-*/--inset-*/--gap-* token`,
      );
    }
  } else if (localPath.endsWith('.tsx')) {
    const seen = new Set();
    for (const match of executableSource.matchAll(STRING_LITERAL_PATTERN)) {
      for (const token of layoutClassTokens(match[2])) {
        const spacing = SPACING_UTILITY_PATTERN.exec(token);
        if (!spacing || seen.has(token)) continue;
        const value = spacing[1];
        const ok = value.startsWith('[')
          ? /^\[var\(--(?:space-[1-9]|inset-[a-z-]+|gap-[a-z-]+)\)\]$/.test(value)
          : !/^\d+(?:\.\d+)?$/.test(value) || SPACING_ALLOWED_MULTIPLIERS.has(value);
        if (ok) continue;
        seen.add(token);
        failures.push(
          `${localPath}:${lineNumber(executableSource, match.index)}: "${token}" is off the 4px spacing scale; use 0, 1, 2, 3, 4, 6, 8, 10, 12, 16 or px, or var(--space-N)`,
        );
      }
    }
  }
  return failures;
}

/* Layout spacing (12px and up) belongs to the layout primitives; 0-8px stays legal for
   component internals. Positioning offsets (top, inset, …) are not spacing. */
const LAYOUT_SPACING_UTILITY_PATTERN =
  /^-?(gap-x|gap-y|space-x|space-y|gap|p|px|py|pt|pr|pb|pl|ps|pe|m|mx|my|mt|mr|mb|ml|ms|me)-(.+)$/;
const LAYOUT_SPACING_MIN_PX = 12;
const SPACING_ROLE_BY_PX = [
  [12, 'heading'],
  [16, 'block'],
  [32, 'section'],
];
const SPACING_PRIMITIVES = ['PageShell', 'Section', 'Stack', 'Cluster', 'Grid', 'ChartGrid'];
const SPACING_PRIMITIVE_TAG_PATTERN = new RegExp(`<(${SPACING_PRIMITIVES.join('|')})\\b`, 'g');
/* Like classTokens, but keeps `p-[var(--x)]` and `p-(--x)` whole. */
const BRACKET_AWARE_CLASS_TOKEN_PATTERN = /(?:[^\s"'`{}$,()[\]]|\[[^\]\s]*\]|\(--[a-z0-9-]+\))+/gi;

function layoutClassTokens(value) {
  return (value.match(BRACKET_AWARE_CLASS_TOKEN_PATTERN) ?? []).map((token) =>
    token.replace(/^!/, '').replace(/^(?:(?:[a-z0-9-]+|\[[^\]]*\]):)+/, ''),
  );
}

/** Pixel size of a spacing utility value, or null when it is not a length (`auto`, `px`…). */
function spacingValuePx(value) {
  if (/^\d+(?:\.\d+)?$/.test(value)) return Number(value) * 4;
  const arbitrary = /^(?:\[(.+)\]|\((--[a-z0-9-]+)\))$/.exec(value);
  if (!arbitrary) return null;
  const inner = arbitrary[1] ?? `var(${arbitrary[2]})`;
  if (/var\(--(?:gap|inset)-[a-z-]+\)/.test(inner)) return Number.POSITIVE_INFINITY;
  const space = /^var\(--space-(\d)\)$/.exec(inner);
  if (space) return [0, 4, 8, 12, 16, 24, 32, 40, 48, 64][Number(space[1])] ?? null;
  const length = /^(-?\d*\.?\d+)(px|rem)$/.exec(inner);
  return length ? Math.abs(lengthInPx(Number(length[1]), length[2])) : null;
}

function spacingRoleHint(kind, px) {
  const role = Number.isFinite(px)
    ? SPACING_ROLE_BY_PX.reduce((best, entry) =>
        Math.abs(entry[0] - px) < Math.abs(best[0] - px) ? entry : best,
      )[1]
    : 'heading|block|section';
  if (kind === 'gap' || kind.startsWith('space-')) {
    return `use Stack, Cluster or Grid gap="${role}"`;
  }
  if (kind.startsWith('p')) {
    return 'let the primitive that frames it own the inset (PageShell, Surface padding, a qf-ui component)';
  }
  return `delete it and let the parent primitive own the gap (Stack gap="${role}", PageShell rhythm)`;
}

/** The `<Tag …>` opening tag text starting at `start`, brace- and quote-aware. */
function openingTagAt(source, start) {
  let depth = 0;
  let quote = null;
  for (let index = start + 1; index < source.length; index += 1) {
    const character = source[index];
    if (quote) {
      if (character === '\\') index += 1;
      else if (character === quote) quote = null;
      continue;
    }
    if (character === '"' || character === "'" || character === '`') quote = character;
    else if (character === '{') depth += 1;
    else if (character === '}') depth -= 1;
    else if (character === '>' && depth === 0) return source.slice(start, index + 1);
  }
  return source.slice(start);
}

/** Page code spaces layout through the primitives, never with 12px+ utilities (spacing SPEC §4). */
export function collectLayoutSpacingFailures(localPath, source) {
  const executableSource = stripComments(source);
  const failures = [];
  const seen = new Set();
  for (const match of executableSource.matchAll(STRING_LITERAL_PATTERN)) {
    for (const token of layoutClassTokens(match[2])) {
      const spacing = LAYOUT_SPACING_UTILITY_PATTERN.exec(token);
      if (!spacing) continue;
      const px = spacingValuePx(spacing[2]);
      if (px === null || px < LAYOUT_SPACING_MIN_PX) continue;
      const key = `${lineNumber(executableSource, match.index)}:${token}`;
      if (seen.has(key)) continue;
      seen.add(key);
      failures.push(
        `${localPath}:${lineNumber(executableSource, match.index)}: "${token}" is layout spacing (12px or more); ${spacingRoleHint(spacing[1], px)}`,
      );
    }
  }
  for (const match of executableSource.matchAll(SPACING_PRIMITIVE_TAG_PATTERN)) {
    const tag = openingTagAt(executableSource, match.index);
    const tokens = classNameValues(tag)
      .flatMap(layoutClassTokens)
      .filter((token) => LAYOUT_SPACING_UTILITY_PATTERN.test(token));
    for (const token of new Set(tokens)) {
      failures.push(
        `${localPath}:${lineNumber(executableSource, match.index)}: <${match[1]}> owns its spacing; remove "${token}" from its className and use its props`,
      );
    }
  }
  return failures;
}

const SHELL_CSS_PATTERN = /^(?:qf-)?ui\/(?:shell|frame)\/[^/]+\.css$/;

/** Shell and section-frame regressions, guarded as code rather than notes. */
export function collectShellFailures(localPath, source) {
  const failures = [];
  const isShellOrFrameCss = SHELL_CSS_PATTERN.test(localPath);
  if (isShellOrFrameCss) {
    for (const { value, index } of declarationsOf(source, 'z-index')) {
      if (/^var\(--z-[a-z-]+\)$/.test(value)) continue;
      failures.push(
        `${localPath}:${lineNumber(source, index)}: shell z-index must use the --z-* scale`,
      );
    }
    for (const match of source.matchAll(/var\(\s*--color-(?:primary|champion)\s*[,)]/g)) {
      failures.push(
        `${localPath}:${lineNumber(source, match.index)}: the shell uses --color-brand only for the active mark`,
      );
    }
  }
  if (!localPath.startsWith(EXTENSIONS_PREFIX)) {
    for (const match of source.matchAll(
      /--color-sidebar-|\b(?:bg|text|border|ring|from|to|via)-sidebar(?:-[a-z-]+)?\b/g,
    )) {
      failures.push(
        `${localPath}:${lineNumber(source, match.index)}: use surface, fg, border or state tokens, not sidebar aliases`,
      );
    }
  }
  if (/^(?:qf-)?ui\/shell\/[^/]+\.css$/.test(localPath)) {
    for (const match of source.matchAll(/var\(\s*--font-data\s*[,)]/g)) {
      failures.push(
        `${localPath}:${lineNumber(source, match.index)}: the shell navigator is sans; mono belongs to content identifiers`,
      );
    }
  }
  return failures;
}

/** `var(--x)` references to a retired token, anywhere in a scanned file. */
export function collectRetiredTokenFailures(localPath, source) {
  const executableSource = stripComments(source);
  const failures = [];
  for (const match of executableSource.matchAll(VAR_REFERENCE_PATTERN)) {
    const name = match[1].toLowerCase();
    const replacement =
      RETIRED_TOKENS.get(name) ??
      RETIRED_TOKEN_FAMILY_PATTERNS.find(([pattern]) => pattern.test(name))?.[1];
    if (!replacement) continue;
    failures.push(
      `${localPath}:${lineNumber(executableSource, match.index)}: "${name}" was retired; use ${replacement}`,
    );
  }
  return failures;
}

/** Class strings in shared TSX may not name a utility the namespace resets removed. */
export function collectRetiredUtilityFailures(localPath, source) {
  const executableSource = stripComments(source);
  const failures = [];
  const seen = new Set();
  for (const match of executableSource.matchAll(STRING_LITERAL_PATTERN)) {
    for (const token of classTokens(match[2])) {
      const utility = token.replace(/^[!-]/, '');
      if (!RETIRED_UTILITY_PATTERN.test(utility) || seen.has(utility)) continue;
      seen.add(utility);
      failures.push(
        `${localPath}:${lineNumber(executableSource, match.index)}: "${utility}" is not a design-system utility; use a type role (text-caption..metric), a radius role (rounded-badge..pill) or a shadow token`,
      );
    }
  }
  return failures;
}

/** In shared TSX a class string that uppercases text must also set the overline role. */
export function collectUppercaseClassFailures(localPath, source) {
  const executableSource = stripComments(source);
  const failures = [];
  for (const match of executableSource.matchAll(STRING_LITERAL_PATTERN)) {
    const tokens = classTokens(match[2]);
    if (!tokens.includes('uppercase') || tokens.includes('text-overline')) continue;
    failures.push(
      `${localPath}:${lineNumber(executableSource, match.index)}: sentence case only; uppercase is reserved for the overline role`,
    );
  }
  return failures;
}

// --------------------------------------------------------------------------- #
// Class utilities
// --------------------------------------------------------------------------- #

export function classNameValues(source) {
  const values = [];
  for (const match of source.matchAll(/className\s*=\s*/g)) {
    const start = match.index + match[0].length;
    const opener = source[start];
    if (opener === '"' || opener === "'") {
      const close = source.indexOf(opener, start + 1);
      if (close < 0) continue;
      values.push(source.slice(start + 1, close));
    } else if (opener === '{') {
      let depth = 0;
      let index = start;
      for (; index < source.length; index += 1) {
        if (source[index] === '{') depth += 1;
        else if (source[index] === '}') {
          depth -= 1;
          if (depth === 0) break;
        }
      }
      if (depth !== 0) continue;
      values.push(source.slice(start + 1, index));
    }
  }
  return values;
}

export function classTokens(value) {
  return value
    .split(/[\s"'`{}()$,]+/)
    .filter((token) => !['', '?', ':', '&&', '||', '!'].includes(token))
    .map((token) => token.replace(/^(?:[a-z0-9-]+:)+/, ''));
}

export function isVisualUtility(token) {
  if (ALLOWED_TEXT_UTILITIES.has(token)) return false;
  if (VISUAL_UTILITY_WORDS.has(token)) return true;
  if (VIEWPORT_SIZE_UTILITY_PATTERN.test(token)) return true;
  if (token.startsWith('overflow-') || token.startsWith('scroll-')) return true;
  if (BARE_VISUAL_UTILITIES.has(token)) return true;
  return VISUAL_UTILITY_PREFIXES.some((prefix) => token.startsWith(`${prefix}-`));
}

// --------------------------------------------------------------------------- #
// Check
// --------------------------------------------------------------------------- #

// Header and footer slots carry a title and controls only (qf-ui AGENTS "No caption
// clutter"): a caption inside a right=, headerRight= or footer= prop is status text.
const SLOT_PROP_PATTERN = /\b(?:right|headerRight|footer)=\{/g;

export function collectSlotCaptionFailures(localPath, source) {
  const failures = [];
  for (const match of source.matchAll(SLOT_PROP_PATTERN)) {
    let depth = 1;
    let end = match.index + match[0].length;
    while (depth > 0 && end < source.length) {
      if (source[end] === '{') depth += 1;
      else if (source[end] === '}') depth -= 1;
      end += 1;
    }
    if (/variant=["']caption["']/.test(source.slice(match.index, end))) {
      failures.push(
        `${localPath}:${lineNumber(source, match.index)}: no caption clutter in ${match[0].slice(0, -2)}; move the value into the title, a StatItem, a table cell or a control label, or drop it`,
      );
    }
  }
  return failures;
}

export function collectFileFailures(localPath, rawSource) {
  const source = stripComments(rawSource);
  const isTest = TEST_EXPECTATION_PATH_PATTERN.test(localPath);
  const isShared = SHARED_UI_PATHS.some((prefix) => localPath.startsWith(prefix));
  const isCss = localPath.endsWith('.css');
  const isTsx = localPath.endsWith('.tsx');
  const failures = [];

  // Group 1: chart-engine rules, applied to every file.
  if (CHART_FRAME_OVERRIDE_PATTERN.test(source)) {
    failures.push(`${localPath}: use the canonical qf-charts 16:9 frame without overrides`);
  }
  if (FULL_CHART_COMPONENT_PATTERN.test(source) && FIXED_CHART_HEIGHT_CLASS_PATTERN.test(source)) {
    failures.push(`${localPath}: full charts must not use fixed-height Tailwind wrappers`);
  }
  if (FIXED_RENDERER_HEIGHT_PATTERN.test(source)) {
    failures.push(`${localPath}: full qf-charts renderers must use the canonical 16:9 frame`);
  }
  if (
    localPath.startsWith(CHART_COMPONENT_PATH) &&
    /<svg\b/.test(source) &&
    !/<svg\b[\s\S]*?aria-hidden=["']true["']/.test(source)
  ) {
    failures.push(`${localPath}: render chart data through qf-charts, not local SVG`);
  }
  if (/<canvas\b/.test(source)) {
    failures.push(`${localPath}: render canvas charts through qf-charts`);
  }
  if (/@visx\//.test(source)) {
    failures.push(`${localPath}: route chart rendering through qf-charts`);
  }
  if (/from ["']echarts(?:\/|["'])/.test(source)) {
    failures.push(`${localPath}: import ECharts only inside qf-charts`);
  }
  // QfChart takes a raw ECharts option; pages and extensions declare data through a
  // named qf-ui chart component instead of building one.
  if (/\b(?:QfChart|QfChartOption)\b/.test(source)) {
    failures.push(`${localPath}: use a qf-ui chart component, not QfChart with a raw option`);
  }

  // Group 2: literal rules.
  failures.push(...collectLiteralFailures(localPath, rawSource));
  failures.push(...collectRetiredTokenFailures(localPath, rawSource));
  if (isShared && isTsx && !isTest) {
    failures.push(...collectRetiredUtilityFailures(localPath, rawSource));
    failures.push(...collectUppercaseClassFailures(localPath, rawSource));
  }
  if (isShared && !isTest) {
    failures.push(...collectSpacingFailures(localPath, rawSource));
  }
  failures.push(...collectShellFailures(localPath, source));
  if (isCss && isShared) {
    failures.push(...collectUnlayeredCssFailures(localPath, source));
  }

  // Group 3: existing presentation rules.
  if (!(isShared || isTest)) {
    if (isTsx) {
      if (/<EmptyState\b[^>]*title=["']Loading/s.test(source)) {
        failures.push(`${localPath}: use shared LoadingSkeleton for pending content`);
      }
      const nativeTag = NATIVE_UI_TAGS.find((tag) => new RegExp(`<${tag}\\b`).test(source));
      if (nativeTag) {
        failures.push(
          `${localPath}: replace native <${nativeTag}> with a component from shared UI`,
        );
      }
    }
    for (const rule of RULES) {
      if (rule.pattern.test(source)) failures.push(`${localPath}: ${rule.message}`);
    }
  }

  // Group 4: page-level rules.
  if (!(isShared || isTest)) {
    if (isCss && localPath !== STYLE_ENTRY_PATH) {
      failures.push(
        `${localPath}: page-level CSS is not allowed outside shared UI; build the page from shared components`,
      );
    }
    if (isTsx) {
      const visualTokens = new Set(
        classNameValues(source).flatMap(classTokens).filter(isVisualUtility),
      );
      for (const token of visualTokens) {
        failures.push(
          `${localPath}: page code may only use layout utilities; move "${token}" into a shared UI component or variant`,
        );
      }
      const extendedTag = EXTENDED_NATIVE_UI_TAGS.find((tag) =>
        new RegExp(`<${tag}\\b`).test(source),
      );
      if (extendedTag) {
        failures.push(
          `${localPath}: replace native <${extendedTag}> with a component from shared UI`,
        );
      }
    }
    if ((isTsx || localPath.endsWith('.ts')) && LOADING_TEXT_PATTERN.test(source)) {
      failures.push(
        `${localPath}: use shared LoadingSkeleton for pending content instead of loading text`,
      );
    }
    if (isTsx || localPath.endsWith('.ts')) {
      failures.push(...collectLayoutSpacingFailures(localPath, rawSource));
    }
    if (isTsx) {
      failures.push(...collectSlotCaptionFailures(localPath, source));
    }
    if (isTsx && INLINE_OVERFLOW_PATTERN.test(source)) {
      failures.push(
        `${localPath}: own overflow through shared ScrollArea or DataTable, not inline styles`,
      );
    }
  }

  // Group 5: shared-UI import rules (absolute).
  if (!isTest && (isTsx || localPath.endsWith('.ts'))) {
    for (const match of source.matchAll(IMPORT_SPECIFIER_PATTERN)) {
      const specifier = match[2];
      if (isShared) {
        if (specifier === SHARED_UI_BARREL || specifier.startsWith(`${SHARED_UI_BARREL}/`)) {
          failures.push(
            `${localPath}: shared UI modules import siblings relatively; the @/ui barrel is for consumers`,
          );
        }
        continue;
      }
      if (specifier === QF_UI_PACKAGE) {
        failures.push(`${localPath}: import shared UI through the @/ui barrel, not "${specifier}"`);
        continue;
      }
      const isRelative = specifier.startsWith('./') || specifier.startsWith('../');
      if (
        specifier.startsWith(`${SHARED_UI_BARREL}/`) ||
        (isRelative && targetsSharedUi(resolveRelativeImport(localPath, specifier)))
      ) {
        failures.push(`${localPath}: import shared UI through the @/ui barrel, not "${specifier}"`);
      }
    }
  }

  return failures;
}

async function checkDesignSystem() {
  const failures = [];

  for (const { root, prefix } of SCAN_ROOTS) {
    const rootPath = fileURLToPath(root);
    if (!existsSync(root)) continue; // apps/viz/extensions is optional
    const entries = await readdir(root, { recursive: true, withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isFile() || !/\.(?:css|ts|tsx)$/.test(entry.name)) continue;
      if (entry.parentPath.includes('node_modules')) continue;
      if (entry.parentPath.includes('_archive')) continue;
      const path = join(entry.parentPath, entry.name);
      const localPath = prefix + relative(rootPath, path).replaceAll('\\', '/');
      if (localPath.startsWith(QF_UI_CHARTS_PREFIX)) continue;
      const rawSource = await readFile(path, 'utf8');
      failures.push(...collectFileFailures(localPath, rawSource));
    }
  }

  if (failures.length) {
    console.error(`Design-system check failed:\n${failures.join('\n')}`);
    process.exitCode = 1;
  } else {
    console.log('Design-system check passed.');
  }
}

// --------------------------------------------------------------------------- #
// Entry point
// --------------------------------------------------------------------------- #

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await checkDesignSystem();
}
