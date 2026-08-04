import json

from app.platform.contracts.manifest import platform_contract_manifest

print(json.dumps(platform_contract_manifest.safe_dict(), sort_keys=True))
