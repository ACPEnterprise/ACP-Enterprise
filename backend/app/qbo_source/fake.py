from __future__ import annotations

from collections.abc import AsyncIterator

from .contracts import AcquisitionRequest, EntityKind, QboSourceEnvelope


class DeterministicSourceFake:
    """Synthetic provider for contract tests; it performs no network or disk I/O."""

    def __init__(self, envelopes: tuple[QboSourceEnvelope, ...]) -> None:
        keys = [(e.native_entity_type, e.native_id) for e in envelopes]
        if len(keys) != len(set(keys)):
            raise ValueError("fake native identities must be unique")
        self._envelopes = tuple(
            sorted(envelopes, key=lambda e: (e.native_entity_type, e.native_id))
        )

    async def acquire(
        self, request: AcquisitionRequest
    ) -> AsyncIterator[QboSourceEnvelope]:
        allowed = {kind.value for kind in request.entity_kinds}
        for envelope in self._envelopes:
            if envelope.snapshot != request.snapshot:
                raise ValueError("envelope snapshot does not match request")
            if envelope.native_entity_type in allowed:
                yield envelope


DEFAULT_ENTITY_KINDS = tuple(EntityKind)
