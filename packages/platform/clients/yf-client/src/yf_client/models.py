"""
Models
---
packages/platform/clients/yf-client/src/yf_client/models.py
---
Pydantic models for yfinance data structures and typed DTOs used by the
yf-client API wrapper.
"""

from datetime import date, datetime
from typing import List, Optional
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Quote(BaseModel):
    """Model for stock quote data."""

    symbol: str = Field(..., description="Stock ticker symbol")
    price: float = Field(..., description="Current price", gt=0)
    currency: str = Field(..., description="Currency code (e.g., USD)")
    timestamp: datetime = Field(..., description="Quote timestamp")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v):
        """Validate stock symbol format."""
        if not v or not isinstance(v, str):
            raise ValueError("Symbol must be a non-empty string")
        return v.upper()

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v):
        """Validate currency format."""
        if not v or not isinstance(v, str):
            raise ValueError("Currency must be a non-empty string")
        return v.upper()

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
        }
    }


# ┌────────────────────────────────────────────────────────────────────────────────────┐
# │ OHLCV                                                                              
# └────────────────────────────────────────────────────────────────────────────────────┘
class OHLCV(BaseModel):
    """Model for OHLCV (Open, High, Low, Close, Volume) data."""

    trading_date: date = Field(..., description="Trading date", alias="date")
    open_price: float = Field(..., description="Opening price", ge=0, alias="open")
    high: float = Field(..., description="Highest price", ge=0)
    low: float = Field(..., description="Lowest price", ge=0)
    close: float = Field(..., description="Closing price", ge=0)
    volume: int = Field(..., description="Trading volume", ge=0)

    model_config = {
        "populate_by_name": True,
        "json_encoders": {
            date: lambda v: v.isoformat(),
        },
    }

    @property
    def date(self) -> date:
        """Get the trading date."""
        return self.trading_date

    @property
    def open(self) -> float:
        """Get the opening price."""
        return self.open_price

    @model_validator(mode="after")
    def validate_price_relationships(self):
        """Validate that high/low prices have correct relationships with open/close."""
        if self.high < self.open_price:
            raise ValueError("High price must be >= open price")
        if self.low > self.open_price:
            raise ValueError("Low price must be <= open price")
        if self.low > self.close:
            raise ValueError("Low price must be <= close price")
        if self.high < self.close:
            raise ValueError("High price must be >= close price")
        return self


# ┌────────────────────────────────────────────────────────────────────────────────────┐
# │ StockInfo                                                                          
# └────────────────────────────────────────────────────────────────────────────────────┘
class StockInfo(BaseModel):
    """Model for comprehensive stock information."""

    symbol: str = Field(..., description="Stock ticker symbol")
    company_name: Optional[str] = Field(None, description="Full company name")
    sector: Optional[str] = Field(None, description="Industry sector")
    industry: Optional[str] = Field(None, description="Specific industry")
    market_cap: Optional[float] = Field(None, description="Market capitalization", ge=0)
    pe_ratio: Optional[float] = Field(None, description="Price-to-earnings ratio")
    pb_ratio: Optional[float] = Field(None, description="Price-to-book ratio")
    dividend_yield: Optional[float] = Field(
        None, description="Dividend yield percentage"
    )
    beta: Optional[float] = Field(None, description="Beta coefficient")
    fifty_two_week_high: Optional[float] = Field(
        None, description="52-week high price", ge=0
    )
    fifty_two_week_low: Optional[float] = Field(
        None, description="52-week low price", ge=0
    )
    average_volume: Optional[int] = Field(
        None, description="Average trading volume", ge=0
    )
    currency: Optional[str] = Field(None, description="Trading currency")
    exchange: Optional[str] = Field(None, description="Stock exchange")
    country: Optional[str] = Field(None, description="Company headquarters country")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v):
        """Validate stock symbol format."""
        if not v or not isinstance(v, str):
            raise ValueError("Symbol must be a non-empty string")
        return v.upper()

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v):
        """Validate currency format."""
        if v is not None and not isinstance(v, str):
            raise ValueError("Currency must be a string")
        return v.upper() if v else v

    model_config = {
        "json_encoders": {
            date: lambda v: v.isoformat(),
        }
    }


