"""
Tests for data exporters.
"""

import json
import pytest
import pandas as pd
from pathlib import Path

from yf_client.exporters import (
    CSVExporter,
    JSONExporter,
    ExcelExporter,
    export_to_csv,
    export_to_json,
    export_to_xlsx,
)
from yf_client.models import Quote, HistoricalData, MultipleQuotes, OHLCV
from yf_client.exceptions import ExportError


class TestCSVExporter:
    """Test CSVExporter class."""

    def test_csv_exporter_initialization(self, temp_output_dir):
        """Test CSV exporter initialization."""
        exporter = CSVExporter(temp_output_dir)
        assert exporter.output_dir == temp_output_dir

    def test_export_quotes_to_csv(self, sample_quote, temp_output_dir):
        """Test exporting quotes to CSV."""
        exporter = CSVExporter(temp_output_dir)
        filepath = exporter.export(sample_quote)

        assert filepath.exists()
        assert filepath.suffix == ".csv"

        # Verify CSV content
        df = pd.read_csv(filepath)
        assert len(df) == 1
        assert df.iloc[0]["symbol"] == "AAPL"
        assert df.iloc[0]["price"] == 150.25

    def test_export_historical_data_to_csv(
        self, sample_historical_data, temp_output_dir
    ):
        """Test exporting historical data to CSV."""
        exporter = CSVExporter(temp_output_dir)
        filepath = exporter.export(sample_historical_data)

        assert filepath.exists()
        assert filepath.suffix == ".csv"

        # Verify CSV content
        df = pd.read_csv(filepath)
        assert len(df) == 2
        assert "Date" in df.columns
        assert "Open" in df.columns
        assert "Close" in df.columns

    def test_export_multiple_quotes_to_csv(
        self, sample_multiple_quotes, temp_output_dir
    ):
        """Test exporting multiple quotes to CSV."""
        exporter = CSVExporter(temp_output_dir)
        filepath = exporter.export(sample_multiple_quotes)

        assert filepath.exists()
        assert filepath.suffix == ".csv"

        # Verify CSV content
        df = pd.read_csv(filepath)
        assert len(df) == 2
        assert df.iloc[0]["symbol"] == "AAPL"
        assert df.iloc[1]["symbol"] == "GOOGL"

    def test_export_empty_data_to_csv(self, temp_output_dir):
        """Test exporting empty data to CSV."""
        exporter = CSVExporter(temp_output_dir)

        with pytest.raises(ExportError):
            exporter.export([])

    def test_export_invalid_data_type(self, temp_output_dir):
        """Test exporting invalid data type."""
        exporter = CSVExporter(temp_output_dir)

        # The exporter wraps every failure in ExportError
        with pytest.raises(ExportError, match="Unsupported data type"):
            exporter.export("invalid_data")


class TestJSONExporter:
    """Test JSONExporter class."""

    def test_json_exporter_initialization(self, temp_output_dir):
        """Test JSON exporter initialization."""
        exporter = JSONExporter(temp_output_dir)
        assert exporter.output_dir == temp_output_dir

    def test_export_quote_to_json(self, sample_quote, temp_output_dir):
        """Test exporting quote to JSON."""
        exporter = JSONExporter(temp_output_dir)
        filepath = exporter.export(sample_quote)

        assert filepath.exists()
        assert filepath.suffix == ".json"

        # Verify JSON content
        with open(filepath, "r") as f:
            data = json.load(f)

        assert "data" in data
        assert "exported_at" in data
        assert data["data"]["symbol"] == "AAPL"
        assert data["data"]["price"] == 150.25

    def test_export_historical_data_to_json(
        self, sample_historical_data, temp_output_dir
    ):
        """Test exporting historical data to JSON."""
        exporter = JSONExporter(temp_output_dir)
        filepath = exporter.export(sample_historical_data)

        assert filepath.exists()
        assert filepath.suffix == ".json"

        # Verify JSON content
        with open(filepath, "r") as f:
            data = json.load(f)

        # HistoricalData is exported flat: its own fields plus exported_at
        assert data["symbol"] == "AAPL"
        assert "exported_at" in data
        assert len(data["data"]) == 2

    def test_export_list_to_json(self, temp_output_dir):
        """Test exporting list of objects to JSON."""
        quotes = [
            Quote(
                symbol="AAPL",
                price=150.0,
                currency="USD",
                timestamp="2023-01-01T00:00:00",
            ),
            Quote(
                symbol="GOOGL",
                price=2800.0,
                currency="USD",
                timestamp="2023-01-01T00:00:00",
            ),
        ]

        exporter = JSONExporter(temp_output_dir)
        filepath = exporter.export(quotes)

        assert filepath.exists()

        # Verify JSON content
        with open(filepath, "r") as f:
            data = json.load(f)

        assert "data" in data
        assert "count" in data
        assert data["count"] == 2
        assert len(data["data"]) == 2


