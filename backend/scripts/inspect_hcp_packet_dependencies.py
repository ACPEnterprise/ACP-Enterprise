import json
from pathlib import Path

packet = json.loads(
    Path(
        "/var/lib/acp-qbo-production-evidence/hcp-runtime-2307/quarantine/runtime-binding-quarantined-packet.json"
    ).read_text()
)
records = packet["records"]
keys = {
    (str(x["domain"]), str(x["source_id"]))
    for x in records
    if str(x.get("disposition", "")).upper() in {"CREATE", "UPDATE", "REPLAY"}
}
held = {
    (str(x["domain"]), str(x["source_id"]))
    for x in records
    if str(x.get("disposition", "")).upper() in {"HOLD", "HOLD_QUARANTINE"}
}
for item in records:
    if str(item.get("disposition", "")).upper() not in {"CREATE", "UPDATE", "REPLAY"}:
        continue
    if str(item.get("domain")) not in {
        "estimate",
        "invoice",
        "payment",
        "appointment",
        "job",
    }:
        continue
    missing = []
    for parent in item.get("parent_keys", []):
        key = (str(parent["domain"]), str(parent["source_id"]))
        if key not in keys and key not in held:
            missing.append(key)
    if missing:
        print(
            json.dumps(
                {
                    "domain": item["domain"],
                    "source_id": item["source_id"],
                    "disposition": item["disposition"],
                    "parents": item.get("parent_keys", []),
                    "missing": missing,
                },
                sort_keys=True,
            )
        )
