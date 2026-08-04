import hashlib
import json
from dataclasses import asdict, dataclass

from app.platform.permissions.catalog import permission_catalog

PLATFORM_CONTRACT_VERSION = "1"
AUTHORIZATION_PROJECTION_VERSION = "1"
SHARED_API_CONTRACT_VERSION = "1"


class PlatformContractDriftError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlatformContractManifest:
    platform_contract_version: str
    permission_codes_digest: str
    permission_catalog_digest: str
    authorization_projection_version: str
    shared_api_contract_version: str
    fingerprint: str

    def safe_dict(self) -> dict[str, str]:
        return asdict(self)

    def assert_expected(self, expected_fingerprint: str | None) -> None:
        if expected_fingerprint is None:
            return
        if expected_fingerprint != self.fingerprint:
            raise PlatformContractDriftError(
                "Configured platform contract does not match this application image."
            )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _build_manifest() -> PlatformContractManifest:
    definitions = sorted(
        (
            {
                "action": item.action,
                "code": item.code,
                "name": item.name,
                "reserved": item.reserved,
                "resource": item.resource,
                "scope": item.scope.value,
            }
            for item in permission_catalog.definitions
        ),
        key=lambda item: item["code"],
    )
    codes_digest = _digest([item["code"] for item in definitions])
    catalog_digest = _digest(definitions)
    contract = {
        "authorization_projection_version": AUTHORIZATION_PROJECTION_VERSION,
        "permission_catalog_digest": catalog_digest,
        "permission_codes_digest": codes_digest,
        "platform_contract_version": PLATFORM_CONTRACT_VERSION,
        "shared_api_contract_version": SHARED_API_CONTRACT_VERSION,
    }
    return PlatformContractManifest(**contract, fingerprint=_digest(contract))


platform_contract_manifest = _build_manifest()
