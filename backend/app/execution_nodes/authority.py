import threading
from datetime import datetime, timezone
from uuid import UUID


class ExecutionAuthorityRegistry:
    """Process-local, fail-closed projection of authenticated lease authority."""

    def __init__(self) -> None:
        self._expirations: dict[tuple[UUID, UUID], datetime] = {}
        self._lock = threading.Lock()

    def record(self, execution_id: UUID, lease_id: UUID, expires_at: datetime) -> None:
        if expires_at <= datetime.now(timezone.utc):
            raise ValueError("Execution authority is already expired.")
        key = (execution_id, lease_id)
        with self._lock:
            prior = self._expirations.get(key)
            if prior is not None and expires_at < prior:
                raise ValueError("Execution authority cannot move backward.")
            self._expirations[key] = expires_at

    def require_valid(self, execution_id: UUID, lease_id: UUID) -> None:
        with self._lock:
            expires_at = self._expirations.get((execution_id, lease_id))
        if expires_at is None or expires_at <= datetime.now(timezone.utc):
            raise RuntimeError("Authenticated execution authority expired.")
