from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar, cast

from development_factory.reports import redact

SCHEMA_VERSION = "twelfthats.durable-coordination.v1"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TERMINAL_STATES = frozenset({"completed", "released"})
SECRET_KEY = re.compile(
    r"(?i)(authorization|cookie|credential|database_url|password|private_key|secret|token)"
)
T = TypeVar("T")


class DurableCoordinationError(ValueError):
    """Fail-closed local coordination error."""


@dataclass(frozen=True)
class CoordinationLimits:
    max_claims: int = 64
    max_file_boundaries: int = 128
    max_resources: int = 128
    max_checkpoints: int = 256
    max_evidence_bytes: int = 64_000
    max_retry_attempts: int = 3
    max_retry_delay_seconds: float = 30.0

    def validate(self) -> None:
        values = (
            self.max_claims,
            self.max_file_boundaries,
            self.max_resources,
            self.max_checkpoints,
            self.max_evidence_bytes,
            self.max_retry_attempts,
        )
        if any(value < 1 for value in values):
            raise DurableCoordinationError("coordination limits must be positive")
        if self.max_claims > 256 or self.max_checkpoints > 1_024:
            raise DurableCoordinationError("coordination limits exceed safe bounds")
        if self.max_file_boundaries > 512 or self.max_resources > 512:
            raise DurableCoordinationError("resource limits exceed safe bounds")
        if self.max_evidence_bytes > 1_000_000:
            raise DurableCoordinationError("evidence limit exceeds safe bounds")
        if self.max_retry_attempts > 8:
            raise DurableCoordinationError("retry limit exceeds safe bounds")
        if not 0 <= self.max_retry_delay_seconds <= 300:
            raise DurableCoordinationError("retry delay exceeds safe bounds")


@dataclass(frozen=True)
class AuthorityFence:
    assignment_id: str
    execution_id: str
    worker_id: str
    lease_id: str
    lease_version: int
    lease_expires_at: datetime
    queue_digest: str

    def validate(self) -> None:
        for name, value in (
            ("assignment_id", self.assignment_id),
            ("execution_id", self.execution_id),
            ("worker_id", self.worker_id),
            ("lease_id", self.lease_id),
        ):
            if SAFE_ID.fullmatch(value) is None:
                raise DurableCoordinationError(f"{name} is invalid")
        if self.lease_version < 1:
            raise DurableCoordinationError("lease version is invalid")
        if self.lease_expires_at.tzinfo is None:
            raise DurableCoordinationError("lease expiration must be timezone-aware")
        if SHA256.fullmatch(self.queue_digest) is None:
            raise DurableCoordinationError("queue digest is invalid")


@dataclass(frozen=True)
class ClaimScope:
    file_boundaries: tuple[str, ...]
    resources: tuple[str, ...]

    def validate(self, limits: CoordinationLimits) -> None:
        if len(self.file_boundaries) > limits.max_file_boundaries:
            raise DurableCoordinationError("file-boundary limit exceeded")
        if len(self.resources) > limits.max_resources:
            raise DurableCoordinationError("resource limit exceeded")
        if len(set(self.file_boundaries)) != len(self.file_boundaries):
            raise DurableCoordinationError("file boundaries must be unique")
        if len(set(self.resources)) != len(self.resources):
            raise DurableCoordinationError("resources must be unique")
        for boundary in self.file_boundaries:
            if not _safe_boundary(boundary):
                raise DurableCoordinationError("file boundary is invalid")
        for resource in self.resources:
            if SAFE_ID.fullmatch(resource) is None:
                raise DurableCoordinationError("resource identifier is invalid")


@dataclass(frozen=True)
class RecoveryDecision:
    state: str
    state_digest: str
    last_checkpoint: str