# ┌────────────────────────────────────────────────────────────────────────────────────┐
# │ HistoricalData                                                                     
# └────────────────────────────────────────────────────────────────────────────────────┘
class HistoricalData(BaseModel):
    """Model for historical price data with multiple OHLCV records."""

    symbol: str = Field(..., description="Stock ticker symbol")
    data: List[OHLCV] = Field(..., description="List of OHLCV records")
    period: str = Field(..., description="Time period requested")
    interval: str = Field(..., description="Data interval")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v):
        """Validate stock symbol format."""
        if not v or not isinstance(v, str):
            raise ValueError("Symbol must be a non-empty string")
        return v.upper()

    def __len__(self) -> int:
        """Return number of data points."""
        return len(self.data)

    def is_empty(self) -> bool:
        """Check if historical data is empty."""
        return len(self.data) == 0


# ┌────────────────────────────────────────────────────────────────────────────────────┐
# │ MultipleQuotes                                                                     
# └────────────────────────────────────────────────────────────────────────────────────┘
class MultipleQuotes(BaseModel):
    """Model for multiple stock quotes."""

    quotes: List[Quote] = Field(..., description="List of stock quotes")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Request timestamp"
    )

    def __len__(self) -> int:
        """Return number of quotes."""
        return len(self.quotes)

    def is_empty(self) -> bool:
        """Check if quotes list is empty."""
        return len(self.quotes) == 0

    def get_quote(self, symbol: str) -> Optional[Quote]:
        """Get quote for specific symbol."""
        for quote in self.quotes:
            if quote.symbol.upper() == symbol.upper():
                return quote
        return None

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
        }
    }


# ┌────────────────────────────────────────────────────────────────────────────────────┐
# │ Corporate Actions & Events                                                          
# └────────────────────────────────────────────────────────────────────────────────────┘
class ActionEvent(BaseModel):
    """Corporate action event (dividend or split)."""

    date: date
    type: Literal["dividend", "split"]
    value: float

    model_config = {
        "json_encoders": {
            date: lambda v: v.isoformat(),
        }
    }


class Dividend(BaseModel):
    """Dividend payment event."""

    date: date
    amount: float

    model_config = {
        "json_encoders": {
            date: lambda v: v.isoformat(),
        }
    }


class Split(BaseModel):
    """Stock split event."""

    date: date
    ratio: float

    model_config = {
        "json_encoders": {
            date: lambda v: v.isoformat(),
        }
    }


# ┌────────────────────────────────────────────────────────────────────────────────────┐
# │ Options                                                                             
# └────────────────────────────────────────────────────────────────────────────────────┘
class OptionContract(BaseModel):
    """Option contract information for an expiration date."""

    contractSymbol: Optional[str] = None
    strike: Optional[float] = None
    lastPrice: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    change: Optional[float] = None
    percentChange: Optional[float] = None
    volume: Optional[float] = None
    openInterest: Optional[float] = None
    impliedVolatility: Optional[float] = None
    inTheMoney: Optional[bool] = None
    expiration: Optional[date] = None
    contractSize: Optional[str] = None
    currency: Optional[str] = None

    model_config = {
        "json_encoders": {
            date: lambda v: v.isoformat(),
        }
    }


# ┌────────────────────────────────────────────────────────────────────────────────────┐
# │ News                                                                                
# └────────────────────────────────────────────────────────────────────────────────────┘
class NewsItem(BaseModel):
    """News item associated with a ticker."""

    title: str
    publisher: str
    link: str
    published: datetime
    summary: Optional[str] = None

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
        }
    }
