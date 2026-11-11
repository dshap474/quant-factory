# yf-client Documentation

Welcome to the comprehensive documentation for yf-client, a typed Python wrapper around Yahoo Finance with async support, CLI tools, and data export capabilities.

## 📚 Documentation Overview

This documentation is organized into the following sections:

- **[API Documentation](api/)** - Complete API reference for Python usage
- **[CLI Documentation](cli/)** - Command-line interface guide and examples

## 🚀 Quick Start

### Installation

```bash
# From the repository root (uv workspace)
uv sync --frozen --group dev
```

### Basic Usage

```python
from yf_client import YFinanceClient

client = YFinanceClient()

# Get current quote
quote = client.get_quote("AAPL")
print(f"AAPL: ${quote.price}")

# Get historical data
history = client.get_history("AAPL", period="1y")
print(f"Data points: {len(history.data)}")

# Get company info
info = client.get_info("AAPL")
print(f"Company: {info.company_name}")
```

### CLI Usage

```bash
# Get quote
yf-client quote AAPL

# Get historical data
yf-client history AAPL --period 1y --export csv

# Get multiple quotes
yf-client multi AAPL GOOGL MSFT --export json
```

## 📖 Documentation Sections

### API Documentation

The [API documentation](api/README.md) provides:

- **YFinanceClient**: Synchronous client for Yahoo Finance data
- **AsyncYFinanceClient**: Asynchronous client with thread pool support
- **Data Models**: Complete reference for Quote, OHLCV, StockInfo, etc.
- **Error Handling**: Exception types and handling patterns
- **Configuration**: Settings and environment variables

### CLI Documentation

The [CLI documentation](cli/README.md) covers:

- **Command Reference**: All available commands and options
- **Usage Examples**: Practical examples for each command
- **Integration**: Using CLI with other tools

## 🔍 Key Features

### ✨ Synchronous & Asynchronous APIs

```python
# Synchronous
client = YFinanceClient()
quote = client.get_quote("AAPL")

# Asynchronous
async with AsyncYFinanceClient() as client:
    quote = await client.get_quote("AAPL")
```

### 📊 Rich Data Models

```python
# Typed data structures
quote: Quote = client.get_quote("AAPL")
history: HistoricalData = client.get_history("AAPL", period="1y")
info: StockInfo = client.get_info("AAPL")
```

### 🖥️ Powerful CLI

```bash
# Simple commands
yf-client quote AAPL
yf-client history AAPL --period 1y --export csv
yf-client multi AAPL GOOGL MSFT --export json

# Advanced options
yf-client history AAPL --start 2023-01-01 --end 2023-12-31 --interval 1wk
```

### 📁 Multiple Export Formats

```python
from yf_client import export_to_csv, export_to_json, export_to_xlsx

export_to_csv(data, "output.csv")
export_to_json(data, "output.json")
export_to_xlsx(data, "output.xlsx")  # requires openpyxl
```

### ⚙️ Flexible Configuration

```bash
# Environment variables
export YF_DEFAULT_PERIOD="3mo"
export YF_DEFAULT_INTERVAL="1d"

# Programmatic
from yf_client.config import settings
settings.default_period = "6mo"
```

## 🐛 Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure dependencies are installed
   uv sync --frozen --group dev
   ```

2. **Network Errors**
   ```bash
   # Increase timeout
   export YF_TIMEOUT=60
   ```

3. **Rate Limiting**
   ```bash
   # Reduce request frequency
   time.sleep(1)  # Between requests
   ```

4. **Memory Issues**
   ```bash
   # Process in batches
   for batch in chunk_list(symbols, 10):
       quotes = client.get_multiple_quotes(batch)
   ```

### Debug Information

```bash
# Enable verbose logging
export YF_VERBOSE=1

# Check CLI version
yf-client --version

# Test basic connectivity
yf-client quote AAPL
```
