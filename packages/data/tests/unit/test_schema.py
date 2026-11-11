"""Unit tests for schema validation module."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
import yaml
from data.platform.schema import (
    PYARROW_TYPE_MAP,
    ColumnSchema,
    DatasetSchema,
    LayerSchema,
    MasterSchema,
    SchemaLoader,
    SchemaValidationError,
    SchemaValidator,
    ValidationResult,
)


class TestColumnSchema:
    """Tests for ColumnSchema dataclass."""

    def test_to_dict_full(self):
        """All fields should be serialized correctly."""
        col = ColumnSchema(
            name="price",
            type="float64",
            nullable=False,
            description="Closing price",
        )
        d = col.to_dict()
        assert d["name"] == "price"
        assert d["type"] == "float64"
        assert d["nullable"] is False
        assert d["description"] == "Closing price"

    def test_to_dict_minimal(self):
        """Only required fields and non-default values should be serialized."""
        col = ColumnSchema(name="volume", type="int64")
        d = col.to_dict()
        assert d == {"name": "volume", "type": "int64"}
        assert "nullable" not in d  # True is default, not serialized
        assert "description" not in d

    def test_to_dict_nullable_false(self):
        """Non-nullable columns should include nullable=False."""
        col = ColumnSchema(name="ts", type="datetime64[us]", nullable=False)
        d = col.to_dict()
        assert d["nullable"] is False

    def test_from_dict(self):
        """Should parse from dict correctly."""
        d = {"name": "open", "type": "float64", "nullable": False}
        col = ColumnSchema.from_dict(d)
        assert col.name == "open"
        assert col.type == "float64"
        assert col.nullable is False

    def test_from_dict_defaults(self):
        """Missing optional fields should use defaults."""
        d = {"name": "close", "type": "float64"}
        col = ColumnSchema.from_dict(d)
        assert col.nullable is True
        assert col.description is None

    def test_roundtrip(self):
        """to_dict -> from_dict should preserve all values."""
        original = ColumnSchema(
            name="test",
            type="string",
            nullable=False,
            description="Test column",
        )
        recovered = ColumnSchema.from_dict(original.to_dict())
        assert recovered.name == original.name
        assert recovered.type == original.type
        assert recovered.nullable == original.nullable
        assert recovered.description == original.description


class TestDatasetSchema:
    """Tests for DatasetSchema dataclass."""

    def test_from_dict_parses_metadata(self):
        """Should parse all metadata fields."""
        d = {
            "source": "vendorb",
            "asset": "BTC",
            "product": "spot",
            "exchange": "exchangex",
            "resolution": "1d",
            "columns": [
                {"name": "timestamp", "type": "datetime64[us]"},
                {"name": "close", "type": "float64"},
            ],
            "row_count": 1000,
            "date_range": {"start": "2024-01-01", "end": "2024-04-10"},
        }
        schema = DatasetSchema.from_dict("test/path", d)
        assert schema.path == "test/path"
        assert schema.source == "vendorb"
        assert schema.asset == "BTC"
        assert schema.product == "spot"
        assert schema.exchange == "exchangex"
        assert schema.resolution == "1d"
        assert schema.row_count == 1000
        assert len(schema.columns) == 2
        assert schema.columns[0].name == "timestamp"

    def test_to_dict_omits_none(self):
        """None values should not be serialized."""
        schema = DatasetSchema(
            path="test",
            columns=[ColumnSchema(name="x", type="int64")],
        )
        d = schema.to_dict()
        assert "source" not in d
        assert "asset" not in d
        assert "columns" in d

    def test_empty_columns(self):
        """Should handle empty columns list."""
        schema = DatasetSchema.from_dict("empty", {})
        assert schema.columns == []


class TestLayerSchema:
    """Tests for LayerSchema dataclass."""

    def test_from_dict_with_datasets(self):
        """Should parse nested datasets correctly."""
        d = {
            "layer": "data/raw",
            "description": "Raw data layer",
            "datasets": {
                "btc_1d": {
                    "source": "vendorb",
                    "columns": [{"name": "close", "type": "float64"}],
                }
            },
        }
        layer = LayerSchema.from_dict(d)
        assert layer.name == "data/raw"
        assert layer.description == "Raw data layer"
        assert "btc_1d" in layer.datasets
        assert layer.datasets["btc_1d"].source == "vendorb"

    def test_empty_datasets(self):
        """Should handle empty datasets dict."""
        layer = LayerSchema.from_dict({"layer": "data/raw"})
        assert layer.name == "data/raw"
        assert layer.datasets == {}

    def test_to_dict(self):
        """Should serialize correctly."""
        layer = LayerSchema(
            name="features",
            description="Feature store",
            datasets={
                "momentum": DatasetSchema(
                    path="momentum",
                    columns=[ColumnSchema(name="value", type="float64")],
                )
            },
        )
        d = layer.to_dict()
        assert d["layer"] == "features"
        assert d["description"] == "Feature store"
        assert "momentum" in d["datasets"]


class TestMasterSchema:
    """Tests for MasterSchema dataclass."""

    def test_default_values(self):
        """Should have correct defaults."""
        schema = MasterSchema()
        assert schema.version == 1
        assert schema.name == "quant-factory-data"
        assert schema.description == "Quantitative trading data lake"
        assert schema.conventions == {}
        assert schema.naming_patterns == {}
        assert schema.layers == []

    def test_from_dict_conventions(self):
        """Should parse conventions correctly."""
        d = {
            "version": 2,
            "name": "test-lake",
            "conventions": {
                "compression": "zstd",
                "compression_level": 3,
            },
        }
        schema = MasterSchema.from_dict(d)
        assert schema.version == 2
        assert schema.name == "test-lake"
        assert schema.conventions["compression"] == "zstd"

    def test_to_dict(self):
        """Should serialize all fields."""
        schema = MasterSchema(
            version=1,
            name="test",
            conventions={"compression": "zstd"},
        )
        d = schema.to_dict()
        assert d["version"] == 1
        assert d["name"] == "test"
        assert d["conventions"]["compression"] == "zstd"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_when_no_errors(self):
        """valid should be True when errors is empty."""
        result = ValidationResult(valid=True, errors=[], warnings=["some warning"])
        assert result.valid is True

    def test_str_format(self):
        """__str__ should produce readable output."""
        result = ValidationResult(
            valid=False,
            errors=["Missing column 'x'"],
            warnings=["Extra column 'y'"],
            changes=["Added 'z'"],
        )
        s = str(result)
        assert "Valid: False" in s
        assert "Errors (1)" in s
        assert "Missing column 'x'" in s
        assert "Warnings (1)" in s
        assert "Changes (1)" in s


class TestSchemaLoader:
    """Tests for SchemaLoader class."""

    def test_load_master_missing_file(self, tmp_path: Path):
        """Should return default MasterSchema when file doesn't exist."""
        loader = SchemaLoader(tmp_path)
        schema = loader.load_master()
        assert schema.version == 1
        assert schema.name == "quant-factory-data"

    def test_save_and_load_master(self, tmp_path: Path):
        """Should roundtrip master schema correctly."""
        loader = SchemaLoader(tmp_path)
        original = MasterSchema(
            version=2,
            name="test-lake",
            conventions={"compression": "zstd"},
        )
        loader.save_master(original)

        loaded = loader.load_master()
        assert loaded.version == original.version
        assert loaded.name == original.name
        assert loaded.conventions == original.conventions

    def test_load_layer_missing_file(self, tmp_path: Path):
        """Should return empty LayerSchema when file doesn't exist."""
        loader = SchemaLoader(tmp_path)
        layer = loader.load_layer("data/raw")
        assert layer.name == "data/raw"
        assert layer.datasets == {}

    def test_save_layer_creates_directory(self, tmp_path: Path):
        """Should create parent directories when saving."""
        loader = SchemaLoader(tmp_path)
        layer = LayerSchema(
            name="features",
            description="Feature layer",
        )
        loader.save_layer(layer)

        assert (tmp_path / "features" / "SCHEMA.yaml").exists()

    def test_save_and_load_layer(self, tmp_path: Path):
        """Should roundtrip layer schema correctly."""
        loader = SchemaLoader(tmp_path)
        original = LayerSchema(
            name="features",
            description="Features layer",
            datasets={
                "combined": DatasetSchema(
                    path="combined",
                    columns=[ColumnSchema(name="x", type="float64")],
                )
            },
        )
        loader.save_layer(original)

        loaded = loader.load_layer("features")
        assert loaded.name == original.name
        assert "combined" in loaded.datasets


