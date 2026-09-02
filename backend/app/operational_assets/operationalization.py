from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_assets.models import Asset, AssetImportRow, AssetOperationalPolicy
from app.operational_assets.schemas import AssetImportCandidate, AssetPolicyDraft
from app.operational_assets.service import AssetConflict, digest
from app.platform.permissions.authorization import AuthorizationContext


def classify_candidate(
    source_type: str, evidence: dict[str, object]
) -> tuple[str, list[str]]:
    issues: list[str] = []
    if source_type == "customer_equipment":
        for field in ("customer_id", "service_location_id"):
            if not evidence.get(field):
                issues.append(f"missing_{field}")
    if source_type == "vehicle" and not any(
        evidence.get(x) for x in ("asset_number", "vin")
    ):
        issues.append("missing_vehicle_identity")
    if source_type in {"tracked_tool", "company_equipment"} and not evidence.get(
        "asset_number"
    ):
        issues.append("missing_asset_number")
    if evidence.get("conflicting_branch"):
        issues.append("conflicting_branch")
        return "conflict", issues
    if evidence.get("replacement_of"):
        return "replacement_candidate", issues
    if issues:
        return "insufficient_evidence", issues
    return "new_asset_candidate", issues


class AssetOperationalizationService:
    async def draft_policy(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        data: AssetPolicyDraft,
    ):
        if not context.can_access_branch(data.branch_id):
            raise AssetConflict()
        raw = data.model_dump(mode="json", exclude={"idempotency_key"})
        request = digest(raw)
        replay = await session.scalar(
            select(AssetOperationalPolicy).where(
                AssetOperationalPolicy.company_id == context.company.id,
                AssetOperationalPolicy.idempotency_key == data.idempotency_key,
            )
        )
        if replay:
            if replay.request_digest != request:
                raise AssetConflict()
            return replay
        version = (
            await session.scalar(
                select(
                    func.coalesce(func.max(AssetOperationalPolicy.version), 0)
                ).where(
                    AssetOperationalPolicy.company_id == context.company.id,
                    AssetOperationalPolicy.branch_id == data.branch_id,
                    AssetOperationalPolicy.policy_type == data.policy_type,
                )
            )
        ) or 0
        version += 1
        row = AssetOperationalPolicy(
            company_id=context.company.id,
            branch_id=data.branch_id,
            policy_type=data.policy_type,
            version=version,
            status="draft" if data.configuration else "unconfigured",
            configuration=data.configuration,
            effective_at=data.effective_at,
            predecessor_policy_id=data.predecessor_policy_id,
            request_digest=request,
            policy_digest=digest({"company": context.company.id, **raw}),
            idempotency_key=data.idempotency_key,
            created_by_user_id=context.user.id,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    async def import_candidate(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        data: AssetImportCandidate,
    ):
        if not context.can_access_branch(data.branch_id):
            raise AssetConflict()
        raw = data.model_dump(mode="json", exclude={"idempotency_key"})
        request = digest(raw)
        replay = await session.scalar(
            select(AssetImportRow).where(
                AssetImportRow.company_id == context.company.id,
                AssetImportRow.idempotency_key == data.idempotency_key,
            )
        )
        if replay:
            if replay.request_digest != request:
                raise AssetConflict()
            return replay
        existing = await session.scalar(
            select(AssetImportRow).where(
                AssetImportRow.company_id == context.company.id,
                AssetImportRow.source_system == data.source_system,
                AssetImportRow.source_identity == data.source_identity,
            )
        )
        if existing:
            raise AssetConflict()
        classification, issues = classify_candidate(data.source_type, data.evidence)
        candidate = None
        asset_number = data.evidence.get("asset_number")
        if asset_number:
            candidate = await session.scalar(
                select(Asset.id).where(
                    Asset.company_id == context.company.id,
                    Asset.asset_number == str(asset_number).upper(),
                )
            )
            if candidate:
                classification = "exact_identity"
        row = AssetImportRow(
            company_id=context.company.id,
            branch_id=data.branch_id,
            source_system=data.source_system,
            source_identity=data.source_identity,
            source_type=data.source_type,
            source_digest=digest(data.evidence),
            normalized_evidence=data.evidence,
            classification=classification,
            candidate_asset_id=candidate,
            issues=issues,
            disposition="blocked"
            if classification in {"conflict", "insufficient_evidence"}
            else "pending_review",
            request_digest=request,
            idempotency_key=data.idempotency_key,
            actor_user_id=context.user.id,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    async def readiness(self, session: AsyncSession, context: AuthorizationContext):
        imports = list(
            (
                await session.scalars(
                    select(AssetImportRow).where(
                        AssetImportRow.company_id == context.company.id
                    )
                )
            ).all()
        )
        policies = list(
            (
                await session.scalars(
                    select(AssetOperationalPolicy)
                    .where(AssetOperationalPolicy.company_id == context.company.id)
                    .order_by(AssetOperationalPolicy.version.desc())
                )
            ).all()
        )
        counts: dict[str, int] = {}
        for row in imports:
            counts[row.classification] = counts.get(row.classification, 0) + 1
        policy_states = {
            kind: "POLICY_REQUIRED"
            for kind in (
                "inspection",
                "maintenance",
                "out_of_service",
                "warranty",
                "sensitive_identifier",
                "import",
            )
        }
        for policy in policies:
            policy_states.setdefault(policy.policy_type, policy.status.upper())
            policy_states[policy.policy_type] = policy.status.upper()
        state = (
            "REVIEW_REQUIRED"
            if any(
                k in counts for k in ("conflict", "ambiguous", "insufficient_evidence")
            )
            else "DATA_REQUIRED"
            if not imports
            else "ENGINEERING_READY"
        )
        return state, counts, policy_states


asset_operationalization_service = AssetOperationalizationService()
