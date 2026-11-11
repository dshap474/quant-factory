/**
 * Copy control for a pipeline lane's path. Loaded separately from the map, which ships in
 * first-load code: the control only appears on hover, so nothing visibly arrives late.
 *
 * USAGE:
 *   <PipelineLaneCopy path="db/data/raw/" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { CopyButton } from '@quant-factory/qf-ui';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function PipelineLaneCopy({ path }: { path: string }) {
  return (
    <div className="pipeline-lane-copy">
      <CopyButton value={path} label={`Copy path ${path}`} />
    </div>
  );
}