class DurableCoordinationJournal:
    """Durable local evidence bound to externally issued Worker Control authority.

    This journal never issues an assignment, claim, lease, approval, or privileged
    action. It serializes use of an already-issued authority fence within a shared
    custody root and turns every ambiguous restart into explicit reconciliation.
    """

    def __init__(self, root: Path, *, limits: CoordinationLimits | None = None) -> None:
        self.root = root.resolve()
        self.limits = limits or CoordinationLimits()
        self.limits.validate()
        self.claims = self.root / "claims"
        self.lock_path = self.root / "coordination.lock"

    def claim(
        self,
        fence: AuthorityFence,
        scope: ClaimScope,
        *,
        now: datetime | None = None,
    ) -> str:
        fence.validate()
        scope.validate(self.limits)
        occurred_at = _aware(now)
        if fence.lease_expires_at <= occurred_at:
            raise DurableCoordinationError("authoritative lease has expired")
        with self._locked():
            states = self._active_states()
            if len(states) >= self.limits.max_claims:
                raise DurableCoordinationError("active-claim limit exceeded")
            for existing_state in states:
                existing = cast(dict[str, object], existing_state["authority"])
                existing_scope = cast(dict[str, list[str]], existing_state["scope"])
                if existing["assignment_id"] == fence.assignment_id:
                    raise DurableCoordinationError("assignment is already claimed")
                if existing["execution_id"] == fence.execution_id:
                    raise DurableCoordinationError("execution is already claimed")
                if set(existing_scope["resources"]) & set(scope.resources):
                    raise DurableCoordinationError("resource is already fenced")
                if _boundaries_overlap(
                    tuple(existing_scope["file_boundaries"]), scope.file_boundaries
                ):
                    raise DurableCoordinationError("file boundary is already fenced")
            path = self._claim_path(fence.execution_id)
            if path.exists():
                raise DurableCoordinationError("execution journal already exists")
            state: dict[str, object] = {
                "schema": SCHEMA_VERSION,
                "authority": _authority_payload(fence),
                "scope": {
                    "file_boundaries": list(scope.file_boundaries),
                    "resources": list(scope.resources),
                },
                "state": "active",
                "checkpoints": [],
                "state_digest": "",
            }
            self._append_checkpoint(
                state,
                phase="claimed",
                evidence={"authority_source": "worker_control"},
                occurred_at=occurred_at,
            )
            self._write_state(path, state)
            return str(state["state_digest"])

    def checkpoint(
        self,
        fence: AuthorityFence,
        *,
        phase: str,
        evidence: Mapping[str, object],
        now: datetime | None = None,
    ) -> str:
        fence.validate()
        occurred_at = _aware(now)
        with self._locked():
            path = self._claim_path(fence.execution_id)
            state = self._load_state(path)
            self._require_fence(state, fence, now=occurred_at)
            if state["state"] != "active":
                raise DurableCoordinationError("execution is not active")
            self._append_checkpoint(
                state,
                phase=phase,
                evidence=evidence,
                occurred_at=occurred_at,
            )
            self._write_state(path, state)
            return str(state["state_digest"])

    def renew(
        self,
        fence: AuthorityFence,
        *,
        new_version: int,
        new_expires_at: datetime,
        now: datetime | None = None,
    ) -> AuthorityFence:
        fence.validate()
        occurred_at = _aware(now)
        new_expires_at = _aware(new_expires_at)
        if new_version != fence.lease_version + 1:
            raise DurableCoordinationError("lease renewal version must be monotonic")
        if new_expires_at <= occurred_at:
            raise DurableCoordinationError("renewed lease has already expired")
        with self._locked():
            path = self._claim_path(fence.execution_id)
            state = self._load_state(path)
            self._require_fence(state, fence, now=occurred_at)
            authority = dict(cast(dict[str, object], state["authority"]))
            authority["lease_version"] = new_version
            authority["lease_expires_at"] = new_expires_at.isoformat()
            state["authority"] = authority
            self._append_checkpoint(
                state,
                phase="lease_renewed",
                evidence={"lease_version": new_version},
                occurred_at=occurred_at,
            )
            self._write_state(path, state)
        return AuthorityFence(
            assignment_id=fence.assignment_id,
            execution_id=fence.execution_id,
            worker_id=fence.worker_id,
            lease_id=fence.lease_id,
            lease_version=new_version,
            lease_expires_at=new_expires_at,
            queue_digest=fence.queue_digest,
        )

    def complete(
        self,
        fence: AuthorityFence,
        *,
        evidence: Mapping[str, object],
        now: datetime | None = None,
    ) -> str:
        occurred_at = _aware(now)
        with self._locked():
            path = self._claim_path(fence.execution_id)
            state = self._load_state(path)
            self._require_fence(state, fence, now=occurred_at)
            if state["state"] != "active":
                raise DurableCoordinationError("execution is not active")
            state["state"] = "completed"
            self._append_checkpoint(
                state,
                phase="completed",
                evidence=evidence,
                occurred_at=occurred_at,
            )
            self._write_state(path, state)
            return str(state["state_digest"])

    def recover(
        self, execution_id: str, *, now: datetime | None = None
    ) -> RecoveryDecision:
        occurred_at = _aware(now)
        with self._locked():
            path = self._claim_path(execution_id)
            state = self._load_state(path)
            checkpoints = cast(list[dict[str, object]], state["checkpoints"])
            if not checkpoints:
                raise DurableCoordinationError("execution journal has no checkpoints")
            if state["state"] not in TERMINAL_STATES:
                state["state"] = "reconciliation_required"
                self._append_checkpoint(
                    state,
                    phase="restart_reconciliation_required",
                    evidence={
                        "lease_expired": _lease_expiration(state) <= occurred_at,
                        "automatic_replay": False,
                    },
                    occurred_at=occurred_at,
                )
                self._write_state(path, state)
                checkpoints = cast(list[dict[str, object]], state["checkpoints"])
            last = checkpoints[-1]
            return RecoveryDecision(
                state=str(state["state"]),
                state_digest=str(state["state_digest"]),
                last_checkpoint=str(last["phase"]),
            )

    def release_reconciled(
        self,
        fence: AuthorityFence,
        *,
        reviewed_state_digest: str,
        now: datetime | None = None,
    ) -> str:
        occurred_at = _aware(now)
        with self._locked():
            path = self._claim_path(fence.execution_id)
            state = self._load_state(path)
            self._require_fence(state, fence, now=occurred_at, permit_expired=True)
            if state["state"] != "reconciliation_required":
                raise DurableCoordinationError("reconciliation is not required")
            if not _constant_equal(str(state["state_digest"]), reviewed_state_digest):
                raise DurableCoordinationError("reviewed state digest is stale")
            state["state"] = "released"
            self._append_checkpoint(
                state,
                phase="reconciliation_released",
                evidence={"reviewed_state_digest": reviewed_state_digest},
                occurred_at=occurred_at,
            )
            self._write_state(path, state)
            return str(state["state_digest"])

    def retry_transient(
        self,
        fence: AuthorityFence,
        operation: Callable[[], T],
        *,
        retryable: tuple[type[BaseException], ...] = (ConnectionError, TimeoutError),
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> T:
        last_error: BaseException | None = None
        for attempt in range(1, self.limits.max_retry_attempts + 1):
            try:
                return operation()
            except retryable as error:
                last_error = error
                self.checkpoint(
                    fence,
                    phase="transient_retry",
                    evidence={
                        "attempt": attempt,
                        "error": f"{type(error).__name__}: {error}",
                    },
                    now=now(),
                )
                if attempt == self.limits.max_retry_attempts:
                    break
                sleep(
                    min(float(2 ** (attempt - 1)), self.limits.max_retry_delay_seconds)
                )
        raise DurableCoordinationError(
            "transient retry budget exhausted"
        ) from last_error

    @contextmanager
    def _locked(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.stat().st_mode & 0o077:
            raise DurableCoordinationError("coordination root must be owner-only")
        self.claims.mkdir(mode=0o700, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            with os.fdopen(descriptor, "r+") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                yield
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            pass

    def _active_states(self) -> tuple[dict[str, object], ...]:
        states = tuple(
            self._load_state(path) for path in sorted(self.claims.glob("*.json"))
        )
        return tuple(state for state in states if state["state"] not in TERMINAL_STATES)

    def _claim_path(self, execution_id: str) -> Path:
        if SAFE_ID.fullmatch(execution_id) is None:
            raise DurableCoordinationError("execution_id is invalid")
        return self.claims / f"{execution_id}.json"

    def _load_state(self, path: Path) -> dict[str, object]:
        if not path.is_file():
            raise DurableCoordinationError("execution journal was not found")
        if path.stat().st_mode & 0o077:
            raise DurableCoordinationError("execution journal must be owner-only")
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DurableCoordinationError("execution journal is unreadable") from error
        if not isinstance(state, dict) or set(state) != {
            "schema",
            "authority",
            "scope",
            "state",
            "checkpoints",
            "state_digest",
        }:
            raise DurableCoordinationError("execution journal shape is invalid")
        if state["schema"] != SCHEMA_VERSION:
            raise DurableCoordinationError("execution journal schema is invalid")
        checkpoints = state["checkpoints"]
        if not isinstance(checkpoints, list) or not checkpoints:
            raise DurableCoordinationError("execution journal has no checkpoints")
        if len(checkpoints) > self.limits.max_checkpoints:
            raise DurableCoordinationError("checkpoint limit exceeded")
        previous = ""
        for sequence, checkpoint in enumerate(checkpoints, start=1):
            if not isinstance(checkpoint, dict) or set(checkpoint) != {
                "sequence",
                "phase",
                "occurred_at",
                "evidence",
                "previous_digest",
                "digest",
            }:
                raise DurableCoordinationError("checkpoint shape is invalid")
            supplied = str(checkpoint["digest"])
            unsigned = {
                key: value for key, value in checkpoint.items() if key != "digest"
            }
            if (
                checkpoint["sequence"] != sequence
                or checkpoint["previous_digest"] != previous
                or not _constant_equal(supplied, _digest(unsigned))
            ):
                raise DurableCoordinationError("checkpoint integrity validation failed")
            previous = supplied
        if not _constant_equal(str(state["state_digest"]), _state_digest(state)):
            raise DurableCoordinationError("journal integrity validation failed")
        return state

    def _require_fence(
        self,
        state: dict[str, object],
        fence: AuthorityFence,
        *,
        now: datetime,
        permit_expired: bool = False,
    ) -> None:
        authority = state["authority"]
        if not isinstance(authority, dict):
            raise DurableCoordinationError("authority fence is invalid")
        expected = _authority_payload(fence)
        if authority != expected:
            raise DurableCoordinationError("authority fence is stale")
        if not permit_expired and fence.lease_expires_at <= now:
            raise DurableCoordinationError("authoritative lease has expired")

    def _append_checkpoint(
        self,
        state: dict[str, object],
        *,
        phase: str,
        evidence: Mapping[str, object],
        occurred_at: datetime,
    ) -> None:
        if SAFE_ID.fullmatch(phase) is None:
            raise DurableCoordinationError("checkpoint phase is invalid")
        checkpoints = state["checkpoints"]
        if not isinstance(checkpoints, list):
            raise DurableCoordinationError("checkpoint journal is invalid")
        if len(checkpoints) >= self.limits.max_checkpoints:
            raise DurableCoordinationError("checkpoint limit exceeded")
        sanitized = _sanitize(evidence)
        encoded = _canonical(sanitized)
        if len(encoded) > self.limits.max_evidence_bytes:
            raise DurableCoordinationError("checkpoint evidence limit exceeded")
        checkpoint: dict[str, object] = {
            "sequence": len(checkpoints) + 1,
            "phase": phase,
            "occurred_at": occurred_at.isoformat(),
            "evidence": sanitized,
            "previous_digest": str(checkpoints[-1]["digest"]) if checkpoints else "",
        }
        checkpoint["digest"] = _digest(checkpoint)
        checkpoints.append(checkpoint)
        state["state_digest"] = _state_digest(state)

    def _write_state(self, path: Path, state: dict[str, object]) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        encoded = _canonical(state)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            temporary.unlink(missing_ok=True)


def _authority_payload(fence: AuthorityFence) -> dict[str, object]:
    return {
        "assignment_id": fence.assignment_id,
        "execution_id": fence.execution_id,
        "worker_id": fence.worker_id,
        "lease_id": fence.lease_id,
        "lease_version": fence.lease_version,
        "lease_expires_at": fence.lease_expires_at.isoformat(),
        "queue_digest": fence.queue_digest,
    }


def _lease_expiration(state: Mapping[str, object]) -> datetime:
    authority = state["authority"]
    if not isinstance(authority, dict):
        raise DurableCoordinationError("authority fence is invalid")
    return datetime.fromisoformat(str(authority["lease_expires_at"]))


def _state_digest(state: Mapping[str, object]) -> str:
    unsigned = {key: value for key, value in state.items() if key != "state_digest"}
    return _digest(unsigned)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sanitize(value: object) -> object:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if SECRET_KEY.search(str(key)) else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact(str(value))


def _aware(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        raise DurableCoordinationError("coordination timestamp must be timezone-aware")
    return result


def _safe_boundary(value: str) -> bool:
    return bool(
        value
        and len(value) <= 500
        and not value.startswith(("/", "~"))
        and ".." not in Path(value).parts
        and "\\" not in value
    )


def _boundary_prefix(value: str) -> str:
    wildcard = min(
        (value.find(token) for token in ("*", "?", "[") if token in value),
        default=len(value),
    )
    return value[:wildcard].rstrip("/")


def _boundaries_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    for first in left:
        first_prefix = _boundary_prefix(first)
        for second in right:
            second_prefix = _boundary_prefix(second)
            if not first_prefix or not second_prefix:
                return True
            if (
                first_prefix == second_prefix
                or first_prefix.startswith(f"{second_prefix}/")
                or second_prefix.startswith(f"{first_prefix}/")
            ):
                return True
    return False


def _constant_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
