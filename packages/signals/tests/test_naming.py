from __future__ import annotations

import pytest
from signals.naming import (
    is_valid_preset_name,
    is_valid_signal_type_name,
    validate_preset_name,
    validate_signal_type_name,
)


def test_signal_type_names_use_kebab_case() -> None:
    assert is_valid_signal_type_name("trend-score")
    assert is_valid_signal_type_name("momentum-score-7d")
    assert is_valid_signal_type_name("equities_index-trend")
    assert not is_valid_signal_type_name("example_signal_type")


def test_preset_names_use_default_or_kebab_case() -> None:
    assert is_valid_preset_name("default")
    assert is_valid_preset_name("trend-score-default")
    assert is_valid_preset_name("equities_index-trend-default")
    assert not is_valid_preset_name("example_signal_default")


def test_validate_signal_type_name_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError):
        validate_signal_type_name("example_signal_type")


def test_validate_preset_name_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError):
        validate_preset_name("example_signal_default")
