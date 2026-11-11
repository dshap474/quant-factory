"""
Command-line interface for yf-client.
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional

import click

try:
    from tqdm import tqdm
except ImportError:
    # Fallback progress bar implementation
    class tqdm:
        def __init__(self, length=None, label=""):
            self.length = length
            self.label = label
            if label:
                click.echo(f"{label}...")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def update(self, n=1):
            pass


from .api import YFinanceClient
from .config import settings
from .exceptions import YFinanceClientError
from .exporters import export_to_csv, export_to_json, export_to_xlsx
from .utils import format_number, format_percentage

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.verbose else logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def setup_client() -> YFinanceClient:
    """Create and configure YFinance client."""
    return YFinanceClient()


def handle_export(
    data, export_format: Optional[str] = None, output: Optional[str] = None
) -> None:
    """
    Handle data export based on format and output options.

    Args:
        data: Data to export
        export_format: Export format (json, csv, xlsx)
        output: Output file path
    """
    if not export_format:
        return

    try:
        if export_format == "json":
            filepath = export_to_json(data, output)
        elif export_format == "csv":
            filepath = export_to_csv(data, output)
        elif export_format == "xlsx":
            filepath = export_to_xlsx(data, output)
        else:
            click.echo(f"Error: Unsupported export format '{export_format}'", err=True)
            return

        click.echo(f"✓ Exported data to: {filepath}")

    except Exception as e:
        click.echo(f"Error: Export failed - {str(e)}", err=True)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True),
    help="Path to configuration file",
)
@click.version_option(version="0.2.0")
def cli(verbose: bool, config_file: Optional[str]):
    """
    yf-client - A typed wrapper around yfinance with CLI support.

    Get stock quotes, historical data, and company information from Yahoo Finance.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if config_file:
        # TODO: Load custom config file if implemented
        click.echo(
            f"Note: Custom config file support not yet implemented: {config_file}"
        )


