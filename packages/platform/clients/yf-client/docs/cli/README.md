# yf-client CLI Documentation

## Overview

The yf-client command-line interface (CLI) provides a convenient way to access Yahoo Finance data directly from the terminal. It supports all major operations with export capabilities and progress indicators.

## Installation

```bash
# From the repository root (uv workspace)
uv sync --frozen --group dev
uv run yf-client --help
```

## Basic Usage

```bash
yf-client [OPTIONS] COMMAND [ARGS]...
```

## Global Options

| Option | Description | Default |
|--------|-------------|---------|
| `--verbose`, `-v` | Enable verbose output | `False` |
| `--config FILE` | Reserved; config files are not yet supported | `None` |
| `--help` | Show help message and exit | |
| `--version` | Show version information and exit | |

## Commands

### quote

Get current quote for a stock symbol.

```bash
yf-client quote [OPTIONS] SYMBOL
```

**Arguments:**
- `SYMBOL`: Stock ticker symbol (e.g., AAPL, GOOGL, MSFT)

**Options:**
- `--export {csv,json,xlsx}`: Export format
- `--output PATH`: Output file path

**Examples:**

```bash
# Basic quote
yf-client quote AAPL

# Export to JSON
yf-client quote AAPL --export json

# Export to specific file
yf-client quote AAPL --export csv --output apple_quote.csv

# Verbose output
yf-client --verbose quote AAPL
```

**Output:**
```
📈 AAPL Quote
─────────────────────
Price:    $150.25
Currency: USD
Time:     2023-12-01 10:30:00
```

### history

Get historical price data for a stock symbol.

```bash
yf-client history [OPTIONS] SYMBOL
```

**Arguments:**
- `SYMBOL`: Stock ticker symbol

**Options:**
- `--period PERIOD`: Time period for data
  - `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `ytd`, `max`
  - Default: `1mo`
- `--interval INTERVAL`: Data interval
  - `1m`, `2m`, `5m`, `15m`, `30m`, `60m`, `90m`, `1h`, `1d`, `5d`, `1wk`, `1mo`, `3mo`
  - Default: `1d`
- `--export {csv,json,xlsx}`: Export format
- `--output PATH`: Output file path
- `--start DATE`: Start date (YYYY-MM-DD)
- `--end DATE`: End date (YYYY-MM-DD)

**Examples:**

```bash
# Get last month's daily data
yf-client history AAPL

# Get last year's data
yf-client history AAPL --period 1y

# Get hourly data for last week
yf-client history AAPL --period 5d --interval 1h

# Custom date range
yf-client history AAPL --start 2023-01-01 --end 2023-12-31

# Export to Excel
yf-client history AAPL --period 6mo --export xlsx --output apple_history.xlsx

# Verbose with progress
yf-client --verbose history AAPL --period 1y
```

**Output:**
```
📊 AAPL Historical Data
───────────────────────────────
Data points: 251
Period:      1y
Interval:    1d
Date range:  2022-12-01 to 2023-12-01

Latest data point:
Date:   2023-11-30
Open:   $149.50
High:   $152.00
Low:    $148.25
Close:  $150.25
Volume: 45,230,000
```

### multi

Get quotes for multiple stock symbols.

```bash
yf-client multi [OPTIONS] SYMBOLS...
```

**Arguments:**
- `SYMBOLS`: One or more stock ticker symbols

**Options:**
- `--export {csv,json,xlsx}`: Export format
- `--output PATH`: Output file path
- `--batch-size INTEGER`: Number of symbols to process per batch (default: 10)

**Examples:**

```bash
# Multiple symbols
yf-client multi AAPL GOOGL MSFT

# Tech stocks
yf-client multi AAPL MSFT GOOGL AMZN TSLA NVDA

# Export to JSON
yf-client multi AAPL GOOGL MSFT --export json --output tech_quotes.json

# Large batch with custom batch size
yf-client multi AAPL GOOGL MSFT TSLA NVDA AMD --batch-size 3

# Export to CSV
yf-client multi AAPL GOOGL MSFT TSLA --export csv --output faang.csv
```

**Output:**
```
📊 Multiple Quotes (4 symbols)
─────────────────────────────
AAPL     $150.25     USD 10:30:00
GOOGL   $2800.50     USD 10:30:00
MSFT     $380.75     USD 10:30:00
TSLA     $245.80     USD 10:30:00
```

### info

Get comprehensive information about a company.

```bash
yf-client info [OPTIONS] SYMBOL
```

**Arguments:**
- `SYMBOL`: Stock ticker symbol

**Options:**
- `--export {csv,json,xlsx}`: Export format
- `--output PATH`: Output file path

**Examples:**

```bash
# Company info
yf-client info AAPL

# Export to JSON
yf-client info TSLA --export json --output tesla_info.json

