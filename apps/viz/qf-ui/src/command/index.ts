/**
 * Code-split entry for the command palette (`@quant-factory/qf-ui/command`): hosts
 * `import()` this to keep cmdk and the Base UI dialog out of their first-load bundle.
 * The root barrel re-exports the same names.
 *
 * USAGE:
 *   const { CommandPalette } = await import('@quant-factory/qf-ui/command');
 */

// --------------------------------------------------------------------------- #
// Cascade layers (first, so kit CSS never precedes the layer order)
// --------------------------------------------------------------------------- #

import '../styles/layers.css';

// --------------------------------------------------------------------------- #
// Exports
// --------------------------------------------------------------------------- #

export * from './CommandPalette';
