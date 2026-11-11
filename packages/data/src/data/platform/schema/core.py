"""Schema validation system for the quant-factory data lake.

Provides YAML-based schema definitions and auto-validation with three modes:
- strict: Fail on any mismatch (CI, production)
- repair: Auto-fix schema, log changes (development)
- warn: Log issues, continue (quick checks)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pyarrow.parquet as pq
import yaml

from data.platform.storage import delta_read

logger = logging.getLogger(__name__)

# Type mappings from DuckDB to our schema format
DUCKDB_TYPE_MAP = {
    "VARCHAR": "string",
    "INTEGER": "int32",
    "BIGINT": "int64",
    "DOUBLE": "float64",
    "FLOAT": "float32",
    "BOOLEAN": "bool",
    "TIMESTAMP": "datetime64[us]",
    "TIMESTAMP WITH TIME ZONE": "datetime64[us]",
    "DATE": "date",
    "VARCHAR[]": "string[]",
    "HUGEINT": "int128",
    "SMALLINT": "int16",
    "TINYINT": "int8",
    "BLOB": "bytes",
    "JSON": "json",
}

# Type mappings from PyArrow to our schema format
PYARROW_TYPE_MAP = {
    "int64": "int64",
    "int32": "int32",
    "float64": "float64",
    "double": "float64",
    "float32": "float32",
    "float": "float32",
    "string": "string",
    "large_string": "string",
    "bool": "bool",
    "boolean": "bool",
    "timestamp[us]": "datetime64[us]",
    "timestamp[ns]": "datetime64[ns]",
    "timestamp[ms]": "datetime64[ms]",
    "timestamp[s]": "datetime64[s]",
    "timestamp[us, tz=UTC]": "datetime64[us]",
    "timestamp[ns, tz=UTC]": "datetime64[ns]",
    "date32[day]": "date",
    "date64[ms]": "date",
}


@dataclass
class ColumnSchema:
    """Schema definition for a single column."""

    name: str
    type: str
    nullable: bool = True
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to YAML-serializable dict."""
        d = {"name": self.name, "type": self.type}
        if not self.nullable:
            d["nullable"] = False
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ColumnSchema:
        """Create from YAML dict."""
        return cls(
            name=data["name"],
            type=data["type"],
            nullable=data.get("nullable", True),
            description=data.get("description"),
        )