# Export to Excel
yf-client info GOOGL --export xlsx --output google_info.xlsx
```

**Output:**
```
🏢 AAPL Information
─────────────────────
Company:     Apple Inc.
Sector:      Technology
Industry:    Consumer Electronics
Market Cap:  $3,000,000,000,000
P/E Ratio:   28.5
Dividend:    0.50%
Beta:        1.20
52W Range:   $120.00 - $200.00
Avg Volume:  50,000,000
Currency:    USD
Exchange:    NASDAQ
Country:     United States
```

### all

Get all available data for a stock symbol (quote, info, and history).

```bash
yf-client all [OPTIONS] SYMBOL
```

**Arguments:**
- `SYMBOL`: Stock ticker symbol

**Options:**
- `--export {csv,json,xlsx}`: Export format for all data
- `--output-dir PATH`: Output directory for exports

**Examples:**

```bash
# Get all data
yf-client all AAPL

# Export all data to separate files
yf-client all TSLA --export csv --output-dir ./tesla_data

# Export all data to JSON files
yf-client all GOOGL --export json --output-dir ./google_data
```

**Output:**
```
📈 Complete AAPL Data
──────────────────────────────
Current Price: $150.25
Company:       Apple Inc.
Sector:        Technology
Data Points:   251
```

**Creates files:**
- `AAPL_quote.json/csv/xlsx`
- `AAPL_info.json/csv/xlsx`
- `AAPL_history.json/csv/xlsx`

(The symbol is used exactly as typed.)

## Export Formats

### CSV Format

- Tabular data format
- Compatible with Excel and data analysis tools
- Includes headers and proper formatting

### JSON Format

- Structured data format
- Includes metadata (export timestamp, count, etc.)
- Human-readable and machine-parseable

### Excel Format

- Native Excel format (.xlsx)
- Requires `openpyxl` package
- Multiple sheets support for complex data

## Configuration

### Environment Variables

```bash
# Set default values
export YF_DEFAULT_PERIOD="3mo"
export YF_DEFAULT_INTERVAL="1d"
export YF_OUTPUT_DIR="./exports"
export YF_TIMEOUT="30"
export YF_VERBOSE="false"
```

### Configuration File

Create a `.env` file in your working directory:

```bash
# .env
YF_DEFAULT_PERIOD=6mo
YF_DEFAULT_INTERVAL=1wk
YF_OUTPUT_DIR=./data
YF_TIMEOUT=60
YF_VERBOSE=true
```

## Advanced Usage

### Batch Processing

```bash
# Process many symbols with progress tracking
yf-client multi AAPL GOOGL MSFT TSLA NVDA AMD INTC META AMZN --batch-size 5

# Export large datasets
yf-client history SPY --period max --export csv --output sp500_history.csv
```

### Automation Scripts

```bash
#!/bin/bash
# daily_quotes.sh - Get daily quotes for watchlist

SYMBOLS="AAPL GOOGL MSFT TSLA NVDA"
DATE=$(date +%Y%m%d)

for symbol in $SYMBOLS; do
    yf-client quote $symbol --export json --output ${symbol}_${DATE}.json
done
```

### Cron Jobs

```bash
# Add to crontab for daily data collection
# Every weekday at 6 PM
0 18 * * 1-5 yf-client history SPY --period 1d --export csv --output /data/spy_daily.csv
```

### Integration with Other Tools

```bash
# Exports are written to a file (stdout carries progress and a summary), so process the file
yf-client quote AAPL --export json --output aapl_quote.json
jq '.data.price' aapl_quote.json

yf-client history AAPL --period 1y --export csv --output apple_data.csv
uv run python -c "import pandas as pd; df = pd.read_csv('apple_data.csv'); print(df.head())"
```

## Error Handling

### Common Errors

```bash
# Symbol not found
yf-client quote INVALID
# Error: [INVALID] Symbol 'INVALID' not found or invalid

# Invalid period
yf-client history AAPL --period invalid
# Error: Invalid period 'invalid'. Valid periods: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max

# Network timeout
yf-client quote AAPL
# Error: [AAPL] Failed to fetch data from Yahoo Finance
```

### Error Exit Codes

- `0`: Success
- `1`: General error
- `130`: Operation cancelled (Ctrl+C)

## Performance Tips

### Large Datasets

```bash
# Use appropriate intervals for large time periods
yf-client history AAPL --period 5y --interval 1wk  # Better than daily
yf-client history AAPL --period 10y --interval 1mo  # Even better
```

### Batch Operations

```bash
# Adjust batch size based on network and API limits
yf-client multi SYMBOLS... --batch-size 5  # Conservative
yf-client multi SYMBOLS... --batch-size 20  # Aggressive
```

### Export Optimization

```bash
# Use CSV for large datasets (smaller file size)
yf-client history AAPL --period max --export csv

