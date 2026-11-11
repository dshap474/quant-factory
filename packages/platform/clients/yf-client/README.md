# yf-client

A typed wrapper around [yfinance](https://github.com/ranaroussi/yfinance) with async support, CLI tool, and data export capabilities.

## Terms of use

yfinance reads Yahoo Finance's public website endpoints; it is not an official Yahoo API.
Yahoo's terms (https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) govern that data and
limit it to personal use. Check them before relying on this client, and do not redistribute the data.

## Features

- 🏗️ **Typed API**: Full type hints and Pydantic models for all data structures
- ⚡ **Async Support**: Asynchronous operations using `asyncio` and thread pools
- 🖥️ **CLI Tool**: Command-line interface for quick data retrieval and export
- 📊 **Data Export**: Export to CSV, JSON, and Excel formats
- 🔧 **Highly Configurable**: Environment variable and file-based configuration
- 🧪 **Tests**: Unit tests under `tests/`
- 📚 **Rich Models**: Detailed financial data models with validation

## Installation

```bash
# Part of the uv workspace; from the repository root
uv sync --frozen --group dev
```

### Optional Dependencies

For Excel export support:
```bash
uv sync --frozen --inexact --group dev --package yf-client --extra excel
```

## Quick Start

### Python API

```python
from yf_client import YFinanceClient, AsyncYFinanceClient

# Synchronous usage
client = YFinanceClient()

# Get current quote
quote = client.get_quote("AAPL")
print(f"AAPL: ${quote.price}")

# Get historical data
history = client.get_history("AAPL", period="1mo", interval="1d")
print(f"Data points: {len(history.data)}")

# Get company info
info = client.get_info("AAPL")
print(f"Company: {info.company_name}")

# Asynchronous usage
import asyncio

async def main():
    async with AsyncYFinanceClient() as client:
        quote = await client.get_quote("AAPL")
        quotes = await client.get_multiple_quotes(["AAPL", "GOOGL", "MSFT"])
        print(f"Got {len(quotes.quotes)} quotes")

asyncio.run(main())
```

### CLI Usage

```bash
# From the repository root, the workspace sync installs the CLI
uv sync --frozen --group dev

# Get current quote
uv run yf-client quote AAPL

# Get historical data and export to CSV
yf-client history AAPL --period 1y --interval 1d --export csv

# Get multiple quotes
yf-client multi AAPL GOOGL MSFT --export json

# Get company information
yf-client info AAPL

# Get all data for a symbol
yf-client all TSLA --export csv --output-dir ./tsla_data
```

## API Reference

### YFinanceClient

The main synchronous client class.

#### Methods

- `get_quote(symbol: str) -> Quote`: Get current price quote
- `get_multiple_quotes(symbols: List[str]) -> MultipleQuotes`: Get quotes for multiple symbols
- `get_history(symbol: str, period="1mo", interval="1d", ...) -> HistoricalData`: Get historical price data
- `get_info(symbol: str) -> StockInfo`: Get comprehensive company information

#### Parameters

**get_history parameters:**
- `symbol`: Stock ticker symbol
- `period`: Time period ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max")
- `interval`: Data interval ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo")
- `start`: Start date (YYYY-MM-DD)
- `end`: End date (YYYY-MM-DD)

### AsyncYFinanceClient

Asynchronous version of the client with the same methods.

```python
async with AsyncYFinanceClient() as client:
    # All methods are async
    quote = await client.get_quote("AAPL")
    history = await client.get_history("AAPL", period="1y")
```

### Data Models

#### Quote
```python
Quote(
    symbol="AAPL",
    price=150.25,
    currency="USD",
    timestamp=datetime.now()
)
```

#### OHLCV (Open, High, Low, Close, Volume)
```python
OHLCV(
    date=date(2023, 12, 1),
    open=148.50,
    high=152.00,
    low=147.80,
    close=150.25,
    volume=50000000
)
```

#### StockInfo
```python
StockInfo(
    symbol="AAPL",
    company_name="Apple Inc.",
    sector="Technology",
    industry="Consumer Electronics",
    market_cap=3000000000000,
    pe_ratio=28.5,
    beta=1.2,
    # ... many more fields
)
```

## CLI Commands

### quote
Get current quote for a symbol.

```bash
yf-client quote AAPL
yf-client quote TSLA --export json --output tsla_quote.json
```

### history
Get historical price data.

```bash
# Last month daily data
yf-client history AAPL

# Last year weekly data
yf-client history AAPL --period 1y --interval 1wk

# Custom date range
yf-client history AAPL --start 2023-01-01 --end 2023-12-31

# Export to CSV
yf-client history AAPL --period 6mo --export csv
```

### multi
Get quotes for multiple symbols.

```bash
yf-client multi AAPL GOOGL MSFT
yf-client multi TSLA NVDA AMD --export xlsx
```

### info
Get comprehensive company information.

```bash
yf-client info AAPL
yf-client info TSLA --export json
```

### all
Get all available data for a symbol.

```bash
yf-client all AAPL
yf-client all TSLA --export csv --output-dir ./data
```

## Export Formats

### CSV Export
```python
from yf_client import export_to_csv

export_to_csv(quote, "quote.csv")
export_to_csv(history, "history.csv")
```

### JSON Export
```python
from yf_client import export_to_json

export_to_json(data, "data.json")
```

### Excel Export
```python
from yf_client import export_to_xlsx

export_to_xlsx(data, "data.xlsx")
```

## Configuration

Configure the client via environment variables:

```bash
# Set default period and interval
export YF_DEFAULT_PERIOD="3mo"
export YF_DEFAULT_INTERVAL="1d"

# Set export preferences
export YF_OUTPUT_DIR="./exports"

# Set API settings
export YF_TIMEOUT="60"
```

Or programmatically:

```python
from yf_client.config import settings

settings.default_period = "6mo"
settings.export_format = "csv"
```

## Error Handling

The package provides specific exception types:

```python
from yf_client import YFinanceClient
from yf_client.exceptions import (
    SymbolNotFoundError,
    DataFetchError,
    ExportError,
    ValidationError
)

client = YFinanceClient()

try:
    quote = client.get_quote("INVALID")
except SymbolNotFoundError as e:
    print(f"Symbol not found: {e.symbol}")
except DataFetchError as e:
    print(f"Data fetch failed: {e.message}")
```

## Advanced Usage

### Custom Async Batch Processing

```python
import asyncio
from yf_client import AsyncYFinanceClient

async def process_large_batch():
    symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"] * 20  # 100 symbols

    async with AsyncYFinanceClient(max_workers=10) as client:
        # Process in batches of 10
        quotes = await client.batch_get_quotes(symbols, batch_size=10)
        print(f"Processed {len(quotes.quotes)} quotes")

asyncio.run(process_large_batch())
```

### Custom Data Processing

```python
from yf_client import YFinanceClient
from yf_client.utils import calculate_returns

client = YFinanceClient()
history = client.get_history("AAPL", period="1y")

# Extract closing prices
prices = [ohlcv.close for ohlcv in history.data]

# Calculate returns
returns = calculate_returns(prices)

# Find best/worst performing days
best_day = max((r, i) for i, r in enumerate(returns[1:], 1) if r is not None)
worst_day = min((r, i) for i, r in enumerate(returns[1:], 1) if r is not None)

print(f"Best return: {best_day[0]:.2%} on day {best_day[1]}")
print(f"Worst return: {worst_day[0]:.2%} on day {worst_day[1]}")
```

### Integration with Pandas

```python
import pandas as pd
from yf_client import YFinanceClient

client = YFinanceClient()
history = client.get_history("AAPL", period="1y")

# Convert to DataFrame
df = pd.DataFrame([
    {
        'date': ohlcv.date,
        'open': ohlcv.open,
        'high': ohlcv.high,
        'low': ohlcv.low,
        'close': ohlcv.close,
        'volume': ohlcv.volume
    }
    for ohlcv in history.data
])

df['date'] = pd.to_datetime(df['date'])
df.set_index('date', inplace=True)

# Calculate moving averages
df['MA20'] = df['close'].rolling(window=20).mean()
df['MA50'] = df['close'].rolling(window=50).mean()

print(df.tail())
```

## Development

### Setup Development Environment

```bash
# From the repository root
uv sync --frozen --group dev
```

### Running Tests

```bash
# From this package directory
# Run the offline suite (integration tests are skipped by default)
uv run pytest
# Include the integration tests, which call Yahoo Finance
YF_CLIENT_INTEGRATION=1 uv run pytest

# Run with coverage
uv run pytest --cov=yf_client --cov-report=html

# Run specific test file
uv run pytest tests/test_api.py

# Run tests matching pattern
uv run pytest -k "test_quote"
```

### Code Quality

```bash
uv run ruff check packages/platform/clients/yf-client
uv run ruff format packages/platform/clients/yf-client
```

See the repository root `CONTRIBUTING.md` to contribute.

## Acknowledgments

- [yfinance](https://github.com/ranaroussi/yfinance) - The underlying Yahoo Finance data library
- [Pydantic](https://pydantic-docs.helpmanual.io/) - Data validation and parsing
- [Click](https://click.palletsprojects.com/) - Command-line interface framework
- [pandas](https://pandas.pydata.org/) - Data manipulation and analysis
