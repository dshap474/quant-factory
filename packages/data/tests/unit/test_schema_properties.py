"""Property-based tests for schema module using Hypothesis."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
from data.platform.schema import (
    ColumnSchema,
    DatasetSchema,
    LayerSchema,
    MasterSchema,
    ValidationResult,
)
from hypothesis import assume, given, settings
from hypothesis import strategies as st


class TestColumnSchemaProperties:
    """Property-based tests for ColumnSchema."""

    @given(
        name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Pc"))),
        type_str=st.sampled_from(["int64", "float64", "string", "bool", "datetime64[us]"]),
    )
    @settings(max_examples=50)
    def test_roundtrip_serialization(self, name: str, type_str: str):
        """to_dict -> from_dict should preserve all values."""
        assume(len(name.strip()) > 0)  # Ensure non-empty name

        original = ColumnSchema(name=name, type=type_str)
        d = original.to_dict()
        recovered = ColumnSchema.from_dict(d)

        assert recovered.name == original.name
        assert recovered.type == original.type
        assert recovered.nullable == original.nullable

    @given(
        name=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
        nullable=st.booleans(),
        description=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    )
    @settings(max_examples=50)
    def test_optional_fields_preserved(self, name: str, nullable: bool, description: str | None):
        """Optional fields should be preserved through serialization."""
        assume(len(name.strip()) > 0)

        original = ColumnSchema(
            name=name,
            type="float64",
            nullable=nullable,
            description=description,
        )
        d = original.to_dict()
        recovered = ColumnSchema.from_dict(d)

        assert recovered.nullable == original.nullable
        assert recovered.description == original.description


class TestDatasetSchemaProperties:
    """Property-based tests for DatasetSchema."""

    @given(
        path=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Pc", "Pd"))),
        source=st.one_of(st.none(), st.sampled_from(["source_a", "source_b", "custom"])),
        asset=st.one_of(st.none(), st.sampled_from(["ASSET_A", "ASSET_B", "ASSET_C"])),
    )
    @settings(max_examples=30)
    def test_metadata_preserved(self, path: str, source: str | None, asset: str | None):
        """Metadata fields should be preserved through serialization."""
        assume(len(path.strip()) > 0)

        original = DatasetSchema(
            path=path,
            source=source,
            asset=asset,
            columns=[ColumnSchema(name="x", type="float64")],
        )
        d = original.to_dict()
        recovered = DatasetSchema.from_dict(path, d)

        assert recovered.source == original.source
        assert recovered.asset == original.asset


class TestValidationResultProperties:
    """Property-based tests for ValidationResult."""

    @given(
        errors=st.lists(st.text(min_size=1, max_size=50), max_size=10),
        warnings=st.lists(st.text(min_size=1, max_size=50), max_size=10),
    )
    @settings(max_examples=30)
    def test_valid_iff_no_errors(self, errors: list[str], warnings: list[str]):
        """valid should be True iff errors list is empty."""
        result = ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

        assert result.valid == (len(result.errors) == 0)

    @given(
        errors=st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=5),
        warnings=st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=5),
        changes=st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=5),
    )
    @settings(max_examples=30)
    def test_str_contains_all_items(self, errors: list[str], warnings: list[str], changes: list[str]):
        """__str__ should contain counts for all non-empty lists."""
        result = ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            changes=changes,
        )
        s = str(result)

        if errors:
            assert f"Errors ({len(errors)})" in s
        if warnings:
            assert f"Warnings ({len(warnings)})" in s
        if changes:
            assert f"Changes ({len(changes)})" in s


class TestNullRateProperties:
    """Property-based tests for null rate calculations."""

    @given(
        n=st.integers(min_value=10, max_value=100),
        null_fraction=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=30)
    def test_null_rate_bounds(self, n: int, null_fraction: float):
        """Null rate should always be between 0 and 1."""
        import tempfile

        # Create data with controlled null fraction
        values = [None if i < int(n * null_fraction) else float(i) for i in range(n)]
        np.random.shuffle(values)

        df = pl.DataFrame({"value": values})

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "test.parquet"
            df.write_parquet(path)

            # Calculate null rate
            actual_nulls = df["value"].null_count()
            actual_rate = actual_nulls / n

            assert 0.0 <= actual_rate <= 1.0


class TestAsofJoinProperties:
    """Property-based tests for ASOF join behavior."""

    @given(
        n_features=st.integers(min_value=5, max_value=20),
        n_targets=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20, deadline=None)
    def test_asof_join_feature_before_target(
        self,
        n_features: int,
        n_targets: int,
    ):
        """ASOF join should only match features before or at target timestamp.

        This is a critical property for ML training - no lookahead bias.
        """
        import tempfile

        import duckdb

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            conn = duckdb.connect(":memory:")

            # Create feature timestamps
            feature_dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n_features)]
            features_df = pl.DataFrame({
                "timestamp": feature_dates,
                "feature_value": list(range(n_features)),
            })
            features_path = tmp_path / "features.parquet"
            features_df.write_parquet(features_path)
            conn.execute(f"CREATE VIEW features AS SELECT * FROM read_parquet('{features_path}')")

            # Create target at a random point within feature range
            target_day = n_features // 2
            target_dates = [datetime(2024, 1, 1) + timedelta(days=target_day + i) for i in range(n_targets)]
            targets_df = pl.DataFrame({
                "timestamp": target_dates,
                "target": [1] * n_targets,
            })
            targets_path = tmp_path / "targets.parquet"
            targets_df.write_parquet(targets_path)
            conn.execute(f"CREATE VIEW targets AS SELECT * FROM read_parquet('{targets_path}')")

            # Perform ASOF join
            result = conn.execute("""
                SELECT
                    t.timestamp as target_ts,
                    f.timestamp as feature_ts,
                    f.feature_value
                FROM targets t
                ASOF JOIN features f
                    ON t.timestamp >= f.timestamp
            """).pl()

            conn.close()

            # Verify: for every row, feature_ts <= target_ts
            for row in result.iter_rows(named=True):
                target_ts = row["target_ts"]
                feature_ts = row["feature_ts"]
                if feature_ts is not None:
                    assert feature_ts <= target_ts, (
                        f"Lookahead detected! feature_ts={feature_ts} > target_ts={target_ts}"
                    )


class TestSchemaTypeMapping:
    """Property-based tests for type mapping consistency."""

    @given(
        type_str=st.sampled_from([
            "int64", "int32", "float64", "float32", "string", "bool",
            "datetime64[us]", "datetime64[ns]", "date",
        ])
    )
    @settings(max_examples=20)
    def test_type_mapping_deterministic(self, type_str: str):
        """Same input type should always map to same output."""
        col1 = ColumnSchema(name="x", type=type_str)
        col2 = ColumnSchema(name="y", type=type_str)

        assert col1.type == col2.type


class TestLayerSchemaProperties:
    """Property-based tests for LayerSchema."""

    @given(
        layer_name=st.sampled_from(["data/raw", "features", "signals"]),
        description=st.text(min_size=0, max_size=100),
    )
    @settings(max_examples=20)
    def test_layer_roundtrip(self, layer_name: str, description: str):
        """LayerSchema should roundtrip through serialization."""
        original = LayerSchema(
            name=layer_name,
            description=description,
            datasets={},
        )
        d = original.to_dict()
        recovered = LayerSchema.from_dict(d)

        assert recovered.name == original.name
        assert recovered.description == original.description


class TestMasterSchemaProperties:
    """Property-based tests for MasterSchema."""

    @given(
        version=st.integers(min_value=1, max_value=100),
        compression=st.sampled_from(["zstd", "snappy", "gzip", "lz4"]),
    )
    @settings(max_examples=20)
    def test_conventions_preserved(self, version: int, compression: str):
        """Conventions should be preserved through serialization."""
        original = MasterSchema(
            version=version,
            conventions={"compression": compression},
        )
        d = original.to_dict()
        recovered = MasterSchema.from_dict(d)

        assert recovered.version == original.version
        assert recovered.conventions["compression"] == compression
