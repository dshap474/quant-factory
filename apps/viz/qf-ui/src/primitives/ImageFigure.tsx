/** Responsive image figure with intrinsic dimensions for stable page layout.
 * USAGE: <ImageFigure src={diagram} alt="Information flow" width={1672} height={941} />
 */
// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #
import './ImageFigure.css';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #
export function ImageFigure({
  src,
  alt,
  width,
  height,
  fit = 'width',
}: {
  src: string;
  alt: string;
  width: number;
  height: number;
  /** Use natural size inside a ScrollArea when diagram labels need magnification. */
  fit?: 'width' | 'natural';
}) {
  return (
    <figure className="ui-image-figure" data-fit={fit}>
      <img src={src} alt={alt} width={width} height={height} decoding="async" />
    </figure>
  );
}
