"""Typer CLI for backtests.

Purpose: parse filesystem/process inputs, call package-owned backtest services,
and emit stable JSON success or failure payloads.

USAGE:
    $ qf-backtest run prices.parquet weights.parquet
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl
import typer

from .api import run_backtest
from .config import BacktestConfig

# --------------------------------------------------------------------------- #
# Application and output
# --------------------------------------------------------------------------- #

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Backtest commands.",
)


@app.callback()
def _root() -> None:
    """Keep ``run`` as an explicit subcommand even when it is the only command."""


def _emit(payload: dict[str, Any], *, pretty: bool) -> None:
    if pretty:
        typer.echo(json.dumps(payload, indent=2, default=str))
    else:
        typer.echo(json.dumps(payload, default=str))


# --------------------------------------------------------------------------- #
# Legacy run command
# --------------------------------------------------------------------------- #


@app.command("run")
def run_command(
    prices: Path = typer.Argument(..., exists=True, help="Parquet file with prices."),
    weights: Path = typer.Argument(..., exists=True, help="Parquet file with weights."),
    funding_rates: Path | None = typer.Option(
        None, "--funding-rates", exists=True, help="Optional parquet file with funding rates."
    ),
    trade_cost_bps: float = typer.Option(5.0, "--trade-cost-bps"),
    include_funding: bool = typer.Option(True, "--include-funding/--no-include-funding"),
    frequency: str = typer.Option("daily", "--frequency"),
    benchmark: str | None = typer.Option(None, "--benchmark"),
    engine: str = typer.Option(
        "nautilus",
        "--engine",
        help="Engine selector: 'nautilus' (default) or 'ledger' ordinary portfolio book.",
    ),
    random_seed: int = typer.Option(42, "--random-seed"),
    initial_capital: float = typer.Option(100_000.0, "--initial-capital"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional JSON output path."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print output."),
) -> None:
    """Run backtest from parquet inputs."""
    try:
        prices_df = pl.read_parquet(prices)
        weights_df = pl.read_parquet(weights)
        funding_df = pl.read_parquet(funding_rates) if funding_rates else None

        config = BacktestConfig(
            trade_cost_bps=trade_cost_bps,
            include_funding=include_funding,
            frequency=frequency,
            benchmark=benchmark,
            engine=engine,
            random_seed=random_seed,
            initial_capital=initial_capital,
        )

        result = run_backtest(
            prices=prices_df,
            weights=weights_df,
            funding_rates=funding_df,
            config=config,
        )

        payload = {
            "status": "ok",
            "metrics": result.metrics,
            "rows": len(result.equity),
            "engine_used": result.engine_used,
            "engine_meta": result.engine_meta,
        }

        if output:
            output.write_text(json.dumps(payload, indent=2, default=str))

        _emit(payload, pretty=pretty)

    except Exception as exc:
        payload = {"status": "error", "code": "backtest_run_failed", "message": str(exc)}
        _emit(payload, pretty=False)
        raise typer.Exit(code=1) from exc


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
