"""Verify exact-file query isolation and integer cutoffs.

USAGE: pytest packages/data/tests/unit/test_query_file_sets.py -q
"""

from dataclasses import replace

import polars as pl
import pytest
from data.query import (
    ParquetCollectionQuery,
    QueryPathError,
    QueryValidationError,
    get_parquet_collection_metadata,
    query_parquet_collection,
    resolve_parquet_collection,
)

# --------------------------------------------------------------------------- #
# Explicit publication snapshots
# --------------------------------------------------------------------------- #


@pytest.fixture
def files(tmp_path):
    root = tmp_path / 'research'
    root.mkdir()
    for i in range(3):
        pl.DataFrame({'seq': [i * 2 + 1, i * 2 + 2], 'name': ['a', 'b']}).write_parquet(root / f'{i}.parquet')
    return tmp_path


def test_exact_list_and_cutoff_exclude_unpublished(files):
    query = ParquetCollectionQuery(scope='research', paths=('0.parquet', '2.parquet'),
                                   integer_column='seq', integer_max=5, order_by='seq')
    result = query_parquet_collection(query, db_root=files)
    assert result.frame['seq'].to_list() == [1, 2, 5]
    assert result.metadata.paths == query.paths
    assert result.metadata.file_count == 2
    query = replace(query, integer_min=2, integer_max=6, limit=2, offset=1)
    assert query_parquet_collection(query, db_root=files).frame['seq'].to_list() == [5, 6]


@pytest.mark.parametrize('paths', [(), ('*.parquet',), ('../bad.parquet',), ('/tmp/a.parquet',),
                                   ('http://a.parquet',), ('0.parquet', '0.parquet'),
                                   ('missing.parquet',), ('.',)])
def test_explicit_paths_fail_closed(files, paths):
    with pytest.raises(QueryPathError):
        resolve_parquet_collection(scope='research', paths=paths, db_root=files)


def test_scope_escape_and_ambiguous_selection(files):
    (files / 'outside.parquet').write_bytes(b'not parquet')
    (files / 'research/link.parquet').symlink_to(files / 'outside.parquet')
    with pytest.raises(QueryPathError):
        resolve_parquet_collection(scope='research', paths=('link.parquet',), db_root=files)
    with pytest.raises(QueryPathError):
        resolve_parquet_collection(scope='research', paths=('0.parquet',), path_glob='*.parquet', db_root=files)


def test_metadata_is_bound_to_exact_file_set(files):
    metadata = get_parquet_collection_metadata(scope='research', paths=('0.parquet',), db_root=files)
    query = ParquetCollectionQuery(scope='research', paths=('1.parquet',))
    with pytest.raises(QueryValidationError, match='paths'):
        query_parquet_collection(query, metadata=metadata, db_root=files)


@pytest.mark.parametrize('bounds', [dict(integer_column='name', integer_max=3),
                                   dict(integer_column='seq', integer_max=True),
                                   dict(integer_column='seq', integer_max=2**63),
                                   dict(integer_column='seq', integer_min=3, integer_max=2)])
def test_invalid_integer_bounds(files, bounds):
    with pytest.raises(QueryValidationError):
        query_parquet_collection(ParquetCollectionQuery(scope='research', paths=('0.parquet',), **bounds),
                                 db_root=files)
