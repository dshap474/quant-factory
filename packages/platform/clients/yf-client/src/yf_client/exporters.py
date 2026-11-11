"""
Data export functionality for yf-client.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from .config import settings
from .exceptions import ExportError, ValidationError
from .models import BaseModel, HistoricalData, MultipleQuotes, Quote, StockInfo
from .utils import create_output_path, generate_filename, historical_data_to_dataframe

logger = logging.getLogger(__name__)


class BaseExporter(ABC):
    """Abstract base class for data exporters."""

    def __init__(self, output_dir: Optional[Union[str, Path]] = None):
        """
        Initialize the exporter.

        Args:
            output_dir: Directory to save exported files
        """
        self.output_dir = Path(output_dir) if output_dir else settings.output_dir

    @abstractmethod
    def export(
        self,
        data: Union[List[BaseModel], BaseModel],
        filename: Optional[str] = None,
        **kwargs,
    ) -> Path:
        """
        Export data to file.

        Args:
            data: Data to export (single object or list)
            filename: Optional filename (auto-generated if not provided)
            **kwargs: Additional export options

        Returns:
            Path to exported file
        """
        pass

    def _generate_filename(self, base_name: str, extension: str) -> str:
        """Generate a filename with timestamp."""
        return generate_filename(base_name, extension)

    def _ensure_output_dir(self) -> None:
        """Ensure output directory exists."""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ExportError(
                f"Cannot create output directory '{self.output_dir}': {str(e)}"
            )


class CSVExporter(BaseExporter):
    """Exporter for CSV format."""

    def export(
        self,
        data: Union[List[BaseModel], BaseModel],
        filename: Optional[str] = None,
        **kwargs,
    ) -> Path:
        """
        Export data to CSV format.

        Args:
            data: Data to export
            filename: Optional filename
            **kwargs: Additional pandas to_csv options

        Returns:
            Path to exported CSV file
        """
        self._ensure_output_dir()

        try:
            df = self._convert_to_dataframe(data)
            if df.empty:
                raise ExportError("No data to export")

            if filename is None:
                base_name = self._get_base_name(data)
                filename = self._generate_filename(base_name, "csv")

            filepath = create_output_path(filename, self.output_dir)

            # Default CSV options
            csv_options = {
                "index": False,
                "date_format": "%Y-%m-%d",
                "float_format": "%.4f",
            }
            csv_options.update(kwargs)

            df.to_csv(filepath, **csv_options)
            logger.info(f"Successfully exported {len(df)} rows to {filepath}")

            return filepath

        except Exception as e:
            raise ExportError(f"Failed to export CSV: {str(e)}", original_error=e)

    def _convert_to_dataframe(
        self, data: Union[List[BaseModel], BaseModel]
    ) -> pd.DataFrame:
        """Convert data to pandas DataFrame."""
        if isinstance(data, list):
            if not data:
                return pd.DataFrame()

            # Convert list of models to DataFrame
            dicts = [item.dict() for item in data]
            df = pd.DataFrame(dicts)

        elif isinstance(data, HistoricalData):
            df = historical_data_to_dataframe(data)
            df.reset_index(inplace=True)

        elif isinstance(data, MultipleQuotes):
            dicts = [quote.dict() for quote in data.quotes]
            df = pd.DataFrame(dicts)

        elif isinstance(data, BaseModel):
            df = pd.DataFrame([data.dict()])

        else:
            raise ValidationError(f"Unsupported data type for CSV export: {type(data)}")

        return df

    def _get_base_name(self, data: Union[List[BaseModel], BaseModel]) -> str:
        """Get base name for filename generation."""
        if isinstance(data, HistoricalData):
            return f"{data.symbol}_historical"
        elif isinstance(data, MultipleQuotes):
            return "multiple_quotes"
        elif isinstance(data, list) and data:
            return f"{type(data[0]).__name__.lower()}_data"
        elif isinstance(data, BaseModel):
            return f"{type(data).__name__.lower()}_data"
        else:
            return "export"


class JSONExporter(BaseExporter):
    """Exporter for JSON format."""

    def export(
        self,
        data: Union[List[BaseModel], BaseModel],
        filename: Optional[str] = None,
        indent: int = 2,
        **kwargs,
    ) -> Path:
        """
        Export data to JSON format.

        Args:
            data: Data to export
            filename: Optional filename
            indent: JSON indentation level
            **kwargs: Additional json.dump options

        Returns:
            Path to exported JSON file
        """
        self._ensure_output_dir()

        try:
            json_data = self._convert_to_dict(data)

            if filename is None:
                base_name = self._get_base_name(data)
                filename = self._generate_filename(base_name, "json")

            filepath = create_output_path(filename, self.output_dir)

            # Default JSON options
            json_options = {
                "indent": indent,
                "default": str,  # Handle datetime serialization
            }
            json_options.update(kwargs)

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(json_data, f, **json_options)

            logger.info(f"Successfully exported data to {filepath}")
            return filepath

        except Exception as e:
            raise ExportError(f"Failed to export JSON: {str(e)}", original_error=e)

    def _convert_to_dict(
        self, data: Union[List[BaseModel], BaseModel]
    ) -> Dict[str, Any]:
        """Convert data to dictionary format."""
        if isinstance(data, list):
            return {
                "data": [item.dict() for item in data],
                "count": len(data),
                "exported_at": datetime.now().isoformat(),
            }

        elif isinstance(data, (HistoricalData, MultipleQuotes)):
            result = data.dict()
            result["exported_at"] = datetime.now().isoformat()
            return result

        elif isinstance(data, BaseModel):
            return {"data": data.dict(), "exported_at": datetime.now().isoformat()}

        else:
            raise ValidationError(
                f"Unsupported data type for JSON export: {type(data)}"
            )

    def _get_base_name(self, data: Union[List[BaseModel], BaseModel]) -> str:
        """Get base name for filename generation."""
        if isinstance(data, HistoricalData):
            return f"{data.symbol}_historical"
        elif isinstance(data, MultipleQuotes):
            return "multiple_quotes"
        elif isinstance(data, list) and data:
            return f"{type(data[0]).__name__.lower()}_data"
        elif isinstance(data, BaseModel):
            return f"{type(data).__name__.lower()}_data"
        else:
            return "export"


class ExcelExporter(BaseExporter):
    """Exporter for Excel format."""

    def export(
        self,
        data: Union[List[BaseModel], BaseModel],
        filename: Optional[str] = None,
        sheet_name: str = "Data",
        **kwargs,
    ) -> Path:
        """
        Export data to Excel format.

        Args:
            data: Data to export
            filename: Optional filename
            sheet_name: Excel sheet name
            **kwargs: Additional pandas to_excel options

        Returns:
            Path to exported Excel file
        """
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            raise ExportError(
                "Excel export requires 'openpyxl' package. Install with: uv sync --frozen --inexact --group dev --package yf-client --extra excel"
            )

        self._ensure_output_dir()

        try:
            df = self._convert_to_dataframe(data)
            if df.empty:
                raise ExportError("No data to export")

            if filename is None:
                base_name = self._get_base_name(data)
                filename = self._generate_filename(base_name, "xlsx")

            filepath = create_output_path(filename, self.output_dir)

            # Default Excel options
            excel_options = {
                "sheet_name": sheet_name,
                "index": False,
                "engine": "openpyxl",
            }
            excel_options.update(kwargs)

            df.to_excel(filepath, **excel_options)
            logger.info(f"Successfully exported {len(df)} rows to {filepath}")

            return filepath

        except ImportError:
            raise ExportError(
                "Excel export requires openpyxl. Install with: uv sync --frozen --inexact --group dev --package yf-client --extra excel"
            )
        except Exception as e:
            raise ExportError(f"Failed to export Excel: {str(e)}", original_error=e)

    def _convert_to_dataframe(
        self, data: Union[List[BaseModel], BaseModel]
    ) -> pd.DataFrame:
        """Convert data to pandas DataFrame."""
        if isinstance(data, list):
            if not data:
                return pd.DataFrame()

            # Convert list of models to DataFrame
            dicts = [item.dict() for item in data]
            df = pd.DataFrame(dicts)

        elif isinstance(data, HistoricalData):
            df = historical_data_to_dataframe(data)
            df.reset_index(inplace=True)

        elif isinstance(data, MultipleQuotes):
            dicts = [quote.dict() for quote in data.quotes]
            df = pd.DataFrame(dicts)

        elif isinstance(data, BaseModel):
            df = pd.DataFrame([data.dict()])

        else:
            raise ValidationError(
                f"Unsupported data type for Excel export: {type(data)}"
            )

        return df

    def _get_base_name(self, data: Union[List[BaseModel], BaseModel]) -> str:
        """Get base name for filename generation."""
        if isinstance(data, HistoricalData):
            return f"{data.symbol}_historical"
        elif isinstance(data, MultipleQuotes):
            return "multiple_quotes"
        elif isinstance(data, list) and data:
            return f"{type(data[0]).__name__.lower()}_data"
        elif isinstance(data, BaseModel):
            return f"{type(data).__name__.lower()}_data"
        else:
            return "export"


# Convenience functions
def export_to_csv(
    data: Union[List[BaseModel], BaseModel],
    filepath: Optional[Union[str, Path]] = None,
    **kwargs,
) -> Path:
    """
    Export data to CSV format.

    Args:
        data: Data to export
        filepath: Optional full filepath (directory auto-created)
        **kwargs: Additional export options

    Returns:
        Path to exported file
    """
    if filepath:
        filepath = Path(filepath)
        exporter = CSVExporter(filepath.parent)
        filename = filepath.name
    else:
        exporter = CSVExporter()
        filename = None

    return exporter.export(data, filename, **kwargs)


def export_to_json(
    data: Union[List[BaseModel], BaseModel],
    filepath: Optional[Union[str, Path]] = None,
    **kwargs,
) -> Path:
    """
    Export data to JSON format.

    Args:
        data: Data to export
        filepath: Optional full filepath (directory auto-created)
        **kwargs: Additional export options

    Returns:
        Path to exported file
    """
    if filepath:
        filepath = Path(filepath)
        exporter = JSONExporter(filepath.parent)
        filename = filepath.name
    else:
        exporter = JSONExporter()
        filename = None

    return exporter.export(data, filename, **kwargs)


def export_to_xlsx(
    data: Union[List[BaseModel], BaseModel],
    filepath: Optional[Union[str, Path]] = None,
    **kwargs,
) -> Path:
    """
    Export data to Excel format.

    Args:
        data: Data to export
        filepath: Optional full filepath (directory auto-created)
        **kwargs: Additional export options

    Returns:
        Path to exported file
    """
    if filepath:
        filepath = Path(filepath)
        exporter = ExcelExporter(filepath.parent)
        filename = filepath.name
    else:
        exporter = ExcelExporter()
        filename = None

    return exporter.export(data, filename, **kwargs)