# Use JSON for structured data with metadata
yf-client multi SYMBOLS... --export json

# Use Excel for human-readable reports
yf-client all AAPL --export xlsx
```

## Examples

### Daily Market Check

```bash
#!/bin/bash
# daily_market_check.sh

echo "=== Daily Market Check ==="
echo "Date: $(date)"
echo

echo "Major Indices:"
yf-client multi ^GSPC ^IXIC ^DJI

echo
echo "Tech Stocks:"
yf-client multi AAPL MSFT GOOGL AMZN TSLA NVDA

echo
echo "SPY Details:"
yf-client info SPY
```

### Historical Analysis

```bash
#!/bin/bash
# historical_analysis.sh

SYMBOL=$1
PERIOD=${2:-1y}
INTERVAL=${3:-1d}

echo "=== Historical Analysis for $SYMBOL ==="
echo "Period: $PERIOD"
echo "Interval: $INTERVAL"
echo

# Get historical data
yf-client history $SYMBOL --period $PERIOD --interval $INTERVAL --export csv --output ${SYMBOL}_history.csv

# Show summary statistics
echo "Summary:"
tail -n 5 ${SYMBOL}_history.csv
```

### Portfolio Tracking

```bash
#!/bin/bash
# portfolio_tracker.sh

PORTFOLIO="AAPL MSFT GOOGL AMZN TSLA"
OUTPUT_DIR="./portfolio_$(date +%Y%m%d)"

mkdir -p $OUTPUT_DIR

echo "=== Portfolio Tracking ==="
echo "Date: $(date)"
echo "Output: $OUTPUT_DIR"
echo

# Get quotes for all positions
yf-client multi $PORTFOLIO --export json --output $OUTPUT_DIR/portfolio_quotes.json

# Get detailed info for each
for symbol in $PORTFOLIO; do
    yf-client info $symbol --export json --output $OUTPUT_DIR/${symbol}_info.json
done

echo "Portfolio data saved to $OUTPUT_DIR"
```

### Market Scanner

```bash
#!/bin/bash
# market_scanner.sh

# Scan multiple markets
echo "=== Market Scanner ==="
echo

echo "US Markets:"
yf-client multi ^GSPC ^IXIC ^DJI ^RUT

echo
echo "International Markets:"
yf-client multi ^FTSE ^N225 ^HSI ^GDAXI

echo
echo "Crypto:"
yf-client multi BTC-USD ETH-USD

echo
echo "Commodities:"
yf-client multi GC=F CL=F SI=F
```

## Troubleshooting

### Verbose Mode

```bash
# Enable verbose output for debugging
yf-client --verbose quote AAPL
yf-client --verbose history AAPL --period 1mo
```

### Network Issues

```bash
# Increase timeout for slow connections
export YF_TIMEOUT=60
yf-client quote AAPL

# Reduce batch size for unstable connections
yf-client multi SYMBOLS... --batch-size 3
```

### Export Issues

```bash
# Check write permissions
ls -la /output/directory

# Excel export needs the optional `excel` extra (openpyxl)
yf-client history AAPL --export xlsx
```

### Rate Limiting

```bash
# Yahoo Finance may limit requests
# Wait between large batches
sleep 5
yf-client multi LARGE_SYMBOL_LIST --batch-size 5
```

## Integration Examples

### Python Scripts

Exports go to a file (stdout carries progress and a summary), so pass `--output` and read the file:

```python
#!/usr/bin/env python3
# yahoo_finance_cli.py

import json
import subprocess
import sys
import tempfile
from pathlib import Path

def get_quote(symbol):
    """Get a quote through the CLI and return it as a dict."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "quote.json"
        result = subprocess.run(
            ["yf-client", "quote", symbol, "--export", "json", "--output", str(path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return None
        return json.loads(path.read_text())["data"]

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python yahoo_finance_cli.py SYMBOL")
        sys.exit(1)

    quote = get_quote(sys.argv[1])
    if quote:
        print(json.dumps(quote, indent=2))
```

### Web Applications

In a Python service, call the client directly instead of the CLI:

```python
# FastAPI integration
from fastapi import FastAPI
from yf_client import AsyncYFinanceClient

app = FastAPI()

@app.get("/quote/{symbol}")
async def get_quote(symbol: str):
    async with AsyncYFinanceClient() as client:
        quote = await client.get_quote(symbol)
    return quote.model_dump(mode="json")
```

### Data Analysis Workflows

```bash
# Download data for analysis
yf-client history AAPL --period 5y --export csv --output aapl_5y.csv
yf-client history GOOGL --period 5y --export csv --output googl_5y.csv
yf-client history MSFT --period 5y --export csv --output msft_5y.csv
```

This CLI provides a powerful and flexible interface to Yahoo Finance data, suitable for both interactive use and automation.
