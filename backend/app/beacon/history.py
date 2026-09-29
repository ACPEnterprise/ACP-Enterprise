from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.models import BeaconEvaluationRunModel, BeaconSignalEvaluationModel
from app.beacon.records import BeaconSignal


class EvaluationDisposition(StrEnum):
    NEW = "new"
    STILL_ACTIVE = "still_active"
    CHANGED = "changed"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class BeaconEvaluationConflictError(ValueError):
    pass


@dataclass(frozen=True)
class BeaconEvaluationRecord:
    id: UUID
    run_id: UUID
    company_id: UUID
    branch_id: UUID | None
    condition_key: UUID
    signal_id: UUID
    definition_id: str
    definition_version: int
    evidence_digest: str
    evaluated_at: datetime
    evidence_as_of: datetime
    signal_expires_at: datetime
    evaluator_version: str
    disposition: EvaluationDisposition
    prior_evaluation_id: UUID | None


@dataclass(frozen=True)
class BeaconEvaluationRun:
    id: UUID
    company_id: UUID
    branch_id: UUID | None
    scope_identity: str
    evaluated_at: datetime
    evidence_as_of: datetime
    evaluator_version: str
    covered_definitions: tuple[str, ...]
    provenance_digest: str
    run_digest: str
    records: tuple[BeaconEvaluationRecord, ...]


