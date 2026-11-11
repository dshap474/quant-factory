# yf-client API Documentation

## Overview

The yf-client package provides two main API classes for accessing Yahoo Finance data:

- [`YFinanceClient`](#yfinanceclient) - Synchronous API client
- [`AsyncYFinanceClient`](#asyncyfinanceclient) - Asynchronous API client

Both clients provide the same functionality but with different execution models to suit different use cases.

## YFinanceClient

Synchronous client for Yahoo Finance data retrieval. Best for simple scripts and single-threaded applications.

### Constructor

```python
YFinanceClient(user_agent: Optional[str] = None)
```

**Parameters:**
- `user_agent` (Optional[str]): Custom user agent string for requests

### Methods

#### get_quote(symbol: str) -> Quote

Get current quote information for a stock symbol.

**Parameters:**
- `symbol` (str): Stock ticker symbol (e.g., "AAPL", "GOOGL")

**Returns:**
- `Quote`: Current quote data

**Raises:**
- `SymbolNotFoundError`: If the symbol is not found
- `DataFetchError`: If data retrieval fails

**Example:**
```python
from yf_client import YFinanceClient

client = YFinanceClient()
quote = client.get_quote("AAPL")

print(f"{quote.symbol}: ${quote.price}")
print(f"Currency: {quote.currency}")
print(f"Timestamp: {quote.timestamp}")
```

#### get_multiple_quotes(symbols: List[str]) -> MultipleQuotes

Get current quotes for multiple stock symbols.

**Parameters:**
- `symbols` (List[str]): List of stock ticker symbols

**Returns:**
- `MultipleQuotes`: Collection of quote data

**Raises:**
- `ValidationError`: If symbols list is invalid
- `DataFetchError`: If data retrieval fails

**Example:**
```python
symbols = ["AAPL", "GOOGL", "MSFT", "TSLA"]
quotes = client.get_multiple_quotes(symbols)

for quote in quotes.quotes:
    print(f"{quote.symbol}: ${quote.price}")
```

#### get_history(symbol: str, period: str = "1mo", interval: str = "1d", start: Optional[str] = None, end: Optional[str] = None) -> HistoricalData

Get historical price data for a stock symbol.

**Parameters:**
- `symbol` (str): Stock ticker symbol
- `period` (str): Time period for data ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max")
- `interval` (str): Data interval ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo")
- `start` (Optional[str]): Start date in YYYY-MM-DD format
- `end` (Optional[str]): End date in YYYY-MM-DD format

**Returns:**
- `HistoricalData`: Historical price data with OHLCV records

**Raises:**
- `SymbolNotFoundError`: If the symbol is not found
- `InvalidPeriodError`: If the period is invalid
- `InvalidIntervalError`: If the interval is invalid
- `DataFetchError`: If data retrieval fails

**Example:**
```python
# Get last year's daily data
history = client.get_history("AAPL", period="1y", interval="1d")

print(f"Symbol: {history.symbol}")
print(f"Data points: {len(history.data)}")
print(f"Period: {history.period}")
print(f"Interval: {history.interval}")

# Access individual data points
for ohlcv in history.data[-5:]:  # Last 5 days
    print(f"{ohlcv.date}: O={ohlcv.open}, H={ohlcv.high}, L={ohlcv.low}, C={ohlcv.close}, V={ohlcv.volume}")
```

#### get_info(symbol: str) -> StockInfo

Get comprehensive information about a company.

**Parameters:**
- `symbol` (str): Stock ticker symbol

**Returns:**
- `StockInfo`: Detailed company information

**Raises:**
- `SymbolNotFoundError`: If the symbol is not found
- `DataFetchError`: If data retrieval fails

**Example:**
```python
info = client.get_info("AAPL")

print(f"Company: {info.company_name}")
print(f"Sector: {info.sector}")
print(f"Industry: {info.industry}")
print(f"Market Cap: ${info.market_cap:,.0f}")
print(f"P/E Ratio: {info.pe_ratio}")
print(f"Dividend Yield: {info.dividend_yield:.2%}")
```

#### clear_cache()

Clear the internal ticker cache. Useful for memory management in long-running applications.

**Example:**
```python
client.clear_cache()
```

## AsyncYFinanceClient

Asynchronous client for Yahoo Finance data retrieval. Best for web applications, concurrent operations, and high-throughput scenarios.

### Constructor

```python
AsyncYFinanceClient(user_agent: Optional[str] = None, max_workers: int = 4)
```

**Parameters:**
- `user_agent` (Optional[str]): Custom user agent string for requests
- `max_workers` (int): Maximum number of thread pool workers (default: 4)

### Context Manager Usage

The async client should be used as a context manager for proper resource cleanup:

```python
async with AsyncYFinanceClient() as client:
    quote = await client.get_quote("AAPL")
```

### Methods

All methods are asynchronous versions of the synchronous client methods:

#### async get_quote(symbol: str) -> Quote

#### async get_multiple_quotes(symbols: List[str]) -> MultipleQuotes

#### async get_history(symbol: str, period: str = "1mo", interval: str = "1d", start: Optional[str] = None, end: Optional[str] = None) -> HistoricalData

#### async get_info(symbol: str) -> StockInfo

**Examples:**
```python
import asyncio
from yf_client import AsyncYFinanceClient

async def main():
    async with AsyncYFinanceClient() as client:
        # Get single quote
        quote = await client.get_quote("AAPL")

        # Get multiple quotes concurrently
        symbols = ["AAPL", "GOOGL", "MSFT", "TSLA"]
        quotes = await client.get_multiple_quotes(symbols)

        # Get historical data
        history = await client.get_history("AAPL", period="1y")

asyncio.run(main())
```

#### async batch_get_quotes(symbols: List[str], batch_size: int = 10) -> MultipleQuotes

Get quotes for multiple symbols in batches to avoid overwhelming the API.

**Parameters:**
- `symbols` (List[str]): List of stock ticker symbols
- `batch_size` (int): Number of symbols to process per batch

**Example:**
```python
# Process 100 symbols in batches of 10
large_symbol_list = ["AAPL", "GOOGL", "MSFT"] * 33 + ["TSLA"]  # 100 symbols

async with AsyncYFinanceClient() as client:
    quotes = await client.batch_get_quotes(large_symbol_list, batch_size=10)
    print(f"Retrieved {len(quotes.quotes)} quotes")
```

## Data Models

### Quote

Represents current quote information.

**Attributes:**
- `symbol` (str): Stock ticker symbol
- `price` (float): Current price
- `currency` (str): Currency code (e.g., "USD")
- `timestamp` (datetime): Quote timestamp

### OHLCV

Represents Open, High, Low, Close, Volume data for a specific date.

**Attributes:**
- `date` (date): Trading date
- `open` (float): Opening price
- `high` (float): Highest price
- `low` (float): Lowest price
- `close` (float): Closing price
- `volume` (int): Trading volume

### StockInfo

Comprehensive company information.

**Attributes:**
- `symbol` (str): Stock ticker symbol
- `company_name` (Optional[str]): Full company name
- `sector` (Optional[str]): Industry sector
- `industry` (Optional[str]): Specific industry
- `market_cap` (Optional[float]): Market capitalization
- `pe_ratio` (Optional[float]): Price-to-earnings ratio
- `pb_ratio` (Optional[float]): Price-to-book ratio
- `dividend_yield` (Optional[float]): Dividend yield percentage
- `beta` (Optional[float]): Beta coefficient
- `fifty_two_week_high` (Optional[float]): 52-week high price
- `fifty_two_week_low` (Optional[float]): 52-week low price
- `average_volume` (Optional[int]): Average trading volume
- `currency` (Optional[str]): Trading currency
- `exchange` (Optional[str]): Stock exchange
- `country` (Optional[str]): Company headquarters country

### HistoricalData

Time series data with metadata.

**Attributes:**
- `symbol` (str): Stock ticker symbol
- `data` (List[OHLCV]): List of OHLCV data points
- `period` (str): Time period requested
- `interval` (str): Data interval requested

**Methods:**
- `__len__()`: Return number of data points
- `is_empty()`: Check if data is empty

### MultipleQuotes

Collection of quote data for multiple symbols.

**Attributes:**
- `quotes` (List[Quote]): List of quote data
- `timestamp` (datetime): Request timestamp

**Methods:**
- `__len__()`: Return number of quotes
- `is_empty()`: Check if quotes list is empty
- `get_quote(symbol: str)`: Get quote for specific symbol

## Error Handling

### Exception Hierarchy

```python
from yf_client.exceptions import (
    YFinanceClientError,      # Base exception
    SymbolNotFoundError,      # Symbol not found/invalid
    DataFetchError,          # Network/API errors
    ExportError,             # Export failures
    ValidationError,         # Input validation errors
    ConfigurationError,      # Configuration errors
    RateLimitError,          # Rate limiting
    NetworkError,            # Network issues
    InvalidPeriodError,      # Invalid time periods
    InvalidIntervalError,    # Invalid data intervals
)
```

### Exception Handling Patterns

```python
from yf_client import YFinanceClient
from yf_client.exceptions import SymbolNotFoundError, DataFetchError, ValidationError

client = YFinanceClient()

try:
    quote = client.get_quote("AAPL")
except SymbolNotFoundError as e:
    print(f"Symbol '{e.symbol}' not found")
except DataFetchError as e:
    print(f"Failed to fetch data: {e.message}")
    if hasattr(e, 'original_error'):
        print(f"Original error: {e.original_error}")
except ValidationError as e:
    print(f"Validation error: {e.message}")
```

### Async Error Handling

```python
import asyncio
from yf_client import AsyncYFinanceClient
from yf_client.exceptions import YFinanceClientError

async def safe_get_quote(symbol: str):
    async with AsyncYFinanceClient() as client:
        try:
            return await client.get_quote(symbol)
        except YFinanceClientError as e:
            print(f"Error fetching {symbol}: {e}")
            return None

asyncio.run(safe_get_quote("AAPL"))
```

## Configuration

### Global Settings

```python
from yf_client.config import settings

# View current settings
print(f"Default period: {settings.default_period}")
print(f"Default interval: {settings.default_interval}")
print(f"Export format: {settings.export_format}")

# Modify settings
settings.default_period = "6mo"
settings.timeout = 60
settings.max_retries = 5
```

### Environment Variables

```bash
# Set via environment variables
export YF_DEFAULT_PERIOD="3mo"
export YF_DEFAULT_INTERVAL="1d"
export YF_TIMEOUT="30"
export YF_OUTPUT_DIR="./exports"
```

### Client-Specific Configuration

```python
# Custom user agent
client = YFinanceClient(user_agent="MyApp/1.0")

# Custom async settings
async_client = AsyncYFinanceClient(max_workers=8)
```

## Performance Considerations

### Synchronous vs Asynchronous

**Use Synchronous Client When:**
- Simple scripts with few requests
- Sequential operations
- Single-threaded applications
- Quick prototyping

**Use Asynchronous Client When:**
- Web applications
- Processing multiple symbols concurrently
- High-throughput requirements
- Integration with async frameworks

### Memory Management

```python
# Clear cache periodically in long-running apps
client.clear_cache()

# Use context managers for async clients
async with AsyncYFinanceClient() as client:
    # Client resources automatically cleaned up
    pass
```

### Batch Processing

```python
# Process large symbol lists efficiently
symbols = ["AAPL", "GOOGL", "MSFT", "TSLA"] * 25  # 100 symbols

async with AsyncYFinanceClient(max_workers=10) as client:
    quotes = await client.batch_get_quotes(symbols, batch_size=10)
```

## Best Practices

### Error Handling

```python
def safe_get_data(symbol: str):
    """Safely retrieve data with proper error handling."""
    client = YFinanceClient()

    try:
        quote = client.get_quote(symbol)
        history = client.get_history(symbol, period="1y")
        info = client.get_info(symbol)

        return {
            "quote": quote,
            "history": history,
            "info": info
        }
    except SymbolNotFoundError:
        raise ValueError(f"Symbol '{symbol}' not found")
    except DataFetchError as e:
        raise RuntimeError(f"Failed to fetch data for '{symbol}': {e.message}")
```

### Resource Management

```python
# Always use context managers for async operations
async def process_symbols(symbols: List[str]):
    async with AsyncYFinanceClient() as client:
        results = []
        for symbol in symbols:
            try:
                quote = await client.get_quote(symbol)
                results.append(quote)
            except YFinanceClientError as e:
                print(f"Failed to get {symbol}: {e}")
                continue
        return results
```

### Data Validation

```python
from yf_client.utils import validate_symbol, validate_symbols

# Validate single symbol
symbol = validate_symbol("AAPL")  # Raises ValidationError if invalid

# Validate multiple symbols
symbols = validate_symbols(["AAPL", "GOOGL", "MSFT"])  # Validates all
```

### Configuration Management

```python
# Use environment-specific settings
import os

if os.getenv("ENVIRONMENT") == "production":
    settings.timeout = 10
    settings.max_retries = 2
else:
    settings.timeout = 30
    settings.max_retries = 5
```

## Advanced Usage

### Custom Data Processing

```python
from yf_client import YFinanceClient
from yf_client.utils import calculate_returns

client = YFinanceClient()
history = client.get_history("AAPL", period="1y")

# Calculate daily returns
prices = [ohlcv.close for ohlcv in history.data]
returns = calculate_returns(prices)

# Find best/worst performing days
if returns:
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

# Add technical indicators
df['SMA_20'] = df['close'].rolling(window=20).mean()
df['SMA_50'] = df['close'].rolling(window=50).mean()

print(df.tail())
```

### Custom Export Integration

```python
from yf_client import YFinanceClient
from yf_client.exporters import JSONExporter
import json

client = YFinanceClient()
data = client.get_quote("AAPL")

# Custom JSON export with metadata
exporter = JSONExporter()
json_data = exporter._convert_to_dict(data)

# Add custom metadata
json_data['metadata'] = {
    'source': 'yf-client',
    'version': '0.1.0',
    'timestamp': data.timestamp.isoformat(),
    'processed_by': 'custom_processor'
}

# Save with custom formatting
with open('custom_export.json', 'w') as f:
    json.dump(json_data, f, indent=2)
```
