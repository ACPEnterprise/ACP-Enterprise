"""Acquire and seal a GET-only HCP operational cutover packet.

The command deliberately implements only HTTP GET.  It stores exact provider
responses in a private, create-once evidence directory, compares source-native
identities with a prior sealed delta manifest, and emits a rehearsal input
packet.  It never calls ACP, Preview, Production, or an HCP mutation endpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

APPROVED_API_BASE = "https://api.housecallpro.com"
OPEN_JOB_STATUSES = frozenset({"open", "scheduled", "needs scheduling", "in progress"})
COLLECTIONS = (
    ("customers", "/customers"),
    ("employees", "/employees"),
    ("jobs", "/jobs"),
    ("estimates", "/estimates"),
    ("invoices", "/invoices"),
)
CREATE_DOMAINS = frozenset({"customer", "service_location", "job", "appointment"})
UPDATE_DOMAINS = frozenset({"customer", "job", "appointment"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    return _digest_bytes(_canonical(value))


def _identity_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _secret_file(path: Path) -> tuple[str, str]:
    if not path.is_file():
        raise ValueError(f"HCP secret file is missing: {path}")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError(f"HCP secret file must have mode 0600: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        if "=" not in candidate:
            raise ValueError("HCP secret file contains a malformed line")
        key, raw = candidate.split("=", 1)
        values[key.strip()] = raw.strip().strip('"').strip("'")
    api_key = values.get("HOUSECALL_PRO_API_KEY", "")
    api_base = values.get("HOUSECALL_PRO_API_BASE", "").rstrip("/")
    if not api_key or not api_base:
        raise ValueError("HCP secret configuration is incomplete")
    if api_base != APPROVED_API_BASE:
        raise ValueError("HCP API base is not approved")
    return api_base, api_key


class GetOnlyClient:
    """Fixed-host client with no non-GET request method."""

    def __init__(self, api_base: str, api_key: str) -> None:
        normalized_base = api_base.rstrip("/")
        if normalized_base != APPROVED_API_BASE:
            raise ValueError("HCP API base is not approved")
        self._api_base = normalized_base
        self._authorization = f"Token {api_key}"

    def get(
        self, path: str, query: Mapping[str, Any] | None = None
    ) -> tuple[int, bytes]:
        parsed = urlparse(path)
        if not path.startswith("/") or parsed.scheme or parsed.netloc:
            raise ValueError("HCP request must use a relative API path")
        url = self._api_base + path
        if query:
            url += "?" + urlencode(query)
        request = Request(
            url,
            headers={
                "Authorization": self._authorization,
                "Accept": "application/json",
            },
            method="GET",
        )
        last_error: BaseException | None = None
        for attempt in range(5):
            try:
                with urlopen(request, timeout=45) as response:
                    return int(response.status), response.read()
            except HTTPError as error:
                body = error.read()
                if error.code != 429 and error.code < 500:
                    return int(error.code), body
                last_error = error
                retry_after = error.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2**attempt, 16)
            except (URLError, TimeoutError) as error:
                last_error = error
                delay = min(2**attempt, 16)
            time.sleep(delay)
        raise RuntimeError("HCP GET failed after bounded retries") from last_error


class EvidenceStore:
    def __init__(self, root: Path) -> None:
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
        os.chmod(str(root), 0o700)
        self.root = root
        self.artifacts: list[dict[str, Any]] = []

    def write_raw(
        self,
        name: str,
        body: bytes,
        *,
        request: str,
        http_status: int,
        family: str,
        record_count: int | None = None,
    ) -> Path:
        if Path(name).name != name:
            raise ValueError("evidence artifact name must be a basename")
        target = self.root / name
        with target.open("xb") as stream:
            stream.write(body)
        os.chmod(str(target), 0o600)
        row: dict[str, Any] = {
            "artifact": name,
            "family": family,
            "http_status": http_status,
            "request": request,
            "sha256": _digest_bytes(body),
            "size_bytes": len(body),
        }
        if record_count is not None:
            row["record_count"] = record_count
        self.artifacts.append(row)
        return target

    def write_json(self, name: str, value: Any) -> Path:
        body = (
            json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode(
                "utf-8"
            )
            + b"\n"
        )
        target = self.root / name
        with target.open("xb") as stream:
            stream.write(body)
        os.chmod(str(target), 0o600)
        return target


def _collection_rows(
    body: bytes, collection: str
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    value = json.loads(body)
    if not isinstance(value, dict) or not isinstance(value.get(collection), list):
        raise TypeError(f"invalid HCP {collection} page")
    rows = value[collection]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"invalid HCP {collection} record")
    pagination = {
        key: value.get(key)
        for key in ("page", "page_size", "total_items", "total_pages")
    }
    if not all(isinstance(item, int) for item in pagination.values()):
        raise ValueError(f"incomplete HCP {collection} pagination")
    return rows, pagination  # type: ignore[return-value]


def _acquire_collection(
    client: GetOnlyClient,
    store: EvidenceStore,
    collection: str,
    path: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 1
    total_pages: int | None = None
    page_seals: list[dict[str, Any]] = []
    seen: set = set()
    while total_pages is None or page <= total_pages:
        status, body = client.get(path, {"page": page, "page_size": 100})
        if status != 200:
            store.write_raw(
                f"{collection}-page-{page:04d}-http-{status}.json",
                body,
                request=f"GET {path}?page={page}&page_size=100",
                http_status=status,
                family=collection,
            )
            raise RuntimeError(f"HCP {collection} page {page} returned HTTP {status}")
        rows, pagination = _collection_rows(body, collection)
        artifact = f"{collection}-page-{page:04d}.json"
        store.write_raw(
            artifact,
            body,
            request=f"GET {path}?page={page}&page_size=100",
            http_status=status,
            family=collection,
            record_count=len(rows),
        )
        if pagination["page"] != page:
            raise ValueError(f"HCP {collection} returned a mismatched page number")
        if total_pages is None:
            total_pages = pagination["total_pages"]
        elif total_pages != pagination["total_pages"]:
            raise ValueError(f"HCP {collection} pagination changed during acquisition")
        for row in rows:
            native_id = row.get("id")
            if not isinstance(native_id, str) or not native_id:
                raise ValueError(f"HCP {collection} record is missing a native ID")
            if native_id in seen:
                raise ValueError(f"duplicate HCP {collection} native ID")
            seen.add(native_id)
        records.extend(rows)
        page_seals.append(
            {
                "artifact": artifact,
                "page": page,
                "record_count": len(rows),
                "sha256": _digest_bytes(body),
            }
        )
        page += 1
    if total_pages is None:
        raise ValueError(f"HCP {collection} returned no pagination")
    return records, {
        "count": len(records),
        "page_count": total_pages,
        "page_seals": page_seals,
        "page_seal_digest": _digest(page_seals),
    }


def _get_detail(
    client: GetOnlyClient,
    store: EvidenceStore,
    *,
    family: str,
    native_id: str,
    path: str,
    query: Mapping[str, Any] | None = None,
) -> tuple[int, Any | None]:
    status, body = client.get(path, query)
    request = f"GET {path}"
    if query:
        request += "?" + urlencode(query)
    name = f"{family}-{_identity_hash(native_id)}-http-{status}.json"
    value: Any | None = None
    record_count: int | None = None
    try:
        value = json.loads(body)
        if isinstance(value, dict):
            for candidate in ("appointments", "attachments", "forms"):
                if isinstance(value.get(candidate), list):
                    record_count = len(value[candidate])
                    break
    except json.JSONDecodeError:
        value = None
    store.write_raw(
        name,
        body,
        request=request,
        http_status=status,
        family=family,
        record_count=record_count,
    )
    return status, value


def _parent_id(record: Mapping[str, Any], key: str) -> str | None:
    value = record.get(key)
    if isinstance(value, dict) and isinstance(value.get("id"), str):
        return value["id"]
    candidate = record.get(f"{key}_id")
    return candidate if isinstance(candidate, str) and candidate else None


def _location_id(record: Mapping[str, Any]) -> str | None:
    address = record.get("address")
    if isinstance(address, dict) and isinstance(address.get("id"), str):
        return address["id"]
    return None


def _prior_index(prior: Mapping[str, Any]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for row in prior.get("records", []):
        if not isinstance(row, dict):
            continue
        domain = row.get("domain")
        source_id = row.get("source_id")
        digest = row.get("after_digest") or row.get("before_digest")
        if (
            isinstance(domain, str)
            and isinstance(source_id, str)
            and isinstance(digest, str)
        ):
            result[(domain, source_id)] = digest
    return result


def _classify(
    *,
    domain: str,
    source_id: str,
    payload: Mapping[str, Any],
    prior: Mapping[tuple[str, str], str],
    forced_hold: str | None = None,
) -> dict[str, Any]:
    after = _digest(payload)
    before = prior.get((domain, source_id))
    if forced_hold:
        disposition = "HOLD"
        reason = forced_hold
    elif before == after:
        disposition = "REPLAY"
        reason = "identical sealed source digest"
    elif before is None and domain in CREATE_DOMAINS:
        disposition = "CREATE"
        reason = "new exact provider identity"
    elif before is not None and domain in UPDATE_DOMAINS:
        disposition = "UPDATE"
        reason = "changed exact provider identity; clone compare-before-write required"
    else:
        disposition = "HOLD"
        reason = "evidence-only or unsupported canonical mutation domain"
    return {
        "after_digest": after,
        "before_digest": before,
        "disposition": disposition,
        "domain": domain,
        "reason": reason,
        "source_id": source_id,
    }


def _append_unique(
    target: list[dict[str, Any]], seen: set, row: dict[str, Any]
) -> None:
    key = (row["domain"], row["source_id"])
    if key in seen:
        return
    seen.add(key)
    target.append(row)


def _status(record: Mapping[str, Any]) -> str:
    return str(record.get("work_status") or record.get("status") or "").strip().lower()


def _embedded_rows(
    value: Any, keys: Sequence[str]
) -> Iterable[tuple[str, dict[str, Any]]]:
    if not isinstance(value, dict):
        return ()
    result: list[tuple[str, dict[str, Any]]] = []
    for key in keys:
        rows = value.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and isinstance(row.get("id"), str):
                    result.append((key.rstrip("s"), row))
    return result


def build(args: argparse.Namespace) -> dict[str, Any]:
    started_at = _now()
    api_base, api_key = _secret_file(args.secret_file)
    client = GetOnlyClient(api_base, api_key)
    store = EvidenceStore(args.output)
    prior_packet = _load_object(args.prior_delta)
    prior = _prior_index(prior_packet)
    prior_delta_digest = prior_packet.get("digest") or _digest(prior_packet)

    company_status, company_body = client.get("/company")
    if company_status != 200:
        store.write_raw(
            f"company-http-{company_status}.json",
            company_body,
            request="GET /company",
            http_status=company_status,
            family="company",
        )
        raise RuntimeError(f"HCP company identity returned HTTP {company_status}")
    company = json.loads(company_body)
    if not isinstance(company, dict) or not company.get("id"):
        raise ValueError("HCP company identity is invalid")
    store.write_raw(
        "company-http-200.json",
        company_body,
        request="GET /company",
        http_status=200,
        family="company",
        record_count=1,
    )

    records: dict[str, list[dict[str, Any]]] = {}
    collection_seals: dict[str, dict[str, Any]] = {}
    for collection, path in COLLECTIONS:
        rows, seal = _acquire_collection(client, store, collection, path)
        records[collection] = rows
        collection_seals[collection] = seal
        print(json.dumps({"acquired": collection, "count": len(rows)}), flush=True)

    jobs_by_id = {row["id"]: row for row in records["jobs"]}
    open_job_ids = {
        source_id
        for source_id, row in jobs_by_id.items()
        if _status(row) in OPEN_JOB_STATUSES
    }
    changed_job_ids = {
        source_id
        for source_id, row in jobs_by_id.items()
        if prior.get(("job", source_id)) != _digest(row)
    }
    scope_job_ids = open_job_ids | changed_job_ids
    scope_jobs = [jobs_by_id[value] for value in sorted(scope_job_ids)]
    open_customer_ids = {
        value
        for value in (
            _parent_id(row, "customer")
            for row in scope_jobs
            if row["id"] in open_job_ids
        )
        if value
    }

    customers_by_id = {row["id"]: row for row in records["customers"]}
    customer_details: dict[str, dict[str, Any]] = {}
    for index, customer_id in enumerate(sorted(open_customer_ids), 1):
        status, value = _get_detail(
            client,
            store,
            family="customer-detail",
            native_id=customer_id,
            path=f"/customers/{customer_id}",
        )
        if status == 200 and isinstance(value, dict):
            customer_details[customer_id] = value
        if index % 50 == 0:
            print(json.dumps({"customer_details": index}), flush=True)

    job_details: dict[str, dict[str, Any]] = {}
    appointment_rows: list[tuple[str, dict[str, Any]]] = []
    appointment_http_statuses: Counter = Counter()
    for index, job_id in enumerate(sorted(scope_job_ids), 1):
        status, value = _get_detail(
            client,
            store,
            family="job-detail",
            native_id=job_id,
            path=f"/jobs/{job_id}",
            query={"expand[]": "attachments"},
        )
        if status == 200 and isinstance(value, dict):
            job_details[job_id] = value
        status, value = _get_detail(
            client,
            store,
            family="job-appointments",
            native_id=job_id,
            path=f"/jobs/{job_id}/appointments",
        )
        appointment_http_statuses[str(status)] += 1
        if status == 200 and isinstance(value, dict):
            rows = value.get("appointments")
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and isinstance(row.get("id"), str):
                        appointment_rows.append((job_id, row))
        if index % 50 == 0:
            print(
                json.dumps({"job_graphs": index, "total": len(scope_job_ids)}),
                flush=True,
            )

    open_locations = {
        value
        for value in (_location_id(jobs_by_id[job_id]) for job_id in open_job_ids)
        if value
    }
    referenced_estimates = set()
    for row in scope_jobs:
        candidate = row.get("original_estimate_id")
        if isinstance(candidate, str) and candidate:
            referenced_estimates.add(candidate)
        candidates = row.get("original_estimate_uuids")
        if isinstance(candidates, list):
            referenced_estimates.update(
                value for value in candidates if isinstance(value, str)
            )
    estimate_scope: list[dict[str, Any]] = []
    for row in records["estimates"]:
        customer_id = _parent_id(row, "customer")
        location_id = _location_id(row)
        if row["id"] in referenced_estimates or (
            (customer_id in open_customer_ids or location_id in open_locations)
            and _status(row) in OPEN_JOB_STATUSES | {"created job from estimate"}
        ):
            estimate_scope.append(row)
    estimate_details: dict[str, dict[str, Any]] = {}
    for row in sorted(estimate_scope, key=lambda value: value["id"]):
        status, value = _get_detail(
            client,
            store,
            family="estimate-detail",
            native_id=row["id"],
            path="/estimates/{}".format(row["id"]),
        )
        if status == 200 and isinstance(value, dict):
            estimate_details[row["id"]] = value

    invoice_scope = [
        row for row in records["invoices"] if row.get("job_id") in scope_job_ids
    ]
    invoice_details: dict[str, dict[str, Any]] = {}
    for row in sorted(invoice_scope, key=lambda value: value["id"]):
        status, value = _get_detail(
            client,
            store,
            family="invoice-detail",
            native_id=row["id"],
            path="/invoices/{}".format(row["id"]),
        )
        if status == 200 and isinstance(value, dict):
            invoice_details[row["id"]] = value

    previous_holds = _load_object(args.prior_holds)
    prior_locationless = {
        row["provider_job_id"]: row
        for row in previous_holds.get("locationless_jobs", [])
        if isinstance(row, dict) and isinstance(row.get("provider_job_id"), str)
    }
    location_reconciliation: list[dict[str, Any]] = []
    unresolved_location_jobs: set = set()
    for job_id in sorted(prior_locationless):
        row = jobs_by_id.get(job_id)
        if row is None:
            result = "ABSENT_FROM_CURRENT_COLLECTION"
        elif job_id not in open_job_ids:
            result = "NO_LONGER_CURRENT_OPEN"
        elif _location_id(job_details.get(job_id, row)):
            result = "RESOLVED_LOCATION_ID_PRESENT"
        else:
            result = "STILL_LOCATION_LESS_OPEN"
            unresolved_location_jobs.add(job_id)
        location_reconciliation.append(
            {"provider_job_id": job_id, "result": result, "status": _status(row or {})}
        )

    appointments_by_job: dict[str, list[dict[str, Any]]] = {}
    for job_id, row in appointment_rows:
        appointments_by_job.setdefault(job_id, []).append(row)
    legacy_appointment_reconciliation: list[dict[str, Any]] = []
    for row in previous_holds.get("appointments", []):
        if not isinstance(row, dict):
            continue
        job_id = row.get("hcp_job_id")
        candidates = (
            appointments_by_job.get(job_id, []) if isinstance(job_id, str) else []
        )
        exact = [
            candidate
            for candidate in candidates
            if row.get("start")
            and row.get("end")
            and candidate.get("start_time") == row.get("start")
            and candidate.get("end_time") == row.get("end")
        ]
        result = "EXACT_WINDOW_CANDIDATE_REVIEW_REQUIRED" if len(exact) == 1 else "HOLD"
        reason = (
            "one exact provider window candidate; successor authority is not yet admitted"
            if len(exact) == 1
            else "fresh provider evidence does not prove a unique legacy successor"
        )
        legacy_appointment_reconciliation.append(
            {
                "candidate_count": len(candidates),
                "exact_window_candidate_count": len(exact),
                "hcp_job_id": job_id,
                "legacy_source_id": row.get("source_id"),
                "reason": reason,
                "result": result,
            }
        )

    classifications: list[dict[str, Any]] = []
    seen_classifications: set = set()
    for customer_id in sorted(open_customer_ids):
        # Compare the same list representation used by the prior delta receipt.
        # The separately sealed detail response is coverage evidence and may have
        # a different provider shape even when the source record is unchanged.
        payload = customers_by_id.get(customer_id)
        if isinstance(payload, dict):
            _append_unique(
                classifications,
                seen_classifications,
                _classify(
                    domain="customer",
                    source_id=customer_id,
                    payload=payload,
                    prior=prior,
                ),
            )
            for address in payload.get("addresses", []):
                if isinstance(address, dict) and isinstance(address.get("id"), str):
                    _append_unique(
                        classifications,
                        seen_classifications,
                        _classify(
                            domain="service_location",
                            source_id=address["id"],
                            payload=address,
                            prior=prior,
                        ),
                    )
    for row in scope_jobs:
        job_id = row["id"]
        forced = (
            "prior location-less open Job remains without provider Location identity"
            if job_id in unresolved_location_jobs
            else None
        )
        _append_unique(
            classifications,
            seen_classifications,
            _classify(
                domain="job",
                source_id=job_id,
                payload=row,
                prior=prior,
                forced_hold=forced,
            ),
        )
    for job_id, row in appointment_rows:
        forced = (
            "parent Job remains without provider Location identity"
            if job_id in unresolved_location_jobs
            else None
        )
        _append_unique(
            classifications,
            seen_classifications,
            _classify(
                domain="appointment",
                source_id=row["id"],
                payload=row,
                prior=prior,
                forced_hold=forced,
            ),
        )
    for row in records["employees"]:
        _append_unique(
            classifications,
            seen_classifications,
            _classify(domain="employee", source_id=row["id"], payload=row, prior=prior),
        )
    for row in estimate_scope:
        _append_unique(
            classifications,
            seen_classifications,
            _classify(domain="estimate", source_id=row["id"], payload=row, prior=prior),
        )
    for row in invoice_scope:
        _append_unique(
            classifications,
            seen_classifications,
            _classify(domain="invoice", source_id=row["id"], payload=row, prior=prior),
        )
    embedded_counts: Counter = Counter()
    for job_id, detail in job_details.items():
        for embedded_domain, row in _embedded_rows(
            detail, ("notes", "attachments", "forms")
        ):
            embedded_counts[embedded_domain] += 1
            _append_unique(
                classifications,
                seen_classifications,
                _classify(
                    domain=embedded_domain,
                    source_id=row["id"],
                    payload=row,
                    prior=prior,
                    forced_hold="evidence-only embedded operational artifact",
                ),
            )
    for row in legacy_appointment_reconciliation:
        source_id = row.get("legacy_source_id")
        if isinstance(source_id, str):
            _append_unique(
                classifications,
                seen_classifications,
                {
                    "after_digest": _digest(row),
                    "before_digest": None,
                    "disposition": "HOLD",
                    "domain": "legacy_appointment",
                    "reason": row["reason"],
                    "source_id": source_id,
                },
            )

    classifications.sort(key=lambda row: (row["domain"], row["source_id"]))
    classification_totals = dict(
        sorted(Counter(row["disposition"] for row in classifications).items())
    )
    domain_totals = {
        domain: dict(sorted(Counter(row["disposition"] for row in rows).items()))
        for domain, rows in sorted(
            (
                (domain, [row for row in classifications if row["domain"] == domain])
                for domain in {row["domain"] for row in classifications}
            ),
            key=lambda item: item[0],
        )
    }

    artifacts = sorted(store.artifacts, key=lambda row: row["artifact"])
    raw_page_seal = _digest(
        [
            {
                "artifact": row["artifact"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
            }
            for row in artifacts
        ]
    )
    completed_at = _now()
    open_status_counts = dict(
        sorted(Counter(_status(jobs_by_id[value]) for value in open_job_ids).items())
    )
    invoice_status_counts = dict(
        sorted(Counter(_status(row) for row in invoice_scope).items())
    )
    open_invoice_balance = {
        "nonzero_due_count": sum(
            1
            for row in invoice_scope
            if row.get("due_amount") not in (None, 0, 0.0, "0", "0.0")
        ),
        "source_amounts_preserved_without_currency_normalization": True,
    }
    manifest: dict[str, Any] = {
        "acquisition": {
            "completed_at": completed_at,
            "http_method_allowlist": ["GET"],
            "started_at": started_at,
        },
        "artifacts": artifacts,
        "classification_by_domain": domain_totals,
        "classification_totals": classification_totals,
        "classifications": classifications,
        "collection_seals": collection_seals,
        "company": {
            "id": company.get("id"),
            "name": company.get("name"),
            "raw_sha256": _digest_bytes(company_body),
        },
        "contract": "hcp-operational-cutover-acquisition/v1",
        "coverage": {
            "appointment_http_statuses": dict(
                sorted(appointment_http_statuses.items())
            ),
            "appointments": len(appointment_rows),
            "changed_jobs_since_prior_receipt": len(changed_job_ids),
            "contacts": {
                "embedded_customer_contacts_preserved_in_raw_customer_graph": True,
                "independent_source_identity_available": False,
            },
            "customer_details": len(customer_details),
            "customers_needed_by_open_work": len(open_customer_ids),
            "employees": len(records["employees"]),
            "estimates": len(estimate_scope),
            "forms_notes_attachments": dict(sorted(embedded_counts.items())),
            "invoice_status_counts": invoice_status_counts,
            "invoices": len(invoice_scope),
            "jobs": len(scope_job_ids),
            "open_invoice_balance_evidence": open_invoice_balance,
            "open_job_status_counts": open_status_counts,
            "open_jobs": len(open_job_ids),
        },
        "open_work_reconciliation": {
            "legacy_appointment_duplicate_risk": legacy_appointment_reconciliation,
            "legacy_appointment_duplicate_risk_counts": dict(
                sorted(
                    Counter(
                        row["result"] for row in legacy_appointment_reconciliation
                    ).items()
                )
            ),
            "prior_locationless_jobs": location_reconciliation,
            "prior_locationless_job_counts": dict(
                sorted(
                    Counter(row["result"] for row in location_reconciliation).items()
                )
            ),
        },
        "prior_receipt": {
            "contract": prior_packet.get("contract"),
            "digest": prior_delta_digest,
        },
        "raw_page_seal": raw_page_seal,
        "state": "COMPLETE_WITH_SEALED_PROVIDER_LIMITATIONS"
        if any(status != "200" for status in appointment_http_statuses)
        else "COMPLETE",
    }
    manifest["digest"] = _digest(manifest)
    store.write_json("operational-acquisition-manifest.json", manifest)

    observation_payloads: dict[
        tuple[str, str], tuple[dict[str, Any], list[dict[str, str]]]
    ] = {}
    for customer_id in open_customer_ids:
        customer = customers_by_id.get(customer_id)
        if not isinstance(customer, dict):
            continue
        observation_payloads[("customer", customer_id)] = (customer, [])
        for address in customer.get("addresses", []):
            if isinstance(address, dict) and isinstance(address.get("id"), str):
                observation_payloads[("service_location", address["id"])] = (
                    address,
                    [{"domain": "customer", "source_id": customer_id}],
                )
    for row in scope_jobs:
        parents = []
        customer_id = _parent_id(row, "customer")
        location_id = _location_id(row)
        if customer_id:
            parents.append({"domain": "customer", "source_id": customer_id})
        if location_id:
            parents.append({"domain": "service_location", "source_id": location_id})
        observation_payloads[("job", row["id"])] = (row, parents)
    for job_id, row in appointment_rows:
        observation_payloads[("appointment", row["id"])] = (
            row,
            [{"domain": "job", "source_id": job_id}],
        )

    provider_observations = {
        "acquired_at": completed_at,
        "contract": "hcp-operational-rehearsal-provider-observations/v1",
        "records": [
            {
                "acquired_at": completed_at,
                "domain": row["domain"],
                "parent_keys": observation_payloads[(row["domain"], row["source_id"])][
                    1
                ],
                "payload": observation_payloads[(row["domain"], row["source_id"])][0],
                "source_digest": row["after_digest"],
                "source_id": row["source_id"],
                "source_updated_at": observation_payloads[
                    (row["domain"], row["source_id"])
                ][0].get("updated_at"),
            }
            for row in classifications
            if (row["domain"], row["source_id"]) in observation_payloads
        ],
        "source_manifest_digest": manifest["digest"],
    }
    provider_observations["digest"] = _digest(provider_observations)
    store.write_json("isolated-clone-provider-observations.json", provider_observations)
    rehearsal = {
        "contract": "hcp-isolated-clone-rehearsal-packet/v1",
        "provider_observations": "isolated-clone-provider-observations.json",
        "provider_observations_digest": provider_observations["digest"],
        "required_native_observation": "read-only export from a fresh isolated clone",
        "source_manifest": "operational-acquisition-manifest.json",
        "source_manifest_digest": manifest["digest"],
        "state": "PREPARED_AWAITING_ISOLATED_CLONE_NATIVE_OBSERVATION",
    }
    rehearsal["digest"] = _digest(rehearsal)
    store.write_json("isolated-clone-rehearsal-packet.json", rehearsal)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-file", required=True, type=Path)
    parser.add_argument("--prior-delta", required=True, type=Path)
    parser.add_argument("--prior-holds", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    value = build(args)
    print(
        json.dumps(
            {
                "acquisition_timestamp": value["acquisition"]["completed_at"],
                "classification_totals": value["classification_totals"],
                "counts": value["coverage"],
                "digest": value["digest"],
                "raw_page_seal": value["raw_page_seal"],
                "state": value["state"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
