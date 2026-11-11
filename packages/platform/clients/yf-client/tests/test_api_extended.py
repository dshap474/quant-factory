"""
Extended tests for new API surface (download, options, actions, fundamentals, discovery).
"""

import pytest
from unittest.mock import MagicMock, patch

import pandas as pd

from yf_client.api import YFinanceClient
from yf_client.exceptions import ValidationError, DataFetchError


@pytest.fixture
def client(mock_yfinance_ticker):
    return YFinanceClient()


def test_download_single_symbol(client):
    with patch("yfinance.download") as mock_dl:
        dates = pd.date_range("2024-01-01", periods=2, freq="D")
        mock_dl.return_value = pd.DataFrame(
            {
                "Open": [1, 2],
                "High": [2, 3],
                "Low": [0.5, 1.5],
                "Close": [1.5, 2.5],
                "Volume": [100, 200],
            },
            index=dates,
        )
        data = client.download("AAPL", period="1mo", interval="1d")
        assert "AAPL" in data and len(data["AAPL"]) == 2


def test_download_multi_symbol(client):
    with patch("yfinance.download") as mock_dl:
        dates = pd.date_range("2024-01-01", periods=1, freq="D")
        idx = pd.MultiIndex.from_product(
            [["AAPL", "MSFT"], ["Open", "High", "Low", "Close", "Volume"]]
        )
        mock_dl.return_value = pd.DataFrame(
            [[1, 2, 0.5, 1.5, 100, 2, 3, 1.5, 2.5, 200]], columns=idx, index=dates
        )
        data = client.download(["AAPL", "MSFT"], period="1mo", interval="1d")
        assert set(data.keys()) >= {"AAPL", "MSFT"}


def test_download_period_vs_start_end(client):
    with pytest.raises(ValidationError):
        client.download("AAPL", period="1mo", start="2024-01-01")


def test_get_fast_info(client, mock_yfinance_ticker):
    mock_yfinance_ticker.fast_info = {"lastPrice": 1.23}
    fi = client.get_fast_info("AAPL")
    assert fi["lastPrice"] == 1.23


def test_options_and_chain(client, mock_yfinance_ticker):
    mock_yfinance_ticker.options = ["2024-06-21"]
    chain_obj = MagicMock()
    chain_obj.calls = pd.DataFrame({"contractSymbol": ["AAPL240621C00100000"], "strike": [100]})
    chain_obj.puts = pd.DataFrame({"contractSymbol": ["AAPL240621P00100000"], "strike": [100]})
    mock_yfinance_ticker.option_chain.return_value = chain_obj
    dates = client.get_options("AAPL")
    assert "2024-06-21" in dates
    chain = client.get_option_chain("AAPL", "2024-06-21")
    assert len(chain["calls"]) == 1 and len(chain["puts"]) == 1


def test_actions_dividends_splits(client, mock_yfinance_ticker):
    idx = pd.to_datetime(["2024-01-01"])  # index
    mock_yfinance_ticker.actions = pd.DataFrame({"Dividends": [0.1], "Stock Splits": [0.0]}, index=idx)
    mock_yfinance_ticker.dividends = pd.Series([0.1], index=idx)
    mock_yfinance_ticker.splits = pd.Series([0.0], index=idx)
    assert client.get_actions("AAPL")[0]["type"] == "dividend"
    assert client.get_dividends("AAPL")[0]["amount"] == 0.1
    assert client.get_splits("AAPL") == [] or client.get_splits("AAPL")[0]["ratio"] >= 0


def test_fundamentals(client, mock_yfinance_ticker):
    df = pd.DataFrame({"2023-12": [1, 2]}, index=["Revenue", "NetIncome"])  # style similar to yfinance
    mock_yfinance_ticker.financials = df
    qdf = pd.DataFrame({"Q1": [1], "Q2": [2], "Q3": [3], "Q4": [4]}, index=["Revenue"])
    mock_yfinance_ticker.quarterly_financials = qdf
    assert client.get_financials("AAPL")
    ttm = client.get_financials_ttm("AAPL")
    assert ttm.get("Revenue") == 10.0


def test_holders_and_analyst(client, mock_yfinance_ticker):
    mock_yfinance_ticker.major_holders = pd.DataFrame({"HOLDER": ["X"]})
    mock_yfinance_ticker.institutional_holders = pd.DataFrame({"HOLDER": ["Y"]})
    mock_yfinance_ticker.mutualfund_holders = pd.DataFrame({"HOLDER": ["Z"]})
    holders = client.get_holders("AAPL")
    assert set(holders.keys()) >= {"major_holders", "institutional_holders", "mutualfund_holders"}

    mock_yfinance_ticker.recommendations = pd.DataFrame({"To Grade": ["Buy"]})
    mock_yfinance_ticker.recommendation_trend = pd.DataFrame({"period": ["2024-03"], "strongBuy": [10]}).set_index("period")
    analyst = client.get_analyst("AAPL")
    assert "recommendations" in analyst and "recommendations_summary" in analyst


def test_news(client, mock_yfinance_ticker):
    mock_yfinance_ticker.news = [
        {"title": "Hello", "publisher": "P", "link": "http://x", "providerPublishTime": "2024-01-01T00:00:00Z"}
    ]
    news = client.get_news("AAPL")
    assert len(news) == 1 and news[0]["title"] == "Hello"
