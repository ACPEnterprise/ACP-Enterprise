import json
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.catalog import CATALOG_DIGEST, QUALITY_CATALOG, QualityRule
from app.data_quality.schemas import QualityIssueResponse, QualitySummaryResponse
from app.platform.permissions.authorization import AuthorizationContext


class DataQualityService:
    """Bounded read-only probes. Source domains retain all correction authority."""

    async def scan(self, session: AsyncSession, *, context: AuthorizationContext,
                   limit: int, offset: int) -> QualitySummaryResponse:
        company_id = str(context.company.id)
        authorized_branch_ids = [item.id for item in context.authorized_branches]
        branch_ids = [str(item) for item in authorized_branch_ids]
        params = {
            "company_id": context.company.id,
            "branch_ids": authorized_branch_ids,
        }
        findings: list[QualityIssueResponse] = []
        probes = (
            ("DQ-CUSTOMER-001", """select id::text as id from customers where company_id=:company_id and (btrim(display_name)='' or btrim(normalized_name)='') order by id limit 201""", ("display identity",)),
            ("DQ-CUSTOMER-002", """select (array_agg(id order by id))[1]::text as id from customers where company_id=:company_id and archived_at is null group by normalized_name having count(*) > 1 order by (array_agg(id order by id))[1] limit 201""", ("shared normalized identity",)),
            ("DQ-CONTACT-001", """select cc.id::text as id from customer_contacts cc join customers c on c.id=cc.customer_id where c.company_id=:company_id and cc.active and cc.archived_at is null and cc.email is null and cc.mobile_phone is null and cc.office_phone is null order by cc.id limit 201""", ("usable destination",)),
            ("DQ-LOCATION-001", """select sl.id::text as id from service_locations sl join customers c on c.id=sl.customer_id where c.company_id=:company_id and sl.archived_at is null and (btrim(sl.address_line_1)='' or btrim(sl.city)='' or btrim(sl.state)='' or btrim(sl.postal_code)='') order by sl.id limit 201""", ("complete operational address",)),
            ("DQ-JOB-001", """select j.id::text as id from jobs j left join customers c on c.id=j.customer_id left join service_locations sl on sl.id=j.service_location_id left join branches b on b.id=j.branch_id where j.company_id=:company_id and j.branch_id=any(cast(:branch_ids as uuid[])) and (c.id is null or c.company_id<>j.company_id or sl.id is null or sl.customer_id<>j.customer_id or b.id is null or b.company_id<>j.company_id) order by j.id limit 201""", ("tenant/Customer/Location/Branch consistency",)),
            ("DQ-APPOINTMENT-001", """select a.id::text as id from appointments a join job_appointment_links l on l.appointment_id=a.id join jobs j on j.id=l.job_id where a.company_id=:company_id and a.branch_id=any(cast(:branch_ids as uuid[])) and (a.company_id<>j.company_id or a.branch_id<>j.branch_id or a.customer_id<>j.customer_id or a.service_location_id<>j.service_location_id) order by a.id limit 201""", ("Job/Appointment scope consistency",)),
            ("DQ-ASSET-001", """select oa.id::text as id from operational_assets oa left join operational_asset_relationships r on r.asset_id=oa.id and r.valid_to is null where oa.company_id=:company_id and oa.branch_id=any(cast(:branch_ids as uuid[])) and r.company_id is not null and r.company_id<>oa.company_id order by oa.id limit 201""", ("Asset relationship tenant consistency",)),
        )
        rules = {rule.rule_id: rule for rule in QUALITY_CATALOG}
        for rule_id, statement, evidence in probes:
            rows = (await session.execute(text(statement), params)).mappings().all()
            rule = rules[rule_id]
            findings.extend(self._issue(rule, row["id"], evidence, company_id) for row in rows)
        findings.sort(key=lambda item: (item.domain, item.rule_id, item.safe_record_identity))
        page = findings[offset:offset + limit]
        return QualitySummaryResponse(
            catalog_digest=CATALOG_DIGEST,
            company_id=company_id,
            branch_scope=branch_ids,
            scanned_rules=len(probes),
            total_issues=len(findings),
            blocks_new_operation=sum(i.blocks_new_operation for i in findings),
            historical_only=sum(i.launch_impact == "HISTORICAL_ONLY" for i in findings),
            owner_review=sum(i.launch_impact == "OWNER_REVIEW" for i in findings),
            issues=page,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _issue(rule: QualityRule, record_id: str, evidence: tuple[str, ...], company_id: str) -> QualityIssueResponse:
        digest = sha256(json.dumps({"company_id": company_id, "evidence": evidence, "record_id": record_id, "rule": rule.digest}, sort_keys=True).encode()).hexdigest()
        return QualityIssueResponse(
            rule_id=rule.rule_id, domain=rule.domain, state=rule.state,
            severity=rule.severity, launch_impact=rule.launch_impact,
            safe_record_identity=record_id, explanation=rule.explanation,
            missing_or_conflicting_evidence=list(evidence), repair_owner=rule.repair_owner,
            evidence_digest=digest,
            blocks_new_operation=rule.launch_impact in {"BLOCKS_NEW_OPERATION", "BLOCKS_SPECIFIC_RECORD"},
        )


data_quality_service = DataQualityService()
