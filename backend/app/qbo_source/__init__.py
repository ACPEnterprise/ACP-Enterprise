"""Provider-neutral, read-only accounting source acquisition contracts."""

from .contracts import (
    AcquisitionRequest,
    EntityKind,
    QboSourceEnvelope,
    SnapshotIdentity,
    SourceAcquisitionProvider,
)

__all__ = [
    "AcquisitionRequest",
    "EntityKind",
    "QboSourceEnvelope",
    "SnapshotIdentity",
    "SourceAcquisitionProvider",
]