@cli.command()
@click.argument("symbol")
@click.option(
    "--export", type=click.Choice(["json", "csv", "xlsx"]), help="Export format"
)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def quote(symbol: str, export: Optional[str], output: Optional[str]):
    """
    Get current quote for a stock symbol.

    SYMBOL: Stock ticker symbol (e.g., AAPL, GOOGL, MSFT)

    Examples:
        yf-client quote AAPL
        yf-client quote TSLA --export json --output tsla_quote.json
    """
    client = setup_client()

    try:
        with click.progressbar(length=1, label=f"Fetching quote for {symbol}") as bar:
            quote_data = client.get_quote(symbol)
            bar.update(1)

        # Display quote information
        click.echo(f"\n📈 {symbol} Quote")
        click.echo(f"{'─' * (len(symbol) + 8)}")
        click.echo(f"Price:    ${format_number(quote_data.price)}")
        click.echo(f"Currency: {quote_data.currency}")
        click.echo(f"Time:     {quote_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

        # Handle export
        if export:
            handle_export(quote_data, export, output)

    except YFinanceClientError as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("symbol")
@click.option(
    "--period",
    "-p",
    type=click.Choice(settings.valid_periods),
    default=settings.default_period,
    help="Time period for historical data",
)
@click.option(
    "--interval",
    "-i",
    type=click.Choice(settings.valid_intervals),
    default=settings.default_interval,
    help="Data interval",
)
@click.option(
    "--export", type=click.Choice(["json", "csv", "xlsx"]), help="Export format"
)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--start", help="Start date (YYYY-MM-DD)")
@click.option("--end", help="End date (YYYY-MM-DD)")
def history(
    symbol: str,
    period: str,
    interval: str,
    export: Optional[str],
    output: Optional[str],
    start: Optional[str],
    end: Optional[str],
):
    """
    Get historical price data for a stock symbol.

    SYMBOL: Stock ticker symbol (e.g., AAPL, GOOGL, MSFT)

    Examples:
        yf-client history AAPL --period 1y --interval 1d
        yf-client history TSLA --period 3mo --export csv --output tsla_history.csv
        yf-client history GOOGL --start 2023-01-01 --end 2023-12-31 --export xlsx
    """
    client = setup_client()

    try:
        click.echo(f"Fetching historical data for {symbol}...")
        click.echo(f"Period: {period}, Interval: {interval}")

        historical_data = client.get_history(
            symbol=symbol, period=period, interval=interval, start=start, end=end
        )

        # Display summary
        click.echo(f"\n📊 {symbol} Historical Data")
        click.echo(f"{'─' * (len(symbol) + 18)}")
        click.echo(f"Data points: {len(historical_data.data)}")
        click.echo(f"Period:      {historical_data.period}")
        click.echo(f"Interval:    {historical_data.interval}")

        if historical_data.data:
            first_date = historical_data.data[0].date
            last_date = historical_data.data[-1].date
            click.echo(f"Date range:  {first_date} to {last_date}")

            # Show latest data point
            latest = historical_data.data[-1]
            click.echo(f"\nLatest data point:")
            click.echo(f"Date:   {latest.date}")
            click.echo(f"Open:   ${format_number(latest.open)}")
            click.echo(f"High:   ${format_number(latest.high)}")
            click.echo(f"Low:    ${format_number(latest.low)}")
            click.echo(f"Close:  ${format_number(latest.close)}")
            click.echo(f"Volume: {format_number(latest.volume, 0)}")

        # Handle export
        if export:
            handle_export(historical_data, export, output)

    except YFinanceClientError as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("symbol")
@click.option(
    "--export", type=click.Choice(["json", "csv", "xlsx"]), help="Export format"
)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def info(symbol: str, export: Optional[str], output: Optional[str]):
    """
    Get comprehensive information about a stock.

    SYMBOL: Stock ticker symbol (e.g., AAPL, GOOGL, MSFT)

    Examples:
        yf-client info AAPL
        yf-client info TSLA --export json --output tsla_info.json
    """
    client = setup_client()

    try:
        with click.progressbar(length=1, label=f"Fetching info for {symbol}") as bar:
            stock_info = client.get_info(symbol)
            bar.update(1)

        # Display company information
        click.echo(f"\n🏢 {stock_info.symbol} Information")
        click.echo(f"{'─' * (len(stock_info.symbol) + 14)}")

        if stock_info.company_name:
            click.echo(f"Company:     {stock_info.company_name}")

        if stock_info.sector:
            click.echo(f"Sector:      {stock_info.sector}")

        if stock_info.industry:
            click.echo(f"Industry:    {stock_info.industry}")

        if stock_info.market_cap:
            click.echo(f"Market Cap:  ${format_number(stock_info.market_cap, 0)}")

        if stock_info.pe_ratio:
            click.echo(f"P/E Ratio:   {format_number(stock_info.pe_ratio, 2)}")

        if stock_info.dividend_yield:
            click.echo(f"Dividend:    {format_percentage(stock_info.dividend_yield)}")

        if stock_info.beta:
            click.echo(f"Beta:        {format_number(stock_info.beta, 2)}")

        if stock_info.fifty_two_week_high and stock_info.fifty_two_week_low:
            click.echo(
                f"52W Range:   ${format_number(stock_info.fifty_two_week_low)} - ${format_number(stock_info.fifty_two_week_high)}"
            )

        if stock_info.average_volume:
            click.echo(f"Avg Volume:  {format_number(stock_info.average_volume, 0)}")

        if stock_info.currency:
            click.echo(f"Currency:    {stock_info.currency}")

        if stock_info.exchange:
            click.echo(f"Exchange:    {stock_info.exchange}")

        if stock_info.country:
            click.echo(f"Country:     {stock_info.country}")

        # Handle export
        if export:
            handle_export(stock_info, export, output)

    except YFinanceClientError as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("symbols", nargs=-1, required=True)
@click.option(
    "--export", type=click.Choice(["json", "csv", "xlsx"]), help="Export format"
)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option(
    "--batch-size", type=int, default=10, help="Number of symbols to process per batch"
)
def multi(
    symbols: List[str], export: Optional[str], output: Optional[str], batch_size: int
):
    """
    Get quotes for multiple stock symbols.

    SYMBOLS: Stock ticker symbols (e.g., AAPL GOOGL MSFT)

    Examples:
        yf-client multi AAPL GOOGL MSFT
        yf-client multi TSLA NVDA AMD --export csv --output tech_stocks.csv
    """
    if not symbols:
        click.echo("Error: No symbols provided", err=True)
        sys.exit(1)

    client = setup_client()

    try:
        click.echo(f"Fetching quotes for {len(symbols)} symbols...")

        # Use async client for multiple symbols to improve performance
        import asyncio
        from .api import AsyncYFinanceClient

        async def fetch_quotes():
            async with AsyncYFinanceClient() as async_client:
                return await async_client.batch_get_quotes(list(symbols), batch_size)

        # Run async fetch
        quotes_data = asyncio.run(fetch_quotes())

        # Display results
        click.echo(f"\n📊 Multiple Quotes ({len(quotes_data.quotes)} symbols)")
        click.echo(f"{'─' * 25}")

        for quote in quotes_data.quotes:
            click.echo(
                f"{quote.symbol:8} ${format_number(quote.price):10} {quote.currency:4} {quote.timestamp.strftime('%H:%M:%S')}"
            )

        # Handle export
        if export:
            handle_export(quotes_data, export, output)

    except YFinanceClientError as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--export",
    type=click.Choice(["json", "csv", "xlsx"]),
    help="Export format for all data",
)
@click.option("--output-dir", type=click.Path(), help="Output directory for exports")
@click.argument("symbol")
def all(symbol: str, export: Optional[str], output_dir: Optional[str]):
    """
    Get all available data for a stock symbol (quote, info, and history).

    SYMBOL: Stock ticker symbol (e.g., AAPL, GOOGL, MSFT)

    Examples:
        yf-client all AAPL
        yf-client all TSLA --export json --output-dir ./tsla_data
    """
    client = setup_client()
    output_path = Path(output_dir) if output_dir else None

    try:
        click.echo(f"Fetching all data for {symbol}...")

        # Fetch all data types
        with click.progressbar(length=3, label="Fetching data") as bar:
            quote_data = client.get_quote(symbol)
            bar.update(1)

            stock_info = client.get_info(symbol)
            bar.update(1)

            historical_data = client.get_history(symbol)
            bar.update(1)

        # Display summary
        click.echo(f"\n📈 Complete {symbol} Data")
        click.echo(f"{'─' * (len(symbol) + 18)}")

        click.echo(f"Current Price: ${format_number(quote_data.price)}")
        click.echo(f"Company:       {stock_info.company_name or 'N/A'}")
        click.echo(f"Sector:        {stock_info.sector or 'N/A'}")
        click.echo(f"Data Points:   {len(historical_data.data)}")

        # Export all data if requested
        if export:
            base_path = output_path or settings.output_dir

            # Export quote
            quote_file = base_path / f"{symbol}_quote.{export}"
            handle_export(quote_data, export, str(quote_file))

            # Export info
            info_file = base_path / f"{symbol}_info.{export}"
            handle_export(stock_info, export, str(info_file))

            # Export history
            history_file = base_path / f"{symbol}_history.{export}"
            handle_export(historical_data, export, str(history_file))

    except YFinanceClientError as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}", err=True)
        sys.exit(1)


