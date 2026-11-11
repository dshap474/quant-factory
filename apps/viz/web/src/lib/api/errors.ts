/**
 * Typed API error for expected HTTP / parse failures.
 *
 * USAGE:
 *   throw new ApiError('Not found', 404);
 *   catch (e) { if (e instanceof ApiError) ... }
 */

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(detail: string, status = 500) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

export function detailFromUnknown(payload: unknown, fallback: string): string {
  if (typeof payload === 'string' && payload.length > 0) {
    return payload;
  }
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === 'string' && detail.length > 0) {
      return detail;
    }
    // FastAPI 422: detail is ValidationError[] with loc + msg.
    if (Array.isArray(detail) && detail.length > 0) {
      const parts = detail.map((item) => {
        if (!item || typeof item !== 'object') return String(item);
        const row = item as { loc?: unknown; msg?: unknown };
        const loc = Array.isArray(row.loc)
          ? row.loc.filter((p) => p !== 'body' && p !== 'query').join('.')
          : '';
        const msg = typeof row.msg === 'string' ? row.msg : 'invalid';
        return loc ? `${loc}: ${msg}` : msg;
      });
      return parts.join('; ');
    }
  }
  return fallback;
}
