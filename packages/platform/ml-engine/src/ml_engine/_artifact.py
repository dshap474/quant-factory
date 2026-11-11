"""Versioned, atomic training-artifact save/load facade.

Usage::

    payload = ArtifactPayload(config={}, schema={}, preprocessor=None, models={})
    save_artifact("models/model-v1", payload)
    loaded = load_artifact("models/model-v1", trusted=True)

Joblib artifacts are trusted-code artifacts.  The default loader warns because
``InferencePipeline.load()`` may execute serialized Python; use trusted sources
only and pass ``trusted=True`` after making that decision explicitly.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Stable private-module facade
# --------------------------------------------------------------------------- #
from ._artifact_format import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactCompatibilityError,
    ArtifactError,
    ArtifactIntegrityError,
    ArtifactPayload,
    ArtifactSchemaError,
    ArtifactSerializationError,
    TrustedArtifactWarning,
    UntrustedArtifactError,
)
from ._artifact_io import load_artifact, save_artifact

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "ArtifactCompatibilityError",
    "ArtifactError",
    "ArtifactIntegrityError",
    "ArtifactPayload",
    "ArtifactSchemaError",
    "ArtifactSerializationError",
    "TrustedArtifactWarning",
    "UntrustedArtifactError",
    "load_artifact",
    "save_artifact",
]