class BeaconEvaluationHistoryService:
    async def record_completed_run(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID | None,
        scope_identity: str,
        evaluated_at: datetime,
        evidence_as_of: datetime,
        evaluator_version: str,
        covered_definitions: tuple[str, ...],
        provenance: dict[str, object],
        signals: tuple[BeaconSignal, ...],
    ) -> BeaconEvaluationRun:
        self._validate(
            evaluated_at=evaluated_at,
            evidence_as_of=evidence_as_of,
            evaluator_version=evaluator_version,
            covered_definitions=covered_definitions,
            signals=signals,
        )
        provenance_digest = _digest(provenance)
        run_digest = _digest(
            {
                "company_id": str(company_id),
                "branch_id": str(branch_id) if branch_id else None,
                "scope_identity": scope_identity,
                "evaluated_at": evaluated_at.isoformat(),
                "evidence_as_of": evidence_as_of.isoformat(),
                "evaluator_version": evaluator_version,
                "covered_definitions": sorted(covered_definitions),
                "provenance_digest": provenance_digest,
                "signals": sorted(
                    (str(item.condition_key), str(item.id), item.evidence_digest)
                    for item in signals
                ),
            }
        )
        existing = await session.scalar(
            select(BeaconEvaluationRunModel).where(
                BeaconEvaluationRunModel.company_id == company_id,
                BeaconEvaluationRunModel.scope_identity == scope_identity,
                BeaconEvaluationRunModel.evaluated_at == evaluated_at,
                BeaconEvaluationRunModel.evaluator_version == evaluator_version,
            )
        )
        if existing is not None:
            if existing.run_digest != run_digest:
                raise BeaconEvaluationConflictError(
                    "Evaluation identity was reused with contradictory evidence."
                )
            return await self._load_run(session, existing)

        latest = await self._latest_by_condition(
            session,
            company_id=company_id,
            branch_id=branch_id,
            scope_identity=scope_identity,
        )
        run = BeaconEvaluationRunModel(
            company_id=company_id,
            branch_id=branch_id,
            scope_identity=scope_identity,
            evaluated_at=evaluated_at,
            evidence_as_of=evidence_as_of,
            evaluator_version=evaluator_version,
            covered_definitions=sorted(covered_definitions),
            provenance=provenance,
            provenance_digest=provenance_digest,
            run_digest=run_digest,
            created_at=evaluated_at,
        )
        session.add(run)
        await session.flush()
        current_keys = {item.condition_key for item in signals}
        entities: list[BeaconSignalEvaluationModel] = []
        for signal in signals:
            prior = latest.get(signal.condition_key)
            disposition = (
                EvaluationDisposition.NEW
                if prior is None
                or prior.disposition
                in {
                    EvaluationDisposition.RESOLVED.value,
                    EvaluationDisposition.EXPIRED.value,
                }
                else EvaluationDisposition.SUPERSEDED
                if (
                    prior.definition_id != signal.definition_id
                    or prior.definition_version != signal.definition_version
                )
                else EvaluationDisposition.STILL_ACTIVE
                if prior.evidence_digest == signal.evidence_digest
                else EvaluationDisposition.CHANGED
            )
            entities.append(
                self._entity(
                    run=run,
                    signal=signal,
                    disposition=disposition,
                    prior=prior,
                )
            )
        covered = set(covered_definitions)
        for condition_key, prior in latest.items():
            if (
                condition_key in current_keys
                or prior.definition_id not in covered
                or prior.disposition
                in {
                    EvaluationDisposition.RESOLVED.value,
                    EvaluationDisposition.EXPIRED.value,
                }
            ):
                continue
            entities.append(
                BeaconSignalEvaluationModel(
                    run_id=run.id,
                    company_id=company_id,
                    branch_id=branch_id,
                    condition_key=prior.condition_key,
                    signal_id=prior.signal_id,
                    definition_id=prior.definition_id,
                    definition_version=prior.definition_version,
                    evidence_digest=prior.evidence_digest,
                    evaluated_at=evaluated_at,
                    evidence_as_of=evidence_as_of,
                    signal_expires_at=prior.signal_expires_at,
                    evaluator_version=evaluator_version,
                    disposition=(
                        EvaluationDisposition.EXPIRED.value
                        if prior.signal_expires_at <= evidence_as_of
                        else EvaluationDisposition.RESOLVED.value
                    ),
                    prior_evaluation_id=prior.id,
                    created_at=evaluated_at,
                )
            )
        session.add_all(entities)
        await session.flush()
        return self._project(run, tuple(entities))

    async def deltas(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID | None,
        since: datetime,
        until: datetime,
    ) -> tuple[BeaconEvaluationRecord, ...]:
        statement = select(BeaconSignalEvaluationModel).where(
            BeaconSignalEvaluationModel.company_id == company_id,
            BeaconSignalEvaluationModel.evaluated_at > since,
            BeaconSignalEvaluationModel.evaluated_at <= until,
        )
        statement = (
            statement.where(BeaconSignalEvaluationModel.branch_id == branch_id)
            if branch_id is not None
            else statement.where(BeaconSignalEvaluationModel.branch_id.is_(None))
        )
        rows = tuple(
            (
                await session.scalars(
                    statement.order_by(
                        BeaconSignalEvaluationModel.evaluated_at,
                        BeaconSignalEvaluationModel.id,
                    )
                )
            ).all()
        )
        return tuple(_record(item) for item in rows)

    async def has_completed_run(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID | None,
        since: datetime,
        until: datetime,
    ) -> bool:
        statement = select(
            exists().where(
                BeaconEvaluationRunModel.company_id == company_id,
                BeaconEvaluationRunModel.evaluated_at > since,
                BeaconEvaluationRunModel.evaluated_at <= until,
                (
                    BeaconEvaluationRunModel.branch_id == branch_id
                    if branch_id is not None
                    else BeaconEvaluationRunModel.branch_id.is_(None)
                ),
            )
        )
        return bool(await session.scalar(statement))

    @staticmethod
    async def _latest_by_condition(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID | None,
        scope_identity: str,
    ) -> dict[UUID, BeaconSignalEvaluationModel]:
        statement = (
            select(BeaconSignalEvaluationModel)
            .join(
                BeaconEvaluationRunModel,
                BeaconEvaluationRunModel.id == BeaconSignalEvaluationModel.run_id,
            )
            .where(
                BeaconSignalEvaluationModel.company_id == company_id,
                BeaconEvaluationRunModel.scope_identity == scope_identity,
            )
            .order_by(
                BeaconSignalEvaluationModel.condition_key,
                BeaconSignalEvaluationModel.evaluated_at.desc(),
                BeaconSignalEvaluationModel.id.desc(),
            )
        )
        statement = (
            statement.where(BeaconSignalEvaluationModel.branch_id == branch_id)
            if branch_id is not None
            else statement.where(BeaconSignalEvaluationModel.branch_id.is_(None))
        )
        rows = tuple((await session.scalars(statement)).all())
        latest: dict[UUID, BeaconSignalEvaluationModel] = {}
        for row in rows:
            latest.setdefault(row.condition_key, row)
        return latest

    @staticmethod
    def _entity(
        *,
        run: BeaconEvaluationRunModel,
        signal: BeaconSignal,
        disposition: EvaluationDisposition,
        prior: BeaconSignalEvaluationModel | None,
    ) -> BeaconSignalEvaluationModel:
        return BeaconSignalEvaluationModel(
            run_id=run.id,
            company_id=run.company_id,
            branch_id=run.branch_id,
            condition_key=signal.condition_key,
            signal_id=signal.id,
            definition_id=signal.definition_id,
            definition_version=signal.definition_version,
            evidence_digest=signal.evidence_digest,
            evaluated_at=run.evaluated_at,
            evidence_as_of=run.evidence_as_of,
            signal_expires_at=signal.expires_at,
            evaluator_version=run.evaluator_version,
            disposition=disposition.value,
            prior_evaluation_id=prior.id if prior else None,
            created_at=run.evaluated_at,
        )

    async def _load_run(
        self, session: AsyncSession, run: BeaconEvaluationRunModel
    ) -> BeaconEvaluationRun:
        rows = tuple(
            (
                await session.scalars(
                    select(BeaconSignalEvaluationModel)
                    .where(BeaconSignalEvaluationModel.run_id == run.id)
                    .order_by(
                        BeaconSignalEvaluationModel.condition_key,
                        BeaconSignalEvaluationModel.id,
                    )
                )
            ).all()
        )
        return self._project(run, rows)

    @staticmethod
    def _project(
        run: BeaconEvaluationRunModel,
        rows: tuple[BeaconSignalEvaluationModel, ...],
    ) -> BeaconEvaluationRun:
        return BeaconEvaluationRun(
            id=run.id,
            company_id=run.company_id,
            branch_id=run.branch_id,
            scope_identity=run.scope_identity,
            evaluated_at=run.evaluated_at,
            evidence_as_of=run.evidence_as_of,
            evaluator_version=run.evaluator_version,
            covered_definitions=tuple(run.covered_definitions),
            provenance_digest=run.provenance_digest,
            run_digest=run.run_digest,
            records=tuple(
                _record(row)
                for row in sorted(rows, key=lambda item: (item.condition_key, item.id))
            ),
        )

    @staticmethod
    def _validate(
        *,
        evaluated_at: datetime,
        evidence_as_of: datetime,
        evaluator_version: str,
        covered_definitions: tuple[str, ...],
        signals: tuple[BeaconSignal, ...],
    ) -> None:
        if not covered_definitions or len(set(covered_definitions)) != len(
            covered_definitions
        ):
            raise ValueError("Evaluation coverage must contain unique definitions.")
        if any(signal.definition_id not in covered_definitions for signal in signals):
            raise ValueError(
                "Every signal must belong to the declared evaluation coverage."
            )
        if len({signal.condition_key for signal in signals}) != len(signals):
            raise ValueError("An evaluation run cannot fork a root condition.")
        if any(signal.created_at > evidence_as_of for signal in signals):
            raise ValueError("Signal evidence cannot occur after the evidence cutoff.")
        if evidence_as_of > evaluated_at:
            raise ValueError("Evidence cutoff cannot occur after evaluation.")
        if not evaluator_version.strip():
            raise ValueError("Evaluator version is required.")


def _record(entity: BeaconSignalEvaluationModel) -> BeaconEvaluationRecord:
    return BeaconEvaluationRecord(
        id=entity.id,
        run_id=entity.run_id,
        company_id=entity.company_id,
        branch_id=entity.branch_id,
        condition_key=entity.condition_key,
        signal_id=entity.signal_id,
        definition_id=entity.definition_id,
        definition_version=entity.definition_version,
        evidence_digest=entity.evidence_digest,
        evaluated_at=entity.evaluated_at,
        evidence_as_of=entity.evidence_as_of,
        signal_expires_at=entity.signal_expires_at,
        evaluator_version=entity.evaluator_version,
        disposition=EvaluationDisposition(entity.disposition),
        prior_evaluation_id=entity.prior_evaluation_id,
    )


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


beacon_evaluation_history_service = BeaconEvaluationHistoryService()
