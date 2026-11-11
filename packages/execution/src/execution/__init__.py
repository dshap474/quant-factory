"""quant-factory execution: engine-neutral contracts, policies, and identities.

Purpose: expose a compact public surface for immutable execution DTOs,
deterministic target sizing / slice policies, and pure reconciliation helpers.
This package does not depend on Nautilus, strategies, backtest, or loaders.

Provider adapters are separate extensions and are not flattened into this
root ``__all__`` so core contracts stay provider-neutral.

USAGE:
    >>> from execution import (
    ...     ImmediateMarketPolicy,
    ...     InstrumentKey,
    ...     size_target_quantities,
    ... )
"""

from __future__ import annotations

from execution.accounting import (
    apply_fee_to_cash,
    apply_funding_to_cash,
    compute_shortfall,
    equity_from_components,
    funding_cashflow,
    total_fees,
    validate_unique_fill_ids,
)
from execution.events import (
    AccountPoint,
    ExecutionResult,
    Fill,
    FundingSettlement,
    HoldingPoint,
    OrderOutcome,
    OrderStatus,
    Shortfall,
    SliceIntent,
)
from execution.instruments import InstrumentKey, InstrumentSpec
from execution.policies import (
    DelayedMarketPolicy,
    ImmediateMarketPolicy,
    ParentOrderPolicy,
    TimeWeightedTakerPolicy,
    maker_child_lots,
    maker_price,
    validate_non_overlapping_windows,
)
from execution.resting import (
    RestingLimitExecutionResult,
    RestingLimitOrder,
    RestingLimitOutcome,
    RestingLimitPlan,
)
from execution.sizing import round_toward_zero_to_increment, size_target_quantities, validate_order_limits
from execution.targets import (
    AccountSnapshot,
    InitialAccountState,
    PortfolioTarget,
    PositionSnapshot,
    ReferencePrice,
    TargetQuantity,
    TargetWeight,
)

__version__ = "0.1.0"

__all__ = [
    # Models
    "InstrumentKey",
    "InstrumentSpec",
    "TargetWeight",
    "ReferencePrice",
    "PortfolioTarget",
    "PositionSnapshot",
    "AccountSnapshot",
    "InitialAccountState",
    "TargetQuantity",
    "SliceIntent",
    "OrderStatus",
    "Fill",
    "OrderOutcome",
    "FundingSettlement",
    "HoldingPoint",
    "AccountPoint",
    "Shortfall",
    "ExecutionResult",
    "RestingLimitOrder",
    "RestingLimitPlan",
    "RestingLimitOutcome",
    "RestingLimitExecutionResult",
    # Sizing
    "round_toward_zero_to_increment",
    "size_target_quantities",
    "validate_order_limits",
    # Policies
    "DelayedMarketPolicy",
    "ImmediateMarketPolicy",
    "ParentOrderPolicy",
    "TimeWeightedTakerPolicy",
    "maker_child_lots",
    "maker_price",
    "validate_non_overlapping_windows",
    # Accounting
    "total_fees",
    "funding_cashflow",
    "equity_from_components",
    "apply_fee_to_cash",
    "apply_funding_to_cash",
    "compute_shortfall",
    "validate_unique_fill_ids",
]
