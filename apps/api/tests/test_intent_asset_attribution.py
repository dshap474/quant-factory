"""Generic published attribution: independent cash-flow fixtures and selection.

USAGE: uv run pytest apps/api/tests/test_intent_asset_attribution.py -q
"""
import json
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest
from db_api.strategy_single_asset import SingleAssetIntegrityError, SingleAssetSelectionError, load_single_asset_view
from strategies.research_surface import publish_research_surface


# --------------------------------------------------------------------------- #
# Independent two-account fixture
# --------------------------------------------------------------------------- #
def publish_fixture(root, *, duplicate=False):
    days = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(3)]
    rows = []
    for config, scale in [('a', 1), ('b', 2)]:
        for asset in ['BTC', 'FLAT']:
            for i, day in enumerate(days):
                rows.append(dict(timestamp=day, config_id=config, asset=asset,
                    price=100.0 if asset == 'BTC' else None, quantity=scale if asset=='BTC' and i==1 else 0,
                    weight=0.1*scale if asset=='BTC' and i==1 else 0,
                    price_pnl=10.0*scale if asset=='BTC' and i==2 else 0,
                    funding_pnl=-2.0*scale if asset=='BTC' and i==2 else 0,
                    fees=1.0*scale if asset=='BTC' and i else 0))
    if duplicate:
        rows.append(rows[0])
    data = pl.DataFrame(rows)
    performance = pl.DataFrame(dict(date=days, strategy_daily_return=[0.,-.01,7/99],
        strategy_portfolio_value=[100.,99.,106.], benchmark_daily_return=[0.,0.,0.],
        benchmark_portfolio_value=[100.,100.,100.]))
    return publish_research_surface(root, strategy_type='fixture', memory_version='v001',
        state='candidate', experiment='test', run_id='run', title='Fixture', summary='Known cash flows',
        performance=performance, benchmark=dict(id='BTC',label='BTC'), asset_attribution=data,
        attribution_metadata=dict(initial_capital=100, cost_bps=10, selected_config_id='a',
                                  configurations=[dict(id='a',label='One'),dict(id='b',label='Two')]))


def test_generic_attribution_selects_asset_and_configuration(tmp_path):
    publish_fixture(tmp_path)
    a = load_single_asset_view(tmp_path, 'fixture', 'v001')
    b = load_single_asset_view(tmp_path, 'fixture', 'v001', asset='BTC', config_id='b')
    assert a['config_id'] == 'a' and a['asset'] == 'BTC'
    assert a['data']['cumulative_contribution_pp'].to_list() == pytest.approx([0,-1,6])
    assert b['data']['cumulative_contribution_pp'].to_list() == pytest.approx([0,-2,12])
    assert b['data']['weight_percent'].to_list() == pytest.approx([0,20,0])
    assert len(b['configurations']) == 2
    flat = load_single_asset_view(tmp_path, 'fixture', 'v001', asset='FLAT')
    assert not flat['ever_held'] and flat['data']['price'].null_count() == 3
    assert flat['ending_contribution_pp'] == 0
    assert b['rebalance_every_bars'] is None


@pytest.mark.parametrize('kwargs', [dict(config_id='missing'),dict(asset='MISSING'),dict(expected_run_id='other')])
def test_wrong_selection_never_substitutes_a_different_result(tmp_path, kwargs):
    publish_fixture(tmp_path)
    with pytest.raises((SingleAssetSelectionError, SingleAssetIntegrityError)):
        load_single_asset_view(tmp_path, 'fixture', 'v001', **kwargs)


def test_duplicate_attribution_cannot_publish(tmp_path):
    with pytest.raises(ValueError, match='duplicate attribution'):
        publish_fixture(tmp_path, duplicate=True)
    assert not (tmp_path/'research/strategies/fixture/v001/surface.json').exists()


def test_manifest_path_cannot_escape_version(tmp_path):
    publish_fixture(tmp_path)
    path=tmp_path/'research/strategies/fixture/v001/test/run/surface/manifest.json'
    meta = json.loads(path.read_text())
    meta['attribution']['path'] = '../../outside.parquet'
    path.write_text(json.dumps(meta))
    with pytest.raises(SingleAssetIntegrityError, match='escapes'):
        load_single_asset_view(tmp_path,'fixture','v001')


def test_manifest_cannot_borrow_another_runs_attribution(tmp_path):
    publish_fixture(tmp_path)
    version = tmp_path/'research/strategies/fixture/v001'
    path = version/'test/run/surface/manifest.json'
    other = version/'test/other/surface/asset_attribution.parquet'
    other.parent.mkdir(parents=True)
    other.write_bytes((path.parent/'asset_attribution.parquet').read_bytes())
    meta = json.loads(path.read_text())
    meta['attribution']['path'] = other.relative_to(version).as_posix()
    path.write_text(json.dumps(meta))
    with pytest.raises(SingleAssetIntegrityError, match='outside the selected run'):
        load_single_asset_view(tmp_path, 'fixture', 'v001')