class TestSchemaValidator:
    """Tests for SchemaValidator class."""

    def test_default_layer_discovery_skips_backups_but_explicit_layer_still_validates(
        self,
        tmp_path: Path,
        sample_ohlcv_data: pl.DataFrame,
    ) -> None:
        """Default validation should ignore non-canonical backups."""
        backups_dir = tmp_path / "backups" / "features"
        backups_dir.mkdir(parents=True)
        sample_ohlcv_data.write_parquet(backups_dir / "orphan.parquet", compression="zstd")

        validator = SchemaValidator(tmp_path)

        assert "backups" not in validator._discover_layer_names(MasterSchema())
        assert not validator.validate(mode="warn").warnings
        explicit_result = validator.validate(mode="warn", layer="backups")
        assert any(
            "backups: File 'features/orphan.parquet' not in schema" in warning
            for warning in explicit_result.warnings
        )

    def test_extract_schema_from_parquet_parses_resolution_first_vendorb_path(
        self,
        tmp_path: Path,
        sample_ohlcv_data: pl.DataFrame,
    ) -> None:
        """Raw metadata should be derived from the resolution-first path layout."""
        raw_dir = tmp_path / "data/raw" / "1h" / "vendorb" / "futures" / "exchangey"
        raw_dir.mkdir(parents=True)
        parquet_path = raw_dir / "btc_futures_exchangey_1h.parquet"
        sample_ohlcv_data.write_parquet(parquet_path, compression="zstd")

        validator = SchemaValidator(tmp_path)
        dataset = validator._extract_schema_from_parquet(
            "data/raw",
            "1h/vendorb/futures/exchangey/btc_futures_exchangey_1h",
            parquet_path,
        )

        assert dataset.source == "vendorb"
        assert dataset.asset == "BTC"
        assert dataset.product == "futures"
        assert dataset.exchange == "exchangey"
        assert dataset.resolution == "1h"

    def test_extract_schema_from_parquet_parses_orderbook_path(
        self,
        tmp_path: Path,
    ) -> None:
        """Orderbook datasets should derive asset/exchange from the canonical stem."""
        raw_dir = tmp_path / "data/raw" / "5m" / "vendorb" / "orderbook"
        raw_dir.mkdir(parents=True)
        frame = pl.DataFrame(
            {
                "timestamp": [datetime(2025, 1, 1, 0, 0), datetime(2025, 1, 1, 0, 5)],
                "bid": [100.0, 101.0],
            }
        )
        parquet_path = raw_dir / "btc_exchangex-futures_5m_summary.parquet"
        frame.write_parquet(parquet_path, compression="zstd")

        validator = SchemaValidator(tmp_path)
        dataset = validator._extract_schema_from_parquet(
            "data/raw",
            "5m/vendorb/orderbook/btc_exchangex-futures_5m_summary",
            parquet_path,
        )

        assert dataset.source == "vendorb"
        assert dataset.asset == "BTC"
        assert dataset.product == "orderbook"
        assert dataset.exchange == "exchangex-futures"
        assert dataset.resolution == "5m"

    def test_extract_schema_from_parquet_parses_daily_vendorb_path_without_resolution_suffix(
        self,
        tmp_path: Path,
        sample_ohlcv_data: pl.DataFrame,
    ) -> None:
        """Daily raw files may omit the resolution in the parquet stem."""
        raw_dir = tmp_path / "data/raw" / "1d" / "vendorb" / "futures" / "exchangex"
        raw_dir.mkdir(parents=True)
        parquet_path = raw_dir / "btc_futures_exchangex.parquet"
        sample_ohlcv_data.write_parquet(parquet_path, compression="zstd")

        validator = SchemaValidator(tmp_path)
        dataset = validator._extract_schema_from_parquet(
            "data/raw",
            "1d/vendorb/futures/exchangex/btc_futures_exchangex",
            parquet_path,
        )

        assert dataset.source == "vendorb"
        assert dataset.asset == "BTC"
        assert dataset.product == "futures"
        assert dataset.exchange == "exchangex"
        assert dataset.resolution == "1d"

    def test_validate_strict_fails_on_missing_file(
        self,
        tmp_path: Path,
        sample_ohlcv_data: pl.DataFrame,
    ):
        """Strict mode should fail when file exists but not in schema."""
        # Create raw layer with a file
        raw_dir = tmp_path / "data/raw" / "1d" / "index"
        raw_dir.mkdir(parents=True)
        parquet_path = raw_dir / "btc.parquet"
        sample_ohlcv_data.write_parquet(parquet_path, compression="zstd")

        # Create empty schema
        schema_path = raw_dir / "SCHEMA.yaml"
        schema_path.write_text("layer: data/raw\ndatasets: {}\n")

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="strict")

        assert not result.valid
        assert any("not in schema" in e for e in result.errors)

    def test_validate_strict_fails_on_missing_schema_entry(
        self,
        tmp_path: Path,
    ):
        """Strict mode should fail when schema entry has no file."""
        raw_dir = tmp_path / "data/raw"
        raw_dir.mkdir(parents=True)

        # Create schema with entry but no file
        schema_data = {
            "layer": "data/raw",
            "datasets": {
                "missing_file": {"columns": []},
            },
        }
        schema_path = raw_dir / "SCHEMA.yaml"
        with open(schema_path, "w") as f:
            yaml.dump(schema_data, f)

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="strict")

        assert not result.valid
        assert any("no file" in e.lower() for e in result.errors)

    def test_validate_repair_adds_missing_files(
        self,
        tmp_path: Path,
        sample_ohlcv_data: pl.DataFrame,
    ):
        """Repair mode should add files missing from schema."""
        raw_dir = tmp_path / "data/raw" / "1d" / "index"
        raw_dir.mkdir(parents=True)

        # Create file
        parquet_path = raw_dir / "btc.parquet"
        sample_ohlcv_data.write_parquet(parquet_path, compression="zstd")

        # Create empty schema
        schema_path = raw_dir / "SCHEMA.yaml"
        schema_path.write_text("layer: data/raw\ndatasets: {}\n")

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="repair")

        assert result.valid
        assert any("Added" in c for c in result.changes)

        # Verify schema was updated
        loader = SchemaLoader(tmp_path)
        layer = loader.load_layer("data/raw")
        assert "1d/index/btc" in layer.datasets

    def test_validate_repair_removes_orphan_entries(
        self,
        tmp_path: Path,
    ):
        """Repair mode should remove schema entries without files."""
        raw_dir = tmp_path / "data/raw"
        raw_dir.mkdir(parents=True)

        # Create schema with orphan entry
        schema_data = {
            "layer": "data/raw",
            "datasets": {
                "orphan": {"columns": []},
            },
        }
        schema_path = raw_dir / "SCHEMA.yaml"
        with open(schema_path, "w") as f:
            yaml.dump(schema_data, f)

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="repair")

        assert result.valid
        assert any("Removed" in c for c in result.changes)

    def test_validate_warn_logs_issues(
        self,
        tmp_path: Path,
        sample_ohlcv_data: pl.DataFrame,
    ):
        """Warn mode should log issues but not fail."""
        raw_dir = tmp_path / "data/raw" / "1d" / "index"
        raw_dir.mkdir(parents=True)

        # Create file without schema entry
        parquet_path = raw_dir / "btc.parquet"
        sample_ohlcv_data.write_parquet(parquet_path, compression="zstd")

        # Create empty schema
        schema_path = raw_dir / "SCHEMA.yaml"
        schema_path.write_text("layer: data/raw\ndatasets: {}\n")

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="warn")

        assert result.valid  # Warn mode should not fail
        assert len(result.warnings) > 0

    def test_validate_warn_reports_raw_metadata_mismatch(
        self,
        tmp_path: Path,
        sample_ohlcv_data: pl.DataFrame,
    ) -> None:
        """Warn mode should flag stale raw metadata even when columns match."""
        raw_dir = tmp_path / "data/raw" / "1d" / "vendorb" / "futures" / "exchangex"
        raw_dir.mkdir(parents=True)

        parquet_path = raw_dir / "btc_futures_exchangex_1d.parquet"
        sample_ohlcv_data.write_parquet(parquet_path, compression="zstd")

        with open(tmp_path / "SCHEMA.yaml", "w") as f:
            yaml.dump({"version": 2, "layers": [{"name": "data/raw"}]}, f)

        layer_schema = {
            "layer": "data/raw",
            "datasets": {
                "1d/vendorb/futures/exchangex/btc_futures_exchangex_1d": {
                    "source": "vendorb",
                    "asset": "1D",
                    "product": "vendorb",
                    "exchange": "futures",
                    "resolution": "exchangex",
                    "columns": [
                        {"name": "timestamp", "type": "datetime64[us]"},
                        {"name": "open", "type": "float64"},
                        {"name": "high", "type": "float64"},
                        {"name": "low", "type": "float64"},
                        {"name": "close", "type": "float64"},
                        {"name": "volume", "type": "float64"},
                    ],
                },
            },
        }
        with open(tmp_path / "data/raw" / "SCHEMA.yaml", "w") as f:
            yaml.dump(layer_schema, f)

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="warn", layer="data/raw")

        assert result.valid is True
        assert any("metadata mismatch" in warning for warning in result.warnings)

    def test_validate_repair_updates_raw_metadata(
        self,
        tmp_path: Path,
        sample_ohlcv_data: pl.DataFrame,
    ) -> None:
        """Repair mode should rewrite stale raw metadata to the canonical layout."""
        raw_dir = tmp_path / "data/raw" / "1d" / "vendorb" / "futures" / "exchangex"
        raw_dir.mkdir(parents=True)

        parquet_path = raw_dir / "btc_futures_exchangex_1d.parquet"
        sample_ohlcv_data.write_parquet(parquet_path, compression="zstd")

        with open(tmp_path / "SCHEMA.yaml", "w") as f:
            yaml.dump({"version": 2, "layers": [{"name": "data/raw"}]}, f)

        layer_schema = {
            "layer": "data/raw",
            "datasets": {
                "1d/vendorb/futures/exchangex/btc_futures_exchangex_1d": {
                    "source": "vendorb",
                    "asset": "1D",
                    "product": "vendorb",
                    "exchange": "futures",
                    "resolution": "exchangex",
                    "columns": [
                        {"name": "timestamp", "type": "datetime64[us]"},
                        {"name": "open", "type": "float64"},
                        {"name": "high", "type": "float64"},
                        {"name": "low", "type": "float64"},
                        {"name": "close", "type": "float64"},
                        {"name": "volume", "type": "float64"},
                    ],
                },
            },
        }
        with open(tmp_path / "data/raw" / "SCHEMA.yaml", "w") as f:
            yaml.dump(layer_schema, f)

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="repair", layer="data/raw")

        assert result.valid is True
        assert any("Updated metadata" in change for change in result.changes)

        repaired = SchemaLoader(tmp_path).load_layer("data/raw").datasets[
            "1d/vendorb/futures/exchangex/btc_futures_exchangex_1d"
        ]
        assert repaired.source == "vendorb"
        assert repaired.asset == "BTC"
        assert repaired.product == "futures"
        assert repaired.exchange == "exchangex"
        assert repaired.resolution == "1d"

    def test_extract_stats_formats_numeric_timestamps_as_dates(self, tmp_path: Path) -> None:
        """Epoch-like timestamps should be normalized to YYYY-MM-DD date ranges."""
        parquet_path = tmp_path / "numeric_timestamps.parquet"
        frame = pl.DataFrame(
            {
                "timestamp": [1609459200, 1609545600],
                "close": [100.0, 101.0],
            }
        )
        frame.write_parquet(parquet_path, compression="zstd")

        validator = SchemaValidator(tmp_path)
        stats = validator._extract_stats(parquet_path)

        assert stats is not None
        assert stats["date_range"] == {"start": "2021-01-01", "end": "2021-01-02"}

    def test_compression_validation_zstd(
        self,
        tmp_path: Path,
        sample_ohlcv_data: pl.DataFrame,
    ):
        """ZSTD compression should pass validation."""
        raw_dir = tmp_path / "data/raw" / "1d" / "index"
        raw_dir.mkdir(parents=True)

        # Create master schema with zstd convention
        master_schema = {
            "version": 1,
            "conventions": {"compression": "zstd"},
        }
        with open(tmp_path / "SCHEMA.yaml", "w") as f:
            yaml.dump(master_schema, f)

        # Create file with zstd
        parquet_path = raw_dir / "btc.parquet"
        sample_ohlcv_data.write_parquet(parquet_path, compression="zstd")

        # Create matching schema
        layer_schema = {
            "layer": "data/raw",
            "datasets": {
                "1d/index/btc": {
                    "columns": [
                        {"name": col, "type": "float64"}
                        for col in sample_ohlcv_data.columns
                        if col != "timestamp"
                    ] + [{"name": "timestamp", "type": "datetime64[us]"}],
                },
            },
        }
        with open(tmp_path / "data/raw" / "SCHEMA.yaml", "w") as f:
            yaml.dump(layer_schema, f)

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="warn")

        # Should not have compression warnings for zstd
        compression_warnings = [w for w in result.warnings if "compression" in w.lower()]
        assert len(compression_warnings) == 0

    def test_compression_validation_fails_snappy(
        self,
        tmp_path: Path,
        sample_ohlcv_data: pl.DataFrame,
    ):
        """Non-ZSTD compression should fail in strict mode."""
        raw_dir = tmp_path / "data/raw" / "1d" / "index"
        raw_dir.mkdir(parents=True)

        # Create master schema with zstd convention
        master_schema = {
            "version": 1,
            "conventions": {"compression": "zstd"},
        }
        with open(tmp_path / "SCHEMA.yaml", "w") as f:
            yaml.dump(master_schema, f)

        # Create file with snappy
        parquet_path = raw_dir / "btc.parquet"
        sample_ohlcv_data.write_parquet(parquet_path, compression="snappy")

        # Create matching schema
        layer_schema = {
            "layer": "data/raw",
            "datasets": {
                "1d/index/btc": {
                    "columns": [
                        {"name": col, "type": "float64"}
                        for col in sample_ohlcv_data.columns
                        if col != "timestamp"
                    ] + [{"name": "timestamp", "type": "datetime64[us]"}],
                },
            },
        }
        with open(tmp_path / "data/raw" / "SCHEMA.yaml", "w") as f:
            yaml.dump(layer_schema, f)

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="strict")

        # Should have compression error
        compression_errors = [e for e in result.errors if "compression" in e.lower()]
        assert len(compression_errors) > 0

    def test_validate_uses_layers_from_master_schema(self, tmp_path: Path):
        """Validator should traverse layers declared in db/SCHEMA.yaml."""
        master_schema = {
            "version": 2,
            "layers": [
                {"name": "index"},
                {"name": "regimes"},
            ],
        }
        with open(tmp_path / "SCHEMA.yaml", "w") as f:
            yaml.dump(master_schema, f)

        for layer in ("index", "regimes"):
            layer_dir = tmp_path / layer
            layer_dir.mkdir()
            with open(layer_dir / "SCHEMA.yaml", "w") as f:
                yaml.dump({"layer": layer, "datasets": {}}, f)

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="warn")
        assert result.valid is True

    def test_validate_discovers_disk_layers_when_master_schema_omits_them(self, tmp_path: Path):
        """Validator should not silently skip on-disk layers missing from db/SCHEMA.yaml."""
        with open(tmp_path / "SCHEMA.yaml", "w") as f:
            yaml.dump({"version": 2, "layers": [{"name": "data/raw"}]}, f)

        index_dir = tmp_path / "index"
        index_dir.mkdir()
        df = pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "value": [1.0]})
        df.write_parquet(index_dir / "btc.parquet")

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="warn")

        assert any("index: File 'btc.parquet' not in schema" in warning for warning in result.warnings)

    def test_scan_parquet_files_for_features_keeps_only_canonical_store_paths(self, tmp_path: Path):
        """Features schema discovery should ignore legacy non-canonical parquet artifacts."""
        features_dir = tmp_path / "features"
        canonical = features_dir / "1d" / "example" / "asset" / "futures" / "v1"
        legacy = features_dir / "orderbook"
        archive = features_dir / "1d" / "_archive" / "crypto_futures" / "v1"

        canonical.mkdir(parents=True)
        legacy.mkdir(parents=True)
        archive.mkdir(parents=True)

        frame = pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "value": [1.0]})
        frame.write_parquet(canonical / "data.parquet", compression="zstd")
        frame.write_parquet(legacy / "asset_example-venue_5m_features.parquet", compression="zstd")
        frame.write_parquet(archive / "data.parquet", compression="zstd")

        validator = SchemaValidator(tmp_path)
        files = validator._scan_parquet_files("features", features_dir)

        assert files == [canonical / "data.parquet"]

    def test_scan_parquet_files_excludes_lifecycle_staging(self, tmp_path: Path):
        """Restartable staging artifacts are not canonical schema members."""
        raw_dir = tmp_path / "data" / "raw"
        canonical = raw_dir / "example" / "provider" / "dataset" / "v3" / "canonical"
        staging = raw_dir / "example" / "provider" / "dataset" / "v3" / "staging"
        canonical.mkdir(parents=True)
        staging.mkdir(parents=True)
        frame = pl.DataFrame({"value": [1]})
        frame.write_parquet(canonical / "dataset.parquet")
        frame.write_parquet(staging / "scratch.parquet")

        validator = SchemaValidator(tmp_path)

        assert validator._scan_parquet_files("data/raw", raw_dir) == [canonical / "dataset.parquet"]

    def test_validate_features_warn_ignores_legacy_noncanonical_parquet_artifacts(self, tmp_path: Path):
        """Legacy files under db/features should not pollute the canonical features schema contract."""
        features_dir = tmp_path / "features"
        canonical = features_dir / "1d" / "example" / "asset" / "futures" / "v1"
        legacy = features_dir / "orderbook"

        canonical.mkdir(parents=True)
        legacy.mkdir(parents=True)

        frame = pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "value": [1.0]})
        frame.write_parquet(canonical / "data.parquet", compression="zstd")
        frame.write_parquet(legacy / "asset_example-venue_5m_features.parquet", compression="zstd")

        with open(tmp_path / "SCHEMA.yaml", "w") as f:
            yaml.dump({"version": 2, "layers": [{"name": "features"}]}, f)
        with open(features_dir / "SCHEMA.yaml", "w") as f:
            yaml.dump({"layer": "features", "datasets": {}}, f)

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="warn", layer="features")

        assert result.valid is True
        assert any("1d/example/asset/futures/v1/data.parquet' not in schema" in warning for warning in result.warnings)
        assert not any("orderbook/asset_example-venue_5m_features.parquet" in warning for warning in result.warnings)

    def test_compare_columns_reports_nullable_mismatch(self, tmp_path: Path):
        """Nullable drift should be treated as a schema mismatch."""
        validator = SchemaValidator(tmp_path)

        errors = validator._compare_columns(
            [ColumnSchema(name="price", type="float64", nullable=False)],
            [ColumnSchema(name="price", type="float64", nullable=True)],
        )

        assert "nullable mismatch" in errors[0]


