import base64
import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.worker_control.transport.contracts import AuthenticatedMessageEnvelope

ED25519_ALGORITHM = "ed25519"


def _encode(value: object) -> object:
    if isinstance(value, (UUID, datetime)):
        return str(value) if isinstance(value, UUID) else value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: _encode(getattr(value, field.name)) for field in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported signed value: {type(value).__name__}")


def canonical_message(envelope: AuthenticatedMessageEnvelope) -> bytes:
    evidence: dict[str, Any] = {
        "key_version": envelope.key_version,
        "kind": envelope.kind.value,
        "message_id": str(envelope.message_id),
        "payload": _encode(envelope.payload),
        "sent_at": envelope.sent_at.isoformat(),
        "sequence_number": envelope.sequence_number,
        "session_id": str(envelope.session_id),
        "worker_id": str(envelope.worker_id),
    }
    return json.dumps(
        evidence, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()


def decode_public_key(verifier: str) -> Ed25519PublicKey:
    raw = base64.urlsafe_b64decode(verifier + "=" * (-len(verifier) % 4))
    if len(raw) != 32:
        raise ValueError("Ed25519 public key length is invalid.")
    return Ed25519PublicKey.from_public_bytes(raw)


def decode_private_key(secret: str) -> Ed25519PrivateKey:
    raw = base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4))
    if len(raw) != 32:
        raise ValueError("Ed25519 private key length is invalid.")
    return Ed25519PrivateKey.from_private_bytes(raw)


def decode_signature(signature: str) -> bytes:
    return base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))


def encode_signature(signature: bytes) -> str:
    return base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def verify_signature(*, public_key: str, signature: str, message: bytes) -> bool:
    try:
        decode_public_key(public_key).verify(decode_signature(signature), message)
    except (InvalidSignature, ValueError):
        return False
    return True
