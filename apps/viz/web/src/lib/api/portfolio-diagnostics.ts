/**
 * Validated, cancellable reads of explicitly selected portfolio diagnostics.
 * USAGE: usePortfolioDiagnostics(family, version, runId, account);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { requestParsed } from './client';

// --------------------------------------------------------------------------- #
// Boundary schemas
// --------------------------------------------------------------------------- #

const finite = z.number().finite();
const timestamp = z.iso
  .datetime({ offset: true })
  .transform((value) => new Date(value).toISOString());
const peakSchema = z.object({
  scenario: z.enum(['observed', 'daily_wick_stress']),
  basis: z.enum(['initial', 'maintenance']),
  rate: finite,
  peak_reserve: finite,
  capital_to_supply: finite,
  peak_at: z.string().nullable(),
});
const datasetSchema = z.object({
  path: z.string(),
  columns: z.array(z.string()),
  rows: z.number().int().max(1_000_000),
});
const metadataSchema = z.object({
  available: z.boolean(),
  report: z
    .object({
      selection: z.object({
        strategy_type: z.string(),
        memory_version: z.string(),
        source_run_id: z.string(),
        source_account: z.string(),
        attempt_id: z.string(),
      }),
      summary: z.object({
        status: z.literal('complete'),
        conventions: z.object({
          initial_equity: finite.positive(),
          retained_profit: z.string(),
          scaling: z.string(),
        }),
        capital: z.object({ headline: z.array(peakSchema) }),
        risk: z.object({ realized_price_vol: finite.nullable() }),
        coverage: z.object({
          days: finite,
          days_with_predicted_risk: finite,
          points_without_snapshot: finite,
        }),
        labels: z.array(z.string()),
      }),
      datasets: z.object({
        capital: datasetSchema,
        exposure: datasetSchema,
        attribution: datasetSchema,
        rolling_btc: datasetSchema,
      }),
    })
    .nullable(),
});
const exposureRow = z.object({
  timestamp,
  point: z.string(),
  btc_exposure: finite.nullable(),
  drift_since_fill: finite.nullable(),
  long_exposure: finite.nullable(),
  short_exposure: finite.nullable(),
  gross_leverage: finite.nullable(),
  net_exposure: finite.nullable(),
  predicted_total_vol: finite.nullable(),
});
const attributionRow = z.object({
  timestamp,
  btc_factor_pnl: finite.nullable(),
  residual_price_pnl: finite.nullable(),
  unmodeled_price_pnl: finite.nullable(),
  funding: finite.nullable(),
  fees: finite.nullable(),
  net_pnl: finite.nullable(),
});
const rollingRow = z.object({
  timestamp,
  window: finite,
  beta: finite.nullable(),
  beta_ci95_low: finite.nullable(),
  beta_ci95_high: finite.nullable(),
});
const capitalRow = z.object({
  timestamp,
  scenario: z.string(),
  basis: z.string(),
  rate: finite,
  reserve_needed: finite.nullable(),
  backing_multiple: finite.nullable(),
  cushion: finite.nullable(),
});

// --------------------------------------------------------------------------- #
// Queries
// --------------------------------------------------------------------------- #

export function usePortfolioDiagnostics(
  family: string,
  version: string,
  runId: string | null,
  account: string | null,
) {
  const params = new URLSearchParams();
  if (runId) params.set('run_id', runId);
  if (account) params.set('account', account);
  const path = `/api/portfolio-diagnostics/${encodeURIComponent(family)}/${encodeURIComponent(version)}`;
  const key = ['portfolio-diagnostics', family, version, runId, account];
  const metadata = useQuery({
    queryKey: key,
    enabled: Boolean(runId),
    queryFn: ({ signal }) => requestParsed(`${path}?${params}`, metadataSchema, { signal }),
    retry: false,
  });
  const report = metadata.data?.report;
  const evidence = useQuery({
    queryKey: [...key, 'evidence', report?.selection.attempt_id],
    enabled: Boolean(report),
    retry: false,
    queryFn: async ({ signal }) => {
      if (!report) throw new Error('Diagnostics selection is unavailable');
      const read = <Schema extends z.ZodType>(
        dataset: z.infer<typeof datasetSchema>,
        row: Schema,
      ) => {
        const query = new URLSearchParams({
          columns: dataset.columns.join(','),
          limit: '20000',
          order_by: 'timestamp',
        });
        return requestParsed(
          `/api/datasets/research/query/${dataset.path}?${query}`,
          z
            .object({
              data: z.array(row).max(20_000),
              returned_rows: z.number().int(),
              total_rows: z.number().int(),
            })
            .refine(
              (value) =>
                value.data.length === dataset.rows &&
                value.returned_rows === dataset.rows &&
                value.total_rows === dataset.rows,
              'Diagnostics evidence is truncated or changed',
            )
            .transform((value) => ({ rows: value.data })),
          { signal },
        );
      };
      const [capital, exposure, attribution, rolling] = await Promise.all([
        requestParsed(
          `${path}/capital?${params}&attempt_id=${encodeURIComponent(report.selection.attempt_id)}`,
          z.object({ rows: z.array(capitalRow).max(20_000) }),
          { signal },
        ),
        read(report.datasets.exposure, exposureRow),
        read(report.datasets.attribution, attributionRow),
        read(report.datasets.rolling_btc, rollingRow),
      ]);
      return {
        capital: capital.rows,
        exposure: exposure.rows,
        attribution: attribution.rows,
        rolling: rolling.rows,
      };
    },
  });
  return { metadata, evidence };
}