@dataclass
class DatasetSchema:
    """Schema definition for a single dataset (parquet file)."""

    path: str
    columns: list[ColumnSchema] = field(default_factory=list)
    source: str | None = None
    asset: str | None = None
    product: str | None = None
    exchange: str | None = None
    resolution: str | None = None
    row_count: int | None = None
    date_range: dict[str, str] | None = None
    last_validated: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to YAML-serializable dict."""
        d: dict[str, Any] = {}
        if self.source:
            d["source"] = self.source
        if self.asset:
            d["asset"] = self.asset
        if self.product:
            d["product"] = self.product
        if self.exchange:
            d["exchange"] = self.exchange
        if self.resolution:
            d["resolution"] = self.resolution
        d["columns"] = [c.to_dict() for c in self.columns]
        if self.row_count is not None:
            d["row_count"] = self.row_count
        if self.date_range:
            d["date_range"] = self.date_range
        if self.last_validated:
            d["last_validated"] = self.last_validated
        return d

    @classmethod
    def from_dict(cls, path: str, data: dict[str, Any]) -> DatasetSchema:
        """Create from YAML dict."""
        columns = [ColumnSchema.from_dict(c) for c in data.get("columns", [])]
        return cls(
            path=path,
            columns=columns,
            source=data.get("source"),
            asset=data.get("asset"),
            product=data.get("product"),
            exchange=data.get("exchange"),
            resolution=data.get("resolution"),
            row_count=data.get("row_count"),
            date_range=data.get("date_range"),
            last_validated=data.get("last_validated"),
        )


@dataclass
class LayerSchema:
    """Schema for a data layer (raw, features, signals)."""

    name: str
    description: str = ""
    datasets: dict[str, DatasetSchema] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to YAML-serializable dict."""
        return {
            "layer": self.name,
            "description": self.description,
            "datasets": {
                path: schema.to_dict()
                for path, schema in self.datasets.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayerSchema:
        """Create from YAML dict."""
        datasets = {}
        for path, schema_data in data.get("datasets", {}).items():
            datasets[path] = DatasetSchema.from_dict(path, schema_data)
        return cls(
            name=data.get("layer", ""),
            description=data.get("description", ""),
            datasets=datasets,
        )


@dataclass
class DatabaseTableSchema:
    """Schema for a single table in a DuckDB database."""

    name: str
    columns: list[ColumnSchema] = field(default_factory=list)
    row_count: int | None = None
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to YAML-serializable dict."""
        d: dict[str, Any] = {"name": self.name}
        d["columns"] = [c.to_dict() for c in self.columns]
        if self.row_count is not None:
            d["row_count"] = self.row_count
        if self.constraints:
            d["constraints"] = self.constraints
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatabaseTableSchema:
        """Create from YAML dict."""
        columns = [ColumnSchema.from_dict(c) for c in data.get("columns", [])]
        return cls(
            name=data["name"],
            columns=columns,
            row_count=data.get("row_count"),
            constraints=data.get("constraints", []),
        )


@dataclass
class DatabaseSchema:
    """Schema for a DuckDB database file."""

    name: str
    path: str
    tables: list[DatabaseTableSchema] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to YAML-serializable dict."""
        return {
            "name": self.name,
            "path": self.path,
            "tables": [t.to_dict() for t in self.tables],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatabaseSchema:
        """Create from YAML dict."""
        tables = [DatabaseTableSchema.from_dict(t) for t in data.get("tables", [])]
        return cls(
            name=data["name"],
            path=data["path"],
            tables=tables,
        )


@dataclass
class MasterSchema:
    """Master schema defining conventions and layer structure."""

    version: int = 1
    name: str = "quant-factory-data"
    description: str = "Quantitative trading data lake"
    conventions: dict[str, Any] = field(default_factory=dict)
    naming_patterns: dict[str, str] = field(default_factory=dict)
    layers: list[dict[str, Any]] = field(default_factory=list)
    databases: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to YAML-serializable dict."""
        d = {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "conventions": self.conventions,
            "naming_patterns": self.naming_patterns,
            "layers": self.layers,
        }
        if self.databases:
            d["databases"] = self.databases
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MasterSchema:
        """Create from YAML dict."""
        return cls(
            version=data.get("version", 1),
            name=data.get("name", ""),
            description=data.get("description", ""),
            conventions=data.get("conventions", {}),
            naming_patterns=data.get("naming_patterns", {}),
            layers=data.get("layers", []),
            databases=data.get("databases", []),
        )


@dataclass
class ValidationResult:
    """Result of schema validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [f"Valid: {self.valid}"]
        if self.errors:
            lines.append(f"Errors ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  - {e}")
        if self.warnings:
            lines.append(f"Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  - {w}")
        if self.changes:
            lines.append(f"Changes ({len(self.changes)}):")
            for c in self.changes:
                lines.append(f"  - {c}")
        return "\n".join(lines)


class SchemaLoader:
    """Load and save SCHEMA.yaml files."""

    def __init__(self, db_root: Path):
        self.db_root = Path(db_root)

    def load_master(self) -> MasterSchema:
        """Load master SCHEMA.yaml from db root."""
        path = self.db_root / "SCHEMA.yaml"
        if not path.exists():
            return MasterSchema()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return MasterSchema.from_dict(data)

    def save_master(self, schema: MasterSchema) -> None:
        """Save master SCHEMA.yaml to db root."""
        path = self.db_root / "SCHEMA.yaml"
        with open(path, "w") as f:
            yaml.dump(schema.to_dict(), f, default_flow_style=False, sort_keys=False)

    def load_layer(self, layer_name: str) -> LayerSchema:
        """Load layer SCHEMA.yaml."""
        path = self.db_root / layer_name / "SCHEMA.yaml"
        if not path.exists():
            return LayerSchema(name=layer_name)
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        schema = LayerSchema.from_dict(data)
        if schema.name != layer_name:
            schema.name = layer_name
        return schema

    def save_layer(self, schema: LayerSchema) -> None:
        """Save layer SCHEMA.yaml."""
        path = self.db_root / schema.name / "SCHEMA.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(schema.to_dict(), f, default_flow_style=False, sort_keys=False)


class SchemaValidator:
    """Validate parquet files against schema definitions."""

    LAYERS = ("data/raw", "data/corrected", "data/derived", "features", "signals", "strategies")
    FEATURE_RESOLUTIONS = ("5m", "15m", "1h", "4h", "1d", "derived")
    # Default validation covers the lake; these db/ trees belong to other owners (pass --layer to check one).
    NON_CANONICAL_LAYERS = {"backups", "research", "agents", "admin", "execution", "ml-engine"}
    IGNORED_PATH_MARKERS = ("__backup_", "__staging_")
    IGNORED_PATH_COMPONENTS = frozenset({"staging"})
    RAW_LAYOUT_PRODUCTS = {"spot", "futures", "options", "orderbook"}

    def __init__(self, db_root: Path):
        self.db_root = Path(db_root)
        self.loader = SchemaLoader(db_root)

    def _discover_layer_names(self, master: MasterSchema) -> list[str]:
        master_layers = [
            layer["name"]
            for layer in master.layers
            if isinstance(layer, dict) and isinstance(layer.get("name"), str)
        ]

        disk_layers: list[str] = []
        if self.db_root.exists():
            for child in sorted(self.db_root.iterdir()):
                if not child.is_dir() or child.name.startswith("."):
                    continue
                if any(marker in child.name for marker in self.IGNORED_PATH_MARKERS):
                    continue
                if child.name in self.NON_CANONICAL_LAYERS:
                    continue
                if child.name == "data":
                    for nested in ("raw", "corrected", "derived"):
                        nested_path = child / nested
                        if nested_path.exists() and nested_path.is_dir():
                            disk_layers.append(f"data/{nested}")
                    continue
                disk_layers.append(child.name)

        ordered = [*self.LAYERS, *master_layers, *disk_layers]
        layer_names: list[str] = []
        seen: set[str] = set()
        for layer_name in ordered:
            if layer_name in seen:
                continue
            seen.add(layer_name)
            layer_names.append(layer_name)
        return layer_names

    def validate(
        self,
        mode: Literal["strict", "repair", "warn"] = "warn",
        layer: str | None = None,
    ) -> ValidationResult:
        """Validate all layers against their schemas.

        Args:
            mode: Validation mode
                - strict: Fail on any mismatch
                - repair: Auto-fix schema to match files
                - warn: Log issues but continue
            layer: Optional single layer name to validate

        Returns:
            ValidationResult with errors, warnings, and changes made
        """
        result = ValidationResult(valid=True)

        # Load master schema (for conventions)
        master = self.loader.load_master()
        layer_names = self._discover_layer_names(master)

        # Filter to single layer if specified
        if layer:
            layer_names = [layer]

        # Validate each layer
        for layer_name in layer_names:
            layer_path = self.db_root / layer_name
            if not layer_path.exists():
                continue

            layer_result = self._validate_layer(layer_name, master, mode)
            result.errors.extend(layer_result.errors)
            result.warnings.extend(layer_result.warnings)
            result.changes.extend(layer_result.changes)

        # Introspect DuckDB databases in repair mode
        if mode == "repair" and not layer:
            db_result = self._introspect_databases(master)
            result.changes.extend(db_result.changes)

        result.valid = len(result.errors) == 0
        return result

    def _validate_layer(
        self,
        layer_name: str,
        master: MasterSchema,
        mode: Literal["strict", "repair", "warn"],
    ) -> ValidationResult:
        """Validate a single layer."""
        result = ValidationResult(valid=True)
        layer_path = self.db_root / layer_name

        # Load existing schema
        schema = self.loader.load_layer(layer_name)

        # Scan for parquet files
        actual_files = self._dataset_files(layer_path, self._scan_parquet_files(layer_name, layer_path))
        schema_paths = set(schema.datasets.keys())
        actual_paths = set(actual_files)

        # Check for files not in schema
        missing_in_schema = actual_paths - schema_paths
        for path in missing_in_schema:
            if mode == "strict":
                result.errors.append(f"{layer_name}: File '{path}.parquet' not in schema")
            elif mode == "repair":
                # Auto-add to schema
                file_path = actual_files[path]
                dataset = self._extract_schema_from_parquet(layer_name, path, file_path)
                schema.datasets[path] = dataset
                result.changes.append(f"{layer_name}: Added '{path}' to schema")
            else:  # warn
                result.warnings.append(f"{layer_name}: File '{path}.parquet' not in schema")

        # Check for schema entries without files
        missing_files = schema_paths - actual_paths
        for path in missing_files:
            if mode == "strict":
                result.errors.append(f"{layer_name}: Schema entry '{path}' has no file")
            elif mode == "repair":
                del schema.datasets[path]
                result.changes.append(f"{layer_name}: Removed '{path}' from schema (no file)")
            else:  # warn
                result.warnings.append(f"{layer_name}: Schema entry '{path}' has no file")

        # Validate existing entries
        for path in schema_paths & actual_paths:
            file_path = actual_files[path]
            expected = schema.datasets[path]

            # Read actual schema from parquet
            actual_cols = self._read_parquet_schema(file_path)

            # Compare columns
            col_errors = self._compare_columns(expected.columns, actual_cols)
            if col_errors:
                if mode == "strict":
                    for err in col_errors:
                        result.errors.append(f"{layer_name}/{path}: {err}")
                elif mode == "repair":
                    # Update schema to match file
                    schema.datasets[path].columns = actual_cols
                    result.changes.append(f"{layer_name}: Updated columns for '{path}'")
                else:  # warn
                    for err in col_errors:
                        result.warnings.append(f"{layer_name}/{path}: {err}")

            actual_metadata = self._derive_dataset_metadata(layer_name, path)
            metadata_errors = self._compare_dataset_metadata(expected, actual_metadata)
            if metadata_errors:
                if mode == "strict":
                    for err in metadata_errors:
                        result.errors.append(f"{layer_name}/{path}: {err}")
                elif mode == "repair":
                    metadata_changed = self._apply_dataset_metadata(
                        schema.datasets[path],
                        actual_metadata,
                    )
                    if metadata_changed:
                        result.changes.append(f"{layer_name}: Updated metadata for '{path}'")
                else:  # warn
                    for err in metadata_errors:
                        result.warnings.append(f"{layer_name}/{path}: {err}")
            elif mode == "repair":
                self._apply_dataset_metadata(schema.datasets[path], actual_metadata)

            # Check compression
            compression = self._check_compression(file_path)
            expected_compression = master.conventions.get("compression", "zstd")
            if compression and compression.lower() != expected_compression.lower():
                msg = f"{layer_name}/{path}: Compression is '{compression}', expected '{expected_compression}'"
                if mode == "strict":
                    result.errors.append(msg)
                else:
                    result.warnings.append(msg)

            # Update row count and date range in repair mode
            if mode == "repair":
                stats = self._extract_stats(file_path)
                if stats:
                    schema.datasets[path].row_count = stats.get("row_count")
                    schema.datasets[path].date_range = stats.get("date_range")
                    schema.datasets[path].last_validated = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Save updated schema in repair mode
        if mode == "repair" and result.changes:
            self.loader.save_layer(schema)

        return result

    @staticmethod
    def _dataset_files(layer_path: Path, files: list[Path]) -> dict[str, Path]:
        """Key each dataset by path; partitions (``key=value`` dirs, ``chunk-*`` files) fold into one
        entry such as ``1d/example/filings/quarter=*/submission``, validated against its latest file."""
        datasets: dict[str, Path] = {}
        for file_path in files:  # sorted, so the latest partition wins
            relative = file_path.relative_to(layer_path)
            if delta_read.is_delta_dir(file_path):  # a Delta table is one dataset keyed by its directory
                datasets[relative.as_posix()] = file_path
                continue
            parts = [
                f"{part.split('=', 1)[0]}=*" if "=" in part else part
                for part in relative.with_suffix("").parts
            ]
            if parts[-1].startswith("chunk-"):
                parts[-1] = "chunk-*"
            datasets["/".join(parts)] = file_path
        return datasets

    def _scan_parquet_files(self, layer_name: str, layer_path: Path) -> list[Path]:
        """Find all parquet files and Delta table directories (one entry each) in a layer directory."""
        parquet_files: list[Path] = []
        files, tables = delta_read.walk_lake(layer_path)
        for file_path in sorted([*files, *tables]):
            relative_parts = file_path.relative_to(layer_path).parts
            if any(part in self.IGNORED_PATH_COMPONENTS for part in relative_parts):
                continue
            if any(
                marker in part
                for part in relative_parts
                for marker in self.IGNORED_PATH_MARKERS
            ):
                continue
            if layer_name == "features" and not self._is_canonical_feature_dataset_path(relative_parts):
                continue
            parquet_files.append(file_path)
        return sorted(parquet_files)

    def _is_canonical_feature_dataset_path(self, relative_parts: tuple[str, ...]) -> bool:
        """Return whether a features-layer parquet path uses canonical FeatureStore layout."""
        if relative_parts[-1] != "data.parquet":
            # A Delta feature table is the category directory itself.
            if len(relative_parts) < 2 or not delta_read.is_delta_dir(self.db_root / "features" / Path(*relative_parts)):
                return False
            relative_parts = (*relative_parts, "data.parquet")
        if len(relative_parts) < 3:
            return False

        resolution = relative_parts[0]
        category_parts = relative_parts[1:-1]

        if resolution not in self.FEATURE_RESOLUTIONS:
            return False
        if not category_parts:
            return False
        if any(part.startswith("_") for part in category_parts):
            return False
        return True

    def _read_parquet_schema(self, path: Path) -> list[ColumnSchema]:
        """Extract column schema from a parquet file or a Delta table."""
        try:
            if delta_read.is_delta_dir(path):
                schema = delta_read.lake_scan(path).collect_schema().to_arrow()
            else:
                schema = pq.ParquetFile(path).schema_arrow
            columns = []
            for i in range(len(schema)):
                field = schema.field(i)
                type_str = str(field.type)
                mapped_type = PYARROW_TYPE_MAP.get(type_str, type_str)
                columns.append(ColumnSchema(
                    name=field.name,
                    type=mapped_type,
                    nullable=field.nullable,
                ))
            return columns
        except Exception as e:
            logger.warning(f"Failed to read schema from {path}: {e}")
            return []

    def _extract_schema_from_parquet(
        self,
        layer_name: str,
        path: str,
        file_path: Path,
    ) -> DatasetSchema:
        """Extract full schema info from a parquet file."""
        columns = self._read_parquet_schema(file_path)
        stats = self._extract_stats(file_path)
        metadata = self._derive_dataset_metadata(layer_name, path)

        return DatasetSchema(
            path=path,
            columns=columns,
            source=metadata["source"],
            asset=metadata["asset"],
            product=metadata["product"],
            exchange=metadata["exchange"],
            resolution=metadata["resolution"],
            row_count=stats.get("row_count") if stats else None,
            date_range=stats.get("date_range") if stats else None,
            last_validated=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    def _extract_stats(self, path: Path) -> dict[str, Any] | None:
        """Extract statistics from a parquet file or a Delta table."""
        try:
            import polars as pl

            if delta_read.is_delta_dir(path):
                from data.platform.storage import delta_tables as dtab

                row_count = dtab.table_stats(delta_read.path_ref(path)).rows
            else:
                row_count = pq.ParquetFile(path).metadata.num_rows

            # Try to get date range from timestamp column
            date_range = None
            try:
                df = (
                    delta_read.lake_scan(path).select("timestamp").collect()
                    if delta_read.is_delta_dir(path)
                    else pl.read_parquet(path, columns=["timestamp"])
                )
                if "timestamp" in df.columns:
                    min_ts = df["timestamp"].min()
                    max_ts = df["timestamp"].max()
                    if min_ts is not None and max_ts is not None:
                        date_range = {
                            "start": self._coerce_date_string(min_ts),
                            "end": self._coerce_date_string(max_ts),
                        }
            except Exception:
                pass

            return {"row_count": row_count, "date_range": date_range}
        except Exception as e:
            logger.warning(f"Failed to extract stats from {path}: {e}")
            return None

    def _check_compression(self, path: Path) -> str | None:
        """Check the compression used in a parquet file (a Delta table's first live data file)."""
        try:
            if delta_read.is_delta_dir(path):
                from deltalake import DeltaTable

                live = DeltaTable(str(path)).file_uris()
                if not live:
                    return None
                from urllib.parse import unquote, urlparse

                path = Path(unquote(urlparse(live[0]).path))  # absolute, percent-encoded
            pf = pq.ParquetFile(path)
            # Get compression from first row group
            if pf.metadata.num_row_groups > 0:
                rg = pf.metadata.row_group(0)
                if rg.num_columns > 0:
                    col = rg.column(0)
                    return col.compression
        except Exception as e:
            logger.warning(f"Failed to check compression for {path}: {e}")
        return None

    def _derive_dataset_metadata(self, layer_name: str, path: str) -> dict[str, str | None]:
        """Derive dataset metadata from canonical path structure."""
        metadata = {
            "source": None,
            "asset": None,
            "product": None,
            "exchange": None,
            "resolution": None,
        }

        if layer_name != "data/raw":
            return metadata

        parts = Path(path).parts
        if not parts:
            return metadata

        metadata["resolution"] = parts[0]
        if len(parts) < 2:
            return metadata

        metadata["source"] = parts[1]
        remainder = list(parts[2:])
        if not remainder:
            return metadata

        stem = remainder[-1]
        if remainder[0] in self.RAW_LAYOUT_PRODUCTS:
            metadata["product"] = remainder[0]
            if metadata["product"] == "orderbook":
                asset, exchange = self._parse_raw_orderbook_stem(
                    stem=stem,
                    resolution=metadata["resolution"],
                )
                metadata["asset"] = asset
                metadata["exchange"] = exchange
                return metadata

            if len(remainder) >= 2:
                metadata["exchange"] = remainder[1]
            metadata["asset"] = self._parse_raw_asset_from_stem(
                stem=stem,
                product=metadata["product"],
                exchange=metadata["exchange"],
                resolution=metadata["resolution"],
            )

        return metadata

    def _parse_raw_orderbook_stem(
        self,
        *,
        stem: str,
        resolution: str | None,
    ) -> tuple[str | None, str | None]:
        """Parse asset and exchange from an orderbook dataset stem."""
        if not stem or not resolution:
            return None, None

        for suffix in (f"_{resolution}_summary", f"_{resolution}_levels"):
            if stem.endswith(suffix):
                core = stem[: -len(suffix)]
                if "_" not in core:
                    return core.upper(), None
                asset, exchange = core.split("_", 1)
                return asset.upper(), exchange

        return None, None

    def _parse_raw_asset_from_stem(
        self,
        *,
        stem: str,
        product: str | None,
        exchange: str | None,
        resolution: str | None,
    ) -> str | None:
        """Parse the asset symbol from a canonical raw dataset stem."""
        if not stem or not product or not resolution:
            return None

        if exchange:
            suffixes = (
                f"_{product}_{exchange}_{resolution}",
                f"_{product}_{exchange}",
            )
            for suffix in suffixes:
                if stem.endswith(suffix):
                    asset = stem[: -len(suffix)]
                    if asset:
                        return asset.upper()

        return None

    def _compare_dataset_metadata(
        self,
        expected: DatasetSchema,
        actual_metadata: dict[str, str | None],
    ) -> list[str]:
        """Compare derived dataset metadata against schema metadata."""
        errors: list[str] = []
        for field_name in ("source", "asset", "product", "exchange", "resolution"):
            expected_value = getattr(expected, field_name)
            actual_value = actual_metadata[field_name]
            if expected_value != actual_value:
                errors.append(
                    f"{field_name} metadata mismatch: schema={expected_value!r} actual={actual_value!r}"
                )
        return errors

    def _apply_dataset_metadata(
        self,
        dataset: DatasetSchema,
        metadata: dict[str, str | None],
    ) -> bool:
        """Apply derived dataset metadata to an existing schema entry."""
        changed = False
        for field_name in ("source", "asset", "product", "exchange", "resolution"):
            new_value = metadata[field_name]
            if getattr(dataset, field_name) != new_value:
                setattr(dataset, field_name, new_value)
                changed = True
        return changed

    def _coerce_date_string(self, value: Any) -> str:
        """Format timestamp-like values as YYYY-MM-DD for schema metadata."""
        if isinstance(value, datetime):
            return value.date().isoformat()
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()[:10]
            except Exception:
                pass
        if isinstance(value, (int, float)):
            timestamp = float(value)
            abs_value = abs(timestamp)
            if abs_value >= 1e18:
                timestamp /= 1_000_000_000
            elif abs_value >= 1e15:
                timestamp /= 1_000_000
            elif abs_value >= 1e12:
                timestamp /= 1_000
            try:
                return datetime.fromtimestamp(timestamp, UTC).date().isoformat()
            except (OverflowError, OSError, ValueError):
                return str(value)
        return str(value)[:10]

    def _compare_columns(
        self,
        expected: list[ColumnSchema],
        actual: list[ColumnSchema],
    ) -> list[str]:
        """Compare expected and actual column schemas."""
        errors = []

        expected_names = {c.name for c in expected}
        actual_names = {c.name for c in actual}

        # Check for missing columns
        missing = expected_names - actual_names
        for name in missing:
            errors.append(f"Missing column '{name}'")

        # Check for extra columns
        extra = actual_names - expected_names
        for name in extra:
            errors.append(f"Extra column '{name}' not in schema")

        # Check type mismatches for common columns
        expected_map = {c.name: c for c in expected}
        actual_map = {c.name: c for c in actual}

        for name in expected_names & actual_names:
            expected_column = expected_map[name]
            actual_column = actual_map[name]
            exp_type = expected_column.type
            act_type = actual_column.type
            if exp_type != act_type:
                errors.append(f"Column '{name}' type mismatch: expected '{exp_type}', got '{act_type}'")
            if expected_column.nullable != actual_column.nullable:
                errors.append(
                    f"Column '{name}' nullable mismatch: expected '{expected_column.nullable}', "
                    f"got '{actual_column.nullable}'"
                )

        return errors

    def _introspect_duckdb(self, db_path: Path) -> DatabaseSchema:
        """Introspect a DuckDB database file and return its schema."""
        import duckdb

        name = db_path.stem
        rel_path = str(db_path.relative_to(self.db_root))
        tables: list[DatabaseTableSchema] = []

        try:
            conn = duckdb.connect(str(db_path), read_only=True)

            # Get all tables
            table_rows = conn.execute(
                "SELECT table_name FROM duckdb_tables() ORDER BY table_name"
            ).fetchall()

            for (table_name,) in table_rows:
                # Get columns
                col_rows = conn.execute(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM duckdb_columns() "
                    "WHERE table_name = ? ORDER BY column_index",
                    [table_name],
                ).fetchall()

                columns = []
                for col_name, col_type, is_nullable in col_rows:
                    mapped_type = DUCKDB_TYPE_MAP.get(col_type, col_type)
                    columns.append(ColumnSchema(
                        name=col_name,
                        type=mapped_type,
                        nullable=is_nullable,
                    ))

                # Get row count
                row_count = conn.execute(
                    f'SELECT COUNT(*) FROM "{table_name}"'
                ).fetchone()[0]

                # Get constraints
                constraints: list[str] = []
                try:
                    constraint_rows = conn.execute(
                        "SELECT constraint_type, constraint_column_names "
                        "FROM duckdb_constraints() "
                        "WHERE table_name = ?",
                        [table_name],
                    ).fetchall()
                    for ctype, ccols in constraint_rows:
                        col_list = ", ".join(ccols) if ccols else ""
                        constraints.append(f"{ctype} ({col_list})")
                except Exception:
                    pass

                tables.append(DatabaseTableSchema(
                    name=table_name,
                    columns=columns,
                    row_count=row_count,
                    constraints=constraints,
                ))

            conn.close()
        except Exception as e:
            logger.warning(f"Failed to introspect DuckDB {db_path}: {e}")

        return DatabaseSchema(name=name, path=rel_path, tables=tables)

    def _introspect_databases(self, master: MasterSchema) -> ValidationResult:
        """Scan for DuckDB files and update the master schema's databases section."""
        result = ValidationResult(valid=True)

        duckdb_files = sorted(self.db_root.glob("*.duckdb"))
        if not duckdb_files:
            return result

        new_databases = []
        for db_file in duckdb_files:
            db_schema = self._introspect_duckdb(db_file)
            new_databases.append(db_schema.to_dict())
            table_count = len(db_schema.tables)
            result.changes.append(
                f"databases: Introspected '{db_schema.name}' ({table_count} tables)"
            )

        master.databases = new_databases
        self.loader.save_master(master)

        return result

    def generate_initial_schemas(self) -> None:
        """One-time generation of schemas from existing files.

        If a master SCHEMA.yaml already exists, reads layer names from it.
        Otherwise generates a skeleton master with the default 3 layers.
        """
        # Try to load existing master to get all layer definitions
        existing_master = self.loader.load_master()
        layer_names = [
            layer["name"]
            for layer in existing_master.layers
            if isinstance(layer, dict) and isinstance(layer.get("name"), str)
        ]

        if layer_names:
            # Use existing master — don't overwrite it
            master = existing_master
        else:
            # No master or no layers defined — generate skeleton
            master = MasterSchema(
                version=1,
                name="quant-factory-data",
                description="Quantitative trading data lake",
                conventions={
                    "compression": "zstd",
                    "compression_level": 3,
                    "timestamp_column": "timestamp",
                    "timestamp_format": "datetime64[us]",
                },
                naming_patterns={
                    "data/raw": "{asset}_{product}_{exchange}_{resolution}.parquet",
                    "data/corrected": "same path as the data/raw dataset it corrects",
                    "data/derived": "{resolution}/{domain}/{dataset_family}/{dataset}.parquet",
                    "features": "{resolution}/{category}/data.parquet",
                    "signals": "{signal_name}/predictions.parquet",
                },
                layers=[
                    {"name": "data/raw", "description": "Untouched provider landings", "path": "data/raw/"},
                    {"name": "data/corrected", "description": "Raw mirrors with point-in-time corrections and flag columns", "path": "data/corrected/"},
                    {"name": "data/derived", "description": "Reusable calculated market data products", "path": "data/derived/"},
                    {"name": "features", "description": "Signal-ready assembled datasets", "path": "features/"},
                    {"name": "signals", "description": "Trading signals and predictions", "path": "signals/", "versioned": False},
                    {"name": "strategies", "description": "Strategy backtest outputs and run artifacts", "path": "strategies/", "versioned": False},
                ],
            )
            layer_names = list(self.LAYERS)

        # Introspect DuckDB databases
        duckdb_files = sorted(self.db_root.glob("*.duckdb"))
        if duckdb_files:
            databases = []
            for db_file in duckdb_files:
                db_schema = self._introspect_duckdb(db_file)
                databases.append(db_schema.to_dict())
                logger.info(f"Introspected {db_schema.name}.duckdb ({len(db_schema.tables)} tables)")
            master.databases = databases

        self.loader.save_master(master)
        logger.info("Generated master SCHEMA.yaml")

        # Generate layer schemas
        for layer_name in layer_names:
            layer_path = self.db_root / layer_name
            if not layer_path.exists():
                continue

            datasets = {}
            for parquet_file in self._scan_parquet_files(layer_name, layer_path):
                rel_path = str(parquet_file.relative_to(layer_path)).replace(".parquet", "")
                datasets[rel_path] = self._extract_schema_from_parquet(
                    layer_name,
                    rel_path,
                    parquet_file,
                )

            schema = LayerSchema(
                name=layer_name,
                description=f"Layer: {layer_name}",
                datasets=datasets,
            )
            self.loader.save_layer(schema)
            logger.info(f"Generated {layer_name}/SCHEMA.yaml with {len(datasets)} datasets")


class SchemaValidationError(Exception):
    """Raised when schema validation fails in strict mode."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Schema validation failed with {len(errors)} errors")