# ┌────────────────────────────────────────────────────────────────────────────────────┐
# │ Additional Commands                                                                  
# └────────────────────────────────────────────────────────────────────────────────────┘

@cli.command("fast-info")
@click.argument("symbol")
@click.option("--export", type=click.Choice(["json"]))
@click.option("--output", "output", type=click.Path())
def fast_info(symbol: str, export: Optional[str], output: Optional[str]):
    """Get lightweight real-time fields for a symbol."""
    client = setup_client()
    try:
        data = client.get_fast_info(symbol)
        click.echo(data)
        if export:
            handle_export(data, export, output)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("tickers", nargs=-1, required=True)
@click.option("--period", type=click.Choice(settings.valid_periods))
@click.option("--interval", type=click.Choice(settings.valid_intervals))
@click.option("--start")
@click.option("--end")
@click.option("--export", type=click.Choice(["json", "csv", "xlsx"]))
@click.option("--output", type=click.Path())
def download(tickers: List[str], period: Optional[str], interval: Optional[str], start: Optional[str], end: Optional[str], export: Optional[str], output: Optional[str]):
    """Bulk historical data for one or more tickers."""
    client = setup_client()
    try:
        data = client.download(list(tickers) if len(tickers) > 1 else tickers[0], period=period, interval=interval, start=start, end=end)
        click.echo({k: len(v) for k, v in data.items()})
        if export:
            handle_export(data, export, output)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("symbol")
