"""Deployment contracts plus explicit authority-gated one-shot execution.

Usage:
    from production import load_deployment, validate_deployment
"""

# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

from production.contracts import (
    ACTIVATION_SCHEMA_VERSION,
    DEPLOYMENT_SCHEMA_VERSION,
    ActivationBinding,
    ActivationReceipt,
    DeploymentDefinition,
    DeploymentValidationError,
    ExecutionDefinition,
    RuntimeDefinition,
    StrategyReference,
)
from production.deployment import (
    deployment_fingerprint,
    discover_deployments,
    load_deployment,
    validate_deployment,
)
from production.registry import UnknownRuntimeAdapterError, UnsupportedActivationSchemaError
from production.runtime import run_once

__all__ = [
    "ACTIVATION_SCHEMA_VERSION",
    "DEPLOYMENT_SCHEMA_VERSION",
    "ActivationBinding",
    "ActivationReceipt",
    "DeploymentDefinition",
    "DeploymentValidationError",
    "ExecutionDefinition",
    "RuntimeDefinition",
    "StrategyReference",
    "UnknownRuntimeAdapterError",
    "UnsupportedActivationSchemaError",
    "deployment_fingerprint",
    "discover_deployments",
    "load_deployment",
    "validate_deployment",
    "run_once",
]

__version__ = "0.1.0"