class TestExcelExporter:
    """Test ExcelExporter class."""

    def test_excel_exporter_initialization(self, temp_output_dir):
        """Test Excel exporter initialization."""
        exporter = ExcelExporter(temp_output_dir)
        assert exporter.output_dir == temp_output_dir

    def test_export_to_excel(self, sample_quote, temp_output_dir):
        """Test exporting data to Excel."""
        pytest.importorskip("openpyxl")
        exporter = ExcelExporter(temp_output_dir)
        filepath = exporter.export(sample_quote)

        assert filepath.exists()
        assert filepath.suffix == ".xlsx"

        # Verify Excel content
        df = pd.read_excel(filepath)
        assert len(df) == 1
        assert df.iloc[0]["symbol"] == "AAPL"

    def test_excel_export_without_openpyxl(self, sample_quote, temp_output_dir):
        """Test Excel export when openpyxl is not available."""
        # Mock import error
        import sys

        original_modules = sys.modules.copy()

        try:
            # Remove openpyxl from sys.modules if it exists
            modules_to_remove = [k for k in sys.modules.keys() if "openpyxl" in k]
            for module in modules_to_remove:
                del sys.modules[module]

            # Mock __import__ to raise ImportError for openpyxl
            def mock_import(name, *args, **kwargs):
                if "openpyxl" in name:
                    raise ImportError("No module named 'openpyxl'")
                return original_modules.get(name, __import__(name, *args, **kwargs))

            original_import = __builtins__["__import__"]
            __builtins__["__import__"] = mock_import

            exporter = ExcelExporter(temp_output_dir)
            with pytest.raises(ExportError, match="Excel export requires 'openpyxl'"):
                exporter.export(sample_quote)

        finally:
            __builtins__["__import__"] = original_import
            sys.modules.update(original_modules)


class TestConvenienceFunctions:
    """Test convenience export functions."""

    def test_export_to_csv_function(self, sample_quote, tmp_path):
        """Test export_to_csv convenience function."""
        output_file = tmp_path / "test_quote.csv"
        filepath = export_to_csv(sample_quote, output_file)

        assert filepath == output_file
        assert filepath.exists()

    def test_export_to_json_function(self, sample_quote, tmp_path):
        """Test export_to_json convenience function."""
        output_file = tmp_path / "test_quote.json"
        filepath = export_to_json(sample_quote, output_file)

        assert filepath == output_file
        assert filepath.exists()

    def test_export_to_xlsx_function(self, sample_quote, tmp_path):
        """Test export_to_xlsx convenience function."""
        pytest.importorskip("openpyxl")
        output_file = tmp_path / "test_quote.xlsx"
        filepath = export_to_xlsx(sample_quote, output_file)

        assert filepath == output_file
        assert filepath.exists()

    def test_export_functions_auto_filename(self, sample_quote, tmp_path):
        """Test export functions with auto-generated filenames."""
        # Change to temp directory for auto-generated filenames
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            filepath = export_to_csv(sample_quote)
            assert filepath.exists()
            assert "quote" in filepath.name.lower()
        finally:
            os.chdir(original_cwd)


class TestExporterErrorHandling:
    """Test exporter error handling."""

    def test_export_to_nonexistent_directory(self, sample_quote):
        """Test export to nonexistent directory."""
        nonexistent_dir = Path("/nonexistent/directory")
        exporter = CSVExporter(nonexistent_dir)

        with pytest.raises(ExportError):
            exporter.export(sample_quote)

    def test_export_with_permission_error(self, sample_quote, tmp_path, monkeypatch):
        """Test export with permission error."""
        output_file = tmp_path / "readonly" / "test.csv"
        output_file.parent.mkdir()

        # Make directory read-only
        import stat

        output_file.parent.chmod(stat.S_IRUSR | stat.S_IXUSR)  # Read and execute only

        try:
            exporter = CSVExporter(output_file.parent)
            with pytest.raises(ExportError):
                exporter.export(sample_quote, filename=output_file.name)
        finally:
            # Restore permissions for cleanup
            output_file.parent.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