def options(symbol: str):
    """List option expiration dates for a symbol."""
    client = setup_client()
    try:
        dates = client.get_options(symbol)
        for d in dates:
            click.echo(d)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("option-chain")
@click.argument("symbol")
@click.option("--date", required=True, help="Expiration date YYYY-MM-DD")
@click.option("--export", type=click.Choice(["json"]))
@click.option("--output", type=click.Path())
def option_chain(symbol: str, date: str, export: Optional[str], output: Optional[str]):
    """Fetch option chain for an expiration date."""
    client = setup_client()
    try:
        chain = client.get_option_chain(symbol, date)
        click.echo({k: len(v) for k, v in chain.items()})
        if export:
            handle_export(chain, export, output)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("symbol")
def actions(symbol: str):
    """List corporate actions (dividends, splits)."""
    client = setup_client()
    try:
        items = client.get_actions(symbol)
        for item in items:
            click.echo(item)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("symbol")
def dividends(symbol: str):
    """List dividends."""
    client = setup_client()
    try:
        items = client.get_dividends(symbol)
        for item in items:
            click.echo(item)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("symbol")
def splits(symbol: str):
    """List splits."""
    client = setup_client()
    try:
        items = client.get_splits(symbol)
        for item in items:
            click.echo(item)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("financials")
@click.argument("symbol")
@click.option("--quarterly", is_flag=True)
@click.option("--ttm", is_flag=True)
def financials_cmd(symbol: str, quarterly: bool, ttm: bool):
    """Show financial statements (annual, quarterly, or TTM)."""
    client = setup_client()
    try:
        if ttm:
            data = client.get_financials_ttm(symbol)
        elif quarterly:
            data = client.get_financials_quarterly(symbol)
        else:
            data = client.get_financials(symbol)
        click.echo(data)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("balance-sheet")
@click.argument("symbol")
@click.option("--quarterly", is_flag=True)
def balance_sheet_cmd(symbol: str, quarterly: bool):
    client = setup_client()
    try:
        data = client.get_balance_sheet(symbol, quarterly=quarterly)
        click.echo(data)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("cashflow")
@click.argument("symbol")
@click.option("--quarterly", is_flag=True)
def cashflow_cmd(symbol: str, quarterly: bool):
    client = setup_client()
    try:
        data = client.get_cashflow(symbol, quarterly=quarterly)
        click.echo(data)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("symbol")
def holders(symbol: str):
    client = setup_client()
    try:
        data = client.get_holders(symbol)
        click.echo(data)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("symbol")
def analyst(symbol: str):
    client = setup_client()
    try:
        data = client.get_analyst(symbol)
        click.echo(data)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("symbol")
def news(symbol: str):
    client = setup_client()
    try:
        items = client.get_news(symbol)
        for item in items:
            click.echo(item)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("query")
@click.option("--max-results", type=int, default=10)
@click.option("--news-count", type=int, default=10)
def search(query: str, max_results: int, news_count: int):
    client = setup_client()
    try:
        data = client.search(query, max_results=max_results, news_count=news_count)
        click.echo(data)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("query")
def lookup(query: str):
    client = setup_client()
    try:
        data = client.lookup(query)
        click.echo(data)
    except YFinanceClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def main():
    """Main entry point for the CLI."""
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\nOperation cancelled by user", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