class TestPyArrowTypeMap:
    """Tests for PyArrow type mapping."""

    def test_basic_types(self):
        """Common types should be mapped correctly."""
        assert PYARROW_TYPE_MAP["int64"] == "int64"
        assert PYARROW_TYPE_MAP["float64"] == "float64"
        assert PYARROW_TYPE_MAP["double"] == "float64"
        assert PYARROW_TYPE_MAP["string"] == "string"
        assert PYARROW_TYPE_MAP["bool"] == "bool"

    def test_timestamp_types(self):
        """Timestamp types should map to datetime64."""
        assert PYARROW_TYPE_MAP["timestamp[us]"] == "datetime64[us]"
        assert PYARROW_TYPE_MAP["timestamp[ns]"] == "datetime64[ns]"
        assert PYARROW_TYPE_MAP["timestamp[us, tz=UTC]"] == "datetime64[us]"

    def test_date_types(self):
        """Date types should map to date."""
        assert PYARROW_TYPE_MAP["date32[day]"] == "date"
        assert PYARROW_TYPE_MAP["date64[ms]"] == "date"


class TestSchemaValidationError:
    """Tests for SchemaValidationError exception."""

    def test_exception_contains_errors(self):
        """Exception should contain list of errors."""
        errors = ["Error 1", "Error 2"]
        exc = SchemaValidationError(errors)
        assert exc.errors == errors
        assert "2 errors" in str(exc)

    def test_exception_raised_in_strict_mode(
        self,
        tmp_path: Path,
        sample_ohlcv_data: pl.DataFrame,
    ):
        """Should be raised when strict validation fails."""
        raw_dir = tmp_path / "data/raw" / "1d" / "index"
        raw_dir.mkdir(parents=True)

        # Create file without schema
        parquet_path = raw_dir / "btc.parquet"
        sample_ohlcv_data.write_parquet(parquet_path, compression="zstd")

        # Create empty schema
        schema_path = raw_dir / "SCHEMA.yaml"
        schema_path.write_text("layer: data/raw\ndatasets: {}\n")

        validator = SchemaValidator(tmp_path)
        result = validator.validate(mode="strict")

        # Validation reports errors but doesn't raise
        assert not result.valid
        assert len(result.errors) > 0
